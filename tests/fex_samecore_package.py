"""Exercise same-core overlay packaging with real artifacts and rejection cases."""
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
BASE = ROOT / 'local/fex3/event-diagnostic'
CANDIDATE = ROOT / 'local/fex3/samecore-diagnostic'


class SamecorePackageTests(unittest.TestCase):
    def module(self):
        path = ROOT / 'tools/package-fex3-samecore.py'
        self.assertTrue(path.is_file(), 'Missing same-core candidate/control package gate')
        spec = importlib.util.spec_from_file_location('samecore_package', path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_real_overlay_and_no_overwrite(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'candidate.zip'
            result = module.package(BASE, CANDIDATE, output)
            self.assertFalse(result['hardware_tested'])
            self.assertTrue(result['samecore_yield'])
            self.assertFalse(result['runtime_fixes'])
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()),
                                 {'README.txt', 'manifest.json', 'switch/pes13-fex/pes13-fex.nro'})
                self.assertEqual(archive.read('switch/pes13-fex/pes13-fex.nro'),
                                 (CANDIDATE / 'payload/pes13-fex.nro').read_bytes())
            with self.assertRaises(FileExistsError):
                module.package(BASE, CANDIDATE, output)

    def test_rejects_drift_before_creating_archive(self):
        module = self.module()
        cases = [
            ('runtime-build.json', lambda r: r.update(runtime_fixes=True)),
            ('runtime-build.json', lambda r: r.update(ntdll_sha256='0' * 64)),
            ('runtime-build.json', lambda r: r.update(toolchain_path='wrong-toolchain')),
            ('runtime-build.json', lambda r: r.update(native_dependencies={})),
            ('runtime-build.json', lambda r: r.update(nro_sha256='0' * 64)),
            ('runtime-build.json', lambda r: r.update(native_elf_sha256='0' * 64)),
            ('wine-patches.json', lambda r: r['pe-source'].update(unexpected='0' * 64)),
            ('wine-patches.json', lambda r: r['native-source'].update(unexpected='0' * 64)),
            ('samecore-validation.json', lambda r: r.update(passed=False)),
            ('samecore-validation.json', lambda r: r.update(native_elf_sha256='0' * 64)),
            ('samecore-validation.json', lambda r: r.update(expected_yield_ns=-1)),
            ('self-suspend-validation.json', lambda r: r.update(passed=False)),
        ]
        for index, (name, mutate) in enumerate(cases):
            with self.subTest(index=index, file=name), tempfile.TemporaryDirectory() as tmp:
                candidate = Path(tmp) / 'candidate'
                candidate.mkdir()
                for path in CANDIDATE.iterdir():
                    if path.is_file() and path.suffix == '.json':
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
