"""Diagnostic overlays for the PERF11 fixed-Compatible runtime."""
from pathlib import Path
import hashlib
import json
import zipfile

p = Path(__file__).resolve().parents[1]
prefix = 'switch/pes13-nx/'
config = (p/'config/drive_c/PES13/pes2013.wine-nx.txt').read_text()
assert config.count('profile=0') == 1
readme = '''PERF11 CPU sampling — diagnostic, not an FPS improvement

Requires the existing PERF11 NRO (pes13-nx-0.2.0-perf11-box64-044).
Close through HOME -> X -> Close, install sample-on's switch folder to SD
root and overwrite. Use the same clocks, NRO, DXVK and game settings.
This retains BIGBLOCK=0 throughout the run and verbose=0.

Reproduce the slow splash/intro, wait about 60 seconds after it appears,
then close and save pes13-nx.log BEFORE launching again. If frozen, save
whatever log was produced. Mark which part of the intro was visible.
Expected: [INIT] profiler on and [PROF] sampler started, then [PROF] records.
If permissions prevent sampling, return that log; don't change the forwarder.

Install sample-off afterward. The sampler pauses threads briefly and adds
overhead; measured FPS with sampling enabled must not be compared directly
with production FPS. It samples where threads are, including waiting threads,
not CPU cycles exclusively. No per-frame verbose logging is enabled.

Neither ZIP changes NRO, DXVK, game data, settings.dat or saves. The PERF11
build ELF must be used for native address symbolization, not the PERF8 ELF.
'''
for enabled in (True, False):
    name = 'on' if enabled else 'off'
    files = {
        prefix+'profile.txt': b'1\n' if enabled else b'0\n',
        prefix+'perf8-turbo.txt': b'0\n',
        prefix+'drive_c/PES13/pes2013.wine-nx.txt':
            config.replace('profile=0',f'profile={int(enabled)}').encode(),
        'PERF11-SAMPLING.txt': readme.encode(),
    }
    files['manifest.json'] = json.dumps({
        'diagnostic': True, 'sampling': enabled, 'BIGBLOCK':0,
        'runtime':'pes13-nx-0.2.0-perf11-box64-044',
        'files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()},
    },indent=2).encode()
    dest=p/'dist'/f'pes13-perf11-sample-{name}.zip'
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in files.items(): z.writestr(n,b)
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        assert all(z.read(n)==b for n,b in files.items())
    print(dest,hashlib.sha256(dest.read_bytes()).hexdigest())
