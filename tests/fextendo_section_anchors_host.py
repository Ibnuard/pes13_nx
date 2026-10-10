"""Reproduce the Kitserver anchor failure with real shared Linux mappings."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'before', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    checks = []
    with tempfile.TemporaryDirectory(prefix='fextendo-anchors-') as tmp:
        for old in (True, False):
            binary = Path(tmp)/('before' if old else 'candidate')
            include = (a.before if old else a.source)/'dlls/ntdll/unix'
            subprocess.run(['gcc', '-O1', '-g', '-std=gnu11', '-Wall', '-Wextra', '-pthread',
                            '-fsanitize=address,undefined',
                            *(['-DTEST_ANCHOR_BASELINE'] if old else []),
                            '-I'+str(include), str(ROOT/'tests/fextendo_section_anchors.c'),
                            '-o', str(binary)], check=True)
            r = subprocess.run([str(binary)], text=True, capture_output=True)
            print(r.stdout, r.stderr, end='', flush=True)
            r.check_returncode()
            checks.append({'baseline': old, 'passed': True, 'output': r.stdout})
    names = ('tools/fextendo_section_anchor_patches.py', 'tests/fextendo_section_anchors.c',
             'tests/fextendo_section_anchors_host.py', 'tests/fextendo_page_store.c')
    report = {'passed': True, 'hardware_tested': False, 'checks': checks,
              'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'],
              'sources': {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},
              'generated_sources': {n: hashlib.sha256((a.source/n).read_bytes()).hexdigest()
                                    for n in ('dlls/ntdll/unix/horizon.c', 'dlls/ntdll/unix/horizon_memfile.h')}}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
