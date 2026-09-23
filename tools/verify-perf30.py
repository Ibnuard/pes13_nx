"""Verify actual linked diagnostics and that unrelated native code is preserved."""
from pathlib import Path
import hashlib,json,os,subprocess
from perf30_archive import members as archive_members
p=Path(__file__).resolve().parents[1];w=p/'local/perf30'
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
build=root/'runtime-perf30-submit-stages';sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
import sys
for test in ('perf30_archive.py','perf30_analysis.py'):
    subprocess.run([sys.executable,str(p/'tests'/test)],check=True)
# Reuse the CPU/copy/ABI verifier against this build without editing it.
path=p/'tools/verify-perf29.py';text=path.read_text().replace('local/perf29','local/perf30')
text=text.replace('runtime-perf29-worker-blocks','runtime-perf30-submit-stages')
text=text.replace('pes13-nx-0.2.0-perf29-worker-blocks','pes13-nx-0.2.0-perf30-submit-stages')
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
report=json.loads((w/'verification.json').read_text());mesa=json.loads((w/'mesa-build.json').read_text())
tests=json.loads((w/'metrics-tests.json').read_text())
for name,digest in tests['source_sha256'].items():assert sha(p/name)==digest,name
stock=root/'mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib/libvulkan.a'
assert sha(stock)==mesa['stock_archive_sha256']
private=Path(mesa['private_archive']);assert sha(private)==mesa['private_archive_sha256']
commands=subprocess.check_output(['ninja','-C',str(build),'-t','commands'],text=True)
link=[line for line in commands.splitlines() if ' -o wine-nx-runtime.elf ' in line];assert len(link)==1
assert str(private) in link[0] and str(stock) not in link[0]
sdk=Path('/opt/devkitpro/devkitA64/bin')
symbols=subprocess.check_output([str(sdk/'aarch64-none-elf-nm'),str(build/'wine-nx-runtime.elf')],text=True)
for name in ('wine_nx_perf30_enter','wine_nx_perf30_leave','wine_nx_perf30_value','wine_nx_perf30_init'):
    assert any(s.endswith(' '+name) and ' U ' not in s for s in symbols.splitlines()),name
for r in mesa['records']:
    assert sha(root/'mesa-switch'/r['source'])==r['source_sha256'],r['source']
    assert sha(Path(r['generated']))==r['generated_sha256']
    dis=subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-dr',r['object']],text=True)
    assert 'R_AARCH64_CALL26\twine_nx_perf30_enter' in dis and 'R_AARCH64_CALL26\twine_nx_perf30_leave' in dis,r['source']
    (w/(Path(r['source']).stem+'-disassembly.txt')).write_text(dis)
audio=list(build.rglob('audio_unix.c.obj'));assert len(audio)==1
dis=subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-dr',str(audio[0])],text=True)
assert 'wine_nx_perf30_enter' in dis and 'wine_nx_perf30_value' in dis
assert json.loads((w/'build.json').read_text())['source_restored']
# Inspect every member, preserving order and unrelated duplicate-name objects.
old=archive_members(stock.read_bytes());new=archive_members(private.read_bytes());assert len(old)==len(new)
changed=[]
expected={(r['member'],r['original_object_sha256']):sha(Path(r['object'])) for r in mesa['records']}
for a,b in zip(old,new):
    assert a[0]==b[0]
    if a in expected:assert b[1]==expected[a];changed.append(a[0])
    else:assert a==b
assert sorted(changed)==sorted(r['member'] for r in mesa['records'] for _ in range(r['matching_members'])),changed
report.update({'diagnostic_only':True,'main_cpu_sampling':False,'scoped_worker_bigblock':0,
    'metrics_tests':tests,'mesa_original_untouched':True,'only_four_source_objects_changed':changed,
    'private_mesa_link_verified':True,'compiled_audio_and_mesa_diagnostics':True,'hardware_tested':False})
for f in [p/'src/runtime'/name for name in ('pes13_perf30.h','pes13_perf30_core.h','pes13_perf30_runtime.h')]+[
    p/'tools'/name for name in ('perf30_mesa.py','perf30_archive.py','perf30_patches.py','build-perf30-mesa.py','build-perf30.py','run-perf30-build.py','verify-perf30.py')]:
    report['changed_sources_sha256'][str(f.relative_to(p))]=sha(f)
for f in (p/'tests/perf30_archive.py',p/'tests/perf30_analysis.py',p/'tools/analyze-perf30.py'):
    report['changed_sources_sha256'][str(f.relative_to(p))]=sha(f)
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF30 private Mesa members, compiled native/audio spans, retained CPU policy and source restoration PASS',flush=True)
