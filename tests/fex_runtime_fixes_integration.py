"""Exercise opt-in backports through the actual FEX3 patch pipeline."""
from pathlib import Path
import json
import os
import sys
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from fex_wine_patches import apply


class RuntimeFixIntegrationTests(unittest.TestCase):
    def test_fex2_rejects_opt_in_before_touching_source(self):
        with self.assertRaisesRegex(ValueError, 'runtime fixes require.*FEX3'):
            apply(None, PROJECT, runtime_fixes=True)

    @unittest.skipUnless(os.environ.get('PES_FEX_TEST_WORK'),
                         'Set PES_FEX_TEST_WORK to an isolated prepared wine3 tree')
    def test_real_pipeline_is_narrow_idempotent_and_reversible(self):
        work = Path(os.environ['PES_FEX_TEST_WORK'])
        before = apply(work, PROJECT, integration=True)
        try:
            after = apply(work, PROJECT, integration=True, runtime_fixes=True)
            self.assertEqual(before['pe-source'], after['pe-source'])
            changed = sorted(name for name in before['native-source'].keys() |
                             after['native-source'].keys()
                             if before['native-source'].get(name) != after['native-source'].get(name))
            self.assertEqual(changed, ['dlls/ntdll/unix/horizon.c',
                                       'wine-nx-probe/source/runtime.c'])
            runtime = (work / 'native-source/wine-nx-probe/source/runtime.c').read_text()
            horizon = (work / 'native-source/dlls/ntdll/unix/horizon.c').read_text()
            self.assertIn('pes13-fex3-runtime-fixes', runtime)
            self.assertIn('DXVK_SHADER_CACHE_PATH=C:\\\\dxvk-cache\\0', runtime)
            self.assertEqual(runtime.count('    fex_cache_prepare_directory();'), 1)
            self.assertIn('horizon_server_update_timers_locked();', horizon)
            self.assertIn('if (R_SUCCEEDED(svcSetThreadCoreMask', horizon)
            self.assertEqual(after, apply(work, PROJECT, integration=True, runtime_fixes=True))
        finally:
            restored = apply(work, PROJECT, integration=True)
        self.assertEqual(before, restored)


if __name__ == '__main__':
    unittest.main()
