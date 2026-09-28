"""Resume-gate overlay must preserve PE/config and reject stale evidence."""
from pathlib import Path
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
BASE = ROOT / 'local/fex3/samecore-diagnostic'
CANDIDATE = ROOT / 'local/fex3/resume-gate'


class ResumePackageTests(unittest.TestCase):
    def module(self):
        path = ROOT / 'tools/package-fex3-resume-gate.py'
        self.assertTrue(path.is_file(), 'Missing resume-gate package guard')
        spec = importlib.util.spec_from_file_location('resume_package', path)
        if spec is None or spec.loader is None:
            self.fail('No packager loader')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_real_overlay_and_no_overwrite(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'candidate.zip'
            result = module.package(BASE, CANDIDATE, output)
            self.assertFalse(result['hardware_tested'])
            self.assertTrue(result['resume_gate'])
            self.assertFalse(result['runtime_fixes'])
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()),
                                 {'README.txt', 'manifest.json', 'switch/pes13-fex/pes13-fex.nro'})
                self.assertEqual(archive.read('switch/pes13-fex/pes13-fex.nro'),
                                 (CANDIDATE / 'payload/pes13-fex.nro').read_bytes())
            with self.assertRaises(FileExistsError):
                module.package(BASE, CANDIDATE, output)

    def test_nro_executable_matches_validated_elf(self):
        module = self.module()
        elf = CANDIDATE / 'reference/pes13-fex.elf'
        blob = (CANDIDATE / 'payload/pes13-fex.nro').read_bytes()
        self.assertTrue(hasattr(module, 'verify_executable'), 'Missing ELF/NRO correspondence guard')
        module.verify_executable(elf, blob)
        changed = bytearray(blob)
        changed[0x1000] ^= 1
        with self.assertRaisesRegex(ValueError, 'NRO executable differs'):
            module.verify_executable(elf, bytes(changed))

    def test_rejects_drift(self):
        module = self.module()
        cases = [
            ('runtime-build.json', lambda r: r.update(runtime_fixes=True)),
            ('runtime-build.json', lambda r: r.update(resume_gate=False)),
            ('runtime-build.json', lambda r: r.update(samecore_yield=False)),
            ('runtime-build.json', lambda r: r.update(ntdll_sha256='0' * 64)),
            ('runtime-build.json', lambda r: r.update(native_dependencies={})),
            ('wine-patches.json', lambda r: r['native-source'].update(unexpected='0' * 64)),
            ('wine-patches.json', lambda r: r['pe-source'].update(unexpected='0' * 64)),
            ('resume-validation.json', lambda r: r.update(passed=False)),
            ('resume-validation.json', lambda r: r.update(native_elf_sha256='0' * 64)),
            ('resume-validation.json', lambda r: r.update(scenarios=0)),
            ('resume-validation.json', lambda r: r.update(scenarios=8)),
            ('samecore-validation.json', lambda r: r['checks'][0].update(svc_sleep_ns=[-1])),
        ]
        for index, (name, mutate) in enumerate(cases):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as tmp:
                candidate = Path(tmp) / 'candidate'
                candidate.mkdir()
                for path in CANDIDATE.glob('*.json'):
                    shutil.copy2(path, candidate / path.name)
                for directory in ('payload', 'reference'):
                    (candidate / directory).symlink_to(CANDIDATE / directory, target_is_directory=True)
                record = json.loads((candidate / name).read_text())
                mutate(record)
                (candidate / name).write_text(json.dumps(record))
                output = Path(tmp) / 'rejected.zip'
                with self.assertRaises(ValueError):
                    module.package(BASE, candidate, output)
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
