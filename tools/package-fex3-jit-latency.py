"""Package matched NRO/FEX DLL with validated 500/5000 JIT control and rollback."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import zipfile
import pefile
from nro_assets import inspect_nro

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT/'local/fex3/jit-latency'
NRO = 'switch/pes13-fex/pes13-fex.nro'
DLL = 'switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'


def helper(name):
    spec=importlib.util.spec_from_file_location('helper',ROOT/'tools'/name)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def sha(data): return hashlib.sha256(data).hexdigest()
def read(path): return json.loads(path.read_text())


def write_overlay(output, files):
    if sorted(n for n in files if n.startswith('switch/'))!=sorted([NRO,DLL]):
        raise ValueError('Only the NRO and FEX DLL may replace installed files')
    for name in files:
        if name.startswith('/') or '..' in Path(name).parts or '\\' in name:
            raise ValueError('Unsafe archive path')
    with tempfile.TemporaryDirectory(prefix='fex-jit-zip-',dir=output.parent) as directory:
        temp=Path(directory)/'package.zip'
        with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for name,data in sorted(files.items()):
                info=zipfile.ZipInfo(name,(2026,9,27,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                info.external_attr=0o100644<<16
                archive.writestr(info,data)
        with zipfile.ZipFile(temp) as archive:
            if archive.testzip() or set(archive.namelist())!=set(files):raise ValueError('ZIP integrity')
            for name,data in files.items():
                if archive.read(name)!=data:raise ValueError('ZIP readback mismatch '+name)
        data=temp.read_bytes()
        with output.open('xb') as stream:stream.write(data)
    return {'path':str(output),'bytes':len(data),'sha256':sha(data),'files':len(files)}


def interface(data):
    pe=pefile.PE(data=data)
    return {
        'machine':pe.FILE_HEADER.Machine,
        'imports':sorted((lib.dll,tuple(sorted((s.name or str(s.ordinal).encode()) for s in lib.imports)))
                         for lib in pe.DIRECTORY_ENTRY_IMPORT),
        'exports':sorted((s.ordinal,s.name,s.forwarder) for s in pe.DIRECTORY_ENTRY_EXPORT.symbols),
    }


def main():
    candidate=WORK/'runtime';module=WORK/'module'
    baseline=ROOT/'local/fex3/warm-start/runtime'
    oldmodule=ROOT/'local/fex3/stability-540p/module'
    build,old,fex,oldfex=map(read,[candidate/'runtime-build.json',baseline/'runtime-build.json',
                                 module/'build.json',oldmodule/'build.json'])
    checked=helper('package-fex3-stability.py').checked
    for key in ('jit_latency','warm_audit','hang_audit','stability','samecore_yield',
                'resume_gate','runtime_fixes','diagnostic'):
        if build.get(key) is not True: raise ValueError('Missing build flag '+key)
    for key in ('native_dependencies','toolchain_path','ntdll_sha256','wow64_sha256','guest_sha256'):
        if build[key]!=old[key]: raise ValueError('Unexpected dependency change '+key)
    if build['toolchain_path']!=fex['toolchain_path']:raise ValueError('Toolchain mismatch')
    for name,digest in build['adapter_sources'].items():checked(ROOT/'src/fex'/name,digest)
    for name,digest in build['patch_sources'].items():checked(ROOT/name,digest)
    for name,digest in fex['adapter_sources'].items():
        checked(ROOT/name,digest)
        if name.startswith('src/fex/') and build['adapter_sources'].get(Path(name).name)!=digest:
            raise ValueError('Native/module source mismatch '+name)
    delta=sorted(k for k in build['adapter_sources'].keys()|old['adapter_sources'].keys()
                 if build['adapter_sources'].get(k)!=old['adapter_sources'].get(k))
    if delta!=['horizon_jit_timing.h','module_jit_timing.cpp','module_profile.cpp']:
        raise ValueError('Unexpected adapter source delta '+repr(delta))
    patches,oldpatches=map(read,[candidate/'wine-patches.json',baseline/'wine-patches.json'])
    if patches['pe-source']!=oldpatches['pe-source']:raise ValueError('Wine PE source changed')
    native_delta=sorted(k for k in patches['native-source'].keys()|oldpatches['native-source'].keys()
                        if patches['native-source'].get(k)!=oldpatches['native-source'].get(k))
    if native_delta!=['wine-nx-probe/source/runtime.c']:raise ValueError('Unexpected native delta')
    modpatch,oldmodpatch=map(read,[module/'patches.json',oldmodule/'patches.json'])
    if modpatch['fex_commit']!=oldmodpatch['fex_commit']:raise ValueError('FEX pin drift')
    a={r['path']:r['patched_sha256'] for r in modpatch['files']}
    b={r['path']:r['patched_sha256'] for r in oldmodpatch['files']}
    mod_delta=sorted(k for k in a.keys()|b.keys() if a.get(k)!=b.get(k))
    if mod_delta!=['FEXCore/Source/Interface/Core/Core.cpp',
                  'Source/Windows/Common/InvalidationTracker.cpp',
                  'Source/Windows/WOW64/CMakeLists.txt','Source/Windows/WOW64/Module.cpp']:
        raise ValueError('Unexpected FEX patch delta '+repr(mod_delta))

    nro=checked(candidate/'payload/pes13-fex.nro',build['nro_sha256'])
    dll=checked(module/'libwow64fex.dll',fex['sha256'])
    oldnro=checked(baseline/'payload/pes13-fex.nro',old['nro_sha256'])
    olddll=checked(oldmodule/'libwow64fex.dll',oldfex['sha256'])
    if interface(dll)!=interface(olddll):raise ValueError('PE import/export interface drift')
    elf=candidate/'reference/pes13-fex.elf';checked(elf,build['native_elf_sha256'])
    helper('package-fex3-stability.py').verify_executable(elf,nro)
    metadata=inspect_nro(nro,(ROOT/'assets/icon.jpg').read_bytes(),
                         expected_title='PES13-NX FEX3',expected_version='0.3.0')
    for marker,data in [(b'pes13-fex3-jit-latency',nro),(b'FEX_MAXINST=500\0',nro),
                        (b'FEX_MAXINST=5000\0',nro),(b'fex_jit_large',nro),
                        (b'[FEX3-JIT] v1',dll),(b'[FEX3-JIT-CONFIG] maxinst=500 ',dll),
                        (b'[FEX3-JIT-CONFIG] maxinst=5000 ',dll)]:
        if marker not in data:raise ValueError('Missing marker '+repr(marker))
    files={NRO:nro,DLL:dll,'rollback/'+NRO:oldnro,'rollback/'+DLL:olddll,
           'README.md':(ROOT/'docs/FEX3-JIT-LATENCY.md').read_bytes(),
           'evidence/input-analysis.json':(WORK/'input-analysis.json').read_bytes()}
    checks={
        'host-validation.json':{'runtime_source_sha256':patches['native-source']['wine-nx-probe/source/runtime.c']},
        'jit-binary.json':{'dll_sha256':fex['sha256']},
        'warm-binary.json':{'native_elf_sha256':build['native_elf_sha256']},
        'unwind.json':{'native_elf_sha256':build['native_elf_sha256'],'fex_sha256':fex['sha256'],
                       'ntdll_sha256':build['ntdll_sha256'],'wow64_sha256':build['wow64_sha256']},
    }
    for name,expected in checks.items():
        report=read(WORK/name)
        if report.get('passed') is not True or any(report.get(k)!=v for k,v in expected.items()):
            raise ValueError('Validation mismatch '+name)
        files['evidence/'+name]=(WORK/name).read_bytes()
    for name,digest in read(WORK/'host-validation.json')['sources'].items():checked(ROOT/'src/fex'/name,digest)
    for directory,names in [(candidate,['runtime-build.json','wine-patches.json']),
                            (module,['build.json','patches.json'])]:
        for name in names:files['evidence/'+directory.name+'/'+name]=(directory/name).read_bytes()
    for name in ('module_profile.cpp','module_jit_timing.cpp','horizon_jit_timing.h'):
        files['source/src/fex/'+name]=(ROOT/'src/fex'/name).read_bytes()
    for name in ('tests/fex_jit_latency.py','tests/fex_jit_latency_binary.py',
                 'tools/fex_jit_latency_patches.py','tools/fex_horizon_patches.py'):
        files['source/'+name]=(ROOT/name).read_bytes()
    files['THIRD_PARTY.md']=(ROOT/'THIRD_PARTY.md').read_bytes()
    files['licenses/Wine-and-PES13-LGPL-2.1.txt']=(ROOT/'LICENSE').read_bytes()
    files['licenses/PES13-FEX-adapter-MIT.txt']=(ROOT/'src/fex/LICENSE').read_bytes()
    for path in (ROOT/'licenses').rglob('*'):
        if path.is_file() and path.name!='Box64-LICENSE.txt':files[path.relative_to(ROOT).as_posix()]=path.read_bytes()
    manifest={'kind':'500 instruction JIT latency candidate with same-binary 5000 control',
              'hardware_tested':False,'stutter_fix_verified':False,
              'replaces':[NRO,DLL],'requires_existing_build':'pes13-fex3-warm-audit',
              'native_source_delta':native_delta,'module_source_delta':mod_delta,
              'native_elf_sha256':build['native_elf_sha256'],'dll_sha256':fex['sha256'],
              'metadata':metadata,'files':{k:sha(v) for k,v in sorted(files.items())}}
    files['manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    output=ROOT/'dist/pes13-fex3-jit-latency.zip';folder=output.with_suffix('')
    if output.exists() or folder.exists():raise FileExistsError('Preserve existing package')
    result=write_overlay(output,files)
    folder.mkdir()
    for name,data in files.items():
        path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        if path.read_bytes()!=data:raise RuntimeError('Readback mismatch')
    (WORK/'package.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
