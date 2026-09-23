"""Verify linked Wine hooks, immutable CPU emitters, source restoration and NRO."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
p=Path(__file__).resolve().parents[1];w=p/'local/perf27'
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
build=root/'runtime-perf27-wakes';prior=root/'runtime-perf26-callret';source=root/'runtime-perf11-source'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
tests=json.loads((w/'wait-tests.json').read_text())
for name,digest in tests['source_sha256'].items():assert sha(p/name)==digest,name
path=p/'tools/verify-perf25.py'
text=path.read_text().replace('local/perf25','local/perf27').replace('runtime-perf25-paircopy','runtime-perf27-wakes')
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
for name in ('wine-nx-box64-core-dynarec_native.c','wine-nx-box64-core-dynarec_arm64_00.c','wine-nx-box64-core-dynarec.c'):
    assert (build/name).read_bytes()==(prior/name).read_bytes(),name
assert (w/'pes13_perf21_callret.h').read_bytes()==(p/'local/perf26/pes13_perf21_callret.h').read_bytes()
for f in (w/'generated').glob('*.c'):
    assert f.read_bytes()==(p/'local/perf26/generated'/f.name).read_bytes(),f
sdk=Path('/opt/devkitpro/devkitA64/bin')
symbols=subprocess.check_output([str(sdk/'aarch64-none-elf-nm'),str(build/'wine-nx-runtime.elf')],text=True)
for name in ('wine_nx_perf27_span','wine_nx_perf27_sync_snapshot','wine_nx_perf26_report','wine_nx_box64_callret_trap'):
    assert any(s.endswith(' '+name) and ' U ' not in s for s in symbols.splitlines()),name
for file,hook in [('vulkan.c.obj','wine_nx_perf27_span'),('vulkan_thunks.c.obj','wine_nx_perf27_span'),
                  ('horizon.c.obj','pes27_signal_object_locked')]:
    objects=list(build.rglob(file))
    if file=='vulkan.c.obj':objects=[f for f in objects if f.parent.name=='win32u']
    assert len(objects)==1,(file,objects)
    dis=subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-dr',str(objects[0])],text=True)
    assert hook in dis,(file,hook)
deps=subprocess.check_output(['ninja','-C',str(build),'-t','deps'],text=True)
for name in ('wait','horizon','metrics','runtime'):
    assert str(p/f'src/runtime/pes13_perf27_{name}.h') in deps,name
for rel in ('dlls/ntdll/unix/horizon.c','dlls/win32u/vulkan.c','dlls/winevulkan/vulkan_thunks.c'):
    assert 'pes13_perf27' not in (source/rel).read_text(),rel
assert json.loads((w/'build.json').read_text())['source_restored']
report=json.loads((w/'verification.json').read_text())
report.update({'wait_tests':tests,'same_cpu_emitters_and_policy_as_perf26':True,
    'linked_horizon_and_vulkan_hooks_verified':True,'source_restored':True,
    'hardware_tested':False,'changed_sources_sha256':{str(f.relative_to(p)):sha(f) for f in [
        p/'tools/build-perf27.py',p/'tools/verify-perf27.py',p/'tools/perf27_patches.py',
        *[p/f'src/runtime/pes13_perf27_{n}.h' for n in ('wait','horizon','metrics','runtime')]]}})
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF27 actual Wine objects/hooks, unchanged CPU emitters/policy and restored sources verified')
