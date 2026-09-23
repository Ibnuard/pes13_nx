"""Verify diagnostics enable sampling, not the failed block-growth experiment."""
from pathlib import Path
import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile

project = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project / "tools"))
spec = importlib.util.spec_from_file_location("control_sampling", project / "tools/package-perf29-control-sampling.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
recovery = package.recovery


class ControlSamplingTest(unittest.TestCase):
    def setUp(self):
        self.control = {recovery.FLAG: b"0\n", recovery.PROFILE: b"0\n",
                        recovery.CONFIG: b"title=PES13-NX\nverbose=0\nprofile=0\nd3d9=dxvk\n",
                        recovery.PREFIX + "pes13-nx.nro": b"unchanged"}

    def test_only_sampling_changes(self):
        before = dict(self.control)
        result = package.sampling_files(self.control, True)
        self.assertEqual(self.control, before)
        self.assertEqual(set(result), {recovery.FLAG, recovery.PROFILE, recovery.CONFIG})
        self.assertEqual(result[recovery.FLAG], b"0\n")
        self.assertEqual(result[recovery.PROFILE], b"1\n")
        self.assertEqual(result[recovery.CONFIG].replace(b"profile=1", b"profile=0"), before[recovery.CONFIG])

    def test_quiet_restores_exact_bytes(self):
        result = package.sampling_files(self.control, False)
        self.assertTrue(all(result[name] == self.control[name] for name in result))

    def test_line_endings_and_no_final_newline_preserved(self):
        for config in (b"title=PES13-NX\r\nprofile=0\r\n", b"title=PES13-NX\nprofile=0"):
            with self.subTest(config=config):
                self.control[recovery.CONFIG] = config
                result = package.sampling_files(self.control, True)
                self.assertEqual(result[recovery.CONFIG], config.replace(b"profile=0", b"profile=1"))

    def test_reject_enabled_growth_or_sampling(self):
        for name in (recovery.FLAG, recovery.PROFILE):
            with self.subTest(name=name):
                control = dict(self.control)
                control[name] = b"1\n"
                with self.assertRaises(ValueError):
                    package.sampling_files(control, True)

    def test_reject_ambiguous_or_missing_game_profile(self):
        for config in (b"profile=0\nprofile=0\n", b"profile=1\n", b"title=PES13-NX\n",
                       b"profile=0\nprofile=1\n"):
            with self.subTest(config=config):
                self.control[recovery.CONFIG] = config
                with self.assertRaises(ValueError):
                    package.sampling_files(self.control, True)

    def test_zip_manifest_reproduction_and_overwrite_guard(self):
        payload = package.sampling_files(self.control, True)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "control-sampling.zip"
            report = package.write_overlay(target, payload, True, "fixture")
            self.assertEqual(report, package.write_overlay(target, payload, True, "fixture"))
            with zipfile.ZipFile(target) as archive:
                manifest = json.loads(archive.read("PERF29-control-profile-manifest.json"))
                self.assertEqual(manifest["scoped_worker_bigblock"], 0)
                self.assertFalse(manifest["nro_included"])
                self.assertTrue(manifest["cpu_sampling"])
                for name, digest in manifest["files"].items():
                    self.assertEqual(recovery.digest(archive.read(name)), digest)
            target.write_bytes(b"different existing artifact")
            with self.assertRaises(ValueError):
                package.write_overlay(target, payload, True, "fixture")
            self.assertEqual(target.read_bytes(), b"different existing artifact")


if __name__ == "__main__":
    unittest.main()
