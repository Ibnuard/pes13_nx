"""Verify the actual linked policy, unchanged emitters, ABI and restored sources."""
from pathlib import Path
import hashlib,json,os,subprocess
p=Path(__file__).resolve().parents[1];w=p/'local/perf29'
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
build=root/'runtime-perf29-worker-blocks';prior=root/'runtime-perf28-diagnostics'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
report=json.loads((w/'verification.json').read_text())
for name in ('policy','fault','wait','copy'):
    test=json.loads((w/f'{name}-tests.json').read_text())
    for path,digest in test['source_sha256'].items(): assert sha(p/path)==digest,path
    report[name+'_tests']=test
native='wine-nx-box64-core-dynarec_native.c'
text=(build/native).read_text()
assert text.count('wine_nx_perf29_completed(block, helper.env)')==1
assert text.count('wine_nx_perf29_block_end(addr, helper.end, helper.env)')==1
assert text.replace('wine_nx_perf29_completed','wine_nx_perf25_completed').replace(
    'wine_nx_perf29_block_end','wine_nx_perf22_block_end')==(prior/native).read_text()
for name in ('wine-nx-box64-core-dynarec_arm64_00.c','wine-nx-box64-core-dynarec.c'):
    assert (build/name).read_bytes()==(prior/name).read_bytes(),name
for name in ('horizon.c','vulkan.c','wow64_box64_unix.c','pes13_perf21_callret.h'):
    assert (w/name).read_bytes()==(p/'local/perf28'/name).read_bytes(),name
for f in (w/'generated').glob('*.c'):
    assert f.read_bytes()==(p/'local/perf28/generated'/f.name).read_bytes(),f
source=root/'runtime-perf11-source'
for rel,digest in json.loads((w/'source-baseline.json').read_text()).items():
    assert sha(source/rel)==digest,rel
vendor=source/'wine-nx-probe/vendor/box64'
assert subprocess.check_output(['git','-C',str(vendor),'status','--porcelain'],text=True)==''
assert subprocess.check_output(['git','-C',str(vendor),'rev-parse','HEAD'],text=True).strip()=='2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a'
sdk=Path('/opt/devkitpro/devkitA64/bin')
symbols=subprocess.check_output([str(sdk/'aarch64-none-elf-nm'),str(build/'wine-nx-runtime.elf')],text=True)
for symbol in ('wine_nx_perf29_block_end','wine_nx_perf29_completed','wine_nx_perf29_report',
               'wine_nx_perf28_identity','wine_nx_perf25_copy','wine_nx_perf27_span','wine_nx_perf24_present'):
    assert any(s.endswith(' '+symbol) and ' U ' not in s for s in symbols.splitlines()),symbol
objects=list(build.rglob('*dynarec_native.c.obj'));assert len(objects)==1,objects
dis=subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-dr',str(objects[0])],text=True)
for symbol in ('wine_nx_perf29_block_end','wine_nx_perf29_completed'):
    assert 'R_AARCH64_CALL26\t'+symbol in dis,symbol
objs=list(build.rglob('*dynarec_arm64_00.c.obj'));assert len(objs)==4
for obj in objs:
    dis=subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-dr',str(obj)],text=True)
    assert 'R_AARCH64_CALL26\twine_nx_perf25_copy' in dis
objects=list(build.rglob('wow64_box64_dynarec.c.obj'));assert len(objects)==1,objects
assert b'perf29-worker-blocks.txt' in objects[0].read_bytes()
# The small environment-normalization helper is inlined and garbage-collected
# from the ELF. Verify its references inside the actual compiled copy gate.
copy_dis=subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-dr',
    '--disassemble=wine_nx_perf25_copy',str(objects[0])],text=True)
(w/'copy-object-disassembly.txt').write_text(copy_dis)
assert 'pes29_env' in copy_dis and 'pes21_env' in copy_dis
deps=subprocess.check_output(['ninja','-C',str(build),'-t','deps'],text=True)
for file in ('src/runtime/pes13_perf29.h','src/runtime/pes13_perf29_policy.h','local/perf29/pes13_perf25_env.h'):
    assert str(p/file) in deps,file
nro=(w/'payload/switch/pes13-nx/pes13-nx.nro').read_bytes()
assert b'pes13-nx-0.2.0-perf29-worker-blocks' in nro
assert hashlib.sha256(nro).hexdigest()==json.loads((w/'build.json').read_text())['nro_sha256']
report.update({'only_native_bound_and_completion_hook_names_changed_vs_perf28':True,
    'same_math_and_copy_emitters_as_perf28':True,'same_horizon_vulkan_fault_capture_as_perf28':True,
    'compiled_scoped_block_policy_and_copy_hooks':True,'vendor_clean_at_pinned_revision':True,
    'source_restored':True,'elf_sha256':sha(build/'wine-nx-runtime.elf'),
    'hardware_tested':False,'main_cpu_sampling':False,'diagnostic_only':False,'startup_fix_claimed':False,
    'changed_sources_sha256':{str(f.relative_to(p)):sha(f) for f in [
        p/'tools/build-perf29.py',p/'tools/run-perf29-build.py',p/'tools/verify-perf29.py',
        p/'tools/perf29_patches.py',p/'src/runtime/pes13_perf29.h',p/'src/runtime/pes13_perf29_policy.h',
        p/'tests/perf29_policy.c',p/'tests/perf29_policy.py']}})
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF29 actual linked hooks, identical emitters, pinned vendor and restored sources PASS',flush=True)
