"""Validate bounded worklists, exact decoder patch scope and linked provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from fex_decode_worklist_patches import apply


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    expected = {}

    def replace(name, old, new, count=1):
        if name not in expected:
            expected[name] = subprocess.check_output(
                ['git', '-C', str(args.source), 'show', 'HEAD:' + name], text=True)
        if expected[name].count(old) != count:
            raise ValueError('Unexpected pinned source: ' + name)
        expected[name] = expected[name].replace(old, new)

    apply(replace)
    for name, text in expected.items():
        if (args.source / name).read_text() != text:
            raise ValueError('Decoder changed outside the worklist replacement: ' + name)
    results = {}
    for mode, flags in (('sanitized', ['-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all']),
                        ('optimized', ['-O2'])):
        exe = args.work / ('decode-worklists-' + mode)
        subprocess.run(['clang++', '-std=c++20', *flags, '-I' + str(ROOT / 'src/fex'),
                        str(ROOT / 'tests/fex_decode_worklists.cpp'), '-o', str(exe)], check=True)
        result = subprocess.check_output([str(exe)], text=True)
        results[mode] = {'checks': result.splitlines()[0],
                         'workloads': [json.loads(row) for row in result.splitlines()[1:]]}
    build = json.loads((args.work / 'module/build.json').read_text())
    patches = json.loads((args.work / 'module/patches.json').read_text())
    for name in expected:
        if not any(r['path'] == name and r['patched_sha256'] == digest(args.source / name) for r in patches['files']):
            raise ValueError('Source not bound to build: ' + name)
    for name in ('src/fex/horizon_decode_set.h', 'tools/fex_decode_worklist_patches.py',
                 'src/fex/module_profile.cpp', 'tools/fex_horizon_patches.py'):
        if build['adapter_sources'][name] != digest(ROOT / name):
            raise ValueError('Stale adapter in build: ' + name)
    dll = args.work / 'module/libwow64fex.dll'
    if digest(dll) != build['sha256'] or '[FEX3-DECODE] v1'.encode() not in dll.read_bytes():
        raise ValueError('Wrong candidate module')
    report = {'passed': True, 'hardware_tested': False, 'dll_sha256': build['sha256'],
        'patches_sha256': digest(args.work / 'module/patches.json'),
        'source_hashes': {name: digest(ROOT / name) for name in
            ('tests/fex_decode_worklists.cpp', 'tests/fex_decode_worklists.py',
             'src/fex/horizon_decode_set.h', 'tools/fex_decode_worklist_patches.py',
             'tools/build-fex-module.py', 'tools/fex_horizon_patches.py', 'src/fex/module_profile.cpp')},
        'decoder_source_hashes': {name: digest(args.source / name) for name in expected},
        'results': results,
        'limits': ['Synthetic decoder-worklist workload, not the whole FEX compiler or Switch FPS.',
                   'Actual allocation callback counts saved on PES13 and device frame times remain unmeasured.',
                   'Sorted branch order, unique addresses and large-worklist fallback are preserved; no new scheduling policy.']}
    (args.work / 'decode-worklists.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
