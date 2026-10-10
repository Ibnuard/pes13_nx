"""Build one NRO and three independent HOME forwarders for memory ABI v1.

Control lacks the ExeFS descriptor. Opt-in A and B request the same layout under
different Title IDs. No changes to installed game forwarders or runtime files.
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
from fextendo_low_window import ROOT, SOURCE, exact, descriptor

TARGET = '/switch/fextendo-memory-probe/fextendo-memory-probe.nro'
TAGS = ('control', 'optin-a', 'optin-b')
PROBE_REVISION = 'probe-r2'
PROBE_VERSION = '0.1.1'


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def run(*cmd, **kw): return subprocess.run(list(map(str, cmd)), check=True, **kw)
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
def title_id(tag, target=TARGET):
    digest = hashlib.sha256((target + '|fxtmem-v1|' + tag).encode()).digest()
    return 0x0500000000000000 | (int.from_bytes(digest[:8], 'little') & 0x00fffffffffff000)
def write_json(p, obj): p.write_text(json.dumps(obj, indent=2) + '\n')


def build_probe(work, output, sdk, env):
    cc = sdk / 'devkitA64/bin/aarch64-none-elf-gcc'
    common = ['-O2', '-g', '-march=armv8-a+crc', '-mtune=cortex-a57', '-ffixed-x18', '-fPIE',
              '-ffunction-sections', '-fdata-sections', '-D__SWITCH__', '-isystem', sdk / 'libnx/include']
    objects = []
    for source in (SOURCE / 'probe.c', ROOT / 'src/fex/horizon_jit.c'):
        obj = work / (source.stem + '.o')
        run(cc, *common, '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-I', ROOT / 'src/fex', '-c', source, '-o', obj, env=env)
        objects.append(obj)
    elf = work / 'memory-probe.elf'
    run(cc, *common, '-specs=' + str(sdk / 'libnx/switch.specs'), '-Wl,-wrap,appletInitialize', *objects,
        '-L' + str(sdk / 'libnx/lib'), '-lnx', '-o', elf, env=env)
    run(sdk / 'tools/bin/nacptool', '--create', 'FEXTendo Memory Probe', 'FEXTendo', PROBE_VERSION, work / 'probe.nacp', env=env)
    run(sdk / 'tools/bin/elf2nro', elf, output, '--nacp=' + str(work / 'probe.nacp'),
        '--icon=' + str(ROOT / 'assets/fextendo-v3/nro-icon.jpg'), env=env)
    return elf


def pack(tag, args, sdk, env, hbl, icon, nacp, base, checks, *,
         target=TARGET, label=None, npdm_name='FXTMemProbe', output_name=None):
    work = args.work / tag
    for folder in ('exefs', 'romfs', 'control'): (work / folder).mkdir(parents=True, exist_ok=True)
    tid = title_id(tag, target)
    npdm = json.loads((hbl / 'forwarder.json').read_text())
    npdm.update(name=npdm_name, address_space_type=3, title_id=hex(tid),
                title_id_range_min=hex(tid), title_id_range_max=hex(tid), system_resource_size='0x1000000')
    write_json(work / 'forwarder.json', npdm)
    nacp = bytearray(nacp)
    label = (label or 'FEXTendo Memory ' + tag.upper()).encode()
    assert len(label) < 0x200
    for lang in range(16): nacp[lang * 0x300:lang * 0x300 + 0x200] = label.ljust(0x200, b'\0')
    nacp[0x3025:0x3028] = bytes((0, 0, 1))
    nacp[0x30f1:0x30f4] = bytes(3)
    for offset in (0x3080, 0x3088, 0x3090, 0x3098, 0x3148, 0x3150, 0x3158, 0x3160):
        struct.pack_into('<Q', nacp, offset, 0)
    (work / 'control/control.nacp').write_bytes(nacp)
    (work / 'control/icon_AmericanEnglish.dat').write_bytes(icon)
    (work / 'romfs/nextNroPath').write_text(target)
    (work / 'romfs/nextArgv').write_text(target + ' ' + tag)
    shutil.copy2(args.work / 'forwarder.nso', work / 'exefs/main')
    if tag != 'control': (work / 'exefs/fxtmem').write_bytes(descriptor())
    run(sdk / 'tools/bin/npdmtool', work / 'forwarder.json', work / 'exefs/main.npdm', env=env)
    parsed = base.check_npdm((work / 'exefs/main.npdm').read_bytes(), 39, tid)
    assert struct.unpack_from('<I', (work / 'exefs/main.npdm').read_bytes(), 0x14)[0] == 16777216
    selected = {}
    for line in args.keys.read_text().splitlines():
        name, separator, value = line.partition('=')
        name, value = name.strip(), value.strip()
        if separator and name in ('header_key', 'key_area_key_application_00'):
            size = 64 if name == 'header_key' else 32
            if not re.fullmatch('[0-9a-fA-F]{' + str(size) + '}', value): raise ValueError('Invalid packing key')
            selected[name] = value
    if len(selected) != 2: raise ValueError('Required local packing keys missing')
    with tempfile.TemporaryDirectory(prefix='fxtmem-pack-') as folder:
        keys = Path(folder) / 'keys.dat'
        keys.touch(mode=0o600)
        keys.write_text(''.join(f'{k} = {v}\n' for k, v in selected.items()))
        result = subprocess.run([str(args.packer / 'hacbrewpack'), '--keyset', str(keys), '--titleid', f'{tid:016x}',
            '--nologo', '--nopatchnacplogo', '--plaintext', '--keepncadir'], cwd=work, capture_output=True)
    if result.returncode: raise RuntimeError('NSP packaging failed; output suppressed to protect key material')
    blob = (work / 'hacbrewpack_nsp' / f'{tid:016x}.nsp').read_bytes()
    ncas = checks.pfs_files(blob)
    assert len(ncas) == 3
    for name, content in ncas.items(): assert hashlib.sha256(content).hexdigest()[:32] == name.split('.')[0]
    # Inspect the actual ExeFS PFS0, not merely an incidental matching byte string
    # elsewhere in the NSP. Marker presence/absence is part of the regression test.
    matching = []
    for nca in ncas.values():
        at = 0
        while True:
            at = nca.find(b'PFS0', at)
            if at < 0: break
            try:
                files = checks.pfs_files(nca[at:])
                if 'main.npdm' in files: matching.append(files)
            except (AssertionError, ValueError, struct.error, UnicodeError): pass
            at += 4
    assert len(matching) == 1, 'Cannot identify packaged ExeFS'
    exefs = matching[0]
    assert exefs['main'] == (work / 'exefs/main').read_bytes()
    assert exefs['main.npdm'] == (work / 'exefs/main.npdm').read_bytes()
    assert (exefs.get('fxtmem') == descriptor()) if tag != 'control' else 'fxtmem' not in exefs
    for name in ('control/control.nacp', 'control/icon_AmericanEnglish.dat', 'romfs/nextNroPath', 'romfs/nextArgv'):
        assert any((work / name).read_bytes() in content for content in ncas.values()), name
    destination = args.output / 'forwarders' / (output_name or 'FEXTendo-Memory-' + tag + '.nsp')
    destination.write_bytes(blob)
    shutil.copy2(work / 'forwarder.json', args.output / 'source' / (tag + '.json'))
    return {**parsed, 'tag': tag, 'nsp': destination.name, 'sha256': sha(destination),
            'marker': 'fxtmem-v1' if tag != 'control' else None, 'packed_exefs_verified': True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--keys', type=Path)
    p.add_argument('--nro-only', action='store_true', help='Update the probe using existing v1 forwarders and boot files; no keys needed')
    p.add_argument('--packer', type=Path, default=Path('/home/blekjek/sleepingdogs-forwarder-tools/hacbrewpack'))
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    if a.nro_only and (a.output is None or a.output.exists()):
        p.error('--nro-only requires a fresh explicit --output directory')
    if not a.nro_only and a.keys is None: p.error('--keys is required when packaging forwarders')
    if a.output is None: a.output = ROOT / 'dist/fextendo-low-window-v1'
    if a.work.exists(): raise RuntimeError('Choose a fresh work directory')
    a.work.mkdir(parents=True)
    sd = a.output / TARGET.lstrip('/')
    sd.parent.mkdir(parents=True, exist_ok=True)
    sdk = Path('/opt/devkitpro')
    env = dict(os.environ, DEVKITPRO=str(sdk))
    if a.nro_only:
        elf = build_probe(a.work, sd, sdk, env)
        write_json(a.output / 'probe-build.json', {'abi': 'fxtmem-v1', 'revision': PROBE_REVISION,
            'target': TARGET, 'nro_sha256': sha(sd), 'probe_elf_sha256': sha(elf),
            'nro_only': True, 'runtime_changed': False, 'hardware_tested': False,
            'source_files': {str(f.relative_to(ROOT)): sha(f) for f in (
                Path(__file__).resolve(), SOURCE / 'probe.c', ROOT / 'src/experimental/as39_probe.c',
                ROOT / 'src/fex/horizon_jit.c', ROOT / 'src/fex/horizon_host.h')}})
        print('Built NRO-only ' + PROBE_REVISION + '; reuse the existing v1 boot pair and HOME tiles.', flush=True)
        return
    for folder in ('forwarders', 'source', 'licenses'): (a.output / folder).mkdir(parents=True, exist_ok=True)
    base = module('as39_probe', ROOT / 'tools/build-as39-probe.py')
    checks = module('forwarder_checks', ROOT / 'tools/build-fextendo-forwarder.py')
    hbl = ROOT / 'local/production-input-fix/approved/source/forwarder/hbl'
    for name, digest in base.HBL_HASHES.items():
        if sha(hbl / name) != digest: raise RuntimeError('Unreviewed HBL source: ' + name)
    git = ['git', '-c', 'safe.directory=' + str(a.packer), '-C', str(a.packer)]
    if subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip() != base.PACKER_REV:
        raise RuntimeError('Unreviewed packer revision')
    if subprocess.check_output(git + ['diff', 'HEAD', '--'], text=True).strip():
        raise RuntimeError('Modified packer source')
    cc = sdk / 'devkitA64/bin/aarch64-none-elf-gcc'
    common = ['-O2', '-g', '-march=armv8-a+crc', '-mtune=cortex-a57', '-ffixed-x18', '-fPIE',
              '-ffunction-sections', '-fdata-sections', '-D__SWITCH__', '-isystem', sdk / 'libnx/include']
    elf = build_probe(a.work, sd, sdk, env)
    icon, nacp = base.extract_assets(sd.read_bytes())
    src = a.work / 'forwarder-source'
    shutil.copytree(hbl / 'source', src)
    text = (src / 'main.c').read_text()
    text = exact(text, 'static Handle g_procHandle = {0};', '#include "forwarder_low.inc"\n\nstatic Handle g_procHandle = {0};')
    text = exact(text, 'void* map_addr = virtmemFindCodeMemory(total_size, 0);', 'void* map_addr = fxt_find_native(total_size);')
    begin = text.index('void __libnx_initheap(void) {')
    end = text.index('\n}', begin) + 2
    text = text[:begin] + '#include "forwarder_heap.inc"' + text[end:]
    text = exact(text, '''// stub alloc calls as they're not used (saves 4KiB).
void* __libnx_alloc(size_t size) {
    diagAbortWithResult(MAKERESULT(Module_HomebrewLoader, 40));
}

void* __libnx_aligned_alloc(size_t alignment, size_t size) {
    diagAbortWithResult(MAKERESULT(Module_HomebrewLoader, 41));
}

void __libnx_free(void* p) {
    diagAbortWithResult(MAKERESULT(Module_HomebrewLoader, 43));
}''', '// Reservation bookkeeping uses libnx allocation on the private BSS heap.')
    (src / 'main.c').write_text(text)
    for name in ('forwarder_low.inc', 'forwarder_heap.inc'): shutil.copy2(SOURCE / name, src / name)
    objects = []
    for name in ('main.c', 'trampoline.s'):
        obj = a.work / (name + '.o')
        run(cc, *common, '-DVERSION="3.0.0"', '-c', src / name, '-o', obj, env=env)
        objects.append(obj)
    run(cc, *common, '-specs=' + str(sdk / 'libnx/switch.specs'), '-Wl,-wrap,exit', *objects,
        '-L' + str(sdk / 'libnx/lib'), '-lnx', '-o', a.work / 'forwarder.elf', env=env)
    run(sdk / 'tools/bin/elf2nso', a.work / 'forwarder.elf', a.work / 'forwarder.nso')
    fws = [pack(tag, a, sdk, env, hbl, icon, nacp, base, checks) for tag in TAGS]
    assert len({f['title_id'] for f in fws}) == len(TAGS)
    assert not {f['title_id'] for f in fws} & {'05b0354496b71000', '059a3db219b42000', '0548eabb35576000'}
    license_dir = ROOT / 'local/production-input-fix/approved/licenses/forwarder'
    shutil.copytree(license_dir, a.output / 'licenses/forwarder', dirs_exist_ok=True)
    shutil.copytree(src, a.output / 'source/forwarder', dirs_exist_ok=True)
    write_json(a.output / 'probe-build.json', {'abi': 'fxtmem-v1', 'forwarders': fws, 'target': TARGET,
        'nro_sha256': sha(sd), 'probe_elf_sha256': sha(elf), 'forwarder_elf_sha256': sha(a.work / 'forwarder.elf'),
        'forwarder_nso_sha256': sha(a.work / 'forwarder.nso'), 'private_bookkeeping_bytes': 16384,
        'runtime_changed': False, 'hardware_tested': False,
        'source_files': {str(f.relative_to(ROOT)): sha(f) for f in [
            Path(__file__).resolve(), ROOT / 'tools/fextendo_low_window.py',
            ROOT / 'src/experimental/as39_probe.c', ROOT / 'src/fex/horizon_jit.c', *sorted(SOURCE.glob('*'))] if f.is_file()}})
    print('Built one probe and three verified NSPs: control, optin-a, optin-b.', flush=True)


if __name__ == '__main__': main()
