"""Check scientific boundary cases and malformed inputs without graphics packages."""
import copy
import unittest
from pathlib import Path

from plot_figures import coverage_parts, lag_probability, read_csv, select_trace

SOURCE = Path(__file__).resolve().parents[1] / 'study/simulation'


class PlotInputsTests(unittest.TestCase):
    def test_constant_independent_and_alternating_markov_sources(self):
        for lag in range(7):
            self.assertEqual(lag_probability(0, lag), 0)
            self.assertEqual(lag_probability(1, lag), lag % 2)
            self.assertEqual(lag_probability(.5, lag), .5 if lag else 0)

    def test_invalid_lag_and_probability_are_rejected(self):
        for alpha, lag in ((-.1, 1), (1.1, 1), (.5, -.1), (.5, 1.5)):
            with self.assertRaises(ValueError):
                lag_probability(alpha, lag)

    def test_coverage_cannot_silently_use_duplicate_summary(self):
        rows = read_csv(SOURCE / 'aggregate_metrics.csv')
        picked = next(r for r in rows if r['condition'] == 'C05' and r['publication'] == 'R0'
                      and r['metric'] == 'V_coverage')
        with self.assertRaises(ValueError):
            coverage_parts(rows + [picked], 'C05')

    def test_coverage_is_partition_of_scheduled_reads(self):
        rows = read_csv(SOURCE / 'aggregate_metrics.csv')
        hidden, detected, coherent = coverage_parts(rows, 'C05')
        self.assertAlmostEqual(hidden + detected, 62.144375)
        self.assertAlmostEqual(coherent, 37.855625)
        self.assertAlmostEqual(hidden + detected + coherent, 100)

    def test_trace_rejects_duplicate_or_truncated_schedule(self):
        rows = select_trace(read_csv(SOURCE / 'sample_traces.csv'), 'R0')
        for changed in (rows[:-1], rows + [rows[-1]]):
            with self.assertRaises(ValueError):
                select_trace(changed, 'R0')

    def test_missing_age_is_a_gap_and_never_a_zero(self):
        rows = select_trace(read_csv(SOURCE / 'sample_traces.csv'), 'R0')
        changed = copy.deepcopy(rows)
        missing = next(r for r in changed if r['reference'] != 'coherent')
        missing['coherent_age_ms'] = '0'
        with self.assertRaises(ValueError):
            select_trace(changed, 'R0')

    def test_clipped_trace_age_is_rejected(self):
        rows = select_trace(read_csv(SOURCE / 'sample_traces.csv'), 'R1')
        next(r for r in rows if r['reference'] == 'coherent')['coherent_age_ms'] = '81'
        with self.assertRaises(ValueError):
            select_trace(rows, 'R1')


if __name__ == '__main__':
    unittest.main()
