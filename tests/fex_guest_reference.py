"""Check the original x86 smoke program on the Windows PC, independent of FEX."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile


def main():
    if os.name != 'nt':
        raise SystemExit('This reference test runs on Windows.')
    project = Path(__file__).resolve().parents[1]
    work = project / 'local/fex2'
    exe = work / 'payload/fex-smoke.exe'
    expected = json.loads((work / 'runtime-build.json').read_text())['guest_sha256']
    assert hashlib.sha256(exe.read_bytes()).hexdigest() == expected
    # Retain evidence; the test touches only this fresh local directory.
    target = Path(tempfile.mkdtemp(prefix='pc-reference-', dir=work))
    run = subprocess.run([str(exe)], cwd=target, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    log = (target / 'fex-guest.log').read_text()
    assert run.returncode == 0 and log.rstrip().endswith('[FEX2-GUEST] PASS all checks'), log
    report = {'passed': True, 'guest_sha256': expected, 'log': str(target / 'fex-guest.log'),
              'scope': 'Original guest test on Windows PC; not FEX and not Switch'}
    (work / 'guest-reference.json').write_text(json.dumps(report, indent=2) + '\n')
    print(log)
    print(report['scope'])


if __name__ == '__main__':
    main()
