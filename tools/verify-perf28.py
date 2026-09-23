"""Check final ARM64 fault hook, unchanged PERF27 CPU code, and restoration."""
from pathlib import Path
import hashlib, json, os, subprocess
p = Path(__file__).resolve().parents[1]
w = p/'local/perf28'
root = Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build'))
path = p/'tools/verify-perf27.py'
text = path.read_text().replace('local/perf27', 'local/perf28').replace('runtime-perf27-wakes', 'runtime-perf28-diagnostics')
for name in ('build', 'verify'):
    text = text.replace(f'tools/{name}-perf27.py', f'tools/{name}-perf28.py')
text = text.replace('tools/perf27_patches.py', 'tools/perf28_patches.py')
exec(compile(text, str(path), 'exec'), {'__file__':str(path), '__name__':'__main__'})
build = root/'runtime-perf28-diagnostics'; prior = root/'runtime-perf27-wakes'
sha = lambda f: hashlib.sha256(f.read_bytes()).hexdigest()
tests = json.loads((w/'fault-tests.json').read_text())
for name, digest in tests['source_sha256'].items(): assert sha(p/name) == digest, name
for name in ('wine-nx-box64-core-dynarec_native.c','wine-nx-box64-core-dynarec_arm64_00.c','wine-nx-box64-core-dynarec.c'):
    assert (build/name).read_bytes() == (prior/name).read_bytes(), name
for file in (w/'generated').glob('*.c'):
    assert file.read_bytes() == (p/'local/perf27/generated'/file.name).read_bytes()
assert (w/'horizon.c').read_bytes() == (p/'local/perf27/horizon.c').read_bytes()
assert (w/'vulkan.c').read_bytes() == (p/'local/perf27/vulkan.c').read_bytes()
sdk = Path('/opt/devkitpro/devkitA64/bin')
symbols = subprocess.check_output([str(sdk/'aarch64-none-elf-nm'),str(build/'wine-nx-runtime.elf')],text=True)
assert any(s.endswith(' wine_nx_perf28_identity') and ' U ' not in s for s in symbols.splitlines())
objects = list(build.rglob('wow64_box64_unix.c.obj')); assert len(objects) == 1, objects
dis = subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-dr',str(objects[0])],text=True)
for hook in ('wine_nx_perf28_identity','NtReadVirtualMemory','wine_nx_box64_run'):
    assert hook in dis, hook
assert b'[FAULT28] begin read-only' in objects[0].read_bytes()
deps = subprocess.check_output(['ninja','-C',str(build),'-t','deps'],text=True)
for name in ('fault', 'unix'): assert str(p/f'src/runtime/pes13_perf28_{name}.h') in deps
restored = (root/'runtime-perf11-source/wine-nx-probe/source/wow64_box64_unix.c').read_text()
assert 'pes28_' not in restored and 'p->fault_address' not in restored
assert json.loads((w/'build.json').read_text())['source_restored']
nro = (w/'payload/switch/pes13-nx/pes13-nx.nro').read_bytes()
assert b'PES13-NX: custom Horizon runtime' in nro
assert b'pes13-nx-0.2.0-perf28-diagnostics' in nro
report = json.loads((w/'verification.json').read_text())
report.update({'fault_tests':tests, 'compiled_fault_hook':True, 'same_cpu_emitters_as_perf27':True,
    'same_horizon_and_vulkan_as_perf27':True, 'unix_source_restored':True, 'diagnostic_only':True,
    'hardware_tested':False, 'main_cpu_sampling':True})
for f in [p/'src/runtime/pes13_perf28_fault.h',p/'src/runtime/pes13_perf28_unix.h',
          p/'tests/perf28_fault.c',p/'tests/perf28_fault.py']:
    report['changed_sources_sha256'][str(f.relative_to(p))] = sha(f)
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF28 linked read-only fault diagnostic, unchanged PERF27 emitters/server, restored source: PASS')
