"""Check event boundaries and rejection of plausible but incorrect log rows."""
from pathlib import Path
import importlib.util
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('audit_evidence',ROOT/'audit_evidence.py')
audit=importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


def row(time=5,online=1,x=1,y=1):
    return dict(condition='C01',seed='0',publication='R0',read_time_ms=str(time),online=str(online),x_origin=str(x),y_origin=str(y))


class ExactReadEvidence(unittest.TestCase):
    def test_duplicate_timestamps_cannot_preserve_a_passing_log(self):
        with self.assertRaisesRegex(ValueError,'timeline differs'):
            audit.compare_read_stream(iter([row(),row()]),iter([('C01',0,'R0',5,1,1,1),('C01',0,'R0',10,1,1,1)]))

    def test_false_origin_is_rejected_even_if_state_remains_coherent(self):
        with self.assertRaisesRegex(ValueError,'timeline differs'):
            audit.compare_read_stream(iter([row(x=2,y=2)]),iter([('C01',0,'R0',5,1,1,1)]))

    def test_extra_and_missing_rows_are_rejected(self):
        wanted=[('C01',0,'R0',5,1,1,1)]
        with self.assertRaisesRegex(ValueError,'truncated'):
            audit.compare_read_stream(iter([]),iter(wanted))
        with self.assertRaisesRegex(ValueError,'extra rows'):
            audit.compare_read_stream(iter([row(),row()]),iter(wanted))

    def test_arrival_at_read_time_is_visible_and_last_tied_generation_wins(self):
        cfg={'generation_count_per_run':3,'restart':{'start_ms':10,'duration_ms':10}}
        self.assertEqual(audit.origin_at([(5,1),(5,2)],5,{'restart':'none'},cfg),2)
        self.assertEqual(audit.origin_at([(5,1)],4,{'restart':'none'},cfg),0)

    def test_clear_and_preserve_have_different_installed_origins_after_reset(self):
        cfg={'generation_count_per_run':3,'restart':{'start_ms':10,'duration_ms':10}}
        self.assertEqual(audit.origin_at([(5,1)],10,{'restart':'clear'},cfg),0)
        self.assertEqual(audit.origin_at([(5,1)],20,{'restart':'preserve'},cfg),1)
        self.assertEqual(audit.origin_at([(5,1),(20,2)],20,{'restart':'clear'},cfg),2)


class JournalContract(unittest.TestCase):
    def setUp(self):
        with audit.ZipFile(ROOT/'manuscript/Ibragimov_Aibar_Article_Revised.docx') as archive:
            root = audit.ET.fromstring(archive.read('word/document.xml'))
        self.paragraphs = [''.join(p.itertext()) for p in root.findall('./w:body/w:p', audit.NS)]

    def test_current_author_orcids_have_valid_checksums(self):
        result = audit.audit_journal_text(self.paragraphs)
        self.assertEqual(result['author_identities'], 2)
        self.assertEqual(result['references_in_citation_order'], 20)
        self.assertFalse(audit.orcid_valid('0000-0002-3382-4684'))
        self.assertFalse(audit.orcid_valid('0000-0002-3382-468'))

    def test_shortened_abstract_is_rejected(self):
        changed = ['Abstract: Too short.' if p.startswith('Abstract: ') else p for p in self.paragraphs]
        with self.assertRaisesRegex(ValueError, '250–280 words'):
            audit.audit_journal_text(changed)

    def test_out_of_order_citations_are_rejected(self):
        changed = [p.replace('[1, 2]', '[2, 1]') for p in self.paragraphs]
        with self.assertRaisesRegex(ValueError, 'First citations'):
            audit.audit_journal_text(changed)


class ManuscriptTableIdentity(unittest.TestCase):
    def test_literature_table_does_not_shift_numerical_evidence(self):
        expected = ['Condition', 'Mode', 'Mixed (%)']
        numerical = [expected, ['C05', 'R0', '62.14']]
        literature = [['Approach', 'Guarantee'], ['Snapshots', 'Atomic access']]
        self.assertIs(audit.table_by_header([literature, numerical], expected), numerical)
        self.assertIs(audit.table_by_header([numerical, literature], expected), numerical)

    def test_missing_or_duplicated_numerical_table_cannot_pass(self):
        expected = ['Condition', 'Mode']
        numerical = [expected, ['C05', 'R0']]
        for tables in ([], [numerical, numerical]):
            with self.assertRaisesRegex(ValueError, 'Missing or duplicate manuscript table'):
                audit.table_by_header(tables, expected)

    def test_all_declared_rows_are_required_but_row_order_is_not_evidence(self):
        table = [['Condition', 'Mode', 'Mixed (%)'], ['C05', 'R1', '0.00'], ['C05', 'R0', '62.14']]
        audit.require_table_rows(table, 2, {('C05', 'R0'), ('C05', 'R1')})

    def test_deleted_duplicate_and_truncated_rows_cannot_reduce_the_audit_scope(self):
        header = ['Condition', 'Mode', 'Mixed (%)']
        first, second = ['C05', 'R0', '62.14'], ['C05', 'R1', '0.00']
        for rows in ([first], [first, second, second], [first, second[:-1]]):
            with self.assertRaisesRegex(ValueError, 'Missing, duplicate or truncated manuscript table row'):
                audit.require_table_rows([header, *rows], 2, {('C05', 'R0'), ('C05', 'R1')})

if __name__=='__main__': unittest.main()
