"""Required validators must refuse optimized Python before touching artifacts."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ELF = ROOT / 'local/fex3/resume-gate/reference/pes13-fex.elf'
OPTIMIZATIONS = (('-O', ['-O'], None), ('-OO', ['-OO'], None),
                 ('PYTHONOPTIMIZE=1', [], '1'))
GUARD_MESSAGE = 'requires Python assertions; disable -O/-OO and PYTHONOPTIMIZE'


class RequiredOptimizationTests(unittest.TestCase):
    def check_validator(self, module, artifacts):
        for _, path in artifacts:
            self.assertTrue(path.is_file(), f'Missing candidate artifact: {path}')
        code = ('import sys; sys.path.insert(0, sys.argv.pop(1)); '
                f'from {module} import main; main()')
        for label, flags, optimize in OPTIMIZATIONS:
            env = os.environ.copy()
            env.pop('PYTHONOPTIMIZE', None)
            if optimize is not None:
                env['PYTHONOPTIMIZE'] = optimize
            # Each missing artifact must still produce the optimization refusal,
            # not a loader error: validation must stop before artifact access.
            for missing in (None, *range(len(artifacts))):
                for entrypoint in ('cli', 'import'):
                    with self.subTest(validator=module, mode=label, missing=missing,
                                      entrypoint=entrypoint), tempfile.TemporaryDirectory() as tmp:
                        output = Path(tmp) / 'report.json'
                        args = []
                        for index, (option, path) in enumerate(artifacts):
                            if option:
                                args.append(option)
                            args.append(Path(tmp) / path.name if index == missing else path)
                        args.extend(['--output', output])
                        if entrypoint == 'cli':
                            args = [ROOT / 'tests' / f'{module}.py', *args]
                        else:
                            args = ['-c', code, ROOT / 'tests', *args]
                        result = subprocess.run([sys.executable, '-B', *flags, *map(str, args)],
                                                cwd=tmp, env=env, capture_output=True,
                                                text=True, timeout=60)
                        self.assertNotEqual(result.returncode, 0,
                                            f'False success: {result.stdout}; report exists: {output.exists()}')
                        self.assertIn(GUARD_MESSAGE, result.stderr)
                        self.assertEqual(result.stdout, '')
                        self.assertFalse(output.exists(), 'Rejected validation wrote output report')

    def test_sync_cli_and_import_fail_closed(self):
        self.check_validator('fex_sync_binary', [(None, ELF)])

    def test_pipeline_cli_and_import_fail_closed(self):
        self.check_validator('fex_pipeline_binary', [(None, ELF)])

    def test_unwind_cli_and_import_fail_closed(self):
        self.check_validator('fex_unwind', [
            (None, ROOT / 'local/fex3/resume-gate/payload/ntdll.dll'),
            (None, ROOT / 'local/fex3/macos-module/libwow64fex.dll'),
            (None, ROOT / 'local/fex3/resume-gate/payload/wow64.dll'),
            ('--elf', ELF),
        ])


if __name__ == '__main__':
    unittest.main()
