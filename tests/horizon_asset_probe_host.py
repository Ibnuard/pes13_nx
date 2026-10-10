"""Exercise the bounded Debug-only native pipe snapshot under ASan/UBSan."""
import argparse, hashlib, json, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    binary = args.output.with_suffix('.test').resolve()
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
        '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-pthread',
        '-I', str(ROOT/'src/runtime'), str(ROOT/'tests/horizon_asset_probe.c'),
        '-o', str(binary)], check=True)
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    report = dict(passed=True, hardware_tested=False, sanitizers=['address', 'undefined'],
        result=result.stdout.strip(), sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        for name in ('src/runtime/horizon_asset_probe.h', 'tests/horizon_asset_probe.c',
                     'tests/horizon_asset_probe_host.py')})
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(result.stdout)

if __name__ == '__main__': main()
