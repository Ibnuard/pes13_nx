"""Assemble the already validated generic-memory probe as copy-ready folders.

Derives one additional test entry from this console's existing EMUMMC entry.
Never writes to the supplied INI/KIP or to an actual SD card.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT / 'dist/fextendo-low-window-v1')
    p.add_argument('--ini', type=Path, required=True)
    p.add_argument('--hoc', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    boot = json.loads((out / 'boot/build.json').read_text())
    validation = json.loads((out / 'validation.json').read_text())
    fw = json.loads((out / 'probe-build.json').read_text())
    assert validation['status'] == 'PASS' and validation['boot_files'] == boot['files']
    for name, digest in boot['files'].items(): assert sha(out / 'boot' / name) == digest, name
    for name, digest in boot['prepared']['inputs'].items(): assert sha(ROOT / name) == digest, name
    for name, digest in fw['source_files'].items(): assert sha(ROOT / name) == digest, name
    for name, digest in validation['tests'].items(): assert sha(ROOT / name) == digest, name
    for entry in fw['forwarders']: assert sha(out / 'forwarders' / entry['nsp']) == entry['sha256']
    assert sha(out / fw['target'].lstrip('/')) == fw['nro_sha256']
    assert sha(a.hoc) == boot['hoc_input_sha256']
    ini_bytes = a.ini.read_bytes()
    text = ini_bytes.decode('utf-8-sig')
    assert text.count('[CFW (EMUMMC)]') == 1
    lines = []
    for line in text.split('[CFW (EMUMMC)]', 1)[1].splitlines():
        if line.startswith('[') or line.startswith('{'): break
        if line.strip(): lines.append(line.strip())
    assert lines.count('pkg3=atmosphere/package3') == 1 and lines.count('emummcforce=1') == 1
    assert lines.count('kip1=atmosphere/kips/hoc.kip') == 1
    assert not any(line.startswith('kernel=') for line in lines)
    newlines = []
    for line in lines:
        if line == 'kip1=atmosphere/kips/hoc.kip': line = 'kip1=atmosphere/fextendo-memory-v1/loader-hoc.kip'
        newlines.append(line)
        if line == 'pkg3=atmosphere/package3': newlines.append('kernel=atmosphere/fextendo-memory-v1/mesosphere.bin')
    entry = '[FEXTendo Memory v1 TEST]\n' + '\n'.join(newlines) + '\n'
    ini_output = out / 'bootloader/ini/fextendo-memory-v1.ini'
    ini_output.parent.mkdir(parents=True, exist_ok=True)
    ini_output.write_text(entry, encoding='utf-8', newline='\n')
    boot_output = out / 'atmosphere/fextendo-memory-v1'
    boot_output.mkdir(parents=True, exist_ok=True)
    for name in ('mesosphere.bin', 'loader-hoc.kip'): shutil.copy2(out / 'boot' / name, boot_output / name)
    paths = set(boot['prepared']['inputs']) | set(fw['source_files']) | set(validation['tests']) | {
        'tools/package-fextendo-memory.py', 'docs/FEXTENDO-MEMORY-ABI-V1.md',
        'tools/build-as39-probe.py', 'tools/build-fextendo-forwarder.py', 'tools/nro_assets.py',
        'src/fex/horizon_host.h', 'src/fex/LICENSE', 'assets/fextendo-v3/nro-icon.jpg'}
    for name in sorted(paths):
        dest = out / 'source' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dest)
    approved = ROOT / 'local/production-input-fix/approved'
    for folder in ('source/forwarder/hbl', 'licenses/forwarder'):
        shutil.copytree(approved / folder, out / 'source/local/production-input-fix/approved' / folder, dirs_exist_ok=True)
    # The reference model is a read-only test dependency; retain its exact hash.
    reference = ROOT.parent / 'sleepingdogs-fex'
    for name in ('tests/check_forwarder_startup_binary.py', 'tools/port_common.py'):
        dest = out / 'source/reference-sleepingdogs' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(reference / name, dest)
    shutil.copy2(ROOT / 'docs/FEXTENDO-MEMORY-ABI-V1.md', out / 'README.md')
    instructions = '''FEXTendo Memory v1 - EXPERIMENTAL BOOT/PROBE, NOT A PES UPDATE

For the reference HOS 22.5.0 / AMS 1.11.2 / HOC 2.5.1 setup only.
The included HOC keeps this console's supplied CUST settings unchanged.

1. Copy atmosphere/, bootloader/, switch/ to the SD root.
2. Install the three forwarders/*.nsp.
3. Reboot once: Hekate > More configs > FEXTendo Memory v1 TEST.
4. Run CONTROL, exit with +; run OPTIN-A, exit; run OPTIN-B, exit.
   Expected: [SUMMARY] PASS on all three. Low-map REJECTED is correct for CONTROL.
5. Return the three logs from switch/fextendo-memory-probe/.

Do not use these NSPs to start PES. They only exercise memory mappings and JIT.
No game runtime, prefix, saves, existing forwarder, package3, hekate_ipl.ini or
original hoc.kip is replaced. For existing game builds, reboot to the original
Hekate entry. The old Sleeping Dogs Title-ID-specific forwarder still needs its
previous boot entry until a descriptor-bearing replacement is provided.

After device validation and game integration, compatible new games will need
only their own forwarder + runtime, without a per-title kernel rebuild/reboot.
Read README.md for the ABI, limits, source links, and validation scope.
'''
    (out / 'INSTALL.txt').write_text(instructions, encoding='utf-8', newline='\n')
    assert not any((out / path).exists() for path in ('bootloader/hekate_ipl.ini', 'atmosphere/package3', 'atmosphere/kips/hoc.kip'))
    assert a.ini.read_bytes() == ini_bytes and sha(a.hoc) == boot['hoc_input_sha256']
    package = {'hardware_tested': False, 'purpose': 'Generic opt-in low-window boot + standalone probe',
               'initial_reboot_required': True, 'game_runtime_changed': False,
               'original_ini_sha256': hashlib.sha256(ini_bytes).hexdigest(),
               'hoc_sha256': sha(a.hoc), 'source_abi': 'fxtmem-v1'}
    (out / 'package.json').write_text(json.dumps(package, indent=2) + '\n')
    files = sorted(path for path in out.rglob('*') if path.is_file() and path.name != 'SHA256SUMS.txt')
    for path in files:
        assert path.suffix.lower() not in ('.keys', '.log', '.zip'), path
        assert path.name not in ('keys.dat', 'prod.keys', 'title.keys'), path
    (out / 'SHA256SUMS.txt').write_text(''.join(sha(path) + '  ' + path.relative_to(out).as_posix() + '\n' for path in files))
    print(f'Copy-ready package verified: {len(files)} files. No ZIP; no installed files changed.')


if __name__ == '__main__': main()
