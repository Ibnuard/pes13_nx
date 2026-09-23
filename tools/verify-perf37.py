"""Verify probe isolation and the deployed artifact against PERF36."""
from pathlib import Path
import hashlib,json,os,re,subprocess
from nro_assets import inspect_nro
p=Path(__file__).resolve().parents[1];w=p/'local/perf37'
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
source=root/'runtime-perf11-source'; build=root/'runtime-perf37-jit-probe';base=root/'runtime-perf36-scoped-fastnan'
sha=lambda data:hashlib.sha256(data).hexdigest()
assert json.loads((w/'build-status.json').read_text())==dict(state='complete',restored=True)
for rel,digest in json.loads((w/'source-baseline.json').read_text()).items():
    assert sha((source/rel).read_bytes())==digest,rel
emitters=[]
for file in sorted((w/'generated').glob('*.c')):
    assert file.read_bytes()==(p/'local/perf36/generated'/file.name).read_bytes(),file.name
    emitters.append(file.name)
assert len(emitters)==14
for file in ('wine-nx-box64-core-dynarec.c','wine-nx-box64-core-dynablock.c','wine-nx-box64-core-dynarec_native.c'):
    assert (build/file).read_bytes()==(base/file).read_bytes(),file
objdump='/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump'
def words(obj):
    dis=subprocess.check_output([objdump,'-d',str(obj)],text=True)
    return re.findall(r'^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s',dis,re.M)
object_hashes={}
for name in emitters:
    old=list((base/'CMakeFiles/wine-nx-box64-core-pass3.dir').rglob(name+'.obj'))
    new=list((build/'CMakeFiles/wine-nx-box64-core-pass3.dir').rglob(name+'.obj'))
    assert len(old)==len(new)==1
    a,b=words(old[0]),words(new[0]);assert a and a==b,('emitter code changed',name)
    object_hashes[name]=sha(''.join(a).encode())
assert (w/'pes13_perf25_env.h').read_bytes()==(p/'local/perf36/pes13_perf25_env.h').read_bytes()
symbols=subprocess.check_output(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-nm',str(build/'wine-nx-runtime.elf')],text=True)
assert any(s.endswith(' wine_nx_box64_sample_detail') for s in symbols.splitlines())
nro=(w/'payload/switch/pes13-nx/pes13-nx.nro').read_bytes()
for marker in (b'pes13-nx-0.2.0-perf37-jit-probe',b'[JIT37-WORDS]',b'[JIT37-BLOCK]',b'[PERF37]'):
    assert marker in nro,marker
assert sha(nro)==json.loads((w/'build.json').read_text())['nro_sha256']
metadata=inspect_nro(nro,(p/'assets/icon.jpg').read_bytes(),expected_title='PES13-NX PERF37 JIT PROBE')
assert 'output bounds PASS' in (w/'probe-test.log').read_text()
report=json.loads((w/'verification.json').read_text())
report.update(source_restored=True,emitter_sources_identical_to_perf36=emitters,
              pass3_machine_code_identical_to_perf36=object_hashes,dispatch_and_native_pass_source_identical=True,
              scoped_policy_unchanged=True,probe_asan_ubsan='PASS',nro_metadata=metadata,
              hardware_tested=False,performance_improvement_claimed=False,target_verified=False,
              changed_source_sha256={str(f.relative_to(p)):sha(f.read_bytes()) for f in [
                  p/'tools/perf37_patches.py',p/'tools/build-perf37.py',p/'tools/run-perf37-build.py',
                  p/'src/runtime/pes13_perf37_probe.h',p/'src/runtime/pes13_perf37_sample.h',
                  p/'tests/perf37_probe.c']} )
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF37: 14 emitter sources and pass3 ARM instructions identical to PERF36; dispatch/scope unchanged; probe linked; NRO assets/source restore PASS')
