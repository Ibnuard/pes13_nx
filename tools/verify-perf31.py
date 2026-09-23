"""Check final ELF calls, all archive copies, retained CPU code and restored sources."""
from pathlib import Path
import hashlib,json,os,subprocess
from perf30_archive import members
p=Path(__file__).resolve().parents[1];w=p/'local/perf31'
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'));build=root/'runtime-perf31-fence-poll'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
path=p/'tools/verify-perf29.py';text=path.read_text().replace('local/perf29','local/perf31')
text=text.replace('runtime-perf29-worker-blocks','runtime-perf31-fence-poll').replace('pes13-nx-0.2.0-perf29-worker-blocks','pes13-nx-0.2.0-perf31-fence-poll')
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
report=json.loads((w/'verification.json').read_text());mesa=json.loads((w/'mesa-build.json').read_text())
for label in ('metrics','poll'):
    tests=json.loads((w/(label+'-tests.json')).read_text())
    for name,digest in tests['source_sha256'].items():assert sha(p/name)==digest,name
    report[label+'_tests']=tests
stock=root/'mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib';private=root/'perf31-mesa-sdk/lib'
expected={(r['member'],r['original_object_sha256']):r['object_sha256'] for r in mesa['records']}
for r in mesa['records']:
    assert sha(root/'mesa-switch'/r['source'])==r['source_sha256']
    assert sha(Path(r['generated']))==r['generated_sha256'] and sha(Path(r['object']))==r['object_sha256']
for a in mesa['archives']:
    old=stock/a['name'];new=private/a['name']
    assert sha(old)==a['stock_sha256'] and sha(new)==a['private_sha256']
    before=members(old.read_bytes());after=members(new.read_bytes());assert len(before)==len(after)
    changed=[]
    for x,y in zip(before,after):
        assert x[0]==y[0]
        if x in expected:assert y[1]==expected[x];changed.append(x[0])
        else:assert x==y
    assert changed==a['changed']
commands=subprocess.check_output(['ninja','-C',str(build),'-t','commands'],text=True)
link=[line for line in commands.splitlines() if ' -o wine-nx-runtime.elf ' in line];assert len(link)==1
for name in ('libEGL.a','libvulkan.a'):
    assert str(private/name) in link[0] and str(stock/name) not in link[0]
sdk=Path('/opt/devkitpro/devkitA64/bin');elf=build/'wine-nx-runtime.elf'
symbols=subprocess.check_output([str(sdk/'aarch64-none-elf-nm'),str(elf)],text=True)
for name in ('wine_nx_perf31_enter','wine_nx_perf31_leave','wine_nx_perf31_poll_mode','wine_nx_perf31_poll_count'):
    assert any(s.endswith(' '+name) and ' U ' not in s for s in symbols.splitlines()),name
# PERF30 failed to validate the selected shared Horizon object. Validate actual
# ELF functions, not just an instrumented object that the linker can discard.
resolved={}
for name in ('nouveau_horizon_channel_submit','vk_common_QueueSubmit2'):
    dis=subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-d','--disassemble='+name,str(elf)],text=True)
    assert '<wine_nx_perf31_enter>' in dis and '<wine_nx_perf31_leave>' in dis,name
    (w/(name+'-linked.txt')).write_text(dis);resolved[name]=True
names=[s.split()[-1] for s in symbols.splitlines() if ' nouveau_horizon_fence_wait' in s and ' U ' not in s]
fence_dis=''.join(subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-d','--disassemble='+n,str(elf)],text=True) for n in names)
assert '<wine_nx_perf31_poll_mode>' in fence_dis and '<wine_nx_perf31_poll_count>' in fence_dis
assert '<wine_nx_perf31_enter>' in fence_dis and '<wine_nx_perf31_leave>' in fence_dis
(w/'fence-linked.txt').write_text(fence_dis)
for r in mesa['records']:
    dis=subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-dr',r['object']],text=True)
    assert 'wine_nx_perf31_enter' in dis and 'wine_nx_perf31_leave' in dis,r['source']
report.update(dict(native_submit_api_link_verified=True,horizon_selected_object_verified=True,
    all_archive_copies_verified=True,retained_cpu_policy=True,main_cpu_sampling=False,
    scoped_worker_bigblock=0,zero_timeout_error_scan_experiment=True,hardware_tested=False,
    diagnostic_only=False,startup_fix_claimed=False,source_restored=True,native_functions=resolved))
files=list((p/'src/runtime').glob('pes13_perf31*.h'))+list((p/'tests').glob('perf31*'))+[
    p/'tools'/n for n in ('perf31_patches.py','perf31_mesa.py','prepare-perf31.py','build-perf31-mesa.py','build-perf31.py','run-perf31-build.py','verify-perf31.py')]
for f in files:
    if f.is_file():report['changed_sources_sha256'][str(f.relative_to(p))]=sha(f)
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF31 final ELF full-submit/Horizon hooks, all archive copies, CPU policy and restoration PASS',flush=True)
