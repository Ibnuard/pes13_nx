"""Run the native stall observer model under ASan/UBSan in WSL/Linux."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = a.build_root / 'fex-experiment/stall-test'
    subprocess.run(['cc', '-std=c11', '-O1', '-g', '-fsanitize=address,undefined', '-pthread',
                    '-I' + str(root / 'src/fex'), str(root / 'tests/fex_stall_native.c'),
                    '-o', str(target)], check=True)
    result = subprocess.run([str(target)], check=True, capture_output=True, text=True)
    assert 'PASS stall observer:' in result.stdout
    sources = ['tests/fex_stall_native.c', 'src/runtime/fex_stall_probe.h',
               'src/runtime/fex_suspend_observe.h', 'src/fex/horizon_stall.h']
    report = {'passed': True, 'source_sha256': {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sources},
        'sanitizers': ['address', 'undefined'], 'output': result.stdout.strip(),
        'scope': 'Actual observer C source, mocked thread/memory kernel operations; not a Switch run',
        'hardware_tested': False}
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
