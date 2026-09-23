"""Verify control packaging rejects changes unrelated to block growth."""
from pathlib import Path
import importlib.util
import sys
import unittest

project = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project / "tools"))
spec = importlib.util.spec_from_file_location("perf29_recovery", project / "tools/package-perf29-recovery.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.main = {package.FLAG: b"1\n", package.PROFILE: b"0\n",
                     package.CONFIG: b"profile=0\n", package.PREFIX + "pes13-nx.nro": b"fixture"}
        self.overlay = {package.FLAG: b"0\n", package.PROFILE: b"0\n",
                        package.CONFIG: b"profile=0\n"}

    def test_only_flag_changes(self):
        original = dict(self.main)
        result = package.control_files(self.main, self.overlay)
        self.assertEqual(self.main, original)
        self.assertEqual(result[package.PREFIX + "pes13-nx.nro"], b"fixture")
        self.assertEqual([name for name in result if result[name] != original[name]], [package.FLAG])

    def test_reject_extra_runtime_change(self):
        self.overlay[package.CONFIG] += b"other=1\n"
        with self.assertRaises(AssertionError):
            package.control_files(self.main, self.overlay)

    def test_reject_sampling_on(self):
        self.main[package.PROFILE] = self.overlay[package.PROFILE] = b"1\n"
        with self.assertRaises(AssertionError):
            package.control_files(self.main, self.overlay)

    def test_reject_game_settings_or_second_nro(self):
        for name in ("drive_c/PES13/settings.dat", "second.nro", "drive_c/PES13/pes2013.exe"):
            with self.subTest(name=name):
                main = dict(self.main)
                main[package.PREFIX + name] = b"unrelated"
                with self.assertRaises(AssertionError):
                    package.control_files(main, self.overlay)


if __name__ == "__main__":
    unittest.main()
