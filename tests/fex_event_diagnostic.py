"""Regression for read-only, one-second FEX3 video-correlatable diagnostics."""
from pathlib import Path
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from fex_wine_patches import apply


class EventDiagnosticTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('PES_FEX_TEST_WORK'),
                         'Set PES_FEX_TEST_WORK to the prepared wine3 build tree')
    def test_control_adds_only_bounded_read_only_event_probe(self):
        work = Path(os.environ['PES_FEX_TEST_WORK'])
        before = apply(work, ROOT, integration=True)
        try:
            after = apply(work, ROOT, integration=True, diagnostic=True)
            self.assertEqual(before['pe-source'], after['pe-source'])
            delta = sorted(k for k in before['native-source'].keys() |
                           after['native-source'].keys()
                           if before['native-source'].get(k) != after['native-source'].get(k))
            self.assertEqual(delta, ['wine-nx-probe/source/runtime.c'])
            runtime = (work / 'native-source/wine-nx-probe/source/runtime.c').read_text()
            self.assertIn('pes13-fex3-event-diagnostic', runtime)
            self.assertIn('if (ticks % 5 == 0) fex_event_report(ticks / 5);', runtime)
            self.assertIn('fex_game_snapshot(wine_nx_fex_timing_read', runtime)
            observer = (ROOT / 'src/runtime/fex_event_runtime.h').read_text()
            self.assertIn('snapshot=%d presents=%u present_delta=%u', observer)
            self.assertIn('state=%u mode=%u scale_bits=%08x presents=%u present_delta=%u', observer)
            self.assertNotIn('if (status != previous_status)', observer)
            self.assertIn('fex_log_metrics_batch = 1;', runtime)
            self.assertEqual(after, apply(work, ROOT, integration=True, diagnostic=True))
        finally:
            restored = apply(work, ROOT, integration=True)
        self.assertEqual(before, restored)

    def test_diagnostic_cannot_mix_with_runtime_fixes_or_fex2(self):
        with self.assertRaisesRegex(ValueError, 'diagnostic requires.*FEX3'):
            apply(None, ROOT, diagnostic=True)
        with self.assertRaisesRegex(ValueError, 'diagnostic cannot combine'):
            apply(None, ROOT, integration=True, diagnostic=True, runtime_fixes=True)


if __name__ == '__main__':
    unittest.main()
