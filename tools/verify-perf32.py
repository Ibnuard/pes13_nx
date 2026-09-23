"""Verify scoped CPU policy in the linked ELF and retained PERF25 components."""
from pathlib import Path
import hashlib,json,os,subprocess
p=Path(__file__).resolve().parents[1];w=p/'local/perf32'
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
build=root/'runtime-perf32-game-blocks';prior=root/'runtime-perf25-paircopy'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
report=json.loads((w/'verification.json').read_text())
for name in ('policy','copy'):
    test=json.loads((w/f'{name}-tests.json').read_text())
    for path,digest in test['source_sha256'].items(): assert sha(p/path)==digest,path
    report[name+'_tests']=test
native='wine-nx-box64-core-dynarec_native.c'
text=(build/native).read_text()
assert text.count('wine_nx_perf32_completed(block, helper.env)')==1
assert text.count('wine_nx_perf32_block_end(addr, helper.end, helper.env)')==1
assert text.replace('wine_nx_perf32_completed','wine_nx_perf25_completed').replace(
    'wine_nx_perf32_block_end','wine_nx_perf22_block_end')==(prior/native).read_text()
for name in ('wine-nx-box64-core-dynarec_arm64_00.c','wine-nx-box64-core-dynarec.c'):
    assert (build/name).read_bytes()==(prior/name).read_bytes(),name
for f in (w/'generated').glob('*.c'):
    assert f.read_bytes()==(p/'local/perf25/generated'/f.name).read_bytes(),f
source=root/'runtime-perf11-source'
for rel,digest in json.loads((w/'source-baseline.json').read_text()).items():
    assert sha(source/rel)==digest,rel
vendor=source/'wine-nx-probe/vendor/box64'
assert subprocess.check_output(['git','-C',str(vendor),'status','--porcelain'],text=True)==''
assert subprocess.check_output(['git','-C',str(vendor),'rev-parse','HEAD'],text=True).strip()=='2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a'
sdk=Path('/opt/devkitpro/devkitA64/bin')
symbols=subprocess.check_output([str(sdk/'aarch64-none-elf-nm'),str(build/'wine-nx-runtime.elf')],text=True)
for symbol in ('wine_nx_perf32_block_end','wine_nx_perf32_completed','wine_nx_perf32_report',
               'wine_nx_perf25_copy','wine_nx_perf24_present'):
    assert any(s.endswith(' '+symbol) and ' U ' not in s for s in symbols.splitlines()),symbol
for unwanted in ('wine_nx_perf26_report','wine_nx_perf27_span','wine_nx_perf29_report',
                 'wine_nx_perf30_enter','wine_nx_perf31_enter'):
    assert not any(s.endswith(' '+unwanted) for s in symbols.splitlines()),unwanted
objects=list(build.rglob('*dynarec_native.c.obj'));assert len(objects)==1,objects
dis=subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-dr',str(objects[0])],text=True)
for symbol in ('wine_nx_perf32_block_end','wine_nx_perf32_completed'):
    assert 'R_AARCH64_CALL26\t'+symbol in dis,symbol
objects=list(build.rglob('wow64_box64_dynarec.c.obj'));assert len(objects)==1,objects
assert b'perf32-blocks.txt' in objects[0].read_bytes()
copy_dis=subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-dr',
    '--disassemble=wine_nx_perf25_copy',str(objects[0])],text=True)
(w/'copy-object-disassembly.txt').write_text(copy_dis)
assert 'pes32_env' in copy_dis and 'pes21_env' in copy_dis
# Compare final instruction bodies against the exact cached PERF25 ELF.
# Ignore instruction addresses/relocation targets, but use the identical raw
# object sections for the driver-facing components to detect behavioral edits.
objects_equal=[]
for pattern in ('audio_unix.c.obj','horizon.c.obj','vulkan.c.obj','thread_profile.c.obj'):
    new=list(build.rglob(pattern));old=list(prior.rglob(pattern))
    assert len(new)==len(old) and new,pattern
    old_by_rel={str(f.relative_to(prior)):f for f in old}
    for f in new:
        old_f=old_by_rel[str(f.relative_to(build))]
        # Version-independent objects must really be identical, not merely
        # source hashes that may fail to describe the linked component.
        assert f.read_bytes()==old_f.read_bytes(),str(f)
        objects_equal.append(str(f.relative_to(build)))
commands=subprocess.check_output(['ninja','-C',str(build),'-t','commands'],text=True)
link=[line for line in commands.splitlines() if ' -o wine-nx-runtime.elf ' in line];assert len(link)==1
stock=root/'mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib'
assert str(stock/'libvulkan.a') in link[0] and str(stock/'libEGL.a') in link[0]
assert 'perf31-mesa-sdk' not in link[0]
deps=subprocess.check_output(['ninja','-C',str(build),'-t','deps'],text=True)
for file in ('src/runtime/pes13_perf32.h','src/runtime/pes13_perf32_policy.h','local/perf32/pes13_perf25_env.h'):
    assert str(p/file) in deps,file
nro=(w/'payload/switch/pes13-nx/pes13-nx.nro').read_bytes()
assert b'pes13-nx-0.2.0-perf32-game-blocks' in nro
assert hashlib.sha256(nro).hexdigest()==json.loads((w/'build.json').read_text())['nro_sha256']
report.update(dict(same_math_and_copy_emitters_as_perf25=True,compiled_scoped_block_policy_and_copy_hooks=True,
    retained_components_identical_objects=objects_equal,stock_mesa_link_verified=True,
    vendor_clean_at_pinned_revision=True,source_restored=True,elf_sha256=sha(build/'wine-nx-runtime.elf'),
    hardware_tested=False,main_cpu_sampling=False,target_match_fps=30,target_verified=False,
    startup_fix_claimed=False,changed_sources_sha256={str(f.relative_to(p)):sha(f) for f in [
        p/'tools/build-perf32.py',p/'tools/run-perf32-build.py',p/'tools/verify-perf32.py',
        p/'tools/perf32_patches.py',p/'tools/prepare-perf32.py',p/'src/runtime/pes13_perf32.h',
        p/'src/runtime/pes13_perf32_policy.h',p/'tests/perf32_policy.c',p/'tests/perf32_policy.py']}))
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF32 actual linked policy, unchanged math/driver/wait/audio components and restored source PASS',flush=True)
