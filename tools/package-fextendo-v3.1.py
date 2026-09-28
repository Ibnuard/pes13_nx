"""Bind v3.1 runtime/artwork/checks to the verified v3 baseline and exact rollback."""
from pathlib import Path
import hashlib,importlib.util,json,zipfile
from nro_assets import inspect_nro
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'local/fex3/fextendo-v3.1'
BASE='pes13-fextendo-v3.zip'
BASE_SHA='96f27663e2e262747f0a8eae7889de7908c8b3e80acbf18623b2574ccff5ae68'
NRO='switch/pes13-fex/pes13-fex.nro'
CHECKS=('launcher','memory','budget','gap','balance','yield','cores','resume','pipeline','jit-log','unwind')
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text())
def checked(p,h):
    b=p.read_bytes()
    if sha(b)!=h:raise ValueError('Hash mismatch: '+str(p))
    return b
def enc(v):return (json.dumps(v,indent=2)+'\n').encode()
def main():
    archive=ROOT/'dist/pes13-fextendo-v3.1.zip';folder=archive.with_suffix('')
    if archive.exists() or folder.exists():raise FileExistsError('Existing artifact protected')
    files={};baseline={};checked(ROOT/'dist'/BASE,BASE_SHA)
    with zipfile.ZipFile(ROOT/'dist'/BASE) as z:
        manifest=json.loads(z.read('manifest.json'))
        if z.testzip() or len(z.namelist())!=len(set(z.namelist())) or set(z.namelist())!=set(manifest['files'])|{'manifest.json'}:
            raise ValueError('Baseline inventory')
        for n,h in manifest['files'].items():
            b=z.read(n)
            if sha(b)!=h:raise ValueError('Baseline member: '+n)
            if n.startswith('switch/'):baseline[n]=b
            if n.startswith('licenses/'):files[n]=b
        files['evidence/baseline/'+BASE+'.manifest.json']=z.read('manifest.json')
        old=json.loads(z.read('evidence/runtime/runtime-build.json'))
        previous=json.loads(z.read('evidence/runtime/wine-patches.json'))
    new=read(WORK/'runtime/runtime-build.json');patches=read(WORK/'runtime/wine-patches.json')
    for k in ('native_dependencies','adapter_sources','ntdll_sha256','wow64_sha256','guest_sha256','toolchain_path'):
        if new[k]!=old[k]:raise ValueError('Dependency changed: '+k)
    for k,v in old.items():
        if isinstance(v,bool) and new.get(k)!=v:raise ValueError('Build flag changed: '+k)
    for k in ('launcher','memory_audit','memory_budget_filter','stable_balance','gap_audit'):
        if new.get(k) is not True:raise ValueError('Missing build flag: '+k)
    if new['yield_adaptive'] or patches['pe-source']!=previous['pe-source']:raise ValueError('Unexpected guest delta')
    delta=sorted(n for n in patches['native-source'].keys()|previous['native-source'].keys()
                 if patches['native-source'].get(n)!=previous['native-source'].get(n))
    if delta!=['wine-nx-probe/source/runtime.c']:raise ValueError('Native delta: '+repr(delta))
    for n,h in new['patch_sources'].items():checked(ROOT/n,h)
    for n,h in new['adapter_sources'].items():checked(ROOT/'src/fex'/n,h)
    nro=checked(WORK/'runtime/payload/pes13-fex.nro',new['nro_sha256'])
    elf=WORK/'runtime/reference/pes13-fex.elf';checked(elf,new['native_elf_sha256'])
    spec=importlib.util.spec_from_file_location('stable',ROOT/'tools/package-fex3-stability.py')
    stable=importlib.util.module_from_spec(spec);spec.loader.exec_module(stable);stable.verify_executable(elf,nro)
    icon=(ROOT/'assets/fextendo-v3/nro-icon.jpg').read_bytes()
    metadata=inspect_nro(nro,icon,expected_title='FEXTendo / PES13',expected_version='0.3.2')
    if metadata!=new['metadata'] or metadata['author']!='AndroSwitch Project':raise ValueError('NRO metadata')
    for marker in (b'pes13-fextendo-v3.1-focus',b'[FEX3-MEMBUDGET]',b'[FEXTENDO-TIME]',b'Debug timestamp',b'Last played'):
        if marker not in nro:raise ValueError('Missing marker: '+repr(marker))
    files[NRO]=nro
    config=(ROOT/'config/fextendo/presets/dxvk.conf').read_bytes()
    for n in ('switch/pes13-fex/drive_c/PES13/dxvk.conf','switch/pes13-fex/launcher/presets/dxvk.conf'):
        if baseline[n]!=config:raise ValueError('Config changed: '+n)
        files[n]=config
    artroot=WORK/'package/switch/pes13-fex/launcher';art=read(artroot/'assets.json')
    if art['format']!=3:raise ValueError('Artwork format')
    for n,h in art['inputs'].items():checked(ROOT/n,h)
    for n,h in art['files'].items():files['switch/pes13-fex/launcher/'+n]=checked(artroot/n,h)
    if sha(icon)!=art['files']['nro-icon.jpg']:raise ValueError('NRO icon differs from artwork')
    files['switch/pes13-fex/launcher/assets.json']=(artroot/'assets.json').read_bytes()
    active=sorted(n for n in files if n.startswith('switch/'))
    for n in active:
        if n in baseline:files['rollback/'+n]=baseline[n]
    protected=('settings.dat','selected.txt','debug-timestamp.txt','menu-sound.txt','last-played.txt')
    if any(n.endswith(protected) for n in active):raise ValueError('Package overwrites preferences')
    sources=set(new['patch_sources'])|{'src/fex/'+n for n in new['adapter_sources']}|set(art['inputs'])
    for name in CHECKS:
        path=WORK/(name+'.json');r=read(path)
        if r.get('passed') is not True or r['native_elf_sha256']!=new['native_elf_sha256']:raise ValueError('Stale check: '+name)
        for n,h in r.get('source_hashes',r.get('source_sha256',{})).items():checked(ROOT/n,h);sources.add(n)
        files['evidence/checks/'+name+'.json']=path.read_bytes()
    for n in ('runtime-build.json','wine-patches.json'):files['evidence/runtime/'+n]=(WORK/'runtime'/n).read_bytes()
    generated=Path(new['native_source']).parent
    for n in delta:files['source/generated/'+n]=checked(generated/n,patches['native-source'][n])
    sources|={'tools/package-fextendo-v3.1.py','tools/benchmark-fextendo-ui.py','tests/run_fextendo_checks.py','tools/nro_assets.py',
              'docs/FEXTENDO-V3.1.md','docs/FEXTENDO-V3.md','assets/README.md','assets/fextendo-v2/GENERATION.md',
              'assets/fextendo-v3/nro-icon.jpg','tools/render-fextendo-preview.py','config/fextendo/presets/dxvk.conf'}
    for n in sources:files['source/'+n]=(ROOT/n).read_bytes()
    files['licenses/Inter-OFL.txt']=(ROOT/'assets/fonts/Inter/OFL.txt').read_bytes()
    preview=read(WORK/'preview/preview.json')
    for n,h in preview['sources'].items():checked(ROOT/n,h)
    for n,h in preview['files'].items():files['preview/'+n]=checked(WORK/'preview'/n,h)
    files['preview/preview.json']=enc(preview)
    benchmark=read(WORK/'ui-benchmark.json')
    if benchmark['native_elf_sha256']!=new['native_elf_sha256']:raise ValueError('Stale benchmark')
    for n,h in benchmark['source_hashes'].items():checked(ROOT/n,h)
    files['evidence/ui-benchmark.json']=enc(benchmark)
    files['README.md']=(ROOT/'docs/FEXTENDO-V3.1.md').read_bytes()
    files['THIRD_PARTY.md']=(ROOT/'THIRD_PARTY.md').read_bytes()
    manifest={'kind':'fextendo-v3.1-focus','hardware_tested':False,'requires':'existing Fextendo/PES13 installation',
              'baseline_zip_sha256':{BASE:BASE_SHA},'native_elf_sha256':new['native_elf_sha256'],'nro_sha256':new['nro_sha256'],
              'native_changed':delta,'checks':list(CHECKS),'vsync':True,'debug_timestamp_default':False,
              'menu_sound_default':True,'memory_budget_extension_default':False,
              'glow_cycle_seconds':12,'menu_target_hz':60,'splash_ms':800,'ui_cpu_host_speedup':benchmark['speedup'],
              'active_files':active,'rollback_target':'FEXTendo v3 runtime/config/artwork',
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
    report={'passed':True,'path':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive.read_bytes()),
            'active_files':len(active),'checks':len(CHECKS)}
    (WORK/'package.json').write_bytes(enc(report));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
