"""Redraw the six article figures from analytical formulas and frozen CSV data.

Optional plotting dependencies are listed in requirements-figures.txt.
The numerical reproduction runner does not require them.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def lag_probability(alpha, lag):
    if not 0 <= alpha <= 1 or lag < 0 or int(lag) != lag:
        raise ValueError('A probability and a nonnegative integer lag are required')
    return (1 - (1 - 2 * alpha) ** lag) / 2


def coverage_parts(records, condition):
    parts = []
    for metric in ('hidden_mixed_share', 'V_coverage', 'coherent_share'):
        selected = [r for r in records if (r['condition'], r['publication'], r['metric'])
                    == (condition, 'R0', metric)]
        if len(selected) != 1:
            raise ValueError(f'Expected one {condition}/{metric} row')
        row = selected[0]
        if int(row['independent_runs']) != 40 or int(row['defined_runs']) != 40:
            raise ValueError('Coverage requires all 40 run summaries')
        value = float(row['mean'])
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('Invalid read share')
        parts.append(100 * value)
    if not math.isclose(sum(parts), 100, abs_tol=1e-8):
        raise ValueError('Read outcome shares do not sum to 100%')
    return parts


def select_trace(records, mode):
    rows = [r for r in records if r['condition'] == 'C10' and int(r['seed']) == 0
            and r['publication'] == mode and 11600 <= int(r['read_time_ms']) <= 12800]
    expected = list(range(11602, 12800, 5))
    if [int(r['read_time_ms']) for r in rows] != expected:
        raise ValueError('Restart trace must contain the exact 240 scheduled reads')
    for row in rows:
        coherent = row['reference'] == 'coherent'
        if bool(row['coherent_age_ms']) != coherent:
            raise ValueError('Coherent age must be absent for mixed/unavailable reads')
        if row['reference'] not in ('coherent', 'mixed', 'unavailable'):
            raise ValueError('Unknown reference state')
        if coherent and not 0 <= float(row['coherent_age_ms']) <= 80:
            raise ValueError('Trace age lies outside the displayed 0–80 ms scale')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('reports/figures'))
    parser.add_argument('--font', default='Times New Roman')
    args = parser.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Rectangle, Patch
    import numpy as np
    from PIL import Image

    font_path = font_manager.findfont(args.font, fallback_to_default=False)
    plt.rcParams.update({'font.family': args.font, 'font.size': 8,
                         'axes.labelsize': 8, 'axes.titlesize': 8,
                         'xtick.labelsize': 8, 'ytick.labelsize': 8,
                         'legend.fontsize': 8, 'axes.spines.top': False,
                         'axes.spines.right': False, 'savefig.facecolor': 'white'})
    root = Path(__file__).resolve().parent
    source = root / 'study/simulation'
    aggregate = read_csv(source / 'aggregate_metrics.csv')
    lags = read_csv(source / 'lag_validation.csv')
    traces = read_csv(source / 'sample_traces.csv')
    output = args.output.resolve()
    if any(output == frozen or frozen in output.parents
           for frozen in (root / 'study', root / 'manuscript')):
        parser.error('Choose an output directory outside the frozen evidence')
    output.mkdir(parents=True, exist_ok=True)
    evidence = {'matplotlib': matplotlib.__version__, 'numpy': np.__version__,
                'font': args.font, 'font_sha256': hashlib.sha256(Path(font_path).read_bytes()).hexdigest(),
                'dpi': 600, 'source_sha256': {}, 'figures': {}}
    for name in ('aggregate_metrics.csv', 'lag_validation.csv', 'sample_traces.csv'):
        evidence['source_sha256'][name] = hashlib.sha256((source / name).read_bytes()).hexdigest()

    def save(figure, number, values):
        png = output / f'figure-{number}.png'
        figure.savefig(png, dpi=600)
        plt.close(figure)
        with Image.open(png) as im:
            im.convert('RGB').save(output / f'figure-{number}.jpg', quality=100,
                                   subsampling=0, dpi=(600, 600))
            size = list(im.size)
        evidence['figures'][str(number)] = {'pixels': size, 'values': values,
                                            'sha256': hashlib.sha256(png.read_bytes()).hexdigest()}
        print(f'PASS figure {number}/6: {png.name}, {size[0]} x {size[1]} px')

    # Figure 1 is a schematic of the declared publication contracts.
    fig, ax = plt.subplots(figsize=(3.37, 2.95))
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis('off')
    def box(x, y, width, height, text):
        ax.add_patch(Rectangle((x, y), width, height, facecolor='white', edgecolor='black', linewidth=.65))
        ax.text(x + width/2, y + height/2, text, ha='center', va='center')
    def arrow(start, end):
        ax.annotate('', xy=end, xytext=start,
                    arrowprops={'arrowstyle': '->', 'lw': .65, 'shrinkA': 0, 'shrinkB': 1})
    box(.16, .86, .68, .115, 'Atomic source capture\nImmutable generation (e, i)')
    box(.01, .64, .45, .115, 'R0 field messages\n(x, origin) or (y, origin)')
    box(.54, .64, .45, .115, 'R1 object message\nWhole snapshot')
    for x, top, bottom in ((.235, .40, .40), (.765, .60, .60)):
        arrow((top, .86), (x, .755)); arrow((x, .64), (x, .60))
        ax.text(x, .57, 'Loss / reordering', ha='center', va='center')
        arrow((x, .54), (x, .48)); arrow((x, .345), (bottom, .265))
    box(.01, .345, .45, .135, 'Atomic field update\nOnly x or only y')
    box(.54, .345, .45, .135, 'Atomic object update\nBoth fields together')
    box(.16, .165, .68, .10, 'Atomic consumer read')
    ax.text(.5, .075, 'Observer: V values | G grouping | I origins', ha='center', va='center')
    arrow((.5, .165), (.5, .115))
    fig.subplots_adjust(left=.01, right=.99, bottom=.01, top=.99)
    save(fig, 1, {'type': 'contract schematic; no empirical observations'})

    probabilities = np.linspace(0, 1, 201)
    fig, ax = plt.subplots(figsize=(3.37, 2.35))
    curves = {}
    for origins, style in ((2, '-'), (3, '--')):
        detected = 1 - probabilities**origins - (1-probabilities)**origins
        ax.plot(probabilities, detected, color='black', ls=style,
                label=f'{"Two" if origins == 2 else "Three"} distinct origins')
        curves[str(origins)] = detected.tolist()
    ax.set(xlim=(0, 1), ylim=(0, 1), xlabel='Probability of source value 1',
           ylabel='Conditional detected fraction')
    ax.legend(frameon=False, loc='upper center'); ax.grid(alpha=.2)
    fig.tight_layout(pad=.65)
    save(fig, 2, {'probabilities': probabilities.tolist(), 'curves': curves})

    conditions = ('C02', 'C05', 'C08')
    parts = {c: coverage_parts(aggregate, c) for c in conditions}
    fig = plt.figure(figsize=(3.37, 2.55))
    ax = fig.add_axes([.165, .185, .805, .605])
    bottom = np.zeros(3)
    colors = ['#bdbdbd', '#202020', '#ffffff']
    labels = ['Hidden\nmixed', 'Detected\nmixed', 'Coherent']
    for index, color in enumerate(colors):
        heights = np.array([parts[c][index] for c in conditions])
        ax.bar(range(3), heights, bottom=bottom, width=.62, color=color,
               edgecolor='#202020', linewidth=.55, zorder=3)
        bottom += heights
    ax.set(xlim=(-.58, 2.58), ylim=(0, 100), xlabel='Source flip probability, α', ylabel='Scheduled reads (%)')
    ax.set_xticks(range(3), ['0.05', '0.50', '0.95'])
    ax.set_axisbelow(True); ax.grid(axis='y', color='#d9d9d9', linewidth=.4)
    handles = [Patch(facecolor=c, edgecolor='#202020', linewidth=.55, label=s) for c, s in zip(colors, labels)]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.57, .985), ncol=3,
               frameon=False, handlelength=1.25, handletextpad=.5, columnspacing=1.2, borderaxespad=0)
    save(fig, 3, {'conditions': conditions, 'hidden_detected_coherent_percent': parts})

    fig = plt.figure(figsize=(3.37, 2.75))
    ax = fig.add_axes([.16, .18, .81, .66])
    lag_values = {}
    for condition, alpha, style, marker in (('C01', .05, '-', 'o'), ('C04', .5, '--', 's'), ('C07', .95, ':', '^')):
        ks = list(range(1, 7))
        predicted = [lag_probability(alpha, k) for k in ks]
        ax.plot(ks, predicted, color='black', ls=style, label=f'α = {alpha:.2f}')
        rows = [r for r in lags if r['condition'] == condition and int(r['lag']) <= 6]
        values = []
        seen = set()
        for row in rows:
            k, mixed, detected = int(row['lag']), int(row['mixed_slots']), int(row['detected_slots'])
            if k in seen or k < 1 or detected < 0 or detected > mixed:
                raise ValueError('Invalid or duplicate lag counts')
            seen.add(k)
            mean, low, high = (float(row[n]) for n in ('empirical_detection', 'ci95_low', 'ci95_high'))
            if not mixed or not math.isclose(mean, detected/mixed, abs_tol=1e-12) or not 0 <= low <= high <= 1:
                raise ValueError('Lag plot disagrees with recorded mixed/detected counts')
            ax.vlines(k, low, high, color='black', linewidth=.65)
            ax.plot([k-.045, k+.045], [low, low], color='black', linewidth=.65)
            ax.plot([k-.045, k+.045], [high, high], color='black', linewidth=.65)
            ax.plot(k, mean, marker, ms=3, color='black')
            values.append({'lag': k, 'mixed': mixed, 'detected': detected, 'ratio': mean, 'ci': [low, high]})
        lag_values[condition] = values
    ax.set(xlabel='Generation lag between distinct origins', ylabel='Conditional detected fraction',
           xlim=(.7, 6.3), ylim=(0, 1.04)); ax.set_xticks(range(1, 7))
    fig.legend(*ax.get_legend_handles_labels(), frameon=False, ncol=3,
               loc='upper center', bbox_to_anchor=(.56, .985),
               handlelength=1.6, columnspacing=.8)
    ax.grid(alpha=.15)
    save(fig, 4, lag_values)

    fig, axes = plt.subplots(2, 1, figsize=(3.37, 3.55))
    age_values = {}
    for ax, metric, scale, label in ((axes[0], 'coherent_age_p95_ms', 1, 'Mean run-level p95 age (ms)'),
                                    (axes[1], 'fresh_coherent_availability', 100, 'Fresh coherent reads (%)')):
        age_values[metric] = []
        for j, (mode, color) in enumerate((('R0', '.7'), ('R1', 'white'))):
            for i, condition in enumerate(('C05', 'C06')):
                rows = [r for r in aggregate if (r['condition'], r['publication'], r['metric']) == (condition, mode, metric)]
                if len(rows) != 1: raise ValueError('Missing or duplicate age/availability row')
                mean, low, high = [float(rows[0][key])*scale for key in ('mean', 'ci95_low', 'ci95_high')]
                x = i + (j-.5)*.33
                ax.bar(x, mean, width=.31, color=color, edgecolor='black', linewidth=.6,
                       label=mode if i == 0 else None)
                ax.vlines(x, low, high, color='black', linewidth=.6)
                for cap in (low, high): ax.plot([x-.035, x+.035], [cap, cap], color='black', linewidth=.6)
                age_values[metric].append({'condition': condition, 'mode': mode, 'mean': mean, 'ci': [low, high]})
        ax.set_xticks([0, 1], ['Independent loss', 'Burst loss']); ax.set_ylabel(label)
        ax.grid(axis='y', alpha=.15)
    axes[0].legend(frameon=False, ncol=2); axes[1].set_ylim(0, 110)
    fig.tight_layout(pad=.65)
    save(fig, 5, age_values)

    fig = plt.figure(figsize=(3.37, 3.60))
    grid = fig.add_gridspec(3, 1, height_ratios=[1.23, 1, 1], top=.885, bottom=.135,
                           left=.17, right=.95, hspace=.47)
    status = fig.add_subplot(grid[0]); ages0 = fig.add_subplot(grid[1], sharex=status)
    ages1 = fig.add_subplot(grid[2], sharex=status)
    palette = {'coherent': ('white', None), 'mixed': ('.20', None), 'unavailable': ('.75', '////')}
    handles = [Patch(facecolor=palette[s][0], edgecolor='.28', hatch=palette[s][1],
                     label=label) for s, label in (('coherent', 'C coherent'), ('mixed', 'M mixed'), ('unavailable', 'U unavailable'))]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.52, .998), ncol=3,
               frameon=False, handlelength=1.1, handletextpad=.35, columnspacing=.7, borderaxespad=0)
    trace_values = {}
    for mode, y, ax, letter in (('R0', 1, ages0, 'b'), ('R1', 0, ages1, 'c')):
        rows = select_trace(traces, mode)
        times = [(int(r['read_time_ms'])-12000)/1000 for r in rows]
        states = [r['reference'] for r in rows]
        ages = [float(r['coherent_age_ms']) if r['coherent_age_ms'] else float('nan') for r in rows]
        start = 0
        for end in range(1, len(rows)+1):
            if end == len(rows) or states[end] != states[start]:
                left, right = max(-.4, times[start]-.0025), min(.8, times[end-1]+.0025)
                color, hatch = palette[states[start]]
                status.add_patch(Rectangle((left, y-.19), right-left, .38, facecolor=color,
                                           edgecolor='.28', hatch=hatch, linewidth=.3, zorder=3))
                start = end
        ax.plot(times, ages, color='.10', linewidth=.6, marker='o', markersize=1.25, markeredgewidth=0)
        ax.set(ylim=(0, 80), yticks=[0, 40, 80], ylabel='Age (ms)')
        ax.set_title(f'({letter}) {mode} coherent-state age', loc='left', pad=3)
        ax.grid(axis='y', color='.89', linewidth=.4)
        trace_values[mode] = {'times_ms': [int(r['read_time_ms']) for r in rows], 'states': states,
                              'coherent_ages_ms': [None if math.isnan(a) else a for a in ages]}
    status.set(yticks=[1, 0], yticklabels=['R0', 'R1'], ylim=(-.36, 1.87))
    status.set_title('(a) Scheduled-read status', loc='left', pad=3)
    status.text(.1, 1.58, 'Receiver\ndown', ha='center', va='center', linespacing=.95)
    status.tick_params(axis='y', length=0, pad=5); status.spines[['left', 'bottom']].set_visible(False)
    for ax in (status, ages0, ages1):
        ax.set(xlim=(-.4, .8), xticks=[-.4, -.2, 0, .2, .4, .6, .8])
        ax.axvspan(0, .2, color='.91', linewidth=0, zorder=0)
        ax.axvline(0, color='.6', linewidth=.4); ax.axvline(.2, color='.6', linewidth=.4)
    status.tick_params(labelbottom=False, axis='x', length=0); ages0.tick_params(labelbottom=False)
    ages1.set_xlabel('Time relative to reset (synthetic s)', labelpad=4)
    save(fig, 6, trace_values)
    (output / 'plot_evidence.json').write_text(json.dumps(evidence, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print('PASS: six PNGs, six JPGs and plot_evidence.json written; numerical source files unchanged.')


if __name__ == '__main__':
    main()
