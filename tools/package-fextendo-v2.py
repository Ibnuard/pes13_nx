"""Package verified v2 assets/runtime, preserve user settings, and bind rollback."""
from pathlib import Path
import hashlib,importlib.util,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'local/fex3/fextendo-v2'
BASES={'pes13-fextendo-launcher.zip':'425e803a753bfe36fe8b993ce4e7984300e32d3b34998b99f0c53bc9f38aee85',
       'pes13-fextendo-memory-trial.zip':'d1e4542561e8a30a2c0b337ab558ecbb8fe7f95776c9ab48c6d1808ee830da0e'}
NRO='switch/pes13-fex/pes13-fex.nro'
CONFIGS=('switch/pes13-fex/drive_c/PES13/dxvk.conf','switch/pes13-fex/launcher/presets/dxvk.conf')
CHECKS=('launcher','memory','budget','gap','balance','yield','cores','resume','pipeline','jit-log','unwind')
LOG_SHA='99c459c5ac19874b5ee366519f03cab7a276001399df4732831341f67bb7c447'
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(x):return (json.dumps(x,indent=2)+'\n').encode()
def read(p):return json.loads(p.read_text())
def checked(p,h):
    b=p.read_bytes()
    if sha(b)!=h:raise ValueError('Hash mismatch: '+str(p))
    return b
def options(b):
    return dict((k.strip(),v.strip()) for k,v in (s.split('=',1) for s in b.decode().splitlines()
                if '=' in s and not s.lstrip().startswith('#')))
def main():
    archive=ROOT/'dist/pes13-fextendo-v2.zip';folder=archive.with_suffix('')
    if archive.exists() or folder.exists():raise FileExistsError('Existing artifact protected')
    files={};baseline={}
    for name,digest in BASES.items():
        path=ROOT/'dist'/name;checked(path,digest)
        with zipfile.ZipFile(path) as z:
            manifest=json.loads(z.read('manifest.json'))
            if z.testzip() or len(z.namelist())!=len(set(z.namelist())) or set(z.namelist())!=set(manifest['files'])|{'manifest.json'}:
                raise ValueError('Baseline inventory: '+name)
            for n,h in manifest['files'].items():
                data=z.read(n)
                if sha(data)!=h:raise ValueError('Baseline member: '+n)
                if n.startswith('switch/'):baseline[n]=data
                if n.startswith('licenses/'):files[n]=data
            files['evidence/baseline/'+name+'.manifest.json']=z.read('manifest.json')
            if name=='pes13-fextendo-memory-trial.zip':
                old=json.loads(z.read('evidence/runtime/runtime-build.json'))
                previous=json.loads(z.read('evidence/runtime/wine-patches.json'))
    new=read(WORK/'runtime/runtime-build.json');patches=read(WORK/'runtime/wine-patches.json')
    for k in ('native_dependencies','adapter_sources','ntdll_sha256','wow64_sha256','guest_sha256','toolchain_path'):
        if new[k]!=old[k]:raise ValueError('Dependency changed: '+k)
    for k in ('launcher','memory_audit','memory_budget_filter','stable_balance','gap_audit'):
        if new.get(k) is not True:raise ValueError('Build flag: '+k)
    if new['yield_adaptive'] or patches['pe-source']!=previous['pe-source']:raise ValueError('Unexpected guest delta')
    delta=sorted(n for n in patches['native-source'].keys()|previous['native-source'].keys()
                 if patches['native-source'].get(n)!=previous['native-source'].get(n))
    if delta!=['dlls/win32u/vulkan.c','wine-nx-probe/source/runtime.c']:raise ValueError('Native delta: '+repr(delta))
    for n,h in new['patch_sources'].items():checked(ROOT/n,h)
    for n,h in new['adapter_sources'].items():checked(ROOT/'src/fex'/n,h)
    nro=checked(WORK/'runtime/payload/pes13-fex.nro',new['nro_sha256'])
    elf=WORK/'runtime/reference/pes13-fex.elf';checked(elf,new['native_elf_sha256'])
    spec=importlib.util.spec_from_file_location('stable',ROOT/'tools/package-fex3-stability.py')
    stable=importlib.util.module_from_spec(spec);spec.loader.exec_module(stable);stable.verify_executable(elf,nro)
    for marker in (b'pes13-fextendo-v2-budget',b'[FEX3-MEMBUDGET]',b'[FEXTENDO-TIME]',b'Debug timestamp'):
        if marker not in nro:raise ValueError('Missing marker: '+str(marker))
    files[NRO]=nro;config=(ROOT/'config/fextendo/presets/dxvk.conf').read_bytes()
    for n in CONFIGS:
        before=options(baseline[n]);after=options(config)
        if {k for k in before|after if before.get(k)!=after.get(k)}!={'dxvk.enableMemoryDefrag'}:
            raise ValueError('Config changed beyond defrag')
        if 'dxvk.enableMemoryDefrag' in after or after['d3d9.presentInterval']!='1':raise ValueError('Wrong config')
        files[n]=config
    artroot=WORK/'package/switch/pes13-fex/launcher';art=read(artroot/'assets.json')
    if art['format']!=2:raise ValueError('Wrong artwork format')
    for n,h in art['inputs'].items():checked(ROOT/n,h)
    for n,h in art['files'].items():files['switch/pes13-fex/launcher/'+n]=checked(artroot/n,h)
    files['switch/pes13-fex/launcher/assets.json']=(artroot/'assets.json').read_bytes()
    active=sorted(n for n in files if n.startswith('switch/'))
    for n in active:
        if n in baseline:files['rollback/'+n]=baseline[n]
    if any(n.endswith(('settings.dat','selected.txt','debug-timestamp.txt')) for n in active):
        raise ValueError('Package would overwrite user preferences')
    sources=set(new['patch_sources'])|{'src/fex/'+n for n in new['adapter_sources']}|set(art['inputs'])
    for name in CHECKS:
        path=WORK/(name+'.json');r=read(path)
        if r.get('passed') is not True or r['native_elf_sha256']!=new['native_elf_sha256']:raise ValueError('Stale check: '+name)
        for n,h in r.get('source_hashes',r.get('source_sha256',{})).items():checked(ROOT/n,h);sources.add(n)
        files['evidence/checks/'+name+'.json']=path.read_bytes()
    for n in ('runtime-build.json','wine-patches.json'):files['evidence/runtime/'+n]=(WORK/'runtime'/n).read_bytes()
    generated=Path(new['native_source']).parent
    for n in (*delta,'dlls/winevulkan/vulkan_thunks.c'):
        files['source/generated/'+n]=checked(generated/n,patches['native-source'][n])
    sources|={'tools/package-fextendo-v2.py','tools/analyze-fex-memory-gaps.py','tests/run_fextendo_checks.py',
              'docs/FEXTENDO-V2.md','assets/README.md','assets/fextendo-v2/GENERATION.md',
              'tools/render-fextendo-preview.py','config/fextendo/presets/dxvk.conf'}
    for n in sources:files['source/'+n]=(ROOT/n).read_bytes()
    files['licenses/Inter-OFL.txt']=(ROOT/'assets/fonts/Inter/OFL.txt').read_bytes()
    files['evidence/input/fex-runtime.log']=checked(ROOT/'TEST RESULT/fex-runtime.log',LOG_SHA)
    if read(WORK/'memory-analysis.json')['sha256']!=LOG_SHA:raise ValueError('Wrong analysis input')
    files['evidence/input/memory-analysis.json']=(WORK/'memory-analysis.json').read_bytes()
    for path in sorted((WORK/'preview').glob('*')):
        if path.suffix in ('.png','.gif'):files['preview/'+path.name]=path.read_bytes()
    files['README.md']=(ROOT/'docs/FEXTENDO-V2.md').read_bytes()
    files['THIRD_PARTY.md']=(ROOT/'THIRD_PARTY.md').read_bytes()
    manifest={'kind':'fextendo-v2-budget','hardware_tested':False,'requires':'existing Fextendo/PES13 installation',
              'baseline_zip_sha256':BASES,'native_elf_sha256':new['native_elf_sha256'],'nro_sha256':new['nro_sha256'],
              'native_changed':delta,'checks':list(CHECKS),'input_log_sha256':LOG_SHA,
              'vsync':True,'debug_timestamp_default':False,'memory_budget_extension_default':False,
              'active_files':active,'rollback_target':'memory-trial runtime/config + Fextendo v1 artwork',
              'files':{n:sha(b) for n,b in sorted(files.items())}}
    files['manifest.json']=enc(manifest)
    for n,b in files.items():p=folder/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in sorted(files.items()):
            info=zipfile.ZipInfo(n,(2026,9,28,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16;z.writestr(info,b)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() or len(z.namelist())!=len(files):raise ValueError('Final inventory')
        for n,b in files.items():
            if z.read(n)!=b:raise ValueError('Final member: '+n)
    print(json.dumps({'passed':True,'path':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive.read_bytes()),
                      'active_files':len(active),'checks':len(CHECKS)},indent=2))
if __name__=='__main__':main()
