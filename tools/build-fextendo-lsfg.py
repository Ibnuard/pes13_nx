#!/usr/bin/env python3
"""Build pinned GPL LSFG native backend locally; never fetch Lossless.dll."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PIN = '8b0da2661c6f3473a7fccc8ba643880050e71642'
URL = 'https://git.lsfg-vk.dev/lsfg-vk-archive.git'
PROJECT = Path(__file__).resolve().parent.parent


def run(*args, cwd=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=PROJECT / 'local/fex3/lsfg-build')
    parser.add_argument('--vulkan-include', type=Path, default=Path.home() / '.cache/pes13-nx-macos/mesa-switch/include')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    source, build, prefix = (work / name for name in ('source', 'fextendo-build', 'install'))
    port = PROJECT / 'third_party/lsfg-horizon'
    if not (source / '.git').exists():
        run('git', 'init', source)
        run('git', 'fetch', '--depth=1', URL, PIN, cwd=source)
        run('git', 'checkout', '--detach', 'FETCH_HEAD', cwd=source)
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    if actual != PIN:
        raise SystemExit(f'Refusing unrelated LSFG checkout {actual}')
    patch = port / 'horizon.patch'
    applied = subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)], cwd=source, capture_output=True)
    if applied.returncode:
        run('git', 'apply', '--check', patch, cwd=source)
        run('git', 'apply', patch, cwd=source)
    run('cmake', '-S', port, '-B', build, '-G', 'Ninja',
        f'-DCMAKE_TOOLCHAIN_FILE={port / "cmake/switch.cmake"}',
        '-DCMAKE_BUILD_TYPE=Release', f'-DCMAKE_INSTALL_PREFIX={prefix}',
        f'-DLSFG_SOURCE={source}', f'-DLSFG_VULKAN_INCLUDE={args.vulkan_include.resolve()}')
    run('cmake', '--build', build, '--parallel', args.jobs)
    run('cmake', '--install', build)
    manifest = {'upstream': URL, 'commit': PIN, 'port_commit': '0fff003d388139829b303382b13c14c5344672b2',
                'horizon_patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
                'library_sha256': hashlib.sha256((prefix / 'lib/liblsfg-vk.a').read_bytes()).hexdigest(),
                'fixed_x18': True, 'prefix': str(prefix), 'proprietary_payload_included': False}
    (work / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
