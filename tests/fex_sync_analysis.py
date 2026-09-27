"""Host-log regression tests; synthetic routing records are not a game replay."""
from pathlib import Path
import importlib.util
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'fex_sync_analysis', ROOT / 'tools/analyze-fex-sync-regression.py')
assert spec is not None and spec.loader is not None
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class SyncAnalysisTests(unittest.TestCase):
    def test_log_parser_import_does_not_require_elf_dependencies(self):
        result = subprocess.run([
            sys.executable, '-S', '-c',
            'import runpy, sys; runpy.run_path(sys.argv[1], run_name="parser_import")',
            str(ROOT / 'tools/analyze-fex-sync-regression.py'),
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def summarize(self, records):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'runtime.log'
            path.write_text('[BUILD] parser-test\n' + records)
            result, _ = analysis.summarize(path)
            return result

    def test_control_router_has_no_filter_percentage(self):
        result = self.summarize(
            '[FEX3-SYNC] targeted=0 notices=0 candidates=0 notified=0 filtered=0 sleeps=0\n')
        totals = result['routing_totals']
        self.assertEqual(totals['candidates'], 0)
        self.assertIsNone(totals['filtered_percent'])

    def test_enabled_router_without_candidates_has_no_filter_percentage(self):
        result = self.summarize(
            '[FEX3-SYNC] targeted=1 notices=4 candidates=0 notified=0 filtered=0 sleeps=0\n')
        self.assertIsNone(result['routing_totals']['filtered_percent'])

    def test_nonempty_router_keeps_weighted_percentage(self):
        result = self.summarize(
            '[FEX3-SYNC] targeted=1 notices=1 candidates=4 notified=1 filtered=3 sleeps=2\n'
            '[FEX3-SYNC] targeted=1 notices=2 candidates=6 notified=4 filtered=2 sleeps=3\n')
        self.assertEqual(result['routing_totals'], {
            'notices': 3, 'candidates': 10, 'notified': 5,
            'filtered': 5, 'sleeps': 5, 'filtered_percent': 50.0,
        })

    def test_log_without_router_records_has_no_routing_totals(self):
        self.assertEqual(self.summarize('')['routing_totals'], {})

    def test_inconsistent_router_totals_remain_rejected(self):
        with self.assertRaises(AssertionError):
            self.summarize(
                '[FEX3-SYNC] targeted=1 notices=1 candidates=4 notified=1 filtered=2 sleeps=2\n')


if __name__ == '__main__':
    unittest.main()
