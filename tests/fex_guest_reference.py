"""Check the original x86 smoke/stress program on Windows, independent of FEX."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile
import argparse


def main():
    if os.name != 'nt':
        raise SystemExit('This reference test runs on Windows.')
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stress', action='store_true')
    args = parser.parse_args()
    work = project / ('local/fex3' if args.stress else 'local/fex2')
    exe = work / ('payload/fex-stress.exe' if args.stress else 'payload/fex-smoke.exe')
    expected = json.loads((work / 'runtime-build.json').read_text())['guest_sha256']
    assert hashlib.sha256(exe.read_bytes()).hexdigest() == expected
    # Retain evidence; the test touches only this fresh local directory.
    target = Path(tempfile.mkdtemp(prefix='pc-reference-', dir=work))
    run = subprocess.run([str(exe)], cwd=target, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    log = (target / 'fex-guest.log').read_text()
    success = ('[FEX3-GUEST] PASS all checks: 16 workers, 256 SMC updates, 256 handled faults'
               if args.stress else '[FEX2-GUEST] PASS all checks')
    assert run.returncode == 0 and log.rstrip().endswith(success), log
    report = {'passed': True, 'guest_sha256': expected, 'log': str(target / 'fex-guest.log'),
              'scope': 'Original guest test on Windows PC; not FEX and not Switch'}
    (work / 'guest-reference.json').write_text(json.dumps(report, indent=2) + '\n')
    print(log)
    print(report['scope'])


if __name__ == '__main__':
    main()
