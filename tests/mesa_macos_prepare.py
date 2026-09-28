#!/usr/bin/env python3
"""Host preparation regressions; no downloads, SDK writes, or target execution."""
import importlib.util
from pathlib import Path
import unittest
import subprocess
import tempfile

SCRIPT = Path(__file__).resolve().parents[1] / "tools/build-mesa-macos.py"


class RelocationTests(unittest.TestCase):
    def test_isolated_bottle_paths(self):
        self.assertTrue(SCRIPT.exists(), "macOS Mesa preparation script missing")
        spec = importlib.util.spec_from_file_location("build_mesa_macos", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        root = Path("/build cache")
        self.assertEqual(
            module.relocated_path("@@HOMEBREW_PREFIX@@/opt/llvm@21/lib/libLLVM.dylib", root),
            "/build cache/toolchains/mesa-llvm/llvm@21/21.1.8/lib/libLLVM.dylib",
        )
        self.assertEqual(
            module.relocated_path("@@HOMEBREW_CELLAR@@/spirv-tools/1.4.357.0", root),
            "/build cache/toolchains/mesa-spirv-tools/spirv-tools/1.4.357.0",
        )
        self.assertEqual(
            module.relocated_path("@@HOMEBREW_PREFIX@@/opt/zstd/lib/libzstd.1.dylib", root),
            "/opt/homebrew/opt/zstd/lib/libzstd.1.dylib",
        )
        self.assertEqual(module.relocated_path("@rpath/libLLVM.dylib", root), "@rpath/libLLVM.dylib")
        with self.assertRaises(ValueError):
            module.relocated_path("@@HOMEBREW_PREFIX@@/opt/unknown/lib/libx.dylib", root)

    def test_relocate_real_dylib_id_and_pc_idempotently(self):
        spec = importlib.util.spec_from_file_location("build_mesa_macos", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, "relocate_bottle"), "bottle relocator missing")
        with tempfile.TemporaryDirectory(prefix="mesa-relocate-") as tmp:
            root = Path(tmp)
            prefix = root / "toolchains/mesa-spirv-tools/spirv-tools/1.4.357.0"
            lib = prefix / "lib/libtest.dylib"
            lib.parent.mkdir(parents=True)
            source = root / "test.c"
            source.write_text("int value(void) { return 1; }\n")
            subprocess.run(["cc", "-dynamiclib", str(source), "-o", str(lib),
                            "-Wl,-headerpad_max_install_names"], check=True)
            subprocess.run(["install_name_tool", "-id",
                            "@@HOMEBREW_PREFIX@@/opt/spirv-tools/lib/libtest.dylib", str(lib)],
                           check=True, capture_output=True)
            pc = prefix / "lib/pkgconfig/test.pc"
            pc.parent.mkdir()
            pc.write_text("prefix=@@HOMEBREW_CELLAR@@/spirv-tools/1.4.357.0\n")
            module.relocate_bottle(prefix, root)
            module.relocate_bottle(prefix, root)
            self.assertIn(str(lib), subprocess.check_output(["otool", "-D", str(lib)], text=True))
            self.assertEqual(pc.read_text(), f"prefix={prefix}\n")
            subprocess.run(["codesign", "--verify", str(lib)], check=True)

    def test_cross_configuration_keeps_sdk_read_only_and_host_rust_native(self):
        spec = importlib.util.spec_from_file_location("build_mesa_macos", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, "cross_configuration"), "cross configuration missing")
        root = Path("/isolated root")
        template = "rust = '/usr/local/libexec/rustc'\nbindgen = '/usr/local/libexec/bindgen'\nc_link_args = ['-L/opt/devkitpro/portlibs/switch/lib']\n"
        cross, native = module.cross_configuration(template, root)
        self.assertIn("/isolated root/mesa-vulkan/tools/rustc", cross)
        self.assertIn("/isolated root/mesa-vulkan/compat/lib", cross)
        self.assertIn("needs_exe_wrapper = true", cross)
        self.assertIn("/opt/devkitpro/portlibs/switch/lib", cross)
        self.assertNotIn("mesa-vulkan/tools/rustc", native)
        self.assertIn("1.93.1-aarch64-apple-darwin/bin/rustc", native)
        self.assertIn("c = '/usr/bin/clang'", native)
        self.assertIn("objc = '/usr/bin/clang'", native)
        with self.assertRaises(ValueError):
            module.cross_configuration("unrecognized cross template", root)

    def test_build_plan_pins_driver_and_stages_install_without_global_writes(self):
        spec = importlib.util.spec_from_file_location("build_mesa_macos", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, "build_commands"), "resumable build plan missing")
        root = Path("/isolated")
        plan = dict(module.build_commands(root, 2))
        cross = plan["cross-configure"]
        self.assertIn("-Dnvk-build-id=" + module.MESA_REVISION, cross)
        self.assertIn("-Dvulkan-drivers=nouveau", cross)
        self.assertIn("-Dgallium-drivers=nouveau", cross)
        self.assertIn("-Db_lto=false", cross)
        self.assertEqual(plan["cross-build"][-1], "-j2")
        self.assertEqual(plan["install"][-2:], ["--destdir", "/isolated/mesa-vulkan/install"])
        self.assertEqual(module.build_environment(root, "cross")["PATH"].split(":")[0], "/isolated/mesa-vulkan/tools")
        self.assertIn("OBJC", module.build_environment(root, "native"))
        self.assertEqual(module.build_environment(root, "cross")["PKG_CONFIG_PATH"], "")
        self.assertEqual(module.build_environment(root, "native")["LDFLAGS"], "")
        for bad in (0, 3):
            with self.assertRaises(ValueError):
                module.build_commands(root, bad)

    def test_cli_plan_read_only_and_revision_gate_before_writes(self):
        import sys
        with tempfile.TemporaryDirectory(prefix="mesa-plan-") as tmp:
            root = Path(tmp) / "absent"
            result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--plan"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("cross-build", result.stdout)
            self.assertFalse(root.exists())
            result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--stage", "prepare"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(root.exists())

    def test_archive_validation_rejects_host_and_thin_archives(self):
        spec = importlib.util.spec_from_file_location("build_mesa_macos", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, "verify_archive"), "target archive validation missing")
        with tempfile.TemporaryDirectory(prefix="mesa-archive-") as tmp:
            root = Path(tmp)
            source, obj = root / "test.c", root / "test.o"
            archive = root / "test.a"
            source.write_text("int mesa_archive_test(void) { return 42; }\n")
            subprocess.run(["/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc", "-c", str(source), "-o", str(obj)], check=True)
            subprocess.run(["/opt/devkitpro/devkitA64/bin/aarch64-none-elf-ar", "rcs", str(archive), str(obj)], check=True)
            result = module.verify_archive(archive)
            self.assertEqual(result["members"], 1)
            self.assertEqual(result["machine"], "AArch64")
            self.assertEqual(len(result["sha256"]), 64)
            subprocess.run(["/opt/devkitpro/devkitA64/bin/aarch64-none-elf-ar", "rcsT", str(root / "thin.a"), str(obj)], check=True)
            with self.assertRaises(ValueError):
                module.verify_archive(root / "thin.a")
            subprocess.run(["cc", "-c", str(source), "-o", str(root / "host.o")], check=True)
            subprocess.run(["ar", "rcs", str(root / "host.a"), str(root / "host.o")], check=True)
            with self.assertRaises(ValueError):
                module.verify_archive(root / "host.a")

    def test_install_verification_rejects_missing_sdk(self):
        spec = importlib.util.spec_from_file_location("build_mesa_macos", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, "verify_install"), "install verification missing")
        with tempfile.TemporaryDirectory(prefix="mesa-missing-") as tmp:
            with self.assertRaises(FileNotFoundError):
                module.verify_install(Path(tmp))
            self.assertFalse((Path(tmp) / "mesa-vulkan/manifest.json").exists())

    def test_unchanged_setup_files_keep_mtime(self):
        spec = importlib.util.spec_from_file_location("build_mesa_macos", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, "write_changed"), "incremental setup writer missing")
        with tempfile.TemporaryDirectory(prefix="mesa-idempotent-") as tmp:
            path = Path(tmp) / "config.txt"
            module.write_changed(path, "same\n")
            before = path.stat().st_mtime_ns
            module.write_changed(path, "same\n")
            self.assertEqual(path.stat().st_mtime_ns, before)
            module.write_changed(path, "changed\n")
            self.assertEqual(path.read_text(), "changed\n")


if __name__ == "__main__":
    unittest.main()
