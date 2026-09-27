"""Build the pinned ARM64 PE WOW64 FEX module using a host-native cross-toolchain."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
from fex_toolchain import cmake_provenance

FEX_COMMIT = 'e2f973fe931e6dc2ce523795e51ca1ac3ca85816'
TOOLCHAIN = 'llvm-mingw-20260505-ucrt-ubuntu-22.04-x86_64'
SUBMODULES = ['External/fmt', 'External/xxhash', 'External/range-v3',
              'External/unordered_dense', 'External/rpmalloc',
              'Source/Common/cpp-optparse']


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-root', type=Path,
                        default=Path(os.environ.get('PES_BUILD_ROOT',
                                     Path.home() / '.cache/pes13-nx')))
    parser.add_argument('--jobs', type=int, default=int(os.environ.get('PES_JOBS', 4)))
    parser.add_argument('--horizon', action='store_true', help='Build the experimental dual-mapping module in a separate tree')
    parser.add_argument('--output-dir', type=Path, help='Separate evidence/output directory for integration builds')
    parser.add_argument('--toolchain', type=Path,
                        help='LLVM-MinGW root (containing bin); use the build host variant')
    args = parser.parse_args()
    root = args.build_root.resolve()
    source = root / ('fex-experiment/source-horizon' if args.horizon else 'fex-experiment/source')
    build = root / ('fex-experiment/build-horizon' if args.horizon else 'fex-experiment/build-wow64')
    output = project / ('local/fex1/horizon-module' if args.horizon else 'local/fex1/module')
    if args.output_dir:
        output = args.output_dir.resolve()
    toolchain = args.toolchain.resolve() if args.toolchain else root / 'toolchains' / TOOLCHAIN
    tc = toolchain / 'bin'
    if not (tc / 'aarch64-w64-mingw32-clang').is_file():
        raise SystemExit(f'Missing LLVM-MinGW toolchain: {tc}')
    cmake_provenance(build, toolchain)
    env = dict(os.environ, PATH=str(tc) + os.pathsep + os.environ['PATH'])

    def run(command, **kw):
        print('+', ' '.join(map(str, command)), flush=True)
        return subprocess.run(list(map(str, command)), check=True, env=env, **kw)

    if not (source / '.git').exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        upstream = root / 'fex-experiment/source'
        if args.horizon and (upstream / '.git').exists() and not source.exists():
            # Independent on-disk copy, including the already pinned submodules.
            # No worktree/shared index and no mutation of the upstream control.
            shutil.copytree(upstream, source, symlinks=True)
        cache = project / 'local/fex-probe/upstream'
        if (source / '.git').exists():
            pass
        elif (cache / '.git').exists():
            run(['git', 'clone', '--no-hardlinks', '--no-checkout', cache, source])
            run(['git', '-C', source, 'remote', 'set-url', 'origin',
                 'https://github.com/FEX-Emu/FEX.git'])
        else:
            run(['git', 'init', source])
            run(['git', '-C', source, 'remote', 'add', 'origin',
                 'https://github.com/FEX-Emu/FEX.git'])
            run(['git', '-C', source, 'fetch', '--depth=1', 'origin', FEX_COMMIT])
        run(['git', '-C', source, 'checkout', '--detach', FEX_COMMIT])
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if head != FEX_COMMIT:
        raise SystemExit(f'Refusing to change existing FEX checkout at {head}')
    run(['git', '-C', source, 'submodule', 'update', '--init', '--recursive',
         '--depth=1', '--jobs=4', *SUBMODULES])
    extra = []
    if args.horizon:
        from fex_horizon_patches import apply
        apply(source, project, output / 'patches.json')
        extra = ['-DPES13_HORIZON_DIR=' + str(project / 'src/fex')]
    else:
        run(['git', '-C', source, 'diff', '--quiet', 'HEAD'])
    run(['cmake', '-S', source, '-B', build, '-G', 'Ninja',
         '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_TOOLCHAIN_FILE=' + str(source / 'Data/CMake/toolchain_mingw.cmake'),
         '-DMINGW_TRIPLE=aarch64-w64-mingw32', '-DENABLE_LTO=OFF',
         '-DBUILD_TESTING=OFF', '-DENABLE_JEMALLOC_GLIBC_ALLOC=OFF',
         '-DENABLE_ASSERTIONS=OFF', '-DENABLE_CCACHE=OFF',
         '-DENABLE_OFFLINE_TELEMETRY=OFF', '-DENABLE_GDB_SYMBOLS=OFF',
         '-DRANGES_NATIVE=OFF', '-DTUNE_CPU=cortex-a57', '-DTUNE_ARCH=armv8-a',
         '-DOVERRIDE_VERSION=pes13-nx-fex1', '-DOVERRIDE_HASH=' + FEX_COMMIT, *extra])
    run(['cmake', '--build', build, '--target', 'wow64fex', '-j', args.jobs])
    dll = build / 'Bin/libwow64fex.dll'
    if not dll.exists():
        raise SystemExit(f'Expected output is missing: {dll}')
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dll, output / dll.name)
    notices = output / 'licenses'
    names = {'LICENSE', 'LICENSE.md', 'LICENSE.txt', 'LICENSE.rst', 'COPYING', 'COPYING.txt', 'COPYRIGHT'}
    license_files = [source / 'LICENSE']
    for directory in (source / 'External', source / 'Source/Common/cpp-optparse'):
        license_files += [p for p in directory.rglob('*') if p.is_file() and p.name in names and '.git' not in p.parts]
    for license_file in license_files:
        dest = notices / license_file.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(license_file, dest)
    report = {'fex_commit': FEX_COMMIT, 'toolchain': toolchain.name,
              'toolchain_path': str(toolchain),
              'dll': str(dll), 'sha256': hashlib.sha256(dll.read_bytes()).hexdigest(),
              'bytes': dll.stat().st_size, 'horizon_adapter': args.horizon, 'hardware_tested': False,
              'ready_for_game': False}
    if args.horizon:
        report['adapter_sources'] = {
            name: hashlib.sha256((project / name).read_bytes()).hexdigest()
            for name in ['src/fex/horizon_host.h', 'src/fex/module_host.cpp',
                         'src/fex/module_host_call.S',
                         'src/fex/module_memory.cpp', 'src/fex/module_heap.cpp', 'src/fex/module_profile.cpp',
                         'src/fex/module_smc.cpp', 'src/fex/module_exception.cpp',
                         'src/fex/horizon_smc.h', 'src/fex/horizon_stall.h', 'src/fex/horizon_counter.h', 'src/fex/horizon_heap.h',
                         'src/fex/module_counter.cpp', 'tools/fex_horizon_patches.py']}
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
