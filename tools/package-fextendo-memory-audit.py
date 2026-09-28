"""Package a three-file launcher update with exact baseline rollback."""
from pathlib import Path
import hashlib
import importlib.util
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'local/fex3/memory-audit'
BASE_SHA='425e803a753bfe36fe8b993ce4e7984300e32d3b34998b99f0c53bc9f38aee85'
LOG_SHA='d4bd5f2de54efd400d6b84036059ef9d620a4bcc7ac0268d49101047ec3f370d'
NRO='switch/pes13-fex/pes13-fex.nro'
CONFIGS=('switch/pes13-fex/drive_c/PES13/dxvk.conf','switch/pes13-fex/launcher/presets/dxvk.conf')
CHECKS=('memory','launcher','gap','balance','yield','cores','resume','pipeline','jit-log','unwind')
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return (json.dumps(v,indent=2)+'\n').encode()
def read(p):return json.loads(p.read_text())
def checked(p,h):
    b=p.read_bytes()
    if sha(b)!=h:raise ValueError('Hash mismatch '+str(p))
    return b
def options(b):
    return dict((k.strip(),v.strip()) for k,v in (line.split('=',1)
                for line in b.decode().splitlines() if '=' in line and not line.lstrip().startswith('#')))


def main():
    archive=ROOT/'dist/pes13-fextendo-memory-trial.zip';folder=archive.with_suffix('')
    if archive.exists() or folder.exists():raise FileExistsError('Existing artifact protected')
    baseline=ROOT/'dist/pes13-fextendo-launcher.zip';checked(baseline,BASE_SHA)
    files={}
    with zipfile.ZipFile(baseline) as z:
        manifest=json.loads(z.read('manifest.json'))
        if z.testzip() or set(z.namelist())!=set(manifest['files'])|{'manifest.json'}:raise ValueError('Baseline inventory')
        for n,h in manifest['files'].items():
            if sha(z.read(n))!=h:raise ValueError('Baseline member '+n)
            if n.startswith('licenses/'):files[n]=z.read(n)
        for n in (NRO,*CONFIGS):files['rollback/'+n]=z.read(n)
        files['evidence/baseline/manifest.json']=z.read('manifest.json')
        old=json.loads(z.read('evidence/runtime/runtime-build.json'))
        previous=json.loads(z.read('evidence/runtime/wine-patches.json'))
    new=read(WORK/'runtime/runtime-build.json');patches=read(WORK/'runtime/wine-patches.json')
    differences={k for k in old.keys()|new.keys() if old.get(k)!=new.get(k)}
    expected={'nro_sha256','native_elf_sha256','memory_audit','metadata','patch_sources'}
    if differences!=expected or not new['memory_audit']:raise ValueError('Build profile delta '+str(differences))
    if patches['pe-source']!=previous['pe-source']:raise ValueError('PE source changed')
    delta=sorted(n for n in patches['native-source'].keys()|previous['native-source'].keys()
                 if patches['native-source'].get(n)!=previous['native-source'].get(n))
    if delta!=['dlls/winevulkan/vulkan_thunks.c','wine-nx-probe/source/runtime.c']:raise ValueError('Native delta '+repr(delta))
    patch_delta={n for n in new['patch_sources'].keys()|old['patch_sources'].keys()
                 if new['patch_sources'].get(n)!=old['patch_sources'].get(n)}
    if patch_delta!={'tools/build-fex-runtime.py','tools/fex_wine_patches.py','tools/fex_memory_probe_patches.py','src/runtime/fex_memory_probe.h'}:
        raise ValueError('Unexpected patch source changes '+str(patch_delta))
    for n,h in new['patch_sources'].items():checked(ROOT/n,h)
    for n,h in new['adapter_sources'].items():checked(ROOT/'src/fex'/n,h)
    nro=checked(WORK/'runtime/payload/pes13-fex.nro',new['nro_sha256'])
    elf=WORK/'runtime/reference/pes13-fex.elf';checked(elf,new['native_elf_sha256'])
    spec=importlib.util.spec_from_file_location('stable',ROOT/'tools/package-fex3-stability.py')
    stable=importlib.util.module_from_spec(spec);spec.loader.exec_module(stable);stable.verify_executable(elf,nro)
    if b'pes13-fextendo-mem-audit' not in nro or b'[FEX3-MEMQUERY]' not in nro:raise ValueError('Wrong markers')
    files[NRO]=nro;config=(ROOT/'config/fextendo/presets/dxvk.conf').read_bytes()
    for n in CONFIGS:
        before=options(files['rollback/'+n]);after=options(config)
        if {k for k in before|after if before.get(k)!=after.get(k)}!={'dxvk.enableMemoryDefrag'}:raise ValueError('Config delta')
        if after['dxvk.enableMemoryDefrag']!='False' or after['d3d9.presentInterval']!='1':raise ValueError('Wrong config')
        files[n]=config
    sources=set(new['patch_sources'])|{'src/fex/'+n for n in new['adapter_sources']}
    for name in CHECKS:
        p=WORK/(name+'.json');r=read(p)
        if r.get('passed') is not True or r['native_elf_sha256']!=new['native_elf_sha256']:raise ValueError('Stale test '+name)
        for n,h in r.get('source_hashes',r.get('source_sha256',{})).items():checked(ROOT/n,h);sources.add(n)
        files['evidence/checks/'+name+'.json']=p.read_bytes()
    generated=Path(new['native_source']).parent
    for n in delta:files['source/generated/'+n]=checked(generated/n,patches['native-source'][n])
    for n in ('runtime-build.json','wine-patches.json'):files['evidence/runtime/'+n]=(WORK/'runtime'/n).read_bytes()
    sources|={'tools/package-fextendo-memory-audit.py','tools/analyze-fex-memory-gaps.py',
              'tools/analyze-fex-pacing.py','tools/analyze-fex-core-pressure.py','tools/analyze-fex-jit-gaps.py',
              'tests/run_fextendo_checks.py','config/fextendo/presets/dxvk.conf','docs/FEXTENDO-MEMORY-AUDIT.md'}
    for n in sources:files['source/'+n]=(ROOT/n).read_bytes()
    feedback=ROOT/'local/fex3/fextendo-feedback'/LOG_SHA
    files['evidence/feedback/fex-runtime.log']=checked(feedback/'fex-runtime.log',LOG_SHA)
    for n in ('pacing.json','core-pressure.json','jit-gaps.json','memory-gaps.json'):
        p=feedback/n
        if read(p)['sha256']!=LOG_SHA:raise ValueError('Feedback hash '+n)
        files['evidence/feedback/'+n]=p.read_bytes()
    files['README.md']=(ROOT/'docs/FEXTENDO-MEMORY-AUDIT.md').read_bytes()
    files['THIRD_PARTY.md']=(ROOT/'THIRD_PARTY.md').read_bytes()
    files['manifest.json']=enc({'kind':'fextendo-memory-audit','baseline_zip_sha256':BASE_SHA,
        'hardware_tested':False,'native_elf_sha256':new['native_elf_sha256'],'nro_sha256':new['nro_sha256'],
        'requires':'pes13-fextendo-launcher','active_files':[NRO,*CONFIGS],
        'runtime_behavior_change':'dxvk.enableMemoryDefrag=False','guest_processors':3,'vsync':True,
        'native_changed':delta,'checks':list(CHECKS),'input_log_sha256':LOG_SHA,
        'files':{n:sha(b) for n,b in sorted(files.items())}})
    for n,b in files.items():p=folder/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in sorted(files.items()):
            i=zipfile.ZipInfo(n,(2026,9,28,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o100644<<16;z.writestr(i,b)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() or set(z.namelist())!=set(files):raise ValueError('Final inventory')
        for n,b in files.items():
            if z.read(n)!=b:raise ValueError('Final mismatch '+n)
    print(json.dumps({'passed':True,'path':str(archive),'bytes':archive.stat().st_size,
                      'sha256':sha(archive.read_bytes()),'files':len(files),'active_files':3,'rollback_files':3},indent=2))


if __name__=='__main__':main()
