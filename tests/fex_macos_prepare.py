"""Preparation tests; optional real Wine integration via PES_FEX_WINE_SOURCE."""
from pathlib import Path
import importlib.util
import hashlib
import json
import os
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
HELPER = PROJECT / "tools/prepare-fex-macos.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("prepare_fex_macos", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExportTests(unittest.TestCase):
    def test_exports_pinned_git_tree_without_untracked_files_or_mutation(self):
        self.assertTrue(HELPER.exists(), "Pinned source preparation helper missing")
        helper = load_helper()
        with tempfile.TemporaryDirectory(prefix="fex-prepare-test-") as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            (source / "source.c").write_text("original\n")
            subprocess.run(["git", "-C", str(source), "add", "source.c"], check=True)
            subprocess.run(["git", "-C", str(source), "-c", "user.name=Test",
                            "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
            revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
            (source / "local-only").write_text("do not copy\n")
            result = helper.export_pinned(source, root / "export", revision)
            self.assertEqual(result["commit"], revision)
            self.assertEqual((root / "export/source.c").read_text(), "original\n")
            self.assertFalse((root / "export/.git").exists())
            self.assertFalse((root / "export/local-only").exists())
            self.assertEqual((source / "local-only").read_text(), "do not copy\n")
            (root / "export/source.c").write_text("isolated\n")
            self.assertEqual((source / "source.c").read_text(), "original\n")


@unittest.skipUnless(os.environ.get("PES_FEX_WINE_SOURCE"), "Set PES_FEX_WINE_SOURCE for real-source integration")
class IntegrationTests(unittest.TestCase):
    def test_real_source_bootstrap_and_master_integration(self):
        helper = load_helper()
        self.assertTrue(hasattr(helper, "prepare"), "FEX3 preparation pipeline missing")
        source = Path(os.environ["PES_FEX_WINE_SOURCE"])
        source_head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"])
        with tempfile.TemporaryDirectory(prefix="fex-integration-test-") as temporary:
            root = Path(temporary)
            report = helper.prepare(root, source, PROJECT)
            baseline = root / "runtime-perf11-source"
            work = root / "fex-experiment/wine3"
            self.assertEqual(report["wine"]["commit"], "1bc4e45163f0d2328cdfd35c7f471dd9821bb879")
            self.assertEqual(report["wine"]["patches"], ["patches/wine-nx.patch"])
            native = work / "native-source"
            pe = work / "pe-source"
            runtime = (native / "wine-nx-probe/source/runtime.c").read_text()
            self.assertIn('"pes13-fex3-timing-audit"', runtime)
            self.assertIn('switch/pes13-fex', runtime)
            self.assertNotIn('switch/pes13-fex2', runtime)
            cmake = (native / "wine-nx-probe/CMakeLists.txt").read_text()
            self.assertIn('PES13_FEX_ISOLATED_EXCEPTIONS=1', cmake)
            self.assertIn('exception_isolated.S', cmake)
            self.assertIn('source/pes13_preload.c', cmake)
            self.assertIn('fex_sync_horizon.h', (native / "dlls/ntdll/unix/horizon.c").read_text())
            self.assertIn('pes13_fex_suspend_local_thread', (pe / "dlls/ntdll/signal_arm64.c").read_text())
            self.assertIn('wine_nx_pe_module_index', (pe / "dlls/ntdll/ntdll.spec").read_text())
            self.assertIn('nx-wow64-console-11', (baseline / "wine-nx-probe/source/runtime.c").read_text())
            self.assertFalse((baseline / "wine-nx-probe/vendor/box64").exists())
            self.assertFalse((native / ".git").exists())
            for kind in ("native-source", "pe-source"):
                stamp = json.loads((work / (kind + ".json")).read_text())
                self.assertIn("files", stamp)
                self.assertIn("origin", stamp)
                patched = json.loads((work / (kind + "-patches.json")).read_text())
                for name, digest in patched.items():
                    self.assertEqual(hashlib.sha256((work / kind / name).read_bytes()).hexdigest(), digest)
            self.assertEqual(source_head, subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"]))
            self.assertTrue((work / "prepare-fex-macos.json").is_file())


if __name__ == "__main__":
    unittest.main()
