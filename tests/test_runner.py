"""Regression checks for failure reporting and reference-data comparisons."""
from pathlib import Path
import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reproduce', ROOT / 'reproduce.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class VerificationFailures(unittest.TestCase):
    def test_percentage_rounding_at_decimal_halfway_is_consistent(self):
        self.assertEqual(runner.display_mean_percent([Fraction(19099,20000)]), '95.50')
        self.assertEqual(runner.display_mean_percent([Fraction(18897,20000)]), '94.49')
        self.assertEqual(runner.display_mean_percent([Fraction(6179,20000)]), '30.90')
    def test_damaged_distributed_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data.csv').write_bytes(b'value\n1\n')
            record = {'path': 'data.csv', 'sha256': hashlib.sha256(b'value\n0\n').hexdigest()}
            (root / 'MANIFEST.json').write_text(json.dumps([record]))
            with self.assertRaisesRegex(ValueError, 'Checksum mismatch: data.csv'):
                runner.verify_manifest(root)

    def test_manifest_cannot_read_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'MANIFEST.json').write_text(json.dumps([{'path':'../outside.txt','sha256':'0'*64}]))
            with self.assertRaisesRegex(ValueError, 'escapes repository'):
                runner.verify_manifest(root)

    def test_missing_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'MANIFEST.json').write_text(json.dumps([{'path':'missing.csv','sha256':'0'*64}]))
            with self.assertRaisesRegex(ValueError, 'Missing file: missing.csv'):
                runner.verify_manifest(root)

    def test_gzip_metadata_does_not_count_as_changed_readings(self):
        with tempfile.TemporaryDirectory() as directory:
            left, right = Path(directory)/'left.gz', Path(directory)/'right.gz'
            left.write_bytes(gzip.compress(b'time,origin\n5,1\n',mtime=0))
            right.write_bytes(gzip.compress(b'time,origin\n5,1\n',mtime=100))
            self.assertNotEqual(left.read_bytes(),right.read_bytes())
            self.assertTrue(runner.same_content(left,right))
            right.write_bytes(gzip.compress(b'time,origin\n5,2\n',mtime=100))
            self.assertFalse(runner.same_content(left,right))

    def test_failed_program_is_visible_in_stage_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'broken.py').write_text("raise RuntimeError('diagnostic marker')\n")
            with self.assertRaisesRegex(ValueError,'Synthetic check failed; see'):
                runner.execute('broken.py',root,root,'Synthetic check')
            self.assertIn('diagnostic marker',(root/'broken.py.log').read_text())

    def test_no_arguments_cannot_report_a_success(self):
        process=subprocess.run([sys.executable,str(ROOT/'reproduce.py')],capture_output=True,text=True)
        self.assertEqual(process.returncode,2)
        self.assertIn('required',process.stderr)

    def test_failure_report_does_not_claim_successful_read_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            runner.write_reports(root,{'status':'FAIL','mode':'verify-only','stages':[{'name':'File integrity','status':'FAIL'}],'error':'Missing evidence'})
            report=(root/'RESULTS.md').read_text(encoding='utf-8')
            self.assertIn('Status: FAIL',report)
            self.assertIn('Missing evidence',report)
            self.assertNotIn('3,840,000',report)
            self.assertTrue((root/'RESULTS_RU.md').is_file())


if __name__=='__main__':
    unittest.main()
