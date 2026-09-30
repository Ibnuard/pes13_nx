"""Build a FEXTendo NSP: 32-bit no-alias, four cores, Sphaira svcDebug disabled.

Uses the locally supplied keyset only during packing; never bundles keys.
See docs/FEXTENDO-FORWARDER.md for pinned upstream dependencies.
"""
import argparse
import hashlib
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
SPHAIRA_REV = '72a94b905816de24817594109fb012a8f7107d8c'
PACKER_REV = '745b16ecfc9ce055743067d200572204cb2aac6c'
NRO_PATH = '/switch/pes13-fex/pes13-fex.nro'
TITLE_ID = 0x0500000000000000 | (int.from_bytes(
    hashlib.sha256((NRO_PATH * 2).encode()).digest()[:8], 'little') & 0x00FFFFFFFFFFF000)
NAME = 'FEXTendo-PES13-32bit-noalias-4core-svcdebug-off'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def check_npdm(data):
    """Decode both requested and allowed capabilities from the actual NPDM."""
    assert data[:4] == b'META'
    assert data[12] & 1, 'The native runtime must remain AArch64'
    assert (data[12] >> 1) & 7 == 2, 'Expected 32-bit no-alias address space'
    aci, acid = struct.unpack_from('<I4xI', data, 0x70)
    assert data[aci:aci + 4] == b'ACI0'
    assert data[acid + 0x200:acid + 0x204] == b'ACID'
    assert struct.unpack_from('<Q', data, aci + 0x10)[0] == TITLE_ID
    assert struct.unpack_from('<QQ', data, acid + 0x210) == (TITLE_ID, TITLE_ID)
    report = {}
    for name, base, field in [('ACI0', aci, 0x30), ('ACID', acid, 0x230)]:
        offset, size = struct.unpack_from('<II', data, base + field)
        caps = [x[0] for x in struct.iter_unpack('<I', data[base + offset:base + offset + size])]
        cores = [x for x in caps if x & 0xf == 7]
        debug = [x for x in caps if x & 0x1ffff == 0xffff]
        assert cores == [0x030073f7], (name, cores)
        # Exactly Sphaira's Disabled setting: legacy prod flag retained,
        # new svcDebug/force_debug bit (19) false, allow_debug false.
        assert debug == [0x0004ffff], (name, debug)
        report[name] = {'cpu_ids': [0, 1, 2, 3], 'priority_range': [28, 63],
                        'svc_debug': False, 'allow_debug': False,
                        'force_debug': False, 'force_debug_prod': True,
                        'kernel_flags': hex(cores[0]), 'debug_descriptor': hex(debug[0])}
    return report


def pfs_files(data):
    assert data[:4] == b'PFS0'
    count, strings_size = struct.unpack_from('<II', data, 4)
    strings_start = 16 + count * 24
    payload_start = strings_start + strings_size
    result = {}
    for i in range(count):
        offset, size, string_offset = struct.unpack_from('<QQI', data, 16 + i * 24)
        start = strings_start + string_offset
        name = data[start:data.index(0, start, payload_start)].decode()
        assert Path(name).name == name
        assert payload_start + offset + size <= len(data)
        result[name] = data[payload_start + offset:payload_start + offset + size]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keys', required=True, type=Path)
    parser.add_argument('--nro', type=Path, default=ROOT / 'local/fex3/port-cleanup-v1/runtime/payload/pes13-fex.nro')
    parser.add_argument('--sphaira', type=Path, default=ROOT / 'local/forwarder-tools/sphaira')
    parser.add_argument('--packer', type=Path, default=ROOT / 'local/forwarder-tools/hacbrewpack/hacbrewpack')
    parser.add_argument('--libnx-license', type=Path, default=ROOT / 'local/forwarder-tools/libnx-LICENSE.md')
    parser.add_argument('--work', type=Path, default=ROOT / 'local/forwarder-build')
    parser.add_argument('--out', type=Path, default=ROOT / 'dist/fextendo-forwarder')
    args = parser.parse_args()
    for name in ('keys', 'nro', 'sphaira', 'packer', 'libnx_license', 'work', 'out'):
        setattr(args, name, getattr(args, name).resolve())
    libnx_license = args.libnx_license.read_bytes()
    for repo, expected in [(args.sphaira, SPHAIRA_REV), (args.packer.parent, PACKER_REV)]:
        actual = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != expected:
            raise ValueError('Unexpected upstream revision: ' + str(repo))
        if subprocess.check_output(['git', '-C', str(repo), 'diff', 'HEAD', '--'], text=True):
            raise ValueError('Modified upstream source: ' + str(repo))
    blob = args.nro.read_bytes()
    meta = inspect_nro(blob, (ROOT / 'assets/fextendo-v3/nro-icon.jpg').read_bytes(),
                       expected_title='PES13 - FEXTendo', expected_version='0.3.7')
    size = struct.unpack_from('<I', blob, 0x18)[0]
    icon_off, icon_len, nacp_off, nacp_len = struct.unpack_from('<4Q', blob, size + 8)
    icon = blob[size + icon_off:size + icon_off + icon_len]
    nacp = bytearray(blob[size + nacp_off:size + nacp_off + nacp_len])
    # Standard forwarder control settings: the game keeps its files on SD.
    # Avoid the NRO metadata's default profile prompt and unused Switch save.
    nacp[0x3025:0x3028] = bytes((0, 0, 1))
    nacp[0x30f1] = 0  # Automatic logo handling (no custom logo is bundled).
    nacp[0x30f2] = 0  # No save-data-loss confirmation.
    nacp[0x30f3] = 0  # No linked network account requirement.
    for offset in (0x3080, 0x3088, 0x3090, 0x3098, 0x3148, 0x3150, 0x3158, 0x3160):
        struct.pack_into('<Q', nacp, offset, 0)
    for directory in ('exefs', 'romfs', 'control', 'source/hbl/source', 'licenses'):
        (args.work / directory).mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.work / 'control/icon_AmericanEnglish.dat').write_bytes(icon)
    (args.work / 'control/control.nacp').write_bytes(nacp)
    for filename in ('nextNroPath', 'nextArgv'):
        (args.work / 'romfs' / filename).write_text(NRO_PATH)

    hbl = args.sphaira / 'hbl'
    config = json.loads((hbl / 'hbl.json').read_text())
    config.update(name='FEXTendo', address_space_type=2,
                  title_id=hex(TITLE_ID), title_id_range_min=hex(TITLE_ID), title_id_range_max=hex(TITLE_ID))
    for cap in config['kernel_capabilities']:
        if cap['type'] == 'kernel_flags':
            # npdmtool's JSON priority names reflect numeric values.
            cap['value'].update(highest_thread_priority=63, lowest_thread_priority=28,
                                lowest_cpu_id=0, highest_cpu_id=3)
        if cap['type'] == 'debug_flags':
            cap['value'] = dict(allow_debug=False, force_debug_prod=True, force_debug=False)
    (args.work / 'forwarder.json').write_text(json.dumps(config, indent=2) + '\n')
    devkit = Path(os.environ.get('DEVKITPRO', '/opt/devkitpro'))
    env = dict(os.environ, DEVKITPRO=str(devkit))
    cc = devkit / 'devkitA64/bin/aarch64-none-elf-gcc'
    common = ['-O2', '-march=armv8-a+crc', '-mtune=cortex-a57', '-ffixed-x18', '-fPIE',
              '-ffunction-sections', '-fdata-sections', '-D__SWITCH__',
              '-DVERSION="3.0.0"', '-isystem', devkit / 'libnx/include']
    objects = []
    for filename in ('main.c', 'trampoline.s'):
        obj = args.work / (filename + '.o')
        run([cc, *common, '-c', hbl / 'source' / filename, '-o', obj], env=env)
        objects.append(obj)
        shutil.copy2(hbl / 'source' / filename, args.work / 'source/hbl/source' / filename)
    run([cc, *common, '-specs=' + str(devkit / 'libnx/switch.specs'),
         '-Wl,-wrap,exit', *objects, '-L' + str(devkit / 'libnx/lib'), '-lnx',
         '-o', args.work / 'forwarder.elf'], env=env)
    run([devkit / 'tools/bin/elf2nso', args.work / 'forwarder.elf', args.work / 'exefs/main'])
    run([devkit / 'tools/bin/npdmtool', args.work / 'forwarder.json', args.work / 'exefs/main.npdm'])
    npdm = check_npdm((args.work / 'exefs/main.npdm').read_bytes())

    # Restrict the temporary keyset to the two keys needed by keygeneration 1.
    selected = {}
    for line in args.keys.read_text().splitlines():
        name, separator, value = line.partition('=')
        name, value = name.strip(), value.strip()
        if separator and name in ('header_key', 'key_area_key_application_00'):
            length = 64 if name == 'header_key' else 32
            if not re.fullmatch('[0-9a-fA-F]{' + str(length) + '}', value):
                raise ValueError('Invalid required key: ' + name)
            selected[name] = value
    if len(selected) != 2:
        raise ValueError('The keyset is missing required packing keys')
    with tempfile.TemporaryDirectory(prefix='fextendo-pack-') as temporary:
        keyfile = Path(temporary) / 'keys.dat'
        keyfile.write_text(''.join(f'{k} = {v}\n' for k, v in selected.items()))
        keyfile.chmod(0o600)
        packed = run([args.packer, '--keyset', keyfile, '--titleid', f'{TITLE_ID:016x}',
                      '--nologo', '--nopatchnacplogo', '--plaintext', '--keepncadir'],
                     cwd=args.work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # The packer's summary includes its content encryption key; omit that line.
    (args.work / 'pack.log').write_text('\n'.join(
        line for line in packed.stdout.splitlines() if 'key area key 2:' not in line.lower()) + '\n')
    payload = (args.work / 'hacbrewpack_nsp' / f'{TITLE_ID:016x}.nsp').read_bytes()
    entries = pfs_files(payload)
    assert len(entries) == 3 and all(name.endswith('.nca') for name in entries)
    for name, content in entries.items():
        assert digest(content)[:32] == name.split('.')[0], 'NCA content ID mismatch'
    assert check_npdm((args.work / 'exefs/main.npdm').read_bytes()) == npdm
    destination = args.out / (NAME + '.nsp')
    destination.write_bytes(payload)
    report = {'title': meta['title'], 'author': meta['author'], 'version': meta['version'],
              'title_id': f'{TITLE_ID:016x}', 'nro_path': 'sdmc:' + NRO_PATH,
              'address_space': '32-bit no-alias', 'native_architecture': 'AArch64',
              'cpu_cores': 4, 'svc_debug': False, 'capabilities': npdm,
              'icon_identical_to_nro': True, 'icon_sha256': digest(icon),
              'source_nro_sha256': digest(blob), 'nro_metadata': meta,
              'sphaira_revision': SPHAIRA_REV, 'hacbrewpack_revision': PACKER_REV,
              'nsp_bytes': len(payload), 'nsp_sha256': digest(payload),
              'nca_files': {name: digest(value) for name, value in entries.items()},
              'device_tested': False}
    (args.out / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    (args.out / 'icon.jpg').write_bytes(icon)
    shutil.copytree(args.work / 'source', args.out / 'source', dirs_exist_ok=True)
    shutil.copy2(__file__, args.out / 'source/build-fextendo-forwarder.py')
    shutil.copy2(ROOT / 'tools/nro_assets.py', args.out / 'source/nro_assets.py')
    shutil.copy2(args.work / 'forwarder.json', args.out / 'source/hbl/forwarder.json')
    (args.out / 'licenses').mkdir(exist_ok=True)
    shutil.copy2(args.sphaira / 'LICENSE', args.out / 'licenses/Sphaira-GPL-3.0.txt')
    shutil.copy2(hbl / 'nx-hbloader.LICENSE.md', args.out / 'licenses/nx-hbloader-ISC.txt')
    (args.out / 'licenses/libnx-ISC.txt').write_bytes(libnx_license)
    print(json.dumps({'nsp': str(destination), 'bytes': len(payload),
                      'sha256': digest(payload), 'settings_verified': True}, indent=2))


if __name__ == '__main__':
    main()
