"""NRO-only package must never replace working configuration or DLLs."""
from pathlib import Path
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))


def load():
    path = PROJECT / 'tools/package-fex3-runtime-fixes.py'
    if not path.is_file():
        raise AssertionError('Missing native-only runtime overlay packager')
    spec = importlib.util.spec_from_file_location('fex_runtime_package', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeOverlayTests(unittest.TestCase):
    def make_pair(self, root):
        """Synthetic metadata/receipt fixture, never a runnable Switch binary."""
        module = load()
        icon = (PROJECT / 'assets/icon.jpg').read_bytes()
        for name, fixes in (('candidate', True), ('control', False)):
            directory = root / name
            (directory / 'payload').mkdir(parents=True)
            (directory / 'reference').mkdir()
            code = bytearray(0x100)
            code[0x10:0x14] = b'NRO0'
            struct.pack_into('<I', code, 0x18, len(code))
            marker = b'pes13-fex3-runtime-fixes' if fixes else b'pes13-fex3-timing-audit'
            code[0x40:0x40 + len(marker)] = marker
            nacp = bytearray(0x4000)
            title = b'PES13-NX FEX3\0'
            nacp[:len(title)] = title
            nacp[0x200:0x208] = b'Fixture\0'
            nacp[0x3060:0x3066] = b'0.3.0\0'
            asset = struct.pack('<II6Q', int.from_bytes(b'ASET', 'little'), 0,
                                56, len(icon), 56 + len(icon), len(nacp), 0, 0)
            blob = bytes(code) + asset + icon + bytes(nacp)
            elf = ('non-executable ELF receipt fixture: ' + name).encode()
            (directory / 'payload/pes13-fex.nro').write_bytes(blob)
            (directory / 'reference/pes13-fex.elf').write_bytes(elf)
            recipe = {'runtime_fixes': fixes, 'box64_engine_linked': False,
                      'nro_sha256': module.sha(blob), 'native_elf_sha256': module.sha(elf),
                      'ntdll_sha256': module.sha(b'ntdll fixture'),
                      'wow64_sha256': module.sha(b'wow64 fixture'),
                      'guest_sha256': module.sha(b'guest fixture'),
                      'adapter_sources': {'adapter.c': module.sha(b'adapter fixture')},
                      'toolchain_path': '/fixture/toolchain',
                      'native_dependencies': {'mesa/libvulkan.a': module.sha(b'nvk fixture')}}
            (directory / 'runtime-build.json').write_text(json.dumps(recipe))
            patches = {'pe-source': {'ntdll.c': module.sha(b'unchanged fixture')},
                       'native-source': {path: module.sha((name + path).encode())
                                         for path in ('dlls/ntdll/unix/horizon.c',
                                                      'wine-nx-probe/source/runtime.c')}}
            (directory / 'wine-patches.json').write_text(json.dumps(patches))
        validation = {'passed': True}
        for name in ('candidate', 'control'):
            recipe = json.loads((root / name / 'runtime-build.json').read_text())
            validation[name + '_elf_sha256'] = recipe['native_elf_sha256']
        (root / 'validation.json').write_text(json.dumps(validation))

    def package_pair(self, root):
        return subprocess.run([
            sys.executable, '-B', str(PROJECT / 'tools/package-fex3-runtime-fixes.py'),
            '--candidate', str(root / 'candidate'), '--control', str(root / 'control'),
            '--validation', str(root / 'validation.json'), '--output-dir', str(root / 'out'),
        ], capture_output=True, text=True, timeout=30)

    def test_main_accepts_matching_metadata_receipts_and_preserves_payload_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_pair(root)
            result = self.package_pair(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs = json.loads(result.stdout)
            self.assertEqual(len(outputs), 2)
            for output in outputs:
                with zipfile.ZipFile(output['path']) as archive:
                    self.assertEqual([n for n in archive.namelist() if n.startswith('switch/')],
                                     [load().NRO])
                    record = json.loads(archive.read('manifest.json'))
                    self.assertFalse(record['hardware_tested'])
                    self.assertFalse(record['fps_gain_verified'])

    def test_changed_binary_bytes_are_rejected_before_any_archive(self):
        for name in ('candidate', 'control'):
            for binary in ('payload/pes13-fex.nro', 'reference/pes13-fex.elf'):
                with self.subTest(name=name, binary=binary), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    self.make_pair(root)
                    path = root / name / binary
                    path.write_bytes(path.read_bytes() + b'tampered')
                    result = self.package_pair(root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('Runtime bytes differ from build receipt', result.stderr)
                    self.assertFalse((root / 'out').exists())

    def test_failed_validation_and_pair_drift_are_rejected_before_any_archive(self):
        cases = [
            ('validation.json', 'passed', False, 'Validation does not match'),
            ('validation.json', 'candidate_elf_sha256', 'wrong', 'Validation does not match'),
            ('validation.json', 'control_elf_sha256', 'wrong', 'Validation does not match'),
            ('candidate/runtime-build.json', 'runtime_fixes', False, 'Unexpected runtime recipe'),
            ('control/runtime-build.json', 'box64_engine_linked', True, 'Unexpected runtime recipe'),
            ('candidate/wine-patches.json', 'pe-source', {}, 'PE source changed'),
            ('candidate/wine-patches.json', 'native-source', {'unexpected.c': 'different'},
             'Unexpected native source delta'),
        ]
        cases += [('candidate/runtime-build.json', key, 'different', 'dependency drift: ' + key)
                  for key in ('ntdll_sha256', 'wow64_sha256', 'guest_sha256', 'adapter_sources',
                              'toolchain_path', 'native_dependencies')]
        for file, key, value, message in cases:
            with self.subTest(file=file, key=key), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.make_pair(root)
                path = root / file
                data = json.loads(path.read_text())
                data[key] = value
                path.write_text(json.dumps(data))
                result = self.package_pair(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertFalse((root / 'out').exists())

    def test_archive_contains_only_one_native_payload_and_refuses_overwrite(self):
        module = load()
        # Archive boundary fixture only, not a genuine NRO or runtime validation.
        files = {module.NRO: b'archive-boundary-fixture', 'README.txt': b'backup first'}
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'overlay.zip'
            module.write_overlay(archive, files)
            with zipfile.ZipFile(archive) as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(set(z.namelist()), set(files))
                self.assertEqual(z.read(module.NRO), files[module.NRO])
            with self.assertRaises(FileExistsError):
                module.write_overlay(archive, files)

    def test_extra_sd_payloads_and_unsafe_archive_paths_are_rejected(self):
        module = load()
        for forbidden in ('switch/pes13-fex/configuration.ini',
                          'switch/pes13-fex/drive_c/windows/system32/ntdll.dll',
                          'switch/pes13-fex/drive_c/PES13/settings.dat',
                          '../escape', '/absolute', 'folder/../escape',
                          'C:/absolute', 'switch\\pes13-fex\\extra.nro'):
            with self.subTest(forbidden=forbidden), tempfile.TemporaryDirectory() as temporary:
                archive = Path(temporary) / 'overlay.zip'
                with self.assertRaises(ValueError):
                    module.write_overlay(archive, {module.NRO: b'fixture', forbidden: b'bad'})
                self.assertFalse(archive.exists())


if __name__ == '__main__':
    unittest.main()
