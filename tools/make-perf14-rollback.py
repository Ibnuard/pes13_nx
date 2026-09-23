"""Recover the exact PERF11 NRO from its preserved ELF and matching assets."""
from pathlib import Path
import hashlib
import os
import subprocess

p = Path(__file__).resolve().parents[1]
root = Path(os.environ.get('PES_BUILD_ROOT', str(Path.home()/'.cache/pes13-nx')))
out = p/'local/perf14'
nacp = out/'rollback-perf11.nacp'
nro = out/'rollback-perf11.nro'
subprocess.run(['/opt/devkitpro/tools/bin/nacptool', '--create', 'PES13-NX PERF11',
                'PES13-NX', '0.2.0', str(nacp)], check=True)
subprocess.run(['/opt/devkitpro/tools/bin/elf2nro',
                str(root/'runtime-perf11-box64-044/wine-nx-runtime.elf'), str(nro),
                f'--nacp={nacp}', f'--icon={p}/assets/icon.jpg'], check=True)
digest = hashlib.sha256(nro.read_bytes()).hexdigest()
assert digest == '98ce549f65046fa44457dc36508cc1e5c65019cb94156e706e6d109ed64190f4', digest
print('Recovered byte-identical PERF11 NRO:', digest)
