"""Reproduce or independently verify the article's synthetic study.

Only the Python standard library is required. Existing evidence is never
overwritten: computational programs execute in a temporary copy of study/.
"""
from pathlib import Path
import argparse
import csv
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from fractions import Fraction
from decimal import Decimal, ROUND_HALF_UP

ROOT = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def display_mean_percent(ratios):
    """Round an exact mean of count ratios without binary-float tie errors."""
    require(bool(ratios), 'Cannot round an empty set of ratios')
    mean = sum(ratios, Fraction()) / len(ratios)
    value = Decimal(mean.numerator) * 100 / Decimal(mean.denominator)
    return str(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def verify_manifest(root):
    records = json.loads((root / 'MANIFEST.json').read_text(encoding='utf-8'))
    require(bool(records), 'The file manifest is empty')
    seen = set()
    for item in records:
        relative = item['path']
        path = (root / relative).resolve()
        require(path.is_relative_to(root.resolve()), 'Manifest path escapes repository')
        require(relative not in seen, 'Duplicate manifest path: ' + relative)
        seen.add(relative)
        require(path.is_file(), 'Missing file: ' + relative)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        require(actual == item['sha256'], 'Checksum mismatch: ' + relative)
    return len(records)


def execute(script, study, reports, stage):
    log = reports / (script.replace('/', '_') + '.log')
    with log.open('w', encoding='utf-8') as output:
        process = subprocess.run(
            [sys.executable, '-X', 'utf8', str(study / script)],
            cwd=study, stdout=output, stderr=subprocess.STDOUT, check=False,
        )
    require(process.returncode == 0, f'{stage} failed; see {log}')


def same_content(reference, regenerated):
    if reference.suffix == '.gz':
        with gzip.open(reference, 'rb') as left, gzip.open(regenerated, 'rb') as right:
            while True:
                block = left.read(1024 * 1024)
                if block != right.read(1024 * 1024):
                    return False
                if not block:
                    return True
    if reference.suffix == '.json':
        return json.loads(reference.read_text(encoding='utf-8')) == json.loads(regenerated.read_text(encoding='utf-8'))
    return reference.read_bytes() == regenerated.read_bytes()


def compare_regenerated(reference, regenerated):
    checked = 0
    for folder in ('model', 'theory', 'graph_validation', 'simulation'):
        for path in sorted((reference / folder).iterdir()):
            if path.suffix not in ('.csv', '.json', '.gz'):
                continue
            require(same_content(path, regenerated / folder / path.name), 'Regenerated output differs: ' + str(path.relative_to(reference)))
            checked += 1
    return checked


def principal_results(study):
    config = json.loads((study / 'simulation/results.json').read_text(encoding='utf-8'))
    with (study / 'simulation/run_metrics.csv').open(encoding='utf-8', newline='') as stream:
        runs = list(csv.DictReader(stream))
    require(len(runs) == 960, 'Expected 960 mode runs')
    require(len({(r['condition'], r['seed'], r['publication']) for r in runs}) == 960, 'Duplicate run keys')
    require(sum(int(r['slots']) for r in runs) == 3_840_000, 'Expected 3,840,000 scheduled reads')
    require(all(int(r['slots']) == 4000 for r in runs), 'A run does not contain 4,000 read slots')
    for run in runs:
        require(sum(int(run[k]) for k in ('coherent', 'mixed', 'unavailable')) == 4000, 'Read states do not partition the run')
        require(int(run['hidden_mixed']) + int(run['detected_mixed']) == int(run['mixed']), 'Mixed-read decomposition failed')
    require(all(int(r['mixed']) == 0 for r in runs if r['publication'] == 'R1'), 'Whole-object publication mixes origins')
    selected = [r for r in runs if r['condition'] == 'C05' and r['publication'] == 'R0']
    require(len(selected) == 40, 'C05 R0 must have 40 replications')
    require(all(int(r['unavailable']) == 0 for r in selected), 'C05 R0 completeness is not 100%')
    mixed = 100 * sum(int(r['mixed']) for r in selected) / (40 * 4000)
    require(round(mixed, 2) == 62.14, 'C05 mixed share differs from manuscript')
    no_loss_detection = {}
    for condition, expected in (('C01', 5.878), ('C04', 49.839), ('C07', 79.129)):
        chosen = [r for r in runs if r['condition'] == condition and r['publication'] == 'R0']
        require(len(chosen) == 40, 'Missing no-loss runs: ' + condition)
        value = 100 * sum(float(r['detected_fraction_given_mixed']) for r in chosen) / 40
        require(round(value, 3) == expected, 'Conditional detection differs: ' + condition)
        no_loss_detection[condition] = value
    rounded = {}
    for condition, mode, count, expected in (
        ('C06', 'R1', 'fresh_coherent', '95.50'),
        ('C12', 'R1', 'fresh_coherent', '94.49'),
        ('C05', 'R0', 'V_conclusive', '30.90'),
    ):
        chosen = [r for r in runs if r['condition'] == condition and r['publication'] == mode]
        require(len(chosen) == 40, 'Missing rounding-check runs: ' + condition)
        value = display_mean_percent([Fraction(int(r[count]), int(r['slots'])) for r in chosen])
        require(value == expected, 'Rounded table result differs: ' + condition + ' ' + count)
        rounded[condition + '_' + mode + '_' + count + '_percent'] = value
    return {
        'conditions': len(config['conditions']), 'mode_runs': len(runs),
        'scheduled_reads': sum(int(r['slots']) for r in runs),
        'replications_per_condition': 40, 'slots_per_mode_run': 4000,
        'C05_R0_actual_mixed_percent': mixed, 'C05_R0_complete_percent': 100.0,
        'R1_actual_mixed_reads_all_conditions': 0,
        'no_loss_values_detection_percent_given_mixed': no_loss_detection,
        'corrected_table_percentages': rounded,
    }


def write_reports(reports, summary):
    reports.mkdir(exist_ok=True)
    (reports / 'verification_summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    lines = ['# Article verification results', '', '**Status: ' + summary['status'] + '**', '',
             'Mode: ' + summary['mode'], '', '## Verification stages', '']
    lines += [f"- {stage['status']}: {stage['name']}" for stage in summary['stages']]
    if 'error' in summary:
        lines += ['', 'Error: ' + summary['error']]
    if 'results' in summary:
        values = summary['results']
        lines += ['', '## Principal results', '', '| Measure | Result |', '| --- | ---: |',
                  f"| Conditions | {values['conditions']} |", f"| Mode runs | {values['mode_runs']} |",
                  f"| Scheduled reads | {values['scheduled_reads']:,} |",
                  f"| C05 R0 actual mixed reads | {values['C05_R0_actual_mixed_percent']:.4f}% |",
                  '| C05 R0 complete-state availability | 100% |', '| R1 mixed reads across conditions | 0 |']
        for condition, value in values['no_loss_values_detection_percent_given_mixed'].items():
            lines.append(f'| {condition} V detection conditional on mixing | {value:.3f}% |')
        lines += ['| C06 R1 fresh coherent availability | 95.50% |',
                  '| C12 R1 fresh coherent availability | 94.49% |',
                  '| C05 R0 V coverage | 30.90% |', '',
                  'Displayed table percentages use decimal half-up rounding of exact count ratios.']
    lines += ['', '## Interpretation', '',
              'All results concern an executed synthetic model. No physical data-diode performance is measured.',
              'Replications are independent within a condition; common random inputs couple different conditions.',
              'State shares use 4,000 planned reads per run. Message losses use attempted emissions over 24 seconds.',
              'Zero R1 mixing depends on the stated capture, origin-binding, publication and read contract.',
              'Stage logs are stored beside this report. Saved evidence under study/ is never overwritten.', '']
    (reports / 'RESULTS.md').write_text('\n'.join(lines), encoding='utf-8')
    russian = ['# Проверка результатов статьи', '', '**Статус: ' + summary['status'] + '**', '',
               'Режим: ' + ('полный повтор расчётов' if summary['mode'] == 'full' else 'проверка сохранённых данных'), '',
               '## Этапы', '']
    russian += [f"- {stage['status']}: {stage['name']}" for stage in summary['stages']]
    if 'error' in summary:
        russian += ['', 'Причина ошибки: ' + summary['error']]
    if 'results' in summary:
        values = summary['results']
        russian += ['', '## Основные результаты', '', '| Показатель | Результат |', '| --- | ---: |',
                    f"| Условия | {values['conditions']} |", f"| Прогоны режимов | {values['mode_runs']} |",
                    f"| Запланированные чтения | {values['scheduled_reads']:,} |",
                    f"| C05 R0 смешанные чтения | {values['C05_R0_actual_mixed_percent']:.4f}% |",
                    '| C05 R0 полнота состояния | 100% |', '| R1 смешанные чтения во всех условиях | 0 |']
        russian += ['| C06 R1 свежие согласованные состояния | 95,50% |',
                    '| C12 R1 свежие согласованные состояния | 94,49% |',
                    '| C05 R0 покрытие V | 30,90% |', '',
                    'Проценты округлены десятичным правилом half-up из точных долей счётчиков.']
    russian += ['', '## Как понимать результат', '',
                'Исследование синтетическое. Производительность физического оборудования не измерялась.',
                'Знаменатель долей состояния — 4 000 запланированных чтений в каждом прогоне.',
                'Потери сообщений считаются от числа отправок за 24 секунды.',
                'Повторы независимы внутри условия; разные условия связаны общими случайными входами.',
                'Исходные материалы study/ не перезаписываются. Подробный вывод находится в файлах *.log.', '']
    (reports / 'RESULTS_RU.md').write_text('\n'.join(russian), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--verify-only', action='store_true', help='Validate supplied data without rerunning the simulator')
    mode.add_argument('--full', action='store_true', help='Regenerate all computations in an isolated copy and compare outputs')
    args = parser.parse_args(argv)
    reports = ROOT / 'reports'
    reports.mkdir(exist_ok=True)
    summary = {'status': 'RUNNING', 'mode': 'full' if args.full else 'verify-only',
               'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'stages': []}
    stage_name = 'File integrity'
    try:
        summary['manifest_files_verified'] = verify_manifest(ROOT)
        summary['stages'].append({'name': stage_name, 'status': 'PASS'})
        print('[PASS] File integrity: ' + str(summary['manifest_files_verified']) + ' files', flush=True)
        with tempfile.TemporaryDirectory(prefix='article1-rerun-') as workspace:
            study = Path(workspace) / 'study'
            shutil.copytree(ROOT / 'study', study)
            scripts = [('model/run_model.py', 'Finite-state and schedule enumeration'),
                       ('theory/verify_theory.py', 'Exact theory and partition checks'),
                       ('graph_checks.py', 'Equality-evidence graph checks')]
            if args.full:
                scripts.append(('simulation/run_simulation.py', 'Regenerate 960 mode runs and bootstrap intervals'))
            scripts += [('simulation/validate_reading_log.py', 'Independent validation of all 3,840,000 reads'),
                        ('audit_study/audit_independent.py', 'Independent arrival-timeline and interval reconstruction')]
            for index, (script, stage_name) in enumerate(scripts, 1):
                print(f'[{index}/{len(scripts)}] {stage_name} ...', flush=True)
                execute(script, study, reports, stage_name)
                summary['stages'].append({'name': stage_name, 'status': 'PASS'})
                print('        PASS', flush=True)
            stage_name = 'Agreement with manuscript results'
            summary['results'] = principal_results(study)
            summary['stages'].append({'name': stage_name, 'status': 'PASS'})
            if args.full:
                stage_name = 'Regenerated outputs match supplied reference'
                summary['regenerated_files_compared'] = compare_regenerated(ROOT / 'study', study)
                summary['stages'].append({'name': stage_name, 'status': 'PASS'})
        summary['status'] = 'PASS'
    except Exception as error:
        summary['status'] = 'FAIL'
        summary['error'] = str(error)
        summary['stages'].append({'name': stage_name, 'status': 'FAIL'})
    write_reports(reports, summary)
    print(summary['status'] + ': ' + str(reports / 'RESULTS.md'), flush=True)
    if summary['status'] == 'PASS':
        print('C05 R0 mixed: 62.14%; completeness: 100%; R1 mixed: 0; reads verified: 3,840,000', flush=True)
    else:
        print(summary['error'], file=sys.stderr)
    return 0 if summary['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
