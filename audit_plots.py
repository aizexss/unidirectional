"""Independently verify the numerical values recorded by plot_figures.py."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import struct


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def equal(actual, expected):
    require(math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10),
            f'Plot value {actual} differs from independent value {expected}')


def audit(directory, root):
    evidence = json.loads((directory / 'plot_evidence.json').read_text(encoding='utf-8'))
    source = root / 'study/simulation'
    for name in ('run_metrics.csv', 'aggregate_metrics.csv', 'lag_validation.csv', 'sample_traces.csv'):
        require((source / name).is_file(), f'Missing source {name}')
    for name in ('aggregate_metrics.csv', 'lag_validation.csv', 'sample_traces.csv'):
        require(evidence['source_sha256'][name] == hashlib.sha256((source / name).read_bytes()).hexdigest(),
                f'Wrong plotting input hash: {name}')
    figures = evidence['figures']
    require(set(figures) == set('123456'), 'Expected exactly six figure records')
    for number, figure in figures.items():
        png = (directory / f'figure-{number}.png').read_bytes()
        require(hashlib.sha256(png).hexdigest() == figure['sha256'], 'Figure hash differs')
        require(png[:8] == b'\x89PNG\r\n\x1a\n', 'Invalid PNG signature')
        require(list(struct.unpack('>II', png[16:24])) == figure['pixels'], 'Wrong figure dimensions')
    curves = figures['2']['values']
    require(len(curves['probabilities']) == 201, 'Analytical curve grid is incomplete')
    require(set(curves['curves']) == {'2', '3'} and all(len(v) == 201 for v in curves['curves'].values()),
            'Analytical curves missing, duplicated or incomplete')
    for index, probability in enumerate(curves['probabilities']):
        equal(probability, index/200)
        equal(curves['curves']['2'][index], 2*probability*(1-probability))
        equal(curves['curves']['3'][index], 3*probability*(1-probability))
    runs = rows(source / 'run_metrics.csv')
    for condition in ('C02', 'C05', 'C08'):
        selected = [r for r in runs if r['condition'] == condition and r['publication'] == 'R0']
        require(len(selected) == 40, 'Expected forty run-level shares')
        for actual, count in zip(figures['3']['values']['hidden_detected_coherent_percent'][condition],
                                 ('hidden_mixed', 'detected_mixed', 'coherent')):
            expected = sum(int(r[count])/int(r['slots']) for r in selected)/40*100
            equal(actual, expected)
    lag_rows = rows(source / 'lag_validation.csv')
    require(set(figures['4']['values']) == {'C01', 'C04', 'C07'}, 'Missing lag-plot condition')
    for condition, points in figures['4']['values'].items():
        expected = [r for r in lag_rows if r['condition'] == condition and 1 <= int(r['lag']) <= 6]
        require(len(points) == len(expected), 'Lag points missing or duplicated')
        for point, row in zip(points, expected):
            require(point['lag'] == int(row['lag']), 'Wrong lag point order')
            require(point['mixed'] == int(row['mixed_slots']) and point['detected'] == int(row['detected_slots']),
                    'Wrong lag counts')
            equal(point['ratio'], int(row['detected_slots'])/int(row['mixed_slots']))
            for value, column in zip(point['ci'], ('ci95_low', 'ci95_high')):
                equal(value, float(row[column]))
    aggregates = rows(source / 'aggregate_metrics.csv')
    require(set(figures['5']['values']) == {'coherent_age_p95_ms', 'fresh_coherent_availability'},
            'Missing age/availability panel')
    for metric, points in figures['5']['values'].items():
        require(len(points) == 4 and {(p['condition'], p['mode']) for p in points}
                == {(c, m) for c in ('C05', 'C06') for m in ('R0', 'R1')},
                'Missing or duplicate age/availability bar')
        for point in points:
            matches = [r for r in aggregates if (r['condition'], r['publication'], r['metric'])
                       == (point['condition'], point['mode'], metric)]
            require(len(matches) == 1, 'Wrong age/availability summary')
            scale = 100 if metric == 'fresh_coherent_availability' else 1
            for value, column in zip([point['mean']] + point['ci'], ('mean', 'ci95_low', 'ci95_high')):
                equal(value, float(matches[0][column])*scale)
    traces = rows(source / 'sample_traces.csv')
    require(set(figures['6']['values']) == {'R0', 'R1'}, 'Missing restart-trace mode')
    for mode, point in figures['6']['values'].items():
        expected = [r for r in traces if r['condition'] == 'C10' and int(r['seed']) == 0
                    and r['publication'] == mode and 11600 <= int(r['read_time_ms']) <= 12800]
        require(point['times_ms'] == [int(r['read_time_ms']) for r in expected], 'Wrong trace time grid')
        require(point['states'] == [r['reference'] for r in expected], 'Wrong trace state')
        require(point['coherent_ages_ms'] == [float(r['coherent_age_ms']) if r['coherent_age_ms'] else None
                                             for r in expected], 'Trace ages or missing values changed')
    return {'status': 'PASS', 'figures': 6, 'analytical_points': 402, 'trace_reads': 480,
            'source': 'run counts, aggregate/lag summaries and unmodified sample traces'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.directory, Path(__file__).resolve().parent), indent=2))
