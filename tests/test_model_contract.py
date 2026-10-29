"""Article requirements checked independently of saved percentages."""
from pathlib import Path
import importlib.util
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('simulation',ROOT/'study/simulation/run_simulation.py')
sim=importlib.util.module_from_spec(spec);spec.loader.exec_module(sim)

class DeclaredModelContract(unittest.TestCase):
    def test_equal_values_without_origin_evidence_remain_ambiguous(self):
        self.assertEqual(sim.monitor(0,0),'ambiguous')
        self.assertEqual(sim.monitor(1,1),'ambiguous')

    def test_labels_resolve_equal_values_and_detect_false_same_origin(self):
        self.assertEqual(sim.monitor(0,0,labels=(7,8)),'mixed')
        self.assertEqual(sim.monitor(0,0,labels=(7,7)),'coherent')
        self.assertEqual(sim.monitor(0,1,labels=(7,7)),'out_of_model')

    def test_invalid_and_missing_values_have_distinct_verdicts(self):
        self.assertEqual(sim.monitor(None,0),'unavailable')
        self.assertEqual(sim.monitor(2,0),'out_of_model')

    def test_false_grouping_is_a_demonstrated_limit_not_authentication(self):
        self.assertEqual(sim.monitor(0,0,grouping='same'),'coherent')
        self.assertEqual(sim.monitor(0,0,labels=(1,2),grouping='same'),'out_of_model')

    def test_source_endpoints_are_constant_or_alternating(self):
        constant=sim.source_history(0,17,20)
        alternating=sim.source_history(1,17,20)
        self.assertEqual(len(set(constant)),1)
        self.assertTrue(all(a!=b for a,b in zip(alternating,alternating[1:])))

    def test_zero_delay_batches_do_not_create_artificial_r0_mixing(self):
        c=dict(id='TEST',alpha=.5,channel='none',restart='none',label='contract')
        row,_,_=sim.simulate(c,31,'R0',delay_bound=0,read_phase=0)
        self.assertEqual((row['mixed'],row['unavailable']),(0,0))
        self.assertEqual(row['coherent'],4000)

    def test_total_loss_never_supplies_a_false_coherent_state(self):
        c=dict(id='TEST',alpha=.5,channel='all',restart='none',label='contract')
        row,_,_=sim.simulate(c,31,'R1',read_phase=0)
        self.assertEqual(row['unavailable'],4000)
        self.assertEqual(row['fresh_coherent'],0)
        self.assertIsNone(row['coherent_age_p95_ms'])

    def test_repeated_values_can_hide_every_actual_mixed_read(self):
        c=dict(id='TEST',alpha=0,channel='none',restart='none',label='constant')
        row,_,_=sim.simulate(c,31,'R0')
        self.assertGreater(row['mixed'],0)
        self.assertEqual(row['mixed'],row['hidden_mixed'])
        self.assertEqual(row['detected_mixed'],0)

if __name__=='__main__':unittest.main()
