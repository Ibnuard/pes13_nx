"""Protect event attribution from missing clocks, buffered logs and invalid CPU samples."""
import argparse
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fextendo_analysis', ROOT/'tools/analyze-fextendo-run.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ORIGIN = 9450000000000


def gap(ms, handle=4, duration=100000, valid=1):
    return (f'[FEX3-GAP] tick={ORIGIN+int(ms*19200)} handle={handle} end_gap_us={duration} '
            f'cpu_valid={valid} thread_cpu_us=30000')


def query(ms, handle=4, valid=1):
    begin = ORIGIN + int(ms*19200)
    return (f'[FEX3-MEMQUERY] begin_tick={begin} end_tick={begin+576000} handle={handle} '
            f'wall_us=30000 cpu_valid={valid} thread_cpu_us=29000')


class Analysis(unittest.TestCase):
    def analyze(self, lines, at=92000):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'run.log'
            path.write_text('\n'.join(lines))
            return module.analyze(path, at, 1000)

    def header(self, enabled=1):
        return ['[BUILD] pes13-fextendo-v2-budget', '[FEX3-MEMBUDGET] client_extension=0',
                f'[FEXTENDO-TIME] origin_tick={ORIGIN} enabled={enabled}',
                '[FEX3-MEMQUERY] v1 enabled=1', '[FEXTENDO-TIME] overlay ready layer=99']

    def test_buffered_samples_use_ticks_and_same_handle(self):
        r = self.analyze(self.header()+[gap(130000), gap(92000), query(91960), query(91960, handle=8)])
        self.assertTrue(r['is_v2'])
        self.assertEqual(r['budget_client_extension'], 0)
        self.assertEqual(len(r['first_120_seconds']['gaps']), 1)
        row = r['selected_event']['gaps'][0]
        self.assertEqual(row['end_elapsed_ms'], 92000)
        self.assertEqual(len(row['query_lines']), 1)
        self.assertAlmostEqual(row['query_to_gap_cpu_ratio'], 29/30)

    def test_legacy_has_no_invented_play_clock(self):
        r = self.analyze(['[BUILD] pes13-fextendo-mem-audit', '[FEX3-EVENT] elapsed_s=90', gap(92000)])
        self.assertFalse(r['is_v2'])
        self.assertFalse(r['selected_event']['available'])
        self.assertIsNone(r['play_origin_tick'])
        self.assertIsNone(r['summary']['query_calls_in_flushed_batches'])

    def test_overlay_off_still_has_play_anchor(self):
        r = self.analyze(self.header(enabled=0)[:-1]+[gap(92000)])
        self.assertEqual(r['timestamp_requested'], 0)
        self.assertEqual(r['overlay'], 'not_reported')
        self.assertTrue(r['selected_event']['available'])

    def test_multiple_origins_and_wrong_snapshots_disable_mapping(self):
        r = self.analyze(self.header()+self.header()+[gap(92000)])
        self.assertFalse(r['selected_event']['available'])
        r = self.analyze(self.header()+[f'[FEXTENDO-TIME] elapsed_ms=50 tick={ORIGIN+1920000}', gap(92000)])
        self.assertFalse(r['selected_event']['available'])

    def test_straddling_gap_is_included(self):
        r = self.analyze(self.header()+[gap(92000, duration=2000000)], at=90100)
        self.assertEqual(len(r['selected_event']['gaps']), 1)

    def test_invalid_cpu_is_unknown_not_zero(self):
        for samples in ([gap(92000), query(91960, valid=0)], [gap(92000, valid=0), query(91960)]):
            r = self.analyze(self.header()+samples)
            self.assertEqual(r['summary']['matched_gaps'], 1)
            self.assertIsNone(r['summary']['median_matched_query_to_gap_cpu_ratio'])

    def test_truncated_and_duplicate_samples(self):
        r = self.analyze(self.header()+[gap(92000), query(91960), query(91960), '[FEX3-GAP] tick=19',
                                      '[FEX3-MEMQUERY] calls=5 dropped=2', '[FEX3-GAP] recorded=1 dropped=3'])
        self.assertEqual(r['summary']['recorded_slow_queries'], 1)
        self.assertEqual(len(r['duplicate_sample_lines']), 1)
        self.assertEqual(len(r['malformed_lines']), 1)
        self.assertEqual(r['summary']['reported_dropped_queries'], 2)
        self.assertEqual(r['summary']['reported_dropped_gaps'], 3)
        self.assertEqual(r['summary']['query_calls_in_flushed_batches'], 5)

    def test_same_capture_never_reports_improvement(self):
        r = self.analyze(self.header()+[gap(92000)])
        self.assertEqual(module.compare(r, r)['verdict'], 'identical_capture')

    def test_mixed_builds_disable_event_attribution(self):
        r = self.analyze(self.header()+['[BUILD] pes13-fextendo-mem-audit', gap(92000)])
        self.assertFalse(r['is_v2'])
        self.assertFalse(r['selected_event']['available'])

    def test_parse_video_times(self):
        self.assertEqual(module.parse_time('T+ 00:01:32.4'), 92400)
        self.assertEqual(module.parse_time('01:32.4'), 92400)
        self.assertEqual(module.parse_time('92.4'), 92400)
        for bad in ('-1', 'nan', 'inf', '1:60', '1:01:70', '1:2:3:4', '1.1:02'):
            with self.assertRaises(argparse.ArgumentTypeError):
                module.parse_time(bad)


if __name__ == '__main__':
    unittest.main()
