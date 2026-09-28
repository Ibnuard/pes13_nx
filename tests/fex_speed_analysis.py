"""Host-log attribution regression tests; fixtures do not simulate a PES match."""
from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fex_speed', ROOT / 'tools/analyze-fex-speed.py')
assert spec is not None and spec.loader is not None
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class SpeedAnalysisTests(unittest.TestCase):
    def test_preserves_frame_gap_bins_and_source_line(self):
        # Same mean FPS can hide long gaps; preserve bins rather than just average.
        data = (b'[FEX3-PACE] elapsed_ms=10000 window_ms=10000 ok=300 errors=0\n'
                b'[FEX3-PACE] entry_gap n=300 avg_us=33333 peak_since_launch_us=900000 '
                b'bins=0,0,0,280,0,20,0,0,0\n')
        window = analysis.analyze(data)['windows'][0]
        self.assertEqual(window.get('source_line'), 1)
        stage = window['stages']['entry_gap']
        self.assertEqual(stage.get('bins'), [0, 0, 0, 280, 0, 20, 0, 0, 0])
        self.assertEqual(stage.get('source_line'), 2)
        self.assertEqual(stage['peak_since_launch_us'], 900000)

    def test_reports_actual_swapchain_and_client_dimensions(self):
        data = (b'[NXVK] present 1: result 1000001003, swapchain 1270x691, '
                b'hwnd 0x20038 client (0,0)-(1280,720), style 0x94000000, foreground 0x20038\n'
                b'[NXVK] present 2: result 0, swapchain 1280x720, '
                b'hwnd 0x20038 client (0,0)-(1280,720), style 0x94000000, foreground 0x20038\n')
        observations = analysis.analyze(data).get('present_observations', [])
        self.assertEqual(len(observations), 2)
        self.assertEqual(observations[0]['result'], 1000001003)
        self.assertEqual(observations[0]['swapchain'], [1270, 691])
        self.assertEqual(observations[1]['swapchain'], [1280, 720])
        self.assertEqual(observations[1]['client_rect'], [0, 0, 1280, 720])
        self.assertEqual(observations[1]['source_line'], 2)
        self.assertNotIn('aspect_correct', observations[1])

    def test_old_thread_report_keeps_its_original_progress_stamp(self):
        data = (b'[PROGRESS] 116s frames=4000\n'
                b'[THREADS] 62 threads use 2.08 cores: 160w@1 80.5%\n'
                b'[FEX3-PACE] elapsed_ms=110000 window_ms=10000 ok=450 errors=0\n'
                b'[PROGRESS] 236s frames=9000\n'
                b'[FEX3-PACE] elapsed_ms=230000 window_ms=10000 ok=420 errors=0\n')
        window = analysis.analyze(data)['windows'][-1]
        self.assertEqual(window.get('threads_source_line'), 2)
        self.assertEqual(window.get('threads_progress_seconds'), 116)
        self.assertEqual(window['progress_seconds'], 236)


if __name__ == '__main__':
    unittest.main()
