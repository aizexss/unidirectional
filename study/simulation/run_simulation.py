"""Reproducible synthetic discrete-event study of telemetry provenance.

Python3.10+, standard library only. No hardware or measured parameter input.
Run this file to regenerate every CSV, JSON and reading log in this directory.
"""
from __future__ import annotations
import csv
import gzip
import hashlib
import heapq
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = 40
BOOTSTRAPS = 2000
PERIOD = 20
END = 24000
WARMUP = 4000
READ_PERIOD = 5
DELAY_BOUND = 40
FRESHNESS = 100
FAULT_START = 12000
FAULT_DURATION = 200
BAD_TO_GOOD = 0.1
GOOD_TO_BAD = 0.05 * BAD_TO_GOOD / 0.95
CATALOG = ((0, 0), (1, 1))
VERDICTS = ('coherent', 'mixed', 'ambiguous', 'out_of_model', 'unavailable')


def rng(*parts):
    payload = '|'.join(map(str, ('article1-synthetic-v1',) + parts)).encode()
    return random.Random(int.from_bytes(hashlib.sha256(payload).digest()[:16], 'big'))


def write_csv(name, rows):
    if not rows:
        return
    with (HERE / name).open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def markov_detection(alpha, lag):
    return (1.0 - (1.0 - 2.0 * alpha) ** lag) / 2.0


def monitor(x, y, labels=None, grouping=None):
    """Pointwise monitor. It receives no source sequence or true origin lookup."""
    if x is None or y is None:
        return 'unavailable'
    same = different = True
    if labels is not None:
        same, different = labels[0] == labels[1], labels[0] != labels[1]
    if grouping == 'same':
        different = False
    elif grouping == 'different':
        same = False
    c = same and (x, y) in CATALOG
    m = different and any(s[0] == x for s in CATALOG) and any(s[1] == y for s in CATALOG)
    return {(True, False): 'coherent', (False, True): 'mixed',
            (True, True): 'ambiguous', (False, False): 'out_of_model'}[(c, m)]


def truth(online, ox, oy):
    if not online or not ox or not oy:
        return 'unavailable'
    return 'coherent' if ox == oy else 'mixed'


def source_history(alpha, seed, n):
    r = rng('source', alpha, seed)
    v = r.randrange(2)
    history = [v]
    for _ in range(1, n):
        if r.random() < alpha:
            v ^= 1
        history.append(v)
    return history


def outage_history(seed, n):
    r = rng('outage', seed)
    bad = r.random() < 0.05
    result = []
    for _ in range(n):
        result.append(bad)
        bad = (r.random() >= BAD_TO_GOOD) if bad else (r.random() < GOOD_TO_BAD)
    return result


def conditions():
    result = []
    for alpha in (0.05, 0.5, 0.95):
        for channel in ('none', 'iid05', 'burst05'):
            result.append(dict(id=f'C{len(result)+1:02}', alpha=alpha, channel=channel,
                               restart='none', label=f'a{alpha:g}_{channel}'))
    for channel, restart in (('iid05', 'clear'), ('iid05', 'preserve'), ('burst05', 'clear')):
        result.append(dict(id=f'C{len(result)+1:02}', alpha=0.5, channel=channel,
                           restart=restart, label=f'a0.5_{channel}_restart_{restart}'))
    return result


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    pos = q * (len(ordered) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    return ordered[lo] + (pos - lo) * (ordered[hi] - ordered[lo])


def simulate(condition, seed, mode, *, readings=None, sample=False, period=PERIOD,
             delay_bound=DELAY_BOUND, read_phase=None):
    alpha = condition['alpha']
    n = (END - 1) // period + 1
    history = source_history(alpha, seed, n)
    outages = outage_history(seed, n)
    if read_phase is None:
        read_phase = rng('read-phase', seed).randrange(READ_PERIOD)
    delays = {key: rng('delay', mode, key, seed) for key in ('x', 'y', 'object')}
    losses = {key: rng('loss', mode, key, seed) for key in ('x', 'y', 'object')}
    queue = []
    attempted = channel_lost = pending_end = delivered = receiver_dropped = 0
    for i in range(n):
        generated = i * period
        components = ('x', 'y') if mode == 'R0' else ('object',)
        for component in components:
            attempted += 1
            channel = condition['channel']
            # Assign per-message random inputs even when this condition drops it,
            # retaining common random numbers across channel-factor conditions.
            delay = delays[component].randint(0, delay_bound)
            independent_loss_draw = losses[component].random()
            # Source, timing, loss and outage streams are value-independent.
            lost = channel == 'all' or (channel == 'iid05' and independent_loss_draw < .05)
            if channel == 'burst05':
                lost = outages[i]
            if lost:
                channel_lost += 1
                continue
            arrival = generated + delay
            if arrival >= END:
                pending_end += 1
                continue
            # All arrivals at a time precede the atomic read at that time.
            order = {'x': 0, 'y': 1, 'object': 0}[component]
            heapq.heappush(queue, (arrival, 1, order, 'delivery', (i + 1, component)))
    if condition['restart'] != 'none':
        heapq.heappush(queue, (FAULT_START, 0, 0, 'reset', None))
        heapq.heappush(queue, (FAULT_START + FAULT_DURATION, 0, 0, 'ready', None))
    for t in range(WARMUP + read_phase, END, READ_PERIOD):
        heapq.heappush(queue, (t, 2, 0, 'read', None))

    online = True
    ox = oy = 0
    references = Counter()
    counts = {p: Counter() for p in ('V', 'I', 'G')}
    errors = Counter()
    conclusive = Counter()
    unavailable_reasons = Counter()
    lags = defaultdict(lambda: [0, 0])
    naive_false = hidden_mixed = fresh_coherent = stale_coherent = 0
    coherent_ages = []
    sample_rows = []
    while queue:
        t, _, _, action, payload = heapq.heappop(queue)
        if action == 'reset':
            online = False
            if condition['restart'] == 'clear':
                ox = oy = 0
        elif action == 'ready':
            online = True
        elif action == 'delivery':
            if not online:
                receiver_dropped += 1
                continue
            origin, component = payload
            if component in ('x', 'object'):
                ox = origin
            if component in ('y', 'object'):
                oy = origin
            delivered += 1
        else:
            reference = truth(online, ox, oy)
            references[reference] += 1
            x = history[ox - 1] if online and ox else None
            y = history[oy - 1] if online and oy else None
            verdicts = dict(V=monitor(x, y), I=monitor(x, y, labels=(ox, oy)),
                            G=monitor(x, y, grouping='same' if mode == 'R1' else None))
            for profile, verdict in verdicts.items():
                counts[profile][verdict] += 1
                if verdict in ('coherent', 'mixed'):
                    conclusive[profile] += 1
                    errors[profile] += int(verdict != reference)
            assert verdicts['I'] == reference
            assert all(v != 'out_of_model' for v in verdicts.values())
            if mode == 'R1':
                assert reference != 'mixed'
            age = None
            if reference == 'unavailable':
                unavailable_reasons['downtime' if not online else 'missing_fields'] += 1
            elif reference == 'coherent':
                age = t - (ox - 1) * period
                assert age >= 0
                coherent_ages.append(age)
                fresh_coherent += age <= FRESHNESS
                stale_coherent += age > FRESHNESS
            else:
                lag = abs(ox - oy)
                assert lag >= 1
                lags[lag][0] += 1
                lags[lag][1] += x != y
                hidden_mixed += verdicts['V'] == 'ambiguous'
                naive_false += (x, y) in CATALOG
            if readings is not None:
                readings.writerow((condition['id'], seed, mode, t, int(online), ox, oy))
            if sample:
                sample_rows.append(dict(condition=condition['id'], seed=seed, publication=mode,
                                        read_time_ms=t, online=int(online), x_origin=ox, y_origin=oy,
                                        x=x, y=y, reference=reference, V=verdicts['V'], I=verdicts['I'],
                                        G=verdicts['G'], coherent_age_ms=age,
                                        fresh_coherent=int(age is not None and age <= FRESHNESS),
                                        receiver_down=int(not online)))
    total = sum(references.values())
    assert total == (END - WARMUP) // READ_PERIOD
    assert delivered + receiver_dropped + pending_end + channel_lost == attempted
    assert naive_false == hidden_mixed
    expected = sum(count * markov_detection(alpha, lag) for lag, (count, _) in lags.items())
    detected = sum(d for _, d in lags.values())
    mixed = references['mixed']
    row = dict(condition=condition['id'], label=condition['label'], alpha=alpha,
               channel=condition['channel'], restart=condition['restart'], seed=seed,
               publication=mode, read_phase_ms=read_phase, slots=total,
               coherent=references['coherent'], mixed=mixed, unavailable=references['unavailable'],
               unavailable_downtime=unavailable_reasons['downtime'],
               unavailable_missing=unavailable_reasons['missing_fields'],
               hidden_mixed=hidden_mixed, naive_false_coherent=naive_false,
               fresh_coherent=fresh_coherent, stale_coherent=stale_coherent,
               attempted_messages=attempted, channel_lost=channel_lost,
               receiver_dropped=receiver_dropped, delivered_before_end=delivered,
               pending_at_end=pending_end, detected_mixed=detected,
               predicted_detected_mixed=expected,
               coherent_age_mean_ms=statistics.fmean(coherent_ages) if coherent_ages else None,
               coherent_age_p95_ms=percentile(coherent_ages, .95))
    for profile in ('V', 'I', 'G'):
        for verdict in VERDICTS:
            row[profile + '_' + verdict] = counts[profile][verdict]
        row[profile + '_conclusive'] = conclusive[profile]
        row[profile + '_errors'] = errors[profile]
    assert all(errors[p] == 0 for p in ('V', 'I', 'G'))
    lag_rows = [dict(condition=condition['id'], seed=seed, publication=mode, alpha=alpha,
                     lag=lag, mixed_slots=a, detected_slots=b,
                     predicted_detection=markov_detection(alpha, lag))
                for lag, (a, b) in sorted(lags.items())]
    return row, lag_rows, sample_rows


def add_metrics(row):
    n = row['slots']
    derived = dict(row)
    for name, numerator in [('mixed_share', 'mixed'), ('coherent_share', 'coherent'),
                            ('unavailable_share', 'unavailable'), ('hidden_mixed_share', 'hidden_mixed'),
                            ('naive_false_coherent_share', 'naive_false_coherent'),
                            ('fresh_coherent_availability', 'fresh_coherent'),
                            ('stale_coherent_share', 'stale_coherent')]:
        derived[name] = row[numerator] / n
    derived['complete_share'] = 1 - derived['unavailable_share']
    for p in ('V', 'I', 'G'):
        derived[p + '_coverage'] = row[p + '_conclusive'] / n
        derived[p + '_error_fraction'] = row[p + '_errors'] / row[p + '_conclusive'] if row[p + '_conclusive'] else None
    derived['channel_loss_fraction'] = row['channel_lost'] / row['attempted_messages']
    derived['receiver_drop_fraction'] = row['receiver_dropped'] / row['attempted_messages']
    derived['detected_fraction_given_mixed'] = row['detected_mixed'] / row['mixed'] if row['mixed'] else None
    derived['predicted_fraction_given_mixed'] = row['predicted_detected_mixed'] / row['mixed'] if row['mixed'] else None
    derived['detection_prediction_residual'] = ((row['detected_mixed'] - row['predicted_detected_mixed']) / row['mixed']) if row['mixed'] else None
    return derived


METRICS = ('mixed_share', 'complete_share', 'coherent_share', 'V_coverage', 'I_coverage',
           'G_coverage', 'hidden_mixed_share', 'naive_false_coherent_share',
           'fresh_coherent_availability', 'stale_coherent_share', 'coherent_age_mean_ms',
           'coherent_age_p95_ms', 'channel_loss_fraction', 'receiver_drop_fraction',
           'detected_fraction_given_mixed', 'predicted_fraction_given_mixed',
           'detection_prediction_residual')


def bootstrap_mean(values, key):
    values = [v for v in values if v is not None]
    if not values:
        return None, None, None
    mean = statistics.fmean(values)
    if min(values) == max(values):
        return mean, mean, mean
    r = rng('bootstrap', key)
    n = len(values)
    samples = [sum(values[r.randrange(n)] for _ in range(n)) / n for _ in range(BOOTSTRAPS)]
    return mean, percentile(samples, .025), percentile(samples, .975)


def aggregate(rows, conditions_list):
    by = defaultdict(list)
    for row in rows:
        by[row['condition'], row['publication']].append(row)
    output = []
    for condition in conditions_list:
        for mode in ('R0', 'R1'):
            values = by[condition['id'], mode]
            assert len(values) == RUNS
            for metric in METRICS:
                mean, lo, hi = bootstrap_mean([r[metric] for r in values], (condition['id'], mode, metric))
                output.append(dict(condition=condition['id'], label=condition['label'], alpha=condition['alpha'],
                                   channel=condition['channel'], restart=condition['restart'], publication=mode,
                                   metric=metric, independent_runs=len(values), defined_runs=sum(r[metric] is not None for r in values),
                                   mean=mean, ci95_low=lo, ci95_high=hi))
    contrasts = []
    for condition in conditions_list:
        a = {r['seed']: r for r in by[condition['id'], 'R0']}
        b = {r['seed']: r for r in by[condition['id'], 'R1']}
        for metric in ('mixed_share', 'complete_share', 'I_coverage', 'hidden_mixed_share', 'fresh_coherent_availability'):
            differences = [a[s][metric] - b[s][metric] for s in sorted(a)]
            mean, lo, hi = bootstrap_mean(differences, ('paired', condition['id'], metric))
            contrasts.append(dict(condition=condition['id'], label=condition['label'], metric=metric,
                                  contrast='R0_minus_R1', independent_pairs=RUNS, mean=mean,
                                  ci95_low=lo, ci95_high=hi, min_pair=min(differences), max_pair=max(differences)))
    return output, contrasts


def aggregate_lags(lag_rows, conditions_list):
    lookup = {(r['condition'], r['seed'], r['lag']): r for r in lag_rows}
    result = []
    for condition in conditions_list:
        lags = sorted({r['lag'] for r in lag_rows if r['condition'] == condition['id']})
        for lag in lags:
            counts = [lookup.get((condition['id'], s, lag), {}).get('mixed_slots', 0) for s in range(RUNS)]
            detections = [lookup.get((condition['id'], s, lag), {}).get('detected_slots', 0) for s in range(RUNS)]
            total = sum(counts)
            r = rng('lag-bootstrap', condition['id'], lag)
            estimates = []
            for _ in range(BOOTSTRAPS):
                chosen = [r.randrange(RUNS) for _ in range(RUNS)]
                denominator = sum(counts[i] for i in chosen)
                if denominator:
                    estimates.append(sum(detections[i] for i in chosen) / denominator)
            result.append(dict(condition=condition['id'], label=condition['label'], alpha=condition['alpha'],
                               lag=lag, mixed_slots=total, detected_slots=sum(detections),
                               empirical_detection=sum(detections) / total,
                               analytical_detection=markov_detection(condition['alpha'], lag),
                               ci95_low=percentile(estimates, .025), ci95_high=percentile(estimates, .975),
                               nonempty_bootstraps=len(estimates), contributing_runs=sum(a > 0 for a in counts)))
    return result


def controls():
    checks = []
    base = dict(id='CONTROL', alpha=.5, channel='none', restart='none', label='zero_delay')
    for mode in ('R0', 'R1'):
        row, _, _ = simulate(base, 999, mode, delay_bound=0, read_phase=0)
        assert row['mixed'] == 0 and row['unavailable'] == 0
        checks.append(dict(control='zero_delay_batch_before_read', publication=mode, outcome='PASS',
                           mixed=row['mixed'], coherent=row['coherent'], unavailable=row['unavailable']))
    for mode in ('R0', 'R1'):
        row, _, _ = simulate(dict(base, channel='all', label='all_lost'), 999, mode, read_phase=0)
        assert row['unavailable'] == row['slots'] and row['I_conclusive'] == 0
        checks.append(dict(control='all_messages_lost', publication=mode, outcome='PASS',
                           mixed=row['mixed'], coherent=row['coherent'], unavailable=row['unavailable']))
    restart_rows = []
    for restart in ('clear', 'preserve'):
        row, _, trace = simulate(dict(base, restart=restart, label=restart), 999, 'R1', period=1000,
                                  delay_bound=0, read_phase=0, sample=True)
        sample = next(s for s in trace if s['read_time_ms'] == FAULT_START + FAULT_DURATION)
        if restart == 'clear':
            assert sample['reference'] == 'unavailable' and sample['coherent_age_ms'] is None
        else:
            assert sample['reference'] == 'coherent' and sample['coherent_age_ms'] == 1200
        sample['restart_policy'] = restart
        restart_rows.append(sample)
    write_csv('restart_diagnostic.csv', restart_rows)
    assert monitor(0, 0, grouping='same') == 'coherent'  # false grouping cannot be detected from equal values
    assert monitor(0, 1, labels=(1, 1)) == 'out_of_model'
    assert monitor(2, 0) == 'out_of_model'
    for alpha in (.05, .5, .95):
        # Independent two-state transition recurrence, not reuse of the closed form.
        different = 0.0
        for lag in range(1, 20):
            different = alpha + (1 - 2 * alpha) * different
            assert abs(different - markov_detection(alpha, lag)) < 1e-12
    write_csv('verification_controls.csv', checks)
    return {'zero_delay_controls': 2, 'all_loss_controls': 2, 'restart_memory_controls': 2,
            'invalid_metadata_controls': 2, 'false_grouping_control': 1,
            'markov_recurrence_checks': 57, 'all_passed': True}


def main():
    configs = conditions()
    rows, lags, sources, traces = [], [], [], []
    for alpha in (.05, .5, .95):
        for seed in range(RUNS):
            sources.append(dict(alpha=alpha, seed=seed,
                                history=''.join(map(str, source_history(alpha, seed, END // PERIOD)))))
    write_csv('source_histories.csv', sources)
    with gzip.open(HERE / 'readings.csv.gz', 'wt', encoding='utf-8', newline='', compresslevel=2) as f:
        reader_log = csv.writer(f)
        reader_log.writerow(('condition', 'seed', 'publication', 'read_time_ms', 'online', 'x_origin', 'y_origin'))
        for condition in configs:
            for seed in range(RUNS):
                for mode in ('R0', 'R1'):
                    keep_sample = seed == 0 and condition['id'] in ('C03', 'C05', 'C06', 'C10')
                    row, lag_rows, sample = simulate(condition, seed, mode, readings=reader_log, sample=keep_sample)
                    rows.append(add_metrics(row)); lags.extend(lag_rows); traces.extend(sample)
    write_csv('run_metrics.csv', rows)
    write_csv('lag_counts_per_run.csv', lags)
    write_csv('sample_traces.csv', traces)
    summaries, contrasts = aggregate(rows, configs)
    write_csv('aggregate_metrics.csv', summaries)
    write_csv('paired_contrasts.csv', contrasts)
    lag_summary = aggregate_lags(lags, configs)
    write_csv('lag_validation.csv', lag_summary)
    verification = controls()
    total_errors = sum(r[p + '_errors'] for r in rows for p in ('V', 'I', 'G'))
    assert total_errors == 0
    summary = dict(study_type='Executed synthetic discrete-event model; not a physical data-diode experiment',
                   experiment_version='article1-synthetic-v1', conditions=configs, independent_pairs_per_condition=RUNS,
                   total_pairs=len(configs) * RUNS, total_mode_runs=len(rows),
                   total_evaluation_readings=sum(r['slots'] for r in rows),
                   generation_period_ms=PERIOD, generation_count_per_run=END // PERIOD,
                   total_duration_ms=END, warmup_ms=WARMUP, evaluation_duration_ms=END-WARMUP,
                   read_period_ms=READ_PERIOD, slots_per_mode_run=(END-WARMUP)//READ_PERIOD,
                   delay_distribution=f'discrete uniform integers0..{DELAY_BOUND} ms per message',
                   freshness_threshold_ms=FRESHNESS,
                   loss=dict(iid_probability=.05, burst_stationary_bad_probability=.05,
                             burst_good_to_bad=GOOD_TO_BAD, burst_bad_to_good=BAD_TO_GOOD,
                             mean_bad_generations=1/BAD_TO_GOOD, loss_applied_at='source generation',
                             burst_shared_by='both R0 fields and R1 object for a generation'),
                   restart=dict(start_ms=FAULT_START, duration_ms=FAULT_DURATION,
                                pending_policy='Arrivals retain scheduled times; arrivals while receiver is down are dropped. Arrivals after ready are accepted.',
                                observer='Continues reading throughout; downtime observations are unavailable even if preserved memory exists.'),
                   bootstrap=dict(replications=BOOTSTRAPS, unit='independent whole run or paired run difference',
                                  interval='percentile2.5th..97.5th; deterministic keyed random stream',
                                  scope='pointwise descriptive intervals; no multiplicity correction or confirmatory hypothesis tests'),
                   conclusive_monitor_errors=total_errors,
                   r1_mixed_readings=sum(r['mixed'] for r in rows if r['publication']=='R1'),
                   checks=verification,
                   inference_limits=['No physical timing, link calibration, bandwidth-normalized comparison or industrial failure estimate.',
                                     'Source values, delivery and loss streams are independent by construction.',
                                     'V/I/G use truthful metadata in main runs; zero errors validate model implementation under those premises.',
                                     'Age is reported only for available coherent state; unavailable and mixed states have no state-age value.',
                                     'R0 and R1 have different message units/counts; comparison describes publication semantics, not transport efficiency.',
                                     'Reading slots are dependent. Independent repetition unit is a seeded paired run.',
                                     'The receiver restarts; source epochs do not restart. No attacker, cryptographic primitive or source capture fault is simulated.'])
    (HERE/'results.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    files=sorted(p for p in HERE.iterdir() if p.is_file() and p.name not in ('SHA256SUMS.txt',))
    (HERE/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files),encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ('study_type','total_pairs','total_mode_runs','total_evaluation_readings','conclusive_monitor_errors','r1_mixed_readings','checks')},indent=2))


if __name__ == '__main__':
    main()
