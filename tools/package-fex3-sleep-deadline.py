"""Package monotonic Wine sleeps with the tested emitter/VSync/540p profile."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'local/fex3/sleep-deadline'
NRO='switch/pes13-fex/pes13-fex.nro'
INPUT='09c1c17e34a666fd64ac605e8ca930ebacf540f7964378bf2d005979d6fe90ae'


def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_text())


def checked(path,digest):
    data=path.read_bytes()
    if sha(data)!=digest:raise ValueError('Hash mismatch '+str(path))
    return data


def main():
    spec=importlib.util.spec_from_file_location('stable',ROOT/'tools/package-fex3-stability.py')
    stable=importlib.util.module_from_spec(spec);spec.loader.exec_module(stable)
    base=ROOT/'dist/pes13-fex3-emit-vsync.zip'
    checked(base,'c6b901806398f4daf88d5296161a76b16ae2a7dbef387e97db73fd67b4160965')
    files={}
    with zipfile.ZipFile(base) as archive:
        if archive.testzip():raise ValueError('Corrupt baseline ZIP')
        manifest=json.loads(archive.read('manifest.json'))
        for name,digest in manifest['files'].items():
            data=archive.read(name)
            if sha(data)!=digest:raise ValueError('Baseline member mismatch '+name)
            if name.startswith('switch/'):
                files[name]=data;files['rollback/'+name]=data
            elif name.startswith('evidence/'):
                files['evidence/emit-vsync/'+name.removeprefix('evidence/')]=data
            elif name.startswith(('source/','licenses/')) or name=='THIRD_PARTY.md':files[name]=data
    new=read(WORK/'runtime/runtime-build.json')
    old=read(ROOT/'local/fex3/jit-latency/runtime/runtime-build.json')
    for flag in ('sleep_deadline','jit_latency','warm_audit','hang_audit','stability','samecore_yield','resume_gate'):
        if new.get(flag) is not True:raise ValueError('Missing build flag '+flag)
    for key in ('native_dependencies','ntdll_sha256','wow64_sha256','guest_sha256','toolchain_path','adapter_sources'):
        if new[key]!=old[key]:raise ValueError('Unexpected dependency delta '+key)
    for name,digest in new['patch_sources'].items():checked(ROOT/name,digest)
    for name,digest in new['adapter_sources'].items():checked(ROOT/'src/fex'/name,digest)
    np=read(WORK/'runtime/wine-patches.json')
    op=read(ROOT/'local/fex3/jit-latency/runtime/wine-patches.json')
    if np['pe-source']!=op['pe-source']:raise ValueError('PE source changed')
    delta=sorted(k for k in np['native-source'].keys()|op['native-source'].keys()
                 if np['native-source'].get(k)!=op['native-source'].get(k))
    if delta!=['dlls/ntdll/unix/horizon.c','dlls/ntdll/unix/sync.c','wine-nx-probe/source/runtime.c']:
        raise ValueError('Unexpected native source delta')
    nro=checked(WORK/'runtime/payload/pes13-fex.nro',new['nro_sha256'])
    elf=WORK/'runtime/reference/pes13-fex.elf'
    checked(elf,new['native_elf_sha256']);stable.verify_executable(elf,nro)
    if b'[FEX3-SLEEP] v1' not in nro or b'[FEX3-WAIT] tid=' not in nro:raise ValueError('Missing markers')
    files[NRO]=nro
    files['rollback/'+NRO]=checked(ROOT/'local/fex3/jit-latency/runtime/payload/pes13-fex.nro',old['nro_sha256'])
    files['README.md']=(ROOT/'docs/FEX3-SLEEP-DEADLINE.md').read_bytes()
    checks={
        'sleep.json':{'native_elf_sha256':new['native_elf_sha256'],'before_native_elf_sha256':old['native_elf_sha256']},
        'resume.json':{'native_elf_sha256':new['native_elf_sha256']},
        'pipeline.json':{'native_elf_sha256':new['native_elf_sha256']},
        'unwind.json':{'native_elf_sha256':new['native_elf_sha256'],'fex_sha256':manifest['dll_sha256'],
                       'ntdll_sha256':new['ntdll_sha256'],'wow64_sha256':new['wow64_sha256']},
    }
    for name,expected in checks.items():
        r=read(WORK/name)
        if r.get('passed') is not True or any(r.get(k)!=v for k,v in expected.items()):
            raise ValueError('Invalid/stale receipt '+name)
        for path,digest in r.get('source_hashes',{}).items():checked(ROOT/path,digest)
        files['evidence/'+name]=(WORK/name).read_bytes()
    evidence=ROOT/'local/fex3/event-slowmo'/INPUT
    checked(evidence/'fex-runtime.log',INPUT)
    analysis=(evidence/'slowmo-analysis.json').read_bytes()
    if json.loads(analysis)['sha256']!=INPUT:raise ValueError('Input analysis mismatch')
    files['evidence/input-analysis.json']=analysis
    for name in ('runtime-build.json','wine-patches.json'):
        files['evidence/runtime/'+name]=(WORK/'runtime'/name).read_bytes()
    for name in (*new['patch_sources'], 'tools/package-fex3-sleep-deadline.py',
                 'tests/fex_sleep_deadline.py','tests/fex_samecore_binary.py',
                 'tests/fex_reservations.py','tests/fex_resume_gate.py',
                 'tests/fex_resume_binary.py','tests/fex_self_suspend_binary.py',
                 'tests/fex_pipeline_binary.py'):
        files['source/'+name]=(ROOT/name).read_bytes()
    files['licenses/Wine-and-PES13-LGPL-2.1.txt']=(ROOT/'LICENSE').read_bytes()
    expected=sorted([NRO,*manifest['replaces']])
    if sorted(n for n in files if n.startswith('switch/'))!=expected:raise ValueError('Overlay boundary')
    if sorted(n.removeprefix('rollback/') for n in files if n.startswith('rollback/'))!=expected:
        raise ValueError('Rollback boundary')
    result={'kind':'Monotonic relative sleeps plus emitter/VSync-off/540p profile',
            'hardware_tested':False,'slowmo_fix_verified':False,'stutter_fix_verified':False,
            'requires_existing_build':'pes13-fex3-emit-vsync','replaces':expected,
            'native_source_delta':delta,'native_elf_sha256':new['native_elf_sha256'],
            'nro_sha256':new['nro_sha256'],'dll_sha256':manifest['dll_sha256'],
            'baseline_log_sha256':INPUT,'files':{n:sha(b) for n,b in sorted(files.items())}}
    files['manifest.json']=(json.dumps(result,indent=2)+'\n').encode()
    output=ROOT/'dist/pes13-fex3-sleep-deadline.zip';folder=output.with_suffix('')
    if output.exists() or folder.exists():raise FileExistsError('Preserve existing artifact')
    with tempfile.TemporaryDirectory(prefix='fex-sleep-',dir=output.parent) as tmp:
        path=Path(tmp)/'package.zip'
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,data in sorted(files.items()):
                if name.startswith('/') or '..' in Path(name).parts:raise ValueError('Unsafe archive path')
                info=zipfile.ZipInfo(name,(2026,9,28,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                info.external_attr=0o100644<<16;archive.writestr(info,data)
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() or set(archive.namelist())!=set(files):raise ValueError('ZIP integrity')
            for name,data in files.items():
                if archive.read(name)!=data:raise ValueError('ZIP readback '+name)
        with output.open('xb') as stream:stream.write(path.read_bytes())
    folder.mkdir()
    for name,data in files.items():
        path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        if path.read_bytes()!=data:raise ValueError('Folder readback '+name)
    report={'passed':True,'path':str(output),'bytes':output.stat().st_size,
            'sha256':sha(output.read_bytes()),'files':len(files),'replaces':expected}
    (WORK/'package.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
