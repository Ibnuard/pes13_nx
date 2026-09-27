"""Exercise explicit host toolchain selection before source preparation."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_builder(script):
    sys.path.insert(0, str(ROOT / 'tools'))
    spec = importlib.util.spec_from_file_location(script.replace('-', '_'), ROOT / 'tools' / script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def toolchain_fixture(root):
    binary = root / 'bin'
    binary.mkdir(parents=True)
    for name in ('aarch64-w64-mingw32-clang', 'aarch64-w64-mingw32-clang++',
                 'i686-w64-mingw32-clang', 'i686-w64-mingw32-gcc'):
        path = binary / name
        path.write_text('#!/bin/sh\nprintf "fixture compiler %s\\n" "$0"\n')
        path.chmod(0o755)
    return root


def cmake_fixture(build, toolchain):
    # Match real Mac cache: C/CXX only in generated compiler metadata.
    metadata = build / 'CMakeFiles/3.31.6'
    metadata.mkdir(parents=True)
    (build / 'CMakeCache.txt').write_text(
        f'CMAKE_ASM_COMPILER:FILEPATH={toolchain}/bin/aarch64-w64-mingw32-clang\n')
    for language, executable in [('C', 'clang'), ('CXX', 'clang++'), ('ASM', 'clang')]:
        (metadata / f'CMake{language}Compiler.cmake').write_text(
            f'set(CMAKE_{language}_COMPILER "{toolchain}/bin/aarch64-w64-mingw32-{executable}")\n')


def wine_fixture(build, toolchain):
    build.mkdir(parents=True)
    (build / 'Makefile').write_text(
        'aarch64_CC = aarch64-w64-mingw32-clang -D__STDC__\n'
        'i386_CC = i686-w64-mingw32-gcc -D__STDC__\n')
    (build / 'config.log').write_text(
        f'configure:7507: found {toolchain}/bin/aarch64-w64-mingw32-clang\n'
        f'configure:7661: found {toolchain}/bin/i686-w64-mingw32-gcc\n')


def tree_state(root):
    return {str(path.relative_to(root)): (path.stat().st_mtime_ns,
            path.read_bytes() if path.is_file() else None) for path in root.rglob('*')}


class BuildToolchainTests(unittest.TestCase):
    def test_module_rejects_changed_cached_toolchain_before_any_mutation(self):
        module = load_builder('build-fex-module.py')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = toolchain_fixture(root / 'A')
            selected = toolchain_fixture(root / 'B')
            cmake_fixture(root / 'fex-experiment/build-horizon', old)
            before = tree_state(root)
            argv = ['build-fex-module.py', '--horizon', '--build-root', str(root),
                    '--toolchain', str(selected), '--output-dir', str(root / 'new-evidence')]
            with mock.patch.object(sys, 'argv', argv), mock.patch.object(
                    module.subprocess, 'run', side_effect=AssertionError('build/source command before guard')):
                with self.assertRaisesRegex(SystemExit, 'Toolchain provenance'):
                    module.main()
            self.assertEqual(tree_state(root), before)

    def test_runtime_rejects_changed_wine_toolchain_before_prepare(self):
        module = load_builder('build-fex-runtime.py')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = toolchain_fixture(root / 'A')
            selected = toolchain_fixture(root / 'B')
            pe = root / 'fex-experiment/wine3/pe-build'
            wine_fixture(pe, old)
            before = tree_state(root)
            argv = ['build-fex-runtime.py', '--integration', '--build-root', str(root),
                    '--toolchain', str(selected), '--output-dir', str(root / 'new-evidence')]
            with mock.patch.object(sys, 'argv', argv), mock.patch.object(
                    module, 'prepare', side_effect=AssertionError('source mutation before guard')):
                with self.assertRaisesRegex(SystemExit, 'Toolchain provenance'):
                    module.main()
            self.assertEqual(tree_state(root), before)

    def test_native_dependency_receipt_requires_nvk_and_hashes_actual_libraries(self):
        spec = importlib.util.spec_from_file_location('build_fex_runtime',
                                                      ROOT / 'tools/build-fex-runtime.py')
        assert spec is not None and spec.loader is not None
        sys.path.insert(0, str(ROOT / 'tools'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, 'native_dependency_receipt'))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mesa, sdk = root / 'mesa', root / 'sdk'
            mesa.mkdir()
            (sdk / 'libnx/lib').mkdir(parents=True)
            (sdk / 'libnx/lib/libnx.a').write_bytes(b'libnx-fixture')
            with self.assertRaisesRegex(FileNotFoundError, 'libvulkan.a'):
                module.native_dependency_receipt(mesa, sdk)
            (mesa / 'libvulkan.a').write_bytes(b'nvk-fixture')
            (mesa / 'libEGL.a').write_bytes(b'egl-fixture')
            receipt = module.native_dependency_receipt(mesa, sdk)
            self.assertEqual(receipt['mesa/libvulkan.a'], hashlib.sha256(b'nvk-fixture').hexdigest())
            self.assertEqual(receipt['mesa/libEGL.a'], hashlib.sha256(b'egl-fixture').hexdigest())
            self.assertEqual(receipt['sdk/libnx/lib/libnx.a'], hashlib.sha256(b'libnx-fixture').hexdigest())

    def test_runtime_fixes_requires_integration_before_source_preparation(self):
        result = subprocess.run([
            sys.executable, '-B', str(ROOT / 'tools/build-fex-runtime.py'),
            '--runtime-fixes',
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--runtime-fixes requires --integration', result.stderr)

    def test_explicit_missing_toolchain_fails_before_build_root_creation(self):
        for script in ('build-fex-module.py', 'build-fex-runtime.py'):
            with self.subTest(script=script), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / 'untouched-build'
                toolchain = Path(tmp) / 'missing-macos-toolchain'
                output = Path(tmp) / 'untouched-evidence'
                result = subprocess.run([
                    sys.executable, '-B', str(ROOT / 'tools' / script),
                    '--build-root', str(root), '--toolchain', str(toolchain),
                    '--output-dir', str(output),
                ], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Missing LLVM-MinGW toolchain:', result.stderr)
                self.assertIn(str(toolchain / 'bin'), result.stderr)
                self.assertFalse(root.exists())
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
