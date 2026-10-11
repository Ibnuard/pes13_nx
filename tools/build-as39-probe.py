"""Build an isolated PES13 32/39-bit memory experiment, with paired HOME forwarders.

No Wine/game runtime is changed. Requires the existing approved source snapshot,
devkitPro, the pinned hacBrewPack checkout and a local keyset. Never packages keys.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

from nro_assets import inspect_nro

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.1.1'
TITLE = 'PES13 Address Space Probe'
NRO_PATH = '/switch/pes13-as39-probe/pes13-as39-probe.nro'
PACKER_REV = '745b16ecfc9ce055743067d200572204cb2aac6c'
HBL_REV = '72a94b905816de24817594109fb012a8f7107d8c'
HBL_HASHES = {
    'source/main.c': 'ee3ad5918d6883a2d289da83b945928b3cca88f390d698e0e056f67256d5cc13',
    'source/trampoline.s': '2f11a79cc9a4a162dcef557274076b66480bb256f353d47cea1ef56ab8e11f4e',
    'forwarder.json': 'b528d66f71a44c472e90cb81dc72b859f7c907da41e92f6a265d027c8831795f',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(argv, **kwargs):
    return subprocess.run(list(map(str, argv)), check=True, **kwargs)


def title_id(mode):
    seed = f'{NRO_PATH}|as{mode}|preflight-v1'
    return 0x0500000000000000 | (int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], 'little') & 0x00FFFFFFFFFFF000)


def check_npdm(data, mode, tid):
    """Validate the compiled NPDM, including both capability tables and SVCs."""
    if mode not in (32, 39):
        raise ValueError('Only the control and experimental modes are supported')
    address_type = 2 if mode == 32 else 3
    assert data[:4] == b'META' and data[12] & 1
    assert (data[12] >> 1) & 7 == address_type
    aci, acid = struct.unpack_from('<I4xI', data, 0x70)
    assert data[aci:aci + 4] == b'ACI0' and data[acid + 0x200:acid + 0x204] == b'ACID'
    assert struct.unpack_from('<Q', data, aci + 0x10)[0] == tid
    assert struct.unpack_from('<QQ', data, acid + 0x210) == (tid, tid)
    tables = {}
    for label, base, field in [('ACI0', aci, 0x30), ('ACID', acid, 0x230)]:
        offset, size = struct.unpack_from('<II', data, base + field)
        caps = [x[0] for x in struct.iter_unpack('<I', data[base + offset:base + offset + size])]
        assert [x for x in caps if x & 0xf == 7] == [0x030073f7]
        assert [x for x in caps if x & 0x1ffff == 0xffff] == [0x0004ffff]
        allowed = set()
        for cap in caps:
            if cap & 0x1f == 0xf:
                group = cap >> 29
                allowed.update(group * 24 + bit for bit in range(24) if (cap >> (5 + bit)) & 1)
        required = {0x06, 0x29, 0x4b, 0x4c, 0x73, 0x77, 0x78}
        assert required <= allowed, (label, required - allowed)
        tables[label] = {'cores': [0, 1, 2, 3], 'svc_debug': False,
                         'required_syscalls_present': [hex(x) for x in sorted(required)]}
    return {'native_architecture': 'AArch64', 'address_space_type': address_type,
            'address_bits': mode, 'title_id': f'{tid:016x}', 'capabilities': tables}


def extract_assets(nro):
    size = struct.unpack_from('<I', nro, 0x18)[0]
    icon_off, icon_len, nacp_off, nacp_len = struct.unpack_from('<4Q', nro, size + 8)
    return nro[size + icon_off:size + icon_off + icon_len], bytearray(nro[size + nacp_off:size + nacp_off + nacp_len])


def pack_forwarder(mode, args, sdk, env, hbl, icon, original_nacp, checks):
    work = args.work / f'forwarder-{mode}'
    for name in ('exefs', 'romfs', 'control'):
        (work / name).mkdir(parents=True, exist_ok=True)
    tid = title_id(mode)
    config = json.loads((hbl / 'forwarder.json').read_text())
    config.update(name=f'PES13AS{mode}', address_space_type=2 if mode == 32 else 3,
                  title_id=hex(tid), title_id_range_min=hex(tid), title_id_range_max=hex(tid))
    (work / 'forwarder.json').write_text(json.dumps(config, indent=2) + '\n')
    nacp = bytearray(original_nacp)
    label = f'PES13 {mode}-bit Probe'.encode()
    for language in range(16):
        nacp[language * 0x300:language * 0x300 + 0x200] = label.ljust(0x200, b'\0')
    nacp[0x3025:0x3028] = bytes((0, 0, 1))
    nacp[0x30f1:0x30f4] = bytes(3)
    for offset in (0x3080, 0x3088, 0x3090, 0x3098, 0x3148, 0x3150, 0x3158, 0x3160):
        struct.pack_into('<Q', nacp, offset, 0)
    (work / 'control/control.nacp').write_bytes(nacp)
    (work / 'control/icon_AmericanEnglish.dat').write_bytes(icon)
    for name in ('nextNroPath', 'nextArgv'):
        (work / 'romfs' / name).write_text(NRO_PATH)
    # Both loaders are identical machine code; only NPDM and display title differ.
    shutil.copy2(args.work / 'forwarder.nso', work / 'exefs/main')
    run([sdk / 'tools/bin/npdmtool', work / 'forwarder.json', work / 'exefs/main.npdm'], env=env)
    decoded = check_npdm((work / 'exefs/main.npdm').read_bytes(), mode, tid)
    selected = {}
    for line in args.keys.read_text().splitlines():
        name, separator, value = line.partition('=')
        name, value = name.strip(), value.strip()
        if separator and name in ('header_key', 'key_area_key_application_00'):
            count = 64 if name == 'header_key' else 32
            if not re.fullmatch('[0-9a-fA-F]{' + str(count) + '}', value):
                raise ValueError('Invalid local packing key')
            selected[name] = value
    if len(selected) != 2:
        raise ValueError('Local keyset does not contain the two required packing keys')
    with tempfile.TemporaryDirectory(prefix='pes13-as39-pack-') as temp:
        keyfile = Path(temp) / 'keys.dat'
        keyfile.touch(mode=0o600)
        keyfile.write_text(''.join(f'{k} = {v}\n' for k, v in selected.items()))
        packed = subprocess.run([str(args.packer / 'hacbrewpack'), '--keyset', str(keyfile),
            '--titleid', f'{tid:016x}', '--nologo', '--nopatchnacplogo', '--plaintext', '--keepncadir'],
            cwd=work, capture_output=True)
    # Packer stdout may contain key material; never print or package it.
    if packed.returncode:
        raise RuntimeError(f'Forwarder packing failed with status {packed.returncode}; output suppressed')
    blob = (work / 'hacbrewpack_nsp' / f'{tid:016x}.nsp').read_bytes()
    entries = checks.pfs_files(blob)
    assert len(entries) == 3 and all(name.endswith('.nca') for name in entries)
    for name, content in entries.items():
        assert sha(content)[:32] == name.split('.')[0]
    for name in ('exefs/main', 'exefs/main.npdm', 'control/control.nacp',
                 'control/icon_AmericanEnglish.dat', 'romfs/nextNroPath', 'romfs/nextArgv'):
        assert any((work / name).read_bytes() in nca for nca in entries.values()), name
    destination = args.output / 'forwarders' / f'PES13-AS{mode}-Probe.nsp'
    destination.write_bytes(blob)
    shutil.copy2(work / 'forwarder.json', args.output / 'source' / f'forwarder-{mode}.json')
    return {**decoded, 'nsp': destination.name, 'sha256': sha(blob), 'bytes': len(blob),
            'target': 'sdmc:' + NRO_PATH, 'packed_payload_verified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--keys', type=Path, required=True)
    parser.add_argument('--packer', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/pes13-as39-experiment-v1.1')
    parser.add_argument('--approved', type=Path, default=ROOT / 'local/production-input-fix/approved')
    args = parser.parse_args()
    for name in ('work', 'keys', 'packer', 'output', 'approved'):
        setattr(args, name, getattr(args, name).resolve())
    hbl = args.approved / 'source/forwarder/hbl'
    for name, expected in HBL_HASHES.items():
        if sha((hbl / name).read_bytes()) != expected:
            raise ValueError('Unreviewed loader input: ' + name)
    git = ['git', '-c', 'safe.directory=' + str(args.packer), '-C', str(args.packer)]
    revision = subprocess.check_output([*git, 'rev-parse', 'HEAD'], text=True).strip()
    if revision != PACKER_REV or subprocess.check_output([*git, 'diff', 'HEAD', '--'], text=True):
        raise ValueError('Unreviewed or modified packer checkout')
    args.work.mkdir(parents=True, exist_ok=True)
    # Never reuse an arbitrary distribution directory with stale payloads.
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError('Output must be empty; select a new experimental directory')
    sd = args.output / NRO_PATH.lstrip('/')
    for path in (sd.parent, args.output / 'forwarders', args.output / 'source', args.output / 'licenses'):
        path.mkdir(parents=True, exist_ok=True)
    sdk = Path(os.environ.get('DEVKITPRO', '/opt/devkitpro'))
    env = dict(os.environ, DEVKITPRO=str(sdk))
    cc = sdk / 'devkitA64/bin/aarch64-none-elf-gcc'
    common = ['-O2', '-g', '-march=armv8-a+crc', '-mtune=cortex-a57', '-ffixed-x18', '-fPIE',
              '-ffunction-sections', '-fdata-sections', '-D__SWITCH__', '-isystem', sdk / 'libnx/include']
    objects = []
    for source in ('src/experimental/as39_probe.c', 'src/fex/horizon_jit.c'):
        obj = args.work / (Path(source).stem + '.o')
        run([cc, *common, '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-I', ROOT / 'src/fex',
             '-c', ROOT / source, '-o', obj], env=env)
        objects.append(obj)
    elf = args.work / 'pes13-as39-probe.elf'
    run([cc, *common, '-specs=' + str(sdk / 'libnx/switch.specs'), '-Wl,-wrap,appletInitialize',
         *objects, '-L' + str(sdk / 'libnx/lib'), '-lnx', '-o', elf], env=env)
    nacp = args.work / 'probe.nacp'
    run([sdk / 'tools/bin/nacptool', '--create', TITLE, 'FEXTendo / AndroSwitch', VERSION, nacp], env=env)
    icon_path = ROOT / 'assets/fextendo-v3/nro-icon.jpg'
    run([sdk / 'tools/bin/elf2nro', elf, sd, '--nacp=' + str(nacp), '--icon=' + str(icon_path)], env=env)
    metadata = inspect_nro(sd.read_bytes(), icon_path.read_bytes(), expected_title=TITLE, expected_version=VERSION)
    icon, nacp_bytes = extract_assets(sd.read_bytes())
    loader_objects = []
    for name in ('main.c', 'trampoline.s'):
        obj = args.work / (name + '.o')
        run([cc, *common, '-DVERSION="3.0.0"', '-c', hbl / 'source' / name, '-o', obj], env=env)
        loader_objects.append(obj)
    run([cc, *common, '-specs=' + str(sdk / 'libnx/switch.specs'), '-Wl,-wrap,exit',
         *loader_objects, '-L' + str(sdk / 'libnx/lib'), '-lnx', '-o', args.work / 'forwarder.elf'], env=env)
    run([sdk / 'tools/bin/elf2nso', args.work / 'forwarder.elf', args.work / 'forwarder.nso'])
    spec = importlib.util.spec_from_file_location('forwarder_checks', ROOT / 'tools/build-fextendo-forwarder.py')
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    forwarders = [pack_forwarder(mode, args, sdk, env, hbl, icon, nacp_bytes, checks) for mode in (32, 39)]
    assert forwarders[0]['title_id'] != forwarders[1]['title_id']
    assert all(f['title_id'] != '05b0354496b71000' for f in forwarders)
    for name in ('src/experimental/as39_probe.c', 'src/fex/horizon_jit.c', 'src/fex/horizon_host.h',
                 'src/fex/LICENSE', 'assets/fextendo-v3/nro-icon.jpg', 'docs/AS39-EXPERIMENT.md',
                 'tests/as39_probe_binary.py', 'tests/as39_jit_host.c',
                 'tools/build-as39-probe.py', 'tools/build-fextendo-forwarder.py', 'tools/nro_assets.py'):
        dst = args.output / 'source' / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dst)
    source_approved = args.output / 'source/local/production-input-fix/approved'
    shutil.copytree(hbl, source_approved / 'source/forwarder/hbl', dirs_exist_ok=True)
    shutil.copytree(args.approved / 'licenses/forwarder', source_approved / 'licenses/forwarder', dirs_exist_ok=True)
    shutil.copytree(args.approved / 'licenses/forwarder', args.output / 'licenses', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'src/fex/LICENSE', args.output / 'licenses/PES13-FEX-adapter-MIT.txt')
    shutil.copy2(ROOT / 'docs/AS39-EXPERIMENT.md', args.output / 'README.md')
    report = {'version': VERSION, 'purpose': 'memory/JIT preflight; no x86 guest or game execution',
              'hardware_tested': False, 'nro_sha256': sha(sd.read_bytes()), 'elf_sha256': sha(elf.read_bytes()),
              'metadata': metadata, 'loader_revision': HBL_REV, 'packer_revision': PACKER_REV,
              'forwarders': forwarders, 'production_runtime_modified': False}
    (args.output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
