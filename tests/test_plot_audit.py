"""The independent plot checker must reject changed values even with valid images."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from audit_plots import audit

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / 'manuscript/figures'


class PlotAuditTests(unittest.TestCase):
    def test_frozen_plot_values_agree_with_the_evidence(self):
        self.assertEqual(audit(FIGURES, ROOT)['trace_reads'], 480)

    def check_changed_values_fail(self, change):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for source in FIGURES.glob('figure-*.png'):
                shutil.copyfile(source, target / source.name)
            evidence = json.loads((FIGURES / 'plot_evidence.json').read_text(encoding='utf-8'))
            change(evidence['figures'])
            (target / 'plot_evidence.json').write_text(json.dumps(evidence), encoding='utf-8')
            with self.assertRaises(ValueError):
                audit(target, ROOT)

    def test_changed_analytical_point_is_rejected(self):
        self.check_changed_values_fail(lambda figures: figures['2']['values']['curves']['2'].__setitem__(100, .51))

    def test_changed_coverage_is_rejected(self):
        self.check_changed_values_fail(lambda figures: figures['3']['values']['hidden_detected_coherent_percent']['C05'].__setitem__(0, 99))

    def test_filling_a_trace_gap_with_zero_is_rejected(self):
        def change(figures):
            ages = figures['6']['values']['R0']['coherent_ages_ms']
            ages[ages.index(None)] = 0
        self.check_changed_values_fail(change)

    def test_missing_panels_and_conditions_are_rejected(self):
        self.check_changed_values_fail(lambda figures: figures['4']['values'].pop('C07'))
        self.check_changed_values_fail(lambda figures: figures['5']['values']['coherent_age_p95_ms'].pop())
        self.check_changed_values_fail(lambda figures: figures['6']['values'].pop('R1'))


if __name__ == '__main__':
    unittest.main()
