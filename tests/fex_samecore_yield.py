"""Check existing opt-in yield experiment's exact source delta, not PES speed."""
from pathlib import Path
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from fex_wine_patches import apply


class SamecoreYieldTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('PES_FEX_TEST_WORK'),
                         'Set PES_FEX_TEST_WORK to the prepared wine3 build tree')
    def test_diagnostic_changes_only_yield_argument_and_startup_marker(self):
        work = Path(os.environ['PES_FEX_TEST_WORK'])
        before = apply(work, ROOT, integration=True, diagnostic=True)
        sync = 'dlls/ntdll/unix/sync.c'
        runtime = 'wine-nx-probe/source/runtime.c'
        original_sync = (work / 'native-source' / sync).read_text()
        original_runtime = (work / 'native-source' / runtime).read_text()
        try:
            after = apply(work, ROOT, integration=True, diagnostic=True, samecore_yield=True)
            self.assertEqual(before['pe-source'], after['pe-source'])
            delta = sorted(k for k in before['native-source'].keys() | after['native-source'].keys()
                           if before['native-source'].get(k) != after['native-source'].get(k))
            self.assertEqual(delta, [sync, runtime])
            old = '    svcSleepThread( -1 );  /* YieldType_WithCoreMigration */'
            new = '    svcSleepThread( 0 );  /* YieldType_WithoutCoreMigration: FEX Sleep(0) */'
            self.assertEqual(original_sync.count(old), 1)
            self.assertEqual((work / 'native-source' / sync).read_text(),
                             original_sync.replace(old, new))
            marker = '\n    wine_nx_runtime_trace("[FEX3-YIELD] same-core Sleep(0) experiment");'
            self.assertEqual((work / 'native-source' / runtime).read_text(),
                             original_runtime.replace(
                                 '    wine_nx_runtime_trace("[FEX3] isolated exception context preflight");',
                                 '    wine_nx_runtime_trace("[FEX3] isolated exception context preflight");' + marker))
            self.assertEqual(after, apply(work, ROOT, integration=True,
                                          diagnostic=True, samecore_yield=True))
        finally:
            restored = apply(work, ROOT, integration=True, diagnostic=True)
        self.assertEqual(before, restored)

    def test_experiment_rejects_fex2(self):
        with self.assertRaisesRegex(ValueError, 'same-core yield requires'):
            apply(None, ROOT, samecore_yield=True)


if __name__ == '__main__':
    unittest.main()
