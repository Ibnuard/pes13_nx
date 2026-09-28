"""Reject optimized Python before same-core validation can report false success."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tests/fex_samecore_binary.py'
CONTROL = ROOT / 'local/fex3/event-diagnostic/reference/pes13-fex.elf'
OPTIMIZATIONS = (('-O', ['-O'], None), ('PYTHONOPTIMIZE=1', [], '1'))
GUARD_MESSAGE = 'requires Python assertions; disable -O/-OO and PYTHONOPTIMIZE'


class SamecoreOptimizationTests(unittest.TestCase):
    def run_python(self, args, flags, optimize, cwd):
        env = os.environ.copy()
        env.pop('PYTHONOPTIMIZE', None)
        if optimize is not None:
            env['PYTHONOPTIMIZE'] = optimize
        return subprocess.run([sys.executable, '-B', *flags, *map(str, args)],
                              cwd=cwd, env=env, capture_output=True, text=True,
                              timeout=60)

    def test_cli_rejects_optimized_python_without_output_report(self):
        self.assertTrue(CONTROL.is_file(), f'Missing control ELF: {CONTROL}')
        for label, flags, optimize in OPTIMIZATIONS:
            with self.subTest(mode=label), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / 'validation.json'
                result = self.run_python(
                    [SCRIPT, CONTROL, '--expected-yield=0', '--output', output],
                    flags, optimize, tmp)
                self.assertNotEqual(result.returncode, 0,
                                    f'False success: {result.stdout}; report exists: {output.exists()}')
                self.assertFalse(output.exists(), 'Rejected validation wrote output report')
                self.assertEqual(result.stdout, '')
                self.assertIn(GUARD_MESSAGE, result.stderr)

    def test_imported_validate_rejects_optimized_python_before_loading_elf(self):
        self.assertTrue(CONTROL.is_file(), f'Missing control ELF: {CONTROL}')
        code = ('import sys; from pathlib import Path; '
                'sys.path.insert(0, sys.argv[1]); '
                'from fex_samecore_binary import validate; '
                'print(validate(Path(sys.argv[2]), 0))')
        for label, flags, optimize in OPTIMIZATIONS:
            with tempfile.TemporaryDirectory() as tmp:
                # Missing ELF proves the guard runs before Model construction.
                for elf in (CONTROL, Path(tmp) / 'missing.elf'):
                    with self.subTest(mode=label, elf=elf.name):
                        result = self.run_python(
                            ['-c', code, SCRIPT.parent, elf], flags, optimize, tmp)
                        self.assertNotEqual(result.returncode, 0,
                                            f'False success: {result.stdout}')
                        self.assertEqual(result.stdout, '')
                        self.assertIn(GUARD_MESSAGE, result.stderr)


if __name__ == '__main__':
    unittest.main()
