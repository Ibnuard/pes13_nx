"""Package matched diagnostic NRO/FEX DLL, bounded trace OFF control and exact v3.2 rollback."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess,sys,zipfile
from nro_assets import inspect_nro
ROOT=Path(__file__).resolve().parents[1];WORK=ROOT/'local/fex3/short-trace'
BASE='pes13-fextendo-v3.2.zip';BASE_SHA='c71b45782e6884ad356e446c7ee361d3b302bff222c433b9ea8e19f1d12896f2'
NRO='switch/pes13-fex/pes13-fex.nro';DLL='switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
OFF='switch/pes13-fex/fex_short_trace_off'
OLD_DLL_SHA='9d2564ec928d9001e05d76cc4e1a37dbd2dae723cc3edce5367004fecd386118'
CHECKS=('launcher','memory','budget','gap','balance','yield','cores','resume','pipeline','jit-log','unwind','short-trace')
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text())
def checked(p,h):
    b=p.read_bytes()
    if sha(b)!=h:raise ValueError('Hash mismatch: '+str(p))
    return b
def enc(v):return (json.dumps(v,indent=2)+'\n').encode()
def main():
    archive=ROOT/'dist/pes13-fextendo-short-trace-v1.zip';folder=archive.with_suffix('')
    if archive.exists() or folder.exists():raise FileExistsError('Existing artifact protected')
    checked(ROOT/'dist'/BASE,BASE_SHA);files={}
    with zipfile.ZipFile(ROOT/'dist'/BASE) as z:
        manifest=json.loads(z.read('manifest.json'))
        if z.testzip() or len(z.namelist())!=len(set(z.namelist())) or set(z.namelist())!=set(manifest['files'])|{'manifest.json'}:raise ValueError('Baseline inventory')
        for n,h in manifest['files'].items():
            b=z.read(n)
            if sha(b)!=h:raise ValueError('Baseline member: '+n)
            if n.startswith('licenses/'):files[n]=b
        files['rollback/'+NRO]=z.read(NRO)
        files['evidence/baseline/'+BASE+'.manifest.json']=z.read('manifest.json')
        old=json.loads(z.read('evidence/runtime/runtime-build.json'))
        previous=json.loads(z.read('evidence/runtime/wine-patches.json'))
    new=read(WORK/'runtime/runtime-build.json');patches=read(WORK/'runtime/wine-patches.json');module=read(WORK/'module/build.json')
    if new.get('short_trace') is not True:raise ValueError('Missing trace flag')
    for k in ('native_dependencies','ntdll_sha256','wow64_sha256','guest_sha256','toolchain_path'):
        if new[k]!=old[k]:raise ValueError('Dependency changed: '+k)
    for k,v in old.items():
        if isinstance(v,bool) and new.get(k)!=v:raise ValueError('Baseline flag changed: '+k)
    if patches['pe-source']!=previous['pe-source']:raise ValueError('Guest Wine changed')
    delta=sorted(n for n in patches['native-source'].keys()|previous['native-source'].keys() if patches['native-source'].get(n)!=previous['native-source'].get(n))
    if delta!=['dlls/ntdll/unix/sync.c','wine-nx-probe/source/runtime.c']:raise ValueError('Native delta: '+repr(delta))
    adapter_delta=sorted(n for n in new['adapter_sources'].keys()|old['adapter_sources'].keys() if new['adapter_sources'].get(n)!=old['adapter_sources'].get(n))
    if adapter_delta!=['module_jit_timing.cpp']:raise ValueError('Adapter delta: '+repr(adapter_delta))
    for n,h in new['patch_sources'].items():checked(ROOT/n,h)
    for n,h in new['adapter_sources'].items():checked(ROOT/'src/fex'/n,h)
    for n,h in module['adapter_sources'].items():checked(ROOT/n,h)
    old_module=read(ROOT/'local/fex3/emit-vsync/module/build.json')
    if module['fex_commit']!=old_module['fex_commit'] or module['toolchain_path']!=old_module['toolchain_path']:raise ValueError('FEX toolchain/commit drift')
    if [n for n in module['adapter_sources'] if module['adapter_sources'][n]!=old_module['adapter_sources'].get(n)]!=['src/fex/module_jit_timing.cpp']:raise ValueError('FEX adapter drift')
    if (WORK/'module/patches.json').read_bytes()!=(ROOT/'local/fex3/emit-vsync/module/patches.json').read_bytes():raise ValueError('FEX patch drift')
    files['rollback/'+DLL]=checked(ROOT/'local/fex3/emit-vsync/module/libwow64fex.dll',OLD_DLL_SHA)
    files[NRO]=checked(WORK/'runtime/payload/pes13-fex.nro',new['nro_sha256'])
    files[DLL]=checked(WORK/'module/libwow64fex.dll',module['sha256'])
    files[OFF]=b'0\n';files['control-off/'+OFF]=b'1\n';files['rollback/'+OFF]=b'1\n'
    elf=WORK/'runtime/reference/pes13-fex.elf';checked(elf,new['native_elf_sha256'])
    spec=importlib.util.spec_from_file_location('stable',ROOT/'tools/package-fex3-stability.py')
    stable=importlib.util.module_from_spec(spec);spec.loader.exec_module(stable);stable.verify_executable(elf,files[NRO])
    metadata=inspect_nro(files[NRO],(ROOT/'assets/fextendo-v3/nro-icon.jpg').read_bytes(),expected_title='PES13 - FEXTendo',expected_version='0.3.3')
    if metadata!=new['metadata'] or metadata['author']!='AndroSwitch Project':raise ValueError('NRO metadata')
    for marker in (b'pes13-fextendo-short-trace-v1',b'[FEX3-SHORT-STATS]',b'[FEXTENDO-TIME]',b'first overlay frame submitted'):
        if marker not in files[NRO]:raise ValueError('Missing marker: '+repr(marker))
    for marker in (b'[FEX3-JIT-THREAD]',b'[FEX3-JIT-SLOW]',b'[FEX3-JIT-CLOCK]',b'FEXTENDO_TRACE'):
        if marker not in files[DLL]:raise ValueError('Missing DLL marker: '+repr(marker))
    sources=set(new['patch_sources'])|{'src/fex/'+n for n in new['adapter_sources']}|set(module['adapter_sources'])
    for name in CHECKS:
        path=WORK/(name+'.json');r=read(path)
        if r.get('passed') is not True or r['native_elf_sha256']!=new['native_elf_sha256']:raise ValueError('Stale check: '+name)
        if name=='unwind' and r['fex_sha256']!=module['sha256']:raise ValueError('Unwind used wrong FEX DLL')
        if name=='short-trace' and r['dll_sha256']!=module['sha256']:raise ValueError('Trace check used wrong FEX DLL')
        for n,h in r.get('source_hashes',r.get('source_sha256',{})).items():checked(ROOT/n,h);sources.add(n)
        files['evidence/checks/'+name+'.json']=path.read_bytes()
    metrics=read(WORK/'jit-metrics.json')
    if metrics.get('passed') is not True:raise ValueError('JIT metrics check')
    if metrics['runtime_source_sha256']!=patches['native-source']['wine-nx-probe/source/runtime.c']:raise ValueError('Stale JIT source check')
    for n,h in metrics['sources'].items():checked(ROOT/'src/fex'/n,h);sources.add('src/fex/'+n)
    files['evidence/checks/jit-metrics.json']=enc(metrics)
    for test in ('fextendo_short_analysis.py','fextendo_analysis.py'):
        result=subprocess.run([sys.executable,'-B',str(ROOT/'tests'/test)],check=True,capture_output=True,text=True)
        files['evidence/checks/'+test+'.txt']=result.stdout.encode();sources.add('tests/'+test)
    for n in ('runtime-build.json','wine-patches.json'):files['evidence/runtime/'+n]=(WORK/'runtime'/n).read_bytes()
    for n in ('build.json','patches.json'):files['evidence/module/'+n]=(WORK/'module'/n).read_bytes()
    generated=Path(new['native_source']).parent
    for n in delta:files['source/generated/wine/'+n]=checked(generated/n,patches['native-source'][n])
    fex_source=Path(module['dll']).parents[2]/'source-horizon'
    for item in read(WORK/'module/patches.json')['files']:
        files['source/generated/fex/'+item['path']]=checked(fex_source/item['path'],item['patched_sha256'])
    for p in (WORK/'module/licenses').rglob('*'):
        if p.is_file():files['licenses/FEX/'+p.relative_to(WORK/'module/licenses').as_posix()]=p.read_bytes()
    sources|={'tools/package-fextendo-short-trace.py','tools/build-fex-runtime.py','tools/build-fex-module.py','tools/fex_wine_patches.py',
              'tests/run_fextendo_checks.py','tools/nro_assets.py','tools/analyze-fextendo-run.py','tools/analyze-fextendo-short-trace.py',
              'docs/FEXTENDO-SHORT-TRACE.md','docs/FEXTENDO-V3.2-DEVICE-RESULT.md','tests/fex_jit_latency.py','assets/fextendo-v3/nro-icon.jpg'}
    for n in sources:files['source/'+n]=(ROOT/n).read_bytes()
    files['README.md']=(ROOT/'docs/FEXTENDO-SHORT-TRACE.md').read_bytes();files['THIRD_PARTY.md']=(ROOT/'THIRD_PARTY.md').read_bytes()
    active=sorted(n for n in files if n.startswith('switch/'))
    if active!=sorted((NRO,DLL,OFF)):raise ValueError('Unexpected active file')
    manifest={'kind':'fextendo-short-trace-v1','hardware_tested':False,'stutter_fix_claimed':False,
              'requires':'existing working FEXTendo v3.2 installation; both NRO and FEX DLL must be copied',
              'baseline_zip_sha256':{BASE:BASE_SHA},'baseline_dll_sha256':OLD_DLL_SHA,
              'native_elf_sha256':new['native_elf_sha256'],'nro_sha256':new['nro_sha256'],'dll_sha256':module['sha256'],
              'trace_default':True,'trace_off_file':'fex_short_trace_off=1','native_changed':delta,'adapter_changed':adapter_delta,
              'checks':list(CHECKS)+['jit-metrics','fextendo_short_analysis.py','fextendo_analysis.py'],
              'active_files':active,'rollback_target':'exact FEXTendo v3.2 NRO + baseline emit-vsync FEX DLL',
              'files':{n:sha(b) for n,b in sorted(files.items())}}
    files['manifest.json']=enc(manifest)
    for n,b in files.items():p=folder/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in sorted(files.items()):
            info=zipfile.ZipInfo(n,(2026,9,29,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,b)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() or len(z.namelist())!=len(files):raise ValueError('Final inventory')
        for n,b in files.items():
            if z.read(n)!=b:raise ValueError('Final member: '+n)
    report={'passed':True,'path':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive.read_bytes()),'active_files':len(active),'checks':len(manifest['checks'])}
    (WORK/'package.json').write_bytes(enc(report));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
