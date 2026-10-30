"""Check the exact read timeline and connect published tables/artwork to evidence.

Standard library only. This module does not import the event simulator.
"""
from pathlib import Path
from bisect import bisect_right
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from zipfile import ZipFile
import csv
import gzip
import hashlib
import json
import posixpath
import random
import re
import xml.etree.ElementTree as ET


def require(value, message):
    if not value:
        raise ValueError(message)


def stream(*parts):
    key = '|'.join(str(p) for p in ('article1-synthetic-v1',) + parts).encode()
    return random.Random(int.from_bytes(hashlib.sha256(key).digest()[:16], 'big'))


def arrivals_for(condition, seed, mode, cfg):
    """Sorted arrivals independently implement the declared loss/restart rules."""
    n = cfg['generation_count_per_run']
    outage = stream('outage', seed)
    bad = outage.random() < cfg['loss']['burst_stationary_bad_probability']
    environment = []
    for _ in range(n):
        environment.append(bad)
        bad = (outage.random() >= cfg['loss']['burst_bad_to_good']) if bad else (outage.random() < cfg['loss']['burst_good_to_bad'])
    components = ('x', 'y') if mode == 'R0' else ('object',)
    result = {}
    start = cfg['restart']['start_ms']
    end = start + cfg['restart']['duration_ms']
    for component in components:
        delay = stream('delay', mode, component, seed)
        loss = stream('loss', mode, component, seed)
        delivered = []
        for index in range(n):
            time = index * cfg['generation_period_ms'] + delay.randint(0, 40)
            draw = loss.random()
            lost = ((condition['channel'] == 'iid05' and draw < cfg['loss']['iid_probability'])
                    or (condition['channel'] == 'burst05' and environment[index]))
            if lost or time >= cfg['total_duration_ms']:
                continue
            if condition['restart'] != 'none' and start <= time < end:
                continue
            delivered.append((time, index + 1))
        result[component] = sorted(delivered)
    return result


def origin_at(arrivals, time, condition, cfg):
    index = bisect_right(arrivals, (time, cfg['generation_count_per_run'] + 1)) - 1
    if index < 0:
        return 0
    arrival, origin = arrivals[index]
    start = cfg['restart']['start_ms']
    ready = start + cfg['restart']['duration_ms']
    if condition['restart'] == 'clear' and time >= start and arrival < ready:
        return 0
    return origin


def compare_read_stream(records, expected):
    count = 0
    for count, wanted in enumerate(expected, 1):
        actual = next(records, None)
        require(actual is not None, f'Reading log is truncated at row {count}')
        observed = (actual['condition'], int(actual['seed']), actual['publication'],
                    int(actual['read_time_ms']), int(actual['online']),
                    int(actual['x_origin']), int(actual['y_origin']))
        require(observed == wanted, f'Reading timeline differs at row {count}: expected {wanted}, got {observed}')
    require(next(records, None) is None, 'Reading log contains extra rows')
    return count


def audit_timeline(study):
    cfg = json.loads((study / 'simulation/results.json').read_text(encoding='utf-8'))

    def expected_rows():
        for condition in cfg['conditions']:
            for seed in range(cfg['independent_pairs_per_condition']):
                phase = stream('read-phase', seed).randrange(cfg['read_period_ms'])
                for mode in ('R0', 'R1'):
                    arrivals = arrivals_for(condition, seed, mode, cfg)
                    for time in range(cfg['warmup_ms'] + phase, cfg['total_duration_ms'], cfg['read_period_ms']):
                        start = cfg['restart']['start_ms']
                        ready = start + cfg['restart']['duration_ms']
                        online = int(condition['restart'] == 'none' or not start <= time < ready)
                        if mode == 'R0':
                            ox = origin_at(arrivals['x'], time, condition, cfg)
                            oy = origin_at(arrivals['y'], time, condition, cfg)
                        else:
                            ox = oy = origin_at(arrivals['object'], time, condition, cfg)
                        yield condition['id'], seed, mode, time, online, ox, oy

    with gzip.open(study / 'simulation/readings.csv.gz', 'rt', encoding='utf-8', newline='') as source:
        count = compare_read_stream(iter(csv.DictReader(source)), expected_rows())
    require(count == cfg['total_evaluation_readings'], 'Unexpected reading count')
    return count


NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'o': 'urn:schemas-microsoft-com:office:office',
      'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}


def manuscript_content(path):
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
        tables = []
        for table in root.findall('./w:body/w:tbl', NS):
            tables.append([[''.join(cell.itertext()) for cell in row.findall('w:tc', NS)] for row in table.findall('w:tr', NS)])
        relations = {r.get('Id'): r.get('Target') for r in ET.fromstring(archive.read('word/_rels/document.xml.rels'))}
        artwork = []
        for blip in root.findall('.//a:blip', NS):
            target = relations[blip.get('{' + NS['r'] + '}embed')]
            member = target.lstrip('/') if target.startswith('/') else posixpath.normpath('word/' + target)
            artwork.append(archive.read(member))
    return tables, artwork


def orcid_valid(identifier):
    """ISO 7064 MOD 11-2 checksum, including the possible final X."""
    if not re.fullmatch(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]', identifier):
        return False
    digits = identifier.replace('-', '')
    total = 0
    for digit in digits[:-1]:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    return digits[-1] == ('X' if check == 10 else str(check))


def audit_journal_text(paragraphs):
    """Check the frozen manuscript's submission and attribution contract."""
    abstracts = [p.removeprefix('Abstract: ') for p in paragraphs if p.startswith('Abstract: ')]
    require(len(abstracts) == 1, 'Expected one English abstract')
    abstract = abstracts[0]
    require(250 <= len(abstract.split()) <= 280, 'Abstract must contain 250–280 words')
    require(250 <= len(abstract) <= 1900, 'Abstract exceeds the submission character range')
    require(paragraphs.count('References') == 1, 'Expected one References heading')
    split = paragraphs.index('References')
    references = [p for p in paragraphs[split + 1:] if p.strip()]
    require(len(references) == 20, 'Expected 20 references')
    require([re.match(r'^\[(\d+)\]', p).group(1) if re.match(r'^\[(\d+)\]', p) else ''
             for p in references] == [str(i) for i in range(1, 21)], 'References are not numbered consecutively')
    first_mentions = []
    for paragraph in paragraphs[:split]:
        for group in re.findall(r'\[([\d,\s–-]+)\]', paragraph):
            numbers = []
            for token in group.split(','):
                bounds = re.split(r'[–-]', token.strip())
                numbers.extend(range(int(bounds[0]), int(bounds[-1]) + 1))
            require(0 < len(numbers) <= 3, 'A citation group contains more than three sources')
            require(all(1 <= n <= 20 for n in numbers), 'Citation outside the bibliography')
            first_mentions.extend(n for n in numbers if n not in first_mentions)
    require(first_mentions == list(range(1, 21)), 'First citations do not follow reference order')
    identities = (
        ('Aibar Ibragimov', 'life33890@gmail.com', '0009-0002-7454-2382'),
        ('Leila Rzayeva', 'l.rzayeva@astanait.edu.kz', '0000-0002-3382-4685'),
    )
    front = '\n'.join(paragraphs[:paragraphs.index('Introduction')])
    for name, email, orcid in identities:
        require(paragraphs.count(name) == 1 and front.count(email) == 1 and front.count(orcid) == 1,
                'Missing or duplicate author identity: ' + name)
        require(orcid_valid(orcid), 'Invalid ORCID checksum: ' + name)
    return {'abstract_words': len(abstract.split()), 'abstract_characters': len(abstract),
            'references_in_citation_order': len(references), 'author_identities': len(identities)}


def rounded_percentage(rows, numerator, denominator='slots'):
    value = sum((Fraction(sum(int(r[k]) for k in numerator), int(r[denominator])) for r in rows), Fraction()) / len(rows)
    decimal = Decimal(value.numerator) * 100 / Decimal(value.denominator)
    return str(decimal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def table_by_header(tables, expected):
    """Locate a numerical table by its meaning rather than its layout position."""
    normalize = lambda cells: tuple(''.join(cell.split()) for cell in cells)
    matches = [table for table in tables if table and normalize(table[0]) == normalize(expected)]
    require(len(matches) == 1, 'Missing or duplicate manuscript table: ' + expected[0])
    return matches[0]


def require_table_rows(table, key_columns, expected_keys):
    rows = table[1:]
    keys = [tuple(row[:key_columns]) for row in rows]
    require(all(len(row) == len(table[0]) for row in rows)
            and len(keys) == len(set(keys)) and set(keys) == set(expected_keys),
            'Missing, duplicate or truncated manuscript table row')


def audit_manuscript(study, manuscript):
    article = manuscript / 'Ibragimov_Aibar_Article_Revised.docx'
    tables, artwork = manuscript_content(article)
    with ZipFile(article) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
    paragraphs = [''.join(p.itertext()) for p in root.findall('./w:body/w:p', NS)]
    journal = audit_journal_text(paragraphs)
    equations = root.findall('.//o:OLEObject', NS)
    require(len(equations) == 10 and all(e.get('ProgID') == 'Equation.DSMT4' and e.get('Type') == 'Embed'
                                       for e in equations), 'Expected ten embedded MathType equations')
    require(not root.findall('.//m:oMath', NS), 'Unconverted native Word equation remains')
    require(len(tables) == 9 and len(artwork) == 6, 'Unexpected manuscript structure')
    with (study / 'simulation/run_metrics.csv').open(encoding='utf-8', newline='') as source:
        runs = list(csv.DictReader(source))
    checked = 0
    publication_table = table_by_header(tables, ['Condition', 'Mode', 'Mixed (%)', 'Complete (%)', 'Fresh coherent (%)'])
    coverage_table = table_by_header(tables, ['Condition', 'α', 'Actual mixed (%)', 'V coverage (%)', 'Hidden mixed (%)', 'Detected given mixed (%)'])
    require_table_rows(publication_table, 2,
                       {(condition, mode) for condition in ('C04', 'C05', 'C06', 'C10', 'C11', 'C12') for mode in ('R0', 'R1')})
    require_table_rows(coverage_table, 1, {(condition,) for condition in ('C02', 'C05', 'C08')})
    for row in publication_table[1:]:
        condition, mode = row[:2]
        selected = [r for r in runs if r['condition'] == condition and r['publication'] == mode]
        require(len(selected) == 40, 'Missing table runs')
        for shown, fields in zip(row[2:], (('mixed',), ('coherent', 'mixed'), ('fresh_coherent',))):
            require(shown == rounded_percentage(selected, fields), f'Publication table differs: {condition} {mode} {fields}')
            checked += 1
    for row in coverage_table[1:]:
        selected = [r for r in runs if r['condition'] == row[0] and r['publication'] == 'R0']
        require(len(selected) == 40, 'Missing table runs')
        for shown, fields, denominator in zip(row[2:], (('mixed',), ('V_conclusive',), ('hidden_mixed',), ('detected_mixed',)), ('slots', 'slots', 'slots', 'mixed')):
            require(shown == rounded_percentage(selected, fields, denominator), 'Coverage table differs: ' + row[0])
            checked += 1
    for index, content in enumerate(artwork, 1):
        path = manuscript / 'figures' / f'figure-{index}.png'
        require(path.is_file() and path.read_bytes() == content, f'Published figure {index} differs from the Word manuscript')
    return {'simulation_table_cells': checked, 'manuscript_tables': len(tables), 'exact_manuscript_figures': len(artwork),
            'embedded_mathtype_equations': len(equations), **journal}


def audit_all(study, manuscript):
    rows = audit_timeline(study)
    result = audit_manuscript(study, manuscript)
    return {'status': 'PASS', 'exact_timeline_rows': rows, **result,
            'scope': 'Declared synthetic event model; no physical-device validation'}
