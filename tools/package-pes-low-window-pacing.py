"""Copy-ready low-window NRO update with exact previous rollback; no NSP."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
TARGET='switch/pes13-fex/pes13-low-window.nro'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--revision',type=int,choices=(2,3),default=2)
    ap.add_argument('--runtime',type=Path,required=True)
    ap.add_argument('--previous-runtime',type=Path,required=True)
    ap.add_argument('--previous',type=Path,default=ROOT/'dist/pes13-low-window-v1')
    ap.add_argument('--evidence',type=Path,default=ROOT/'local/pes-low-window-v2')
    ap.add_argument('--output',type=Path,default=ROOT/'dist/pes13-low-window-v2-pacing')
    a=ap.parse_args();a.output.resolve().relative_to((ROOT/'dist').resolve())
    assert not a.output.exists(),'Use a fresh package directory'
    build,previous,tests,host=(read(p) for p in (a.runtime/'build.json',a.previous/'package.json',
        a.evidence/'binary-tests.json',a.evidence/'host-tests.json'))
    assert build['built'] and build['version']==f'0.3.9-lw{a.revision}'
    assert tests['passed'] and tests['elf_sha256']==build['elf_sha256']
    assert tests['normal_launch_diagnostic_io_disabled'] and tests['lw2_pacing_debug_gate_checked']
    if a.revision==3:assert tests['lw3_live_settings_and_vk_attribution_checked']
    assert host['passed'] and not host['hardware_tested']
    assert previous['version']==f'0.3.9-lw{a.revision-1}' and previous['abi']=='fxtmem-v1'
    assert sha(a.runtime/'native-build/wine-nx-runtime.elf')==build['elf_sha256']
    assert sha(a.runtime/'pes13-fex.nro')==build['nro_sha256']
    old_build=read(a.previous_runtime/'build.json')
    assert old_build['nro_sha256']==previous['payload'][TARGET]==sha(a.previous/TARGET)
    for rel,digest in previous['files'].items():assert sha(a.previous/rel)==digest,rel
    for rel,digest in build['inputs'].items():assert sha(ROOT/rel)==digest,rel
    for rel,digest in host['sources'].items():assert sha(ROOT/rel)==digest,rel
    for root,key in (('native-source','source_changes'),('feature','feature_changes')):
        for rel,digest in build[key].items():assert sha(a.runtime/root/rel)==digest,rel
    # Every old native source except runtime.c and rebased CMake must remain
    # identical. In particular this does not retune FEX or memory allocation.
    old=read(a.previous_runtime/'prepared.json');new=read(a.runtime/'prepared.json')
    native_delta={n for n in set(old['after'])|set(new['after']) if old['after'].get(n)!=new['after'].get(n)}
    assert native_delta=={'wine-nx-probe/source/runtime.c','wine-nx-probe/CMakeLists.txt'},native_delta
    feature_delta={n for n in set(old['feature_after'])|set(new['feature_after']) if old['feature_after'].get(n)!=new['feature_after'].get(n)}
    expected_feature=({'src/runtime/fextendo_presets.h','src/runtime/pes_low_window_diagnostics.h'} if a.revision==2 else
        {'src/runtime/fextendo_wait_probe.h','src/runtime/pes_live_settings.h','src/runtime/pes_vk_work.h'})
    assert feature_delta==expected_feature,feature_delta
    if a.revision==3:
        for name in ('pes_live_settings.h','pes_vk_work.h'):
            assert sha(a.runtime/'feature/src/runtime'/name)==sha(ROOT/'src/runtime'/name)
        oracle=read(a.evidence/'settings-oracle.json')
        assert oracle['passed'] and oracle['bit']=='0x0002'
        assert not any(v['frame_skipping'] for v in oracle['references'].values())
    a.output.mkdir(parents=True)
    def copy(p,rel):
        out=a.output/rel;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
    copy(a.runtime/'pes13-fex.nro',TARGET)
    copy(a.previous/TARGET,'rollback/'+TARGET)
    copy(a.previous/'package.json',f'evidence/lw{a.revision-1}-package.json')
    copy(a.runtime/'build.json','evidence/build.json')
    copy(a.runtime/'prepared.json','evidence/prepared.json')
    for name in ('binary-tests.json','host-tests.json','analysis.json',
                 'pc-settings-audit.json' if a.revision==2 else 'settings-oracle.json'):
        copy(a.evidence/name,'evidence/'+name)
    for directory in ('source','licenses'):
        if (a.previous/directory).exists():shutil.copytree(a.previous/directory,a.output/directory/f'lw{a.revision-1}-baseline')
    sources=set(build['inputs'])|set(host['sources'])|{
        'tools/package-pes-low-window-pacing.py','tools/analyze-pes-low-window-run.py','tests/pes_low_window_binary.py'}
    if a.revision==3:sources.add('tools/audit-pes-settings-reference.py')
    for rel in sorted(sources):copy(ROOT/rel,f'source/lw{a.revision}/'+rel)
    diffs=[]
    for root,names in (('native-source',native_delta),('feature',feature_delta)):
        for rel in sorted(names):
            before=a.previous_runtime/root/rel;after=a.runtime/root/rel
            diffs.extend(difflib.unified_diff(before.read_text().splitlines(keepends=True) if before.exists() else [],
                after.read_text().splitlines(keepends=True),fromfile='a/'+root+'/'+rel,tofile='b/'+root+'/'+rel))
            copy(after,'source/generated/'+root+'/'+rel)
    (a.output/f'source/lw{a.revision}.patch').write_text(''.join(diffs))
    doc='PES13-LOW-WINDOW-V2-PACING.md' if a.revision==2 else 'PES13-LOW-WINDOW-V3-LIVE-SETTINGS.md'
    copy(ROOT/'docs'/doc,'README.md')
    files={p.relative_to(a.output).as_posix():sha(p) for p in sorted(a.output.rglob('*')) if p.is_file()}
    payload={n:h for n,h in files.items() if n.startswith('switch/')}
    assert payload=={TARGET:build['nro_sha256']}
    assert not list(a.output.rglob('*.zip')) and not list(a.output.rglob('*.nsp'))
    report=dict(built=True,version=build['version'],hardware_tested=False,abi='fxtmem-v1',
        target='/'+TARGET,previous_nro_sha256=old_build['nro_sha256'],native_elf_sha256=build['elf_sha256'],
        functional_changes=(['enforce frame skipping off; keep VSync/XInput on and preserve bindings',
                            'verify actual CRC/flags in all three settings files before launch'] if a.revision==2 else []),
        diagnostics=('Debug-only live timing fingerprint checks and existing frame/pipeline/SD counters' if a.revision==2 else
                     'Debug-only version-aware WECF reads, clock-call target observations and per-thread/stage Vulkan completed-call counters'),
        kernel_loader_changed=False,fex_changed=False,dxvk_changed=False,clock_scaled=False,
        fps_gain_verified=False,loading_time_gain_verified=False,payload=payload,files=files)
    (a.output/'package.json').write_text(json.dumps(report,indent=2)+'\n')
    files['package.json']=sha(a.output/'package.json')
    (a.output/'SHA256SUMS.txt').write_text(''.join(f'{h}  {n}\n' for n,h in sorted(files.items())))
    for n,h in files.items():assert sha(a.output/n)==h,n
    print(f'Packaged LW{a.revision}: one NRO, exact LW{a.revision-1} rollback, {len(files)} verified files, no ZIP/NSP.',flush=True)

if __name__=='__main__':main()
