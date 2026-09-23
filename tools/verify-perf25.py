"""Check actual generated sources, compiled hooks, restored vendor and ABI."""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile
p=Path(__file__).resolve().parents[1]
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
w=p/'local/perf25';build=root/'runtime-perf25-paircopy'
source=root/'runtime-perf11-source/wine-nx-probe'
with tempfile.TemporaryDirectory(prefix='perf25-policy-',dir=root) as tmp:
    exe=Path(tmp)/'policy'
    subprocess.run(['cc','-O2','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-I'+str(source/'vendor/box64/src/include'),'-I'+str(source/'vendor/box64/src'),
        str(p/'tests/perf25_policy.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe),str(p/'local/game/pes2013.exe')],check=True)
# Inherit the established frame-hook and restored-source checks on this build.
previous=p/'tools/verify-perf24.py'
text=previous.read_text().replace('local/perf24','local/perf25').replace('runtime-perf24-diagnostics','runtime-perf25-paircopy')
exec(compile(text,str(previous),'exec'),{'__file__':str(previous),'__name__':'__main__'})
old=list((root/'runtime-perf24-diagnostics').glob('*-dynarec_arm64_00.c'))
new=list(build.glob('*-dynarec_arm64_00.c'));assert len(old)==len(new)==1
text=new[0].read_text()
prefix='#include <stdint.h>\n#include "'+str(p/'src/runtime/pes13_perf25_copy_emit.h')+'"\nextern int wine_nx_perf25_copy(uintptr_t, const void*);\n'
assert text.startswith(prefix);reversed=text[len(prefix):]
fragment='''                if (rex.is32bits && !rex.is67 && !rex.w &&
                    wine_nx_perf25_copy(dyn->insts[ninst].x64.addr, dyn->env)) {
                    PES25_COPY_FORWARD();
                }
'''
assert reversed.count(fragment)==1
assert reversed.replace(fragment,'')==old[0].read_text()
commands=subprocess.check_output(['ninja','-C',str(build),'-t','commands'],text=True)
assert sum(' -c '+str(new[0]) in c for c in commands.splitlines())==4
for path in (w/'generated').glob('*.c'):
    assert path.read_bytes()==(p/'local/perf24/generated'/path.name).read_bytes()
native=list(build.glob('*-dynarec_native.c'));oldnative=list((root/'runtime-perf24-diagnostics').glob('*-dynarec_native.c'))
assert len(native)==len(oldnative)==1
assert native[0].read_text().replace('wine_nx_perf25_completed','wine_nx_perf22_completed')==oldnative[0].read_text()
capture=(w/'pes13_perf20_capture.h').read_text()
assert 'if (i == 5) continue; /* PERF25 startup fault capture */' in capture
sdk=Path('/opt/devkitpro/devkitA64/bin')
symbols=subprocess.check_output([str(sdk/'aarch64-none-elf-nm'),str(build/'wine-nx-runtime.elf')],text=True)
for symbol in ('wine_nx_perf25_copy','wine_nx_perf25_completed','wine_nx_perf25_report'):
    assert any(line.endswith(' '+symbol) and ' U ' not in line for line in symbols.splitlines())
objs=list(build.rglob('*dynarec_arm64_00.c.obj'));assert len(objs)==4
for obj in objs:
    dis=subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-dr',str(obj)],text=True)
    assert 'R_AARCH64_CALL26\twine_nx_perf25_copy' in dis
report=json.loads((w/'verification.json').read_text())
report.update({'four_pass_compiled_copy_hook':True,'opcode00_only_scoped_paircopy_changed':True,
    'startup_slot_reserved':True,'stable_pass_and_capture_tests':'PASS ASan/UBSan',
    'native_only_completion_hook_changed_vs_perf24':True,'hardware_tested':False})
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF25 real object hooks and scoped changes verified; hardware results pending',flush=True)
