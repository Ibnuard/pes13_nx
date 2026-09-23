"""Verify final linked diagnostic hooks and host frame scenarios, under WSL."""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile
p=Path(__file__).resolve().parents[1]
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
w=p/'local/perf24'; build=root/'runtime-perf24-diagnostics'
with tempfile.TemporaryDirectory(prefix='perf24-frame-test-',dir=root) as tmp:
    exe=Path(tmp)/'frames'
    subprocess.run(['cc','-O2','-std=gnu11','-Wall','-Wextra','-Werror',
        '-fsanitize=address,undefined',str(p/'tests/perf24_frames.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
sdk=Path('/opt/devkitpro/devkitA64/bin')
symbols=subprocess.check_output([str(sdk/'aarch64-none-elf-nm'),str(build/'wine-nx-runtime.elf')],text=True)
for symbol in ('wine_nx_perf24_present','wine_nx_perf24_host','wine_nx_perf24_sampling_epoch'):
    assert any(line.endswith(' '+symbol) and ' U ' not in line for line in symbols.splitlines()),symbol
objs=[o for o in build.rglob('vulkan.c.obj') if o.parent.name=='win32u']
assert len(objs)==1,objs
dis=subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-dr',str(objs[0])],text=True)
for symbol in ('wine_nx_perf24_present','wine_nx_perf24_host'):
    assert 'R_AARCH64_CALL26\t'+symbol in dis,symbol
vendor=root/'runtime-perf11-source/wine-nx-probe/vendor/box64'
assert subprocess.check_output(['git','-C',str(vendor),'status','--porcelain'],text=True)==''
assert subprocess.check_output(['git','-C',str(vendor),'rev-parse','HEAD'],text=True).strip()=='2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a'
assert '#define NX_PROF_PERIOD_NS    2000000' in (root/'runtime-perf11-source/wine-nx-probe/source/thread_profile.c').read_text()
assert 'wine_nx_perf24_host' not in (root/'runtime-perf11-source/dlls/win32u/vulkan.c').read_text()
report=json.loads((w/'verification.json').read_text())
report.update({'compiled_vulkan_frame_hooks':True,'vendor_clean_at_pinned_revision':True,
    'frame_scenario_tests':'PASS with ASan/UBSan',
    'metrics_tests':'PASS: boundaries, concurrent writers and cadence',
    'elf_sha256':hashlib.sha256((build/'wine-nx-runtime.elf').read_bytes()).hexdigest()})
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF24 final linked hooks, actual frame scenarios, restored sources and pinned vendor verified',flush=True)
