"""Host tests for regression evidence parsing, not Switch execution."""
from pathlib import Path
import importlib.util
import tempfile
import unittest

project = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("perf29_result", project / "tools/analyze-perf29-result.py")
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class ResultsTest(unittest.TestCase):
    def parse_text(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pes13-nx.log"
            path.write_text(text, encoding="utf-8")
            return analysis.parse(path)

    def test_initial_marker_and_separate_progress_clock(self):
        run = self.parse_text(
            "[PERF29] worker_blocks=0 selected=0\n"
            "[BUILD] pes13-nx-0.2.0-perf29-worker-blocks\n"
            "[PERF24] CPU sampler=off; math flags\n"
            "[PERF8] uptime_s=120 interval_ms=10009 presents=20 fps=2.00\n"
            "[PERF29] worker_blocks=1 selected=4885 completed=4885\n"
            "[PROGRESS] 60s frames=2916 audio_under=608\n")
        self.assertEqual(run["build"], ["pes13-nx-0.2.0-perf29-worker-blocks"])
        self.assertEqual(run["sampler"], ["off"])
        self.assertEqual(run["worker_blocks"]["worker_blocks"], 1)
        self.assertEqual(run["progress"][0]["progress_elapsed_s"], 60)
        self.assertEqual(run["progress"][0]["after_perf8_uptime_s"], 120)
        self.assertEqual(run["progress"][0]["audio_under"], 608)
        self.assertNotIn("fps", run["rows"][0])

    def test_weighted_spans_histograms_and_launch_maximum(self):
        run = self.parse_text(
            "[PERF8] uptime_s=110 interval_ms=10000 presents=26\n"
            "[FRAME24] gap_quiet n=2 avg_us=700000 max_since_launch_us=1845456 bins=0,0,0,0,0,0,0,1,1,0\n"
            "[PIPE27] submit_host n=2 total_us=200000 avg_us=100000 gt16ms=1 max_since_launch_us=641053\n"
            "[THREADS] 70 threads use 1.92 cores: 176w@3 70.4% 124w@1 59.6%\n"
            "[PERF8] uptime_s=120 interval_ms=20000 presents=20\n"
            "[FRAME24] gap_quiet n=1 avg_us=20000 max_since_launch_us=1845456 bins=0,1,0,0,0,0,0,0,0,0\n"
            "[PIPE27] submit_host n=1 total_us=1000 avg_us=1000 gt16ms=0 max_since_launch_us=641053\n")
        summary = analysis.summarize(run["rows"], 110, 120)
        self.assertAlmostEqual(summary["presents_per_s"], 46 / 30)
        self.assertEqual(summary["pipe"]["submit_host"]["avg_us"], 67000)
        frame = summary["frames"]["gap_quiet"]
        self.assertEqual(frame["over_500ms"], 2)
        self.assertEqual(frame["over_1000ms"], 1)
        self.assertEqual(frame["max_since_launch_us"], 1845456)
        self.assertAlmostEqual(frame["avg_us"], 1420000 / 3)
        self.assertEqual(run["rows"][0]["threads"]["176w"], 70.4)
        self.assertIsNone(analysis.summarize(run["rows"], 200, 300)["presents_per_s"])

    def test_invalid_histogram_rejected(self):
        with self.assertRaises(ValueError):
            self.parse_text("[PERF8] uptime_s=10 interval_ms=10000 presents=1\n"
                            "[FRAME24] gap_quiet n=2 avg_us=1 max_since_launch_us=1 bins=1,0,0,0,0,0,0,0,0,0\n")

    def test_rotated_history_identified_by_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "new"
            prior = Path(directory) / "old"
            source.mkdir()
            prior.mkdir()
            old = b"[BUILD] pes13-nx-0.2.0-perf28-diagnostics\n"
            (prior / "pes13-nx.log").write_bytes(old)
            (source / "pes13-nx.previous-1.log").write_bytes(old)
            (source / "pes13-nx.log").write_bytes(b"[BUILD] pes13-nx-0.2.0-perf29-worker-blocks\n")
            runs = analysis.analyze(source, prior)["runs"]
            self.assertEqual(runs[0]["identical_prior_files"], [])
            self.assertEqual(runs[1]["identical_prior_files"], ["pes13-nx.log"])

    def test_samples_and_lifecycle_keep_interval_context(self):
        run = self.parse_text(
            "[PROF] sampler not started: permissions unavailable\n"
            "[THREAD] NtCreateThreadEx tid=188 start=0x4da0e3\n"
            "[PERF8] uptime_s=170 interval_ms=10000 presents=166\n"
            "[THREADS] 70 threads use 2.92 cores: 188w@0 95.7% 4w@1 65.4%\n"
            "[SAMPLE24] rounds=99 target_suspend_wall_us=3500 epoch=4; samples include blocked time\n"
            "[PROF] 4w samples=99 missed=1 x86=10.1% native=89.9%\n"
            "[PROF] 4w native: +0x1234 89.9%\n"
            "[PROF] 4w callers: +0x1234<+0x4567 89.9%\n"
            "[LIFECYCLE] exit tid=188 code=00000000\n"
            "[THREAD] NtCreateThreadEx tid=200 start=0x4da0e3\n"
            "[PERF8] uptime_s=180 interval_ms=10000 presents=30\n")
        row = run["rows"][0]
        self.assertEqual(row["cores"], 2.92)
        self.assertEqual(row["sampling"]["rounds"], 99)
        self.assertEqual(row["profiles"]["4w"]["samples"], 99)
        self.assertEqual(row["profiles"]["4w"]["sites"]["callers"], {"+0x1234<+0x4567": 89.9})
        self.assertEqual(run["rows"][1]["profiles"], {})
        self.assertIsNone(run["lifecycle"][0]["after_perf8_uptime_s"])
        self.assertEqual(run["lifecycle"][2]["after_perf8_uptime_s"], 170)
        self.assertEqual(len(run["sampler_status"]), 1)

    def test_profiles_before_first_interval_remain_status(self):
        run = self.parse_text("[PROF] 4w samples=2 missed=0 native=100.0%\n")
        self.assertEqual(run["rows"], [])
        self.assertEqual(len(run["sampler_status"]), 1)


if __name__ == "__main__":
    unittest.main()
