"""Reject optimized validators before opening artifacts or emitting reports."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ResumeOptimizationTests(unittest.TestCase):
    def test_cli_and_import_fail_closed(self):
        code = ('import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); '
                'from fex_resume_binary import validate; print(validate(Path(sys.argv[2])))')
        for flags, optimize in ((['-O'], None), (['-OO'], None), ([], '1')):
            with self.subTest(flags=flags, optimize=optimize), tempfile.TemporaryDirectory() as tmp:
                missing = Path(tmp) / 'missing.elf'
                output = Path(tmp) / 'report.json'
                env = os.environ.copy()
                env.pop('PYTHONOPTIMIZE', None)
                if optimize:
                    env['PYTHONOPTIMIZE'] = optimize
                for args in ([ROOT / 'tests/fex_resume_binary.py', missing, '--output', output],
                             ['-c', code, ROOT / 'tests', missing]):
                    result = subprocess.run([sys.executable, '-B', *flags, *map(str, args)],
                                            env=env, capture_output=True, text=True, timeout=60)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('requires assertions; disable -O/-OO and PYTHONOPTIMIZE', result.stderr)
                    self.assertEqual(result.stdout, '')
                    self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
