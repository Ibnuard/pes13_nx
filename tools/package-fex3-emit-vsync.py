"""Package one emitter + VSync-off overlay with a complete checkpoint rollback."""
import binascii
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT/'local/fex3/emit-vsync'
OLD = ROOT/'local/fex3/dispatch-cache'
RUNTIME = ROOT/'local/fex3/jit-latency/runtime'
PREFIX = 'switch/pes13-fex/'
DLL = PREFIX+'drive_c/windows/system32/libwow64fex.dll'
DXVK = PREFIX+'drive_c/PES13/dxvk.conf'
LOG_SHA = 'e7945dd2f0be655381781153cf3b12ca8ed688e4e9569ab835945d03910ae0a0'


def sha(data): return hashlib.sha256(data).hexdigest()
def read(path): return json.loads(path.read_text())


def checked(path, expected):
    data = path.read_bytes()
    if sha(data) != expected: raise ValueError('Hash mismatch: '+str(path))
    return data


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    queue = load('queue_package', 'tools/package-fex3-smooth-queue.py')
    stable = load('stability_package', 'tools/package-fex3-stability.py')
    jit = load('jit_package', 'tools/package-fex3-jit-latency.py')
    settings = load('pes_settings', 'tools/make-settings.py')
    baseline = (ROOT/'config/fex/dxvk-smooth-queue.conf').read_bytes()
    candidate = (ROOT/'config/fex/dxvk-vsync-off.conf').read_bytes()
    before, after = queue.options(baseline), queue.options(candidate)
    delta = {k:[before.get(k), after.get(k)] for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    if delta != {'d3d9.presentInterval':['1','0']}: raise ValueError('Unexpected DXVK option delta')
    log = checked(ROOT/'local/fex3/dispatch-feedback'/LOG_SHA/'fex-runtime.log', LOG_SHA)
    effective = dict(re.findall(r'^info:    ([\w.]+) = (\S+)\s*$', log.decode(), re.M))
    if effective != before: raise ValueError('Rollback does not match checkpoint options')
    if b'[FEX3-LOOKUP] v2 dispatcher=L1-first' not in log or b'flags=0289 vsync=1' not in log:
        raise ValueError('Wrong baseline build/settings')
    analysis = (ROOT/'local/fex3/vsync-off/baseline-analysis.json').read_bytes()
    if json.loads(analysis)['sha256'] != LOG_SHA: raise ValueError('Analysis mismatch')

    # Derive the same 540p preset as the tested stability package, then change
    # only VSync and its CRC. Controller/aspect/frame-skip words stay intact.
    original = (ROOT/'config/drive_c/users/steamuser/Documents/KONAMI/Pro Evolution Soccer 2013/settings.dat').read_bytes()
    old_settings = stable.resize_settings(original, 960, 540)
    new_settings = bytearray(old_settings)
    flags = struct.unpack_from('<H', new_settings, 14)[0]
    if flags != 0x0289: raise ValueError('Unexpected checkpoint flags')
    struct.pack_into('<H', new_settings, 14, flags & ~1)
    struct.pack_into('<H', new_settings, 12, 0)
    struct.pack_into('<H', new_settings, 12, settings.crc16(new_settings))
    settings.validate(new_settings)
    independent = bytearray(new_settings)
    independent[12:14] = b'\0\0'
    if struct.unpack_from('<H', new_settings, 12)[0] != (~binascii.crc_hqx(independent, 0) & 0xffff):
        raise ValueError('Independent settings CRC failed')
    if any(a != b and i not in (12,13,14) for i,(a,b) in enumerate(zip(old_settings,new_settings))):
        raise ValueError('Unrelated settings changed')
    if struct.unpack_from('<HII', new_settings,14) != (0x0288,960,540):
        raise ValueError('Settings flags/resolution mismatch')
    new_settings = bytes(new_settings)

    new, old, runtime = read(WORK/'module/build.json'), read(OLD/'module/build.json'), read(RUNTIME/'runtime-build.json')
    if new['fex_commit'] != old['fex_commit'] or new['toolchain_path'] != old['toolchain_path']:
        raise ValueError('FEX pin/toolchain drift')
    for path,digest in new['adapter_sources'].items(): checked(ROOT/path,digest)
    changed = sorted(k for k in new['adapter_sources'].keys() | old['adapter_sources'].keys()
                     if new['adapter_sources'].get(k) != old['adapter_sources'].get(k))
    if changed != ['tools/fex_horizon_patches.py']: raise ValueError('Unexpected adapter delta')
    maps = [{f['path']:f['patched_sha256'] for f in read(base/'module/patches.json')['files']} for base in (WORK,OLD)]
    changes = sorted(k for k in maps[0].keys() | maps[1].keys() if maps[0].get(k) != maps[1].get(k))
    if changes != ['CodeEmitter/CodeEmitter/Buffer.h', 'Source/Windows/WOW64/Module.cpp']:
        raise ValueError('Unexpected FEX source delta '+repr(changes))
    dll = checked(WORK/'module/libwow64fex.dll',new['sha256'])
    rollback = checked(OLD/'module/libwow64fex.dll',old['sha256'])
    if jit.interface(dll) != jit.interface(rollback): raise ValueError('PE interface drift')
    if b'[FEX3-EMIT] v1 cached writable buffer' not in dll: raise ValueError('Missing emitter marker')
    checked(RUNTIME/'payload/pes13-fex.nro',runtime['nro_sha256'])
    checked(RUNTIME/'reference/pes13-fex.elf',runtime['native_elf_sha256'])

    files = {DLL:dll, DXVK:candidate, 'rollback/'+DLL:rollback, 'rollback/'+DXVK:baseline,
             'README.md':(ROOT/'docs/FEX3-VSYNC-OFF.md').read_bytes(),
             'evidence/baseline-analysis.json':analysis}
    for name in stable.SETTINGS:
        files[PREFIX+name] = new_settings
        files['rollback/'+PREFIX+name] = old_settings
    prior_jit = read(ROOT/'local/fex3/jit-latency/module/build.json')
    checks = {
        'emitter.json':{'dll_sha256':new['sha256'], 'before_sha256':old['sha256'],
                        'buffer_source_sha256':maps[0]['CodeEmitter/CodeEmitter/Buffer.h']},
        'dispatch-binary.json':{'dll_sha256':new['sha256'], 'before_sha256':prior_jit['sha256']},
        'counter.json':{'dll_sha256':new['sha256']},
        'smc.json':{'dll_sha256':new['sha256']},
        'jit-binary.json':{'dll_sha256':new['sha256']},
        'unwind.json':{'fex_sha256':new['sha256'], 'native_elf_sha256':runtime['native_elf_sha256'],
                       'ntdll_sha256':runtime['ntdll_sha256'], 'wow64_sha256':runtime['wow64_sha256']},
        'present-support.json':{'native_elf_sha256':runtime['native_elf_sha256'], 'nro_sha256':runtime['nro_sha256']},
    }
    for path,values in checks.items():
        report = read(WORK/path)
        if report.get('passed') is not True or any(report.get(k) != v for k,v in values.items()):
            raise ValueError('Stale or failed validation: '+path)
        files['evidence/'+path] = (WORK/path).read_bytes()
        for name,digest in report.get('test_sources',{}).items():
            files['source/tests/'+name] = checked(ROOT/'tests'/name,digest)
    for path in (*new['adapter_sources'], 'tools/package-fex3-emit-vsync.py', 'tools/make-settings.py',
                 'tools/package-fex3-stability.py', 'tools/package-fex3-smooth-queue.py',
                 'tools/package-fex3-jit-latency.py', 'tools/nro_assets.py',
                 'tools/analyze-fex-pacing.py', 'config/fex/dxvk-vsync-off.conf',
                 'tests/fex_counter.py', 'tests/fex_smc.py', 'tests/fex_smc_ranges.cpp',
                 'tests/fex_jit_latency_binary.py', 'tests/fex_unwind.py'):
        files['source/'+path] = (ROOT/path).read_bytes()
    for name in ('build.json','patches.json'):
        files['evidence/module/'+name] = (WORK/'module'/name).read_bytes()
    files['evidence/required-runtime-build.json'] = (RUNTIME/'runtime-build.json').read_bytes()
    files['THIRD_PARTY.md'] = (ROOT/'THIRD_PARTY.md').read_bytes()
    files['licenses/PES13-FEX-adapter-MIT.txt'] = (ROOT/'src/fex/LICENSE').read_bytes()
    for path in (ROOT/'licenses').rglob('*'):
        if path.is_file() and path.name != 'Box64-LICENSE.txt': files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    replaces = sorted([DLL,DXVK,*[PREFIX+n for n in stable.SETTINGS]])
    if sorted(n for n in files if n.startswith('switch/')) != replaces: raise ValueError('Overlay boundary')
    if sorted(n.removeprefix('rollback/') for n in files if n.startswith('rollback/')) != replaces:
        raise ValueError('Incomplete rollback')
    manifest = {'kind':'Cached emitter writable buffer plus game/DXVK VSync off',
                'hardware_tested':False, 'stutter_fix_verified':False, 'kickoff_fix_verified':False,
                'checkpoint_commit':'8939d56489cea2731a62c2760445e068dfbe556d',
                'requires_existing_build':'pes13-fex3-dispatch-cache', 'replaces':replaces,
                'required_nro_sha256':runtime['nro_sha256'], 'dll_sha256':new['sha256'],
                'rollback_dll_sha256':old['sha256'], 'module_source_delta':changes,
                'dxvk_options_delta':delta, 'settings_flags':{'before':'0289','after':'0288'},
                'settings_resolution':[960,540], 'baseline_log_sha256':LOG_SHA,
                'files':{n:sha(b) for n,b in sorted(files.items())}}
    files['manifest.json'] = (json.dumps(manifest,indent=2)+'\n').encode()
    output = ROOT/'dist/pes13-fex3-emit-vsync.zip'
    folder = output.with_suffix('')
    if output.exists() or folder.exists(): raise FileExistsError('Preserve previous artifact')
    with tempfile.TemporaryDirectory(prefix='emit-vsync-',dir=output.parent) as tmp:
        path = Path(tmp)/'package.zip'
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,blob in sorted(files.items()):
                if name.startswith('/') or '..' in Path(name).parts: raise ValueError('Unsafe archive path')
                info = zipfile.ZipInfo(name,(2026,9,27,0,0,0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info,blob)
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() or set(archive.namelist()) != set(files): raise ValueError('ZIP integrity')
            for name,blob in files.items():
                if archive.read(name) != blob: raise ValueError('ZIP readback mismatch '+name)
        with output.open('xb') as stream: stream.write(path.read_bytes())
    folder.mkdir()
    for name,blob in files.items():
        path = folder/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(blob)
        if path.read_bytes() != blob: raise ValueError('Folder readback mismatch '+name)
    report = {'path':str(output), 'bytes':output.stat().st_size, 'sha256':sha(output.read_bytes()),
              'files':len(files), 'replaces':replaces, 'dll_sha256':new['sha256'],
              'settings_sha256':sha(new_settings), 'settings_flags':'0288',
              'settings_resolution':[960,540], 'readback_verified':True, 'passed':True}
    (WORK/'package.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__': main()
