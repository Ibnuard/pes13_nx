"""Build a narrow FEX candidate from the hash-pinned delivered module source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from fex_protect_roundtrip_patches import apply
from fex_toolchain import cmake_provenance

PIN = 'e2f973fe931e6dc2ce523795e51ca1ac3ca85816'
BASE_DLL = '17dcf3e78371a717a9c41da5bffa4d6a5755d6479afa0a8ade12abcc7639ad23'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('upstream', 'approved', 'work', 'output', 'toolchain'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=3)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    upstream, approved, work, output, toolchain = (
        getattr(args, name).resolve() for name in ('upstream', 'approved', 'work', 'output', 'toolchain'))
    git = ['git', '-c', 'safe.directory=' + str(upstream), '-C', str(upstream)]
    assert subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip() == PIN
    subprocess.run(git + ['diff', '--quiet', 'HEAD'], check=True)
    build_info = json.loads((approved / 'evidence/rollback-fex/module/build.json').read_text())
    changes = json.loads((approved / 'evidence/rollback-fex/module/patches.json').read_text())
    assert build_info['sha256'] == BASE_DLL and build_info['fex_commit'] == PIN
    assert changes['fex_commit'] == PIN
    source, adapter, build = work / 'source', work / 'adapter', work / 'build'
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        shutil.copytree(upstream, source, symlinks=True, ignore=shutil.ignore_patterns('.git'))
    frozen = approved / 'source/rollback-fex'
    frozen_files = {}
    for entry in changes['files']:
        name = entry['path']
        original = frozen / 'generated/fex' / name
        assert sha(original) == entry['patched_sha256'], name
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
        frozen_files[name] = sha(original)
    # This upstream header was not patched by the delivered build.
    header = 'Source/Windows/Common/InvalidationTracker.h'
    shutil.copy2(upstream / header, source / header)
    for name in ('Source/Windows/Common/InvalidationTracker.cpp', header, 'Source/Windows/WOW64/Module.cpp'):
        destination = work / 'before' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, destination)
    shutil.copytree(frozen / 'src/fex', adapter, dirs_exist_ok=True)
    adapter_hashes = {}
    for name, digest in build_info['adapter_sources'].items():
        if not name.startswith('src/fex/'):
            continue
        path = adapter / Path(name).name
        assert sha(path) == digest, name
        adapter_hashes[path.name] = digest
    changed = apply(source)
    scripts = {Path(__file__).name: sha(Path(__file__)),
               'fex_protect_roundtrip_patches.py': sha(Path(__file__).with_name('fex_protect_roundtrip_patches.py'))}
    report = {'kind': 'kit6-fex-protection-roundtrip', 'fex_commit': PIN,
              'baseline_dll_sha256': BASE_DLL, 'frozen_sources': frozen_files,
              'adapter_sources': adapter_hashes, 'candidate_sources': {name: sha(source / name) for name in sorted(changed)},
              'build_scripts': scripts, 'toolchain': toolchain.name,
              'baseline_toolchain': build_info['toolchain'], 'hardware_tested': False,
              'scope': 'Only memory-protection notification/old-permission semantics; no profile or optimizer changes.'}
    (output / 'source-report.json').write_text(json.dumps(report, indent=2) + '\n')
    if args.prepare_only:
        print(json.dumps({'prepared': str(source), 'changed': sorted(changed)}), flush=True)
        return
    cmake_provenance(build, toolchain)
    env = dict(os.environ, PATH=str(toolchain / 'bin') + os.pathsep + os.environ['PATH'])
    def run(command):
        print('+', ' '.join(map(str, command)), flush=True)
        subprocess.run(list(map(str, command)), check=True, env=env)
    run(['cmake', '-S', source, '-B', build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_TOOLCHAIN_FILE=' + str(source / 'Data/CMake/toolchain_mingw.cmake'),
         '-DMINGW_TRIPLE=aarch64-w64-mingw32', '-DENABLE_LTO=OFF', '-DBUILD_TESTING=OFF',
         '-DENABLE_JEMALLOC_GLIBC_ALLOC=OFF', '-DENABLE_ASSERTIONS=OFF', '-DENABLE_CCACHE=OFF',
         '-DENABLE_OFFLINE_TELEMETRY=OFF', '-DENABLE_GDB_SYMBOLS=OFF', '-DRANGES_NATIVE=OFF',
         '-DTUNE_CPU=cortex-a57', '-DTUNE_ARCH=armv8-a', '-DOVERRIDE_VERSION=pes13-nx-fex1',
         '-DOVERRIDE_HASH=' + PIN, '-DPES13_HORIZON_DIR=' + str(adapter)])
    run(['cmake', '--build', build, '--target', 'wow64fex', '-j', args.jobs])
    dll = build / 'Bin/libwow64fex.dll'
    shutil.copy2(dll, output / dll.name)
    report.update({'built': True, 'dll_sha256': sha(dll), 'dll_bytes': dll.stat().st_size,
                   'compiler_provenance': cmake_provenance(build, toolchain, required=True)})
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'built': str(dll), 'sha256': report['dll_sha256']}), flush=True)


if __name__ == '__main__':
    main()
