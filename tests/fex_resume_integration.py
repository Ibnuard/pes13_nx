"""Opt-in wake isolation wiring; source delta checks require prepared wine3."""
from pathlib import Path
import os
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from fex_wine_patches import apply


class ResumeIntegrationTests(unittest.TestCase):
    def test_resume_gate_requires_fex3_without_runtime_fixes(self):
        with self.assertRaisesRegex(ValueError, 'resume gate requires.*FEX3'):
            apply(None, ROOT, resume_gate=True)
        with self.assertRaisesRegex(ValueError, 'resume gate cannot combine'):
            apply(None, ROOT, integration=True, resume_gate=True, runtime_fixes=True)

    def test_cli_rejects_invalid_combinations_before_build(self):
        for args, message in [(['--resume-gate'], '--resume-gate requires --integration'),
                              (['--integration', '--resume-gate', '--runtime-fixes'],
                               '--resume-gate excludes --runtime-fixes')]:
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/build-fex-runtime.py'),
                                         *args], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)

    @unittest.skipUnless(os.environ.get('PES_FEX_TEST_WORK'), 'Prepared wine3 source required')
    def test_native_only_delta_and_repeatability(self):
        work = Path(os.environ['PES_FEX_TEST_WORK'])
        options = dict(integration=True, diagnostic=True, samecore_yield=True)
        before = apply(work, ROOT, **options)
        try:
            after = apply(work, ROOT, resume_gate=True, **options)
            self.assertEqual(before['pe-source'], after['pe-source'])
            delta = sorted(key for key in before['native-source'].keys() | after['native-source'].keys()
                           if before['native-source'].get(key) != after['native-source'].get(key))
            self.assertEqual(delta, ['dlls/ntdll/unix/horizon.c', 'wine-nx-probe/source/runtime.c'])
            self.assertEqual(after, apply(work, ROOT, resume_gate=True, **options))
        finally:
            self.assertEqual(before, apply(work, ROOT, **options))


if __name__ == '__main__':
    unittest.main()
