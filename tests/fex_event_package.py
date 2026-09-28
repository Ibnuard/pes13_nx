"""NRO-only diagnostic must match validated control ABI and reject drift."""
from pathlib import Path
import importlib.util
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
SPEC = importlib.util.spec_from_file_location('event_package', ROOT / 'tools/package-fex3-event-diagnostic.py')


class EventPackageTests(unittest.TestCase):
    def test_real_build_preserves_control_abi_and_nro_only_boundary(self):
        assert SPEC is not None and SPEC.loader is not None
        module = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'diagnostic.zip'
            result = module.package(ROOT / 'local/fex3/control',
                                    ROOT / 'local/fex3/event-diagnostic', path)
            self.assertEqual(result['hardware_tested'], False)
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual([name for name in archive.namelist() if name.startswith('switch/')],
                                 ['switch/pes13-fex/pes13-fex.nro'])
                self.assertIn(b'pes13-fex3-event-diagnostic',
                              archive.read('switch/pes13-fex/pes13-fex.nro'))
            with self.assertRaises(FileExistsError):
                module.package(ROOT / 'local/fex3/control',
                               ROOT / 'local/fex3/event-diagnostic', path)


if __name__ == '__main__':
    unittest.main()
