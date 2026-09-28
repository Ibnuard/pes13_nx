"""Package incremental placement on the smoother yield-burst payload, with rollback."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT/'local/fex3/stable-balance'
NRO = 'switch/pes13-fex/pes13-fex.nro'
INPUT = '7faa5ceffad038ce98ff9861c4a2ca69fd4361d1c59471a20a0078a64c7601e5'
BASE = '173983edacc1ce7a07929c71a7104ed9ae8c083266e3243fb2281f9f574f174e'


def sha(data): return hashlib.sha256(data).hexdigest()
def read(path): return json.loads(path.read_text())
def encoded(value): return (json.dumps(value,indent=2)+'\n').encode()


def checked(path,digest):
    data=path.read_bytes()
    if sha(data)!=digest:raise ValueError('Hash mismatch '+str(path))
    return data


def main():
    spec=importlib.util.spec_from_file_location('stable',ROOT/'tools/package-fex3-stability.py')
    stable=importlib.util.module_from_spec(spec);spec.loader.exec_module(stable)
    base=ROOT/'dist/pes13-fex3-yield-burst.zip';checked(base,BASE)
    files={}
    with zipfile.ZipFile(base) as archive:
        if archive.testzip():raise ValueError('Corrupt baseline ZIP')
        manifest=json.loads(archive.read('manifest.json'));names=archive.namelist()
        if len(names)!=len(set(names)) or set(names)!=set(manifest['files'])|{'manifest.json'}:
            raise ValueError('Baseline member inventory')
        for name,digest in manifest['files'].items():
            data=archive.read(name)
            if sha(data)!=digest:raise ValueError('Baseline member mismatch '+name)
            if name.startswith('switch/'):
                files[name]=data;files['rollback/'+name]=data
            elif name.startswith(('evidence/','source/')):
                prefix,rest=name.split('/',1);files[prefix+'/yield-burst/'+rest]=data
            elif name.startswith(('licenses/','benchmark/')) or name=='THIRD_PARTY.md':files[name]=data
        files['evidence/yield-burst/manifest.json']=archive.read('manifest.json')
    new=read(WORK/'runtime/runtime-build.json')
    old=json.loads(files['evidence/yield-burst/runtime/runtime-build.json'])
    for flag in ('stable_balance','yield_burst','jit_log_queue','worker_cores','sleep_deadline','jit_latency',
                 'warm_audit','hang_audit','stability','samecore_yield','resume_gate'):
        if new.get(flag) is not True:raise ValueError('Missing build flag '+flag)
    if new.get('yield_adaptive') is not False:raise ValueError('Adaptive yield must be absent')
    for key in ('native_dependencies','ntdll_sha256','wow64_sha256','guest_sha256',
                'toolchain_path','adapter_sources'):
        if new[key]!=old[key]:raise ValueError('Unexpected dependency delta '+key)
    for path,digest in new['patch_sources'].items():checked(ROOT/path,digest)
    for path,digest in new['adapter_sources'].items():checked(ROOT/'src/fex'/path,digest)
    np=read(WORK/'runtime/wine-patches.json')
    op=json.loads(files['evidence/yield-burst/runtime/wine-patches.json'])
    if np['pe-source']!=op['pe-source']:raise ValueError('PE source delta')
    delta=sorted(k for k in np['native-source'].keys()|op['native-source'].keys()
                 if np['native-source'].get(k)!=op['native-source'].get(k))
    if delta!=['wine-nx-probe/source/runtime.c','wine-nx-probe/source/thread_profile.c']:
        raise ValueError('Unexpected native source delta '+repr(delta))
    nro=checked(WORK/'runtime/payload/pes13-fex.nro',new['nro_sha256'])
    elf=WORK/'runtime/reference/pes13-fex.elf';checked(elf,new['native_elf_sha256'])
    stable.verify_executable(elf,nro)
    for marker in (b'pes13-fex3-stable-balance',b'[FEX3-YIELD] v1',b'[FEX3-BALANCE] v1',b'[FEX3-JITLOG] v1',
                   b'[FEX3-CORES] v1',b'[FEX3-COREMAP]',b'[FEX3-SLEEP] v1'):
        if marker not in nro:raise ValueError('Missing marker '+str(marker))
    if b'[FEX3-YIELD-ADAPT]' in nro:raise ValueError('Adaptive policy leaked into candidate')
    files[NRO]=nro
    if sha(files['rollback/'+NRO])!=old['nro_sha256']:raise ValueError('Rollback NRO')
    files['README.md']=(ROOT/'docs/FEX3-STABLE-BALANCE.md').read_bytes()
    checks={
        'balance.json':{'before_native_elf_sha256':old['native_elf_sha256']},
        'yield.json':{'before_native_elf_sha256':json.loads(
            files['evidence/yield-burst/camera-720/runtime/runtime-build.json'])['native_elf_sha256']},
        'resume.json':{},'pipeline.json':{},
        'cores.json':{},
        'jit-log.json':{'before_native_elf_sha256':'03d571884b36c132b593949ed1900b33d590ad6e5c926dca16d99679cd225bdd',
                        'generated_runtime_sha256':np['native-source']['wine-nx-probe/source/runtime.c']},
        'unwind.json':{'fex_sha256':manifest['dll_sha256'],
                       'ntdll_sha256':new['ntdll_sha256'],'wow64_sha256':new['wow64_sha256']},
    }
    # The core-policy regression uses its original pre-policy ELF as the red baseline.
    checks['cores.json']['before_native_elf_sha256']=json.loads(
        files['evidence/yield-burst/camera-720/worker-cores/sleep-deadline/runtime/runtime-build.json'])['native_elf_sha256']
    for name,expected in checks.items():
        expected['native_elf_sha256']=new['native_elf_sha256'];report=read(WORK/name)
        if report.get('passed') is not True or any(report.get(k)!=v for k,v in expected.items()):
            raise ValueError('Invalid/stale test receipt '+name)
        for path,digest in report.get('source_hashes',report.get('source_sha256',{})).items():checked(ROOT/path,digest)
        for path,digest in report.get('generated_source_hashes',{}).items():
            if np['native-source'].get(path)!=digest:raise ValueError('Generated test source mismatch '+path)
        files['evidence/'+name]=(WORK/name).read_bytes()
    files['evidence/checkpoint-sync.c']=checked(ROOT/'local/fex3/yield-adaptive/before/sync.c',
                                                   op['native-source']['dlls/ntdll/unix/sync.c'])
    files['evidence/before/sync.c']=checked(ROOT/'local/fex3/yield-burst/before/sync.c',
        json.loads(files['evidence/yield-burst/camera-720/runtime/wine-patches.json'])['native-source']['dlls/ntdll/unix/sync.c'])
    evidence=ROOT/'local/fex3/adaptive-feedback'/INPUT
    checked(evidence/'fex-runtime.log',INPUT);checked(ROOT/'TEST RESULT/fex-runtime.log',INPUT)
    for name in ('pacing.json','core-pressure.json'):
        data=(evidence/name).read_bytes()
        if json.loads(data)['sha256']!=INPUT:raise ValueError('Analysis hash mismatch')
        files['evidence/input/'+name]=data
    for name in ('runtime-build.json','wine-patches.json'):
        files['evidence/runtime/'+name]=(WORK/'runtime'/name).read_bytes()
    for name in (*new['patch_sources'],'tools/package-fex3-stable-balance.py',
                 'tools/package-fex3-stability.py','tools/analyze-fex-core-pressure.py',
                 'tools/analyze-fex-pacing.py','tests/fex_yield_burst.py','tests/fex_balance_stable.py',
                 'tests/fex_worker_cores.py','tests/fex_jit_log_queue.py',
                 'tests/fex_reservations.py','tests/fex_resume_gate.py',
                 'tests/fex_samecore_binary.py','tests/fex_resume_binary.py',
                 'tests/fex_self_suspend_binary.py','tests/fex_pipeline_binary.py',
                 'tests/fex_unwind.py','tests/fex_alloc.py'):
        files['source/'+name]=(ROOT/name).read_bytes()
    expected=sorted(manifest['replaces'])
    if len(expected)!=6 or sorted(n for n in files if n.startswith('switch/'))!=expected:
        raise ValueError('Overlay boundary')
    if sorted(n.removeprefix('rollback/') for n in files if n.startswith('rollback/'))!=expected:
        raise ValueError('Rollback boundary')
    for name in expected:
        if name!=NRO and files[name]!=files['rollback/'+name]:raise ValueError('Payload drift '+name)
    result={'kind':'Restore yield-burst polling; incremental single-worker balancing',
            'hardware_tested':False,'stutter_fix_verified':False,'kickoff_fix_verified':False,
            'requires_existing_build':['pes13-fex3-yield-burst','pes13-fex3-yield-adaptive'],
            'checkpoint_commit':'cf4f43e','baseline_package_sha256':BASE,
            'baseline_log_sha256':INPUT,'native_source_delta':delta,'replaces':expected,
            'nro_sha256':new['nro_sha256'],'native_elf_sha256':new['native_elf_sha256'],
            'dll_sha256':manifest['dll_sha256'],'active_settings':manifest['active_settings'],
            'files':{n:sha(b) for n,b in sorted(files.items())}}
    files['manifest.json']=encoded(result)
    output=ROOT/'dist/pes13-fex3-stable-balance.zip';folder=output.with_suffix('')
    if output.exists() or folder.exists():raise FileExistsError('Preserve existing artifact')
    with tempfile.TemporaryDirectory(prefix='fex-yield-',dir=output.parent) as tmp:
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
    (WORK/'package.json').write_bytes(encoded(report));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
