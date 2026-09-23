"""Isolate the post-present BIGBLOCK policy without changing the runtime/DXVK."""
from pathlib import Path
import hashlib
import json
import zipfile

project = Path(__file__).resolve().parents[1]
prefix = 'switch/pes13-nx/'
readme = '''PERF11 fixed Compatible test

Close PES through HOME -> X -> Close. Copy the switch folder to the SD root,
overwriting files. Keep the current NRO, DXVK, settings.dat and game files.

compatible-only disables the inherited post-present BIGBLOCK=1 policy.
BIGBLOCK remains 0 throughout boot and gameplay; other preset values stay
SAFEFLAGS=2 FASTNAN=0 FASTROUND=0 X87DOUBLE=1 STRONGMEM=1 CALLRET=0.
The expected telemetry is enabled=0 active=0 BIGBLOCK=0.
translation_attempts=0 in this mode is a disabled-policy counter, NOT proof
that Box64 is not translating code. Sampling and verbose stay disabled.

Restore-post-present sets the old policy back on. Install one package only.
This is a controlled stability experiment, not a confirmed hang fix. Do not
delete caches or change DXVK at the same time. Save the log from a stuck run
before relaunching, then save the successful run separately if it succeeds.
Neither package contains an NRO or replaces game/save files.
'''
preset = (project/'config/drive_c/PES13/pes2013.box64.txt').read_bytes()
assert b'BOX64_DYNAREC_BIGBLOCK=0' in preset
for name, enabled in [('compatible-only',False),('restore-post-present',True)]:
    files = {
        prefix+'perf8-turbo.txt': b'1\n' if enabled else b'0\n',
        prefix+'profile.txt': b'0\n',
        prefix+'drive_c/PES13/pes2013.box64.txt': preset,
        prefix+'drive_c/PES13/pes2013.wine-nx.txt':
            (project/'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes(),
        'PERF11-COMPATIBLE.txt': readme.encode(),
    }
    files['manifest.json'] = json.dumps({'variant':name,'hardware_tested':False,
        'files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()}},indent=2).encode()
    dest=project/'dist'/f'pes13-perf11-{name}.zip'
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in files.items(): z.writestr(n,b)
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        assert all(z.read(n)==b for n,b in files.items())
    print(dest,hashlib.sha256(dest.read_bytes()).hexdigest())
