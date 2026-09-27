"""Package the validated FEX-only dispatcher/cache overlay and previous DLL."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT/'local/fex3/dispatch-cache'
OLD = ROOT/'local/fex3/jit-latency'
TARGET = 'switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'


def read(path): return json.loads(path.read_text())
def sha(data): return hashlib.sha256(data).hexdigest()


def checked(path, digest):
    data = path.read_bytes()
    if sha(data) != digest: raise ValueError('Hash mismatch: '+str(path))
    return data


def main():
    spec = importlib.util.spec_from_file_location('jit_package', ROOT/'tools/package-fex3-jit-latency.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    new, old = read(WORK/'module/build.json'), read(OLD/'module/build.json')
    runtime = read(OLD/'runtime/runtime-build.json')
    if new['fex_commit'] != old['fex_commit'] or new['toolchain_path'] != old['toolchain_path']:
        raise ValueError('FEX pin/toolchain drift')
    for path, digest in new['adapter_sources'].items(): checked(ROOT/path, digest)
    changed = sorted(k for k in new['adapter_sources'].keys() | old['adapter_sources'].keys()
                     if new['adapter_sources'].get(k) != old['adapter_sources'].get(k))
    if changed != ['tools/fex_horizon_patches.py']: raise ValueError('Unexpected adapter change '+repr(changed))
    maps = []
    for base in (WORK, OLD):
        maps.append({f['path']: f['patched_sha256'] for f in read(base/'module/patches.json')['files']})
    changes = sorted(k for k in maps[0].keys() | maps[1].keys() if maps[0].get(k) != maps[1].get(k))
    expected = ['FEXCore/Source/Interface/Core/Dispatcher/Dispatcher.cpp',
                'FEXCore/Source/Interface/Core/LookupCache.cpp',
                'FEXCore/Source/Interface/Core/LookupCache.h']
    if changes != expected: raise ValueError('Unexpected FEX delta '+repr(changes))
    dll = checked(WORK/'module/libwow64fex.dll', new['sha256'])
    rollback = checked(OLD/'module/libwow64fex.dll', old['sha256'])
    if helper.interface(dll) != helper.interface(rollback): raise ValueError('PE interface drift')
    if b'[FEX3-LOOKUP] v2 dispatcher=L1-first' not in dll: raise ValueError('Marker missing')
    nro = checked(OLD/'runtime/payload/pes13-fex.nro', runtime['nro_sha256'])
    # This overlay intentionally doesn't replace its already-installed launcher.
    files = {TARGET:dll, 'rollback/'+TARGET:rollback,
             'README.md':(ROOT/'docs/FEX3-DISPATCH-CACHE.md').read_bytes(),
             'evidence/input-analysis.json':(WORK/'input-analysis.json').read_bytes()}
    analysis = read(WORK/'input-analysis.json')
    checked(ROOT/'local/fex3/kickoff-investigation'/analysis['sha256']/'fex-runtime.log', analysis['sha256'])
    checks = {
        'dispatch-binary.json':{'dll_sha256':new['sha256'], 'before_sha256':old['sha256']},
        'memory.json':{'dll_sha256':new['sha256']},
        'jit-binary.json':{'dll_sha256':new['sha256']},
        'unwind.json':{'fex_sha256':new['sha256'], 'native_elf_sha256':runtime['native_elf_sha256'],
                       'ntdll_sha256':runtime['ntdll_sha256'], 'wow64_sha256':runtime['wow64_sha256']},
    }
    for path, values in checks.items():
        report = read(WORK/path)
        if report.get('passed') is not True or any(report.get(k) != v for k, v in values.items()):
            raise ValueError('Validation missing or stale: '+path)
        files['evidence/'+path] = (WORK/path).read_bytes()
    for path, digest in read(WORK/'dispatch-binary.json')['test_sources'].items():
        files['source/tests/'+path] = checked(ROOT/'tests'/path, digest)
    for path in new['adapter_sources']:
        files['source/'+path] = (ROOT/path).read_bytes()
    for path in ('tools/package-fex3-dispatch-cache.py', 'tools/analyze-fex-pacing.py',
                 'tests/fex_jit_latency_binary.py', 'tests/fex_unwind.py'):
        files['source/'+path] = (ROOT/path).read_bytes()
    for name in ('build.json', 'patches.json'):
        files['evidence/module/'+name] = (WORK/'module'/name).read_bytes()
    files['evidence/required-runtime-build.json'] = (OLD/'runtime/runtime-build.json').read_bytes()
    files['THIRD_PARTY.md'] = (ROOT/'THIRD_PARTY.md').read_bytes()
    files['licenses/PES13-FEX-adapter-MIT.txt'] = (ROOT/'src/fex/LICENSE').read_bytes()
    for path in (ROOT/'licenses').rglob('*'):
        if path.is_file() and path.name != 'Box64-LICENSE.txt':
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    manifest = {'kind':'Resident L1 and direct dispatcher lookup', 'hardware_tested':False,
                'stutter_fix_verified':False, 'kickoff_fix_verified':False, 'replaces':[TARGET],
                'requires_existing_build':'pes13-fex3-jit-latency', 'required_nro_sha256':sha(nro),
                'dll_sha256':new['sha256'], 'rollback_dll_sha256':old['sha256'],
                'module_source_delta':changes, 'files':{n:sha(b) for n,b in sorted(files.items())}}
    files['manifest.json'] = (json.dumps(manifest, indent=2)+'\n').encode()
    if [n for n in files if n.startswith('switch/')] != [TARGET]: raise ValueError('Overlay boundary')
    output = ROOT/'dist/pes13-fex3-dispatch-cache.zip'
    folder = output.with_suffix('')
    if output.exists() or folder.exists(): raise FileExistsError('Preserve previous package')
    with tempfile.TemporaryDirectory(prefix='dispatch-cache-', dir=output.parent) as tmp:
        path = Path(tmp)/'package.zip'
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(files.items()):
                if name.startswith('/') or '..' in Path(name).parts: raise ValueError('Unsafe archive path')
                info = zipfile.ZipInfo(name, (2026,9,27,0,0,0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() or set(archive.namelist()) != set(files): raise ValueError('ZIP integrity')
            for name, data in files.items():
                if archive.read(name) != data: raise ValueError('ZIP readback '+name)
        data = path.read_bytes()
        with output.open('xb') as stream: stream.write(data)
    folder.mkdir()
    for name, data in files.items():
        path = folder/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if path.read_bytes() != data: raise ValueError('Folder readback '+name)
    report = {'path':str(output), 'bytes':output.stat().st_size, 'sha256':sha(output.read_bytes()),
              'files':len(files), 'dll_sha256':new['sha256'], 'passed':True}
    (WORK/'package.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
