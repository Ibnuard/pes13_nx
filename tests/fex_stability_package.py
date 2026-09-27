"""Validate matched stability payload, corruption rejection and install boundaries."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
SPEC = importlib.util.spec_from_file_location('stability_package', ROOT / 'tools/package-fex3-stability.py')
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


class StabilityPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = PACKAGE.collect(ROOT / 'local/fex3/stability-540p')

    def test_delivered_zip_matches_tested_sources_and_binaries(self):
        archive = ROOT / 'dist/pes13-fex3-stability-540p.zip'
        with zipfile.ZipFile(archive) as zipped:
            self.assertIsNone(zipped.testzip())
            self.assertEqual(set(zipped.namelist()), set(self.files))
            for name, data in self.files.items():
                self.assertEqual(zipped.read(name), data, name)

    def test_settings_preserve_controller_and_display_flags(self):
        original = (ROOT / 'config/drive_c/users/steamuser/Documents/KONAMI/Pro Evolution Soccer 2013/settings.dat').read_bytes()
        for name in PACKAGE.SETTINGS:
            data = self.files[PACKAGE.PREFIX + name]
            self.assertEqual(struct.unpack_from('<II', data, 16), (960, 540))
            self.assertEqual(data[:12], original[:12])
            self.assertEqual(data[14:16], original[14:16])
            self.assertEqual(data[24:], original[24:])
        self.assertEqual(struct.unpack_from('<II', self.files['profiles/720p/settings.dat'], 16), (1280, 720))
        with self.assertRaises(ValueError):
            PACKAGE.resize_settings(original[:-1], 960, 540)
        corrupted = bytearray(original)
        corrupted[123] ^= 1
        with self.assertRaises(ValueError):
            PACKAGE.resize_settings(corrupted, 960, 540)

    def test_rejects_binary_corruption_and_mismatched_pair_receipts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'module.dll'
            path.write_bytes(b'wrong module')
            with self.assertRaises(ValueError):
                PACKAGE.checked(path, PACKAGE.sha(b'expected module'))
        report = json.loads(self.files['evidence/unwind-binary.json'])
        wrong = {key: report[key] for key in ('fex_sha256', 'native_elf_sha256', 'ntdll_sha256', 'wow64_sha256')}
        for key in wrong:
            with self.assertRaises(ValueError):
                PACKAGE.checked_report(json.dumps(report), {**wrong, key: '0' * 64})
        with self.assertRaises(ValueError):
            PACKAGE.checked_report('{"passed": false}', {})

    def test_no_game_or_save_overwrite_and_refuses_existing_output(self):
        PACKAGE.validate_boundary(self.files)
        for name in ('../escaped', '/absolute', 'switch/pes13-fex/drive_c/PES13/pes2013.exe',
                     'switch/pes13-fex/drive_c/KONAMI/Pro Evolution Soccer 2013/save/EDIT.bin'):
            with self.assertRaises(ValueError):
                PACKAGE.validate_boundary({**self.files, name: b'bad'})
        missing = dict(self.files)
        del missing[PACKAGE.PREFIX + 'drive_c/windows/system32/ntdll.dll']
        with self.assertRaises(ValueError):
            PACKAGE.validate_boundary(missing)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileExistsError):
                PACKAGE.write_package(self.files, Path(folder))


if __name__ == '__main__':
    unittest.main()
