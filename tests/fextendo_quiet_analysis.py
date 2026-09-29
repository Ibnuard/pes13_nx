"""Guard quiet-capture analysis against mixed clocks and incomplete evidence."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('quiet', Path(__file__).resolve().parents[1] / 'tools/analyze-fextendo-quiet.py')
QUIET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUIET)
ORIGIN = '[FEXTENDO-TIME] origin_tick=192000000 enabled=0 units=19200000_ticks_per_second; T+ starts at Play\n'


def jit(ms, calls, us):
    return f'[FEX3-JIT] phase=compile_code uptime_ms={ms} calls={calls} total_us={us} peak_us=9999 over20ms=0 over50ms=0\n'


class QuietAnalysis(unittest.TestCase):
    def analyze(self, body, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'device.log'
            path.write_text(body)
            return QUIET.analyze(path, **kwargs)

    def test_separate_clocks_and_full_counter_deltas(self):
        body = ORIGIN + jit(99000, 100, 1000) + jit(100100, 120, 1500) + jit(150200, 150, 2500)
        body += '[PROGRESS] 999s reads=8 read_ms=9 sd_reads=8 sd_ms=9 frames=42\n'
        body += '[FEX3-GAP] tick=2496000000 end_gap_us=65000 thread_cpu_us=900\n'
        result = self.analyze(body)
        gap = result['recorded_gaps_overlapping_play_range'][0]
        self.assertEqual(gap['play_end_s'], 120)
        self.assertEqual(result['batches_containing_selected_gaps'][0]['runtime_elapsed_s'], 999)
        self.assertEqual(result['jit_comparisons'][0]['actual_jit_uptime_ms'], [100100, 150200])
        self.assertEqual(result['jit_comparisons'][0]['delta']['total_us'], 1000)
        self.assertEqual(result['jit_comparisons'][0]['delta']['calls'], 30)
        self.assertFalse(result['jit_comparisons'][1]['available'])
        self.assertEqual(result['capture_gap_reports_without_drop_counter'], 1)

    def test_observer_drops_not_hidden_by_empty_selection(self):
        body = ORIGIN + '[PROGRESS] 1s frames=0\n[FEX3-GAP] recorded=0 dropped=12\n'
        result = self.analyze(body)
        self.assertEqual(result['recorded_gaps_overlapping_play_range'], [])
        self.assertEqual(result['capture_gap_dropped'], 12)
        self.assertIsNone(result['last_compile_counter'])

    def test_reject_multiple_sessions_and_unknown_frequency(self):
        for body in ('', ORIGIN + ORIGIN, ORIGIN.replace('19200000_ticks', '10000000_ticks')):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.analyze(body)

    def test_reject_resets_and_reordered_jit(self):
        for last in (jit(11000, 5, 200), jit(11000, 11, 10), jit(9000, 11, 200)):
            with self.subTest(last=last), self.assertRaises(ValueError):
                self.analyze(ORIGIN + jit(10000, 10, 100) + last)

    def test_reject_corrupt_histogram(self):
        with self.assertRaises(ValueError):
            self.analyze(ORIGIN + '[PROGRESS] 1s frames=0\n' +
                         '[FEX3-PACE] entry_gap n=2 avg_us=1 bins=1,0,0,0,0,0,0,0,0\n')

    def test_reject_invalid_ranges(self):
        for bounds in ((float('nan'), 10), (0, float('inf')), (-1, 2), (5, 5)):
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                self.analyze(ORIGIN, play_range=bounds)


if __name__ == '__main__':
    unittest.main()
