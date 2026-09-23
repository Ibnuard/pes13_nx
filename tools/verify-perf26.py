"""Verify compiled artifacts and isolate the single environment change."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
from perf26_patches import policy_text
p=Path(__file__).resolve().parents[1];w=p/'local/perf26'
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
build=root/'runtime-perf26-callret';prior=root/'runtime-perf25-paircopy'
env=dict(os.environ,PYTHONPATH=str(p/'local/perf20/linux-libs'))
subprocess.run([sys.executable,str(p/'tests/perf26_callret.py')],env=env,check=True)
path=p/'tools/verify-perf25.py'
text=path.read_text().replace('local/perf25','local/perf26').replace('runtime-perf25-paircopy','runtime-perf26-callret')
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
for name in ('wine-nx-box64-core-dynarec_native.c','wine-nx-box64-core-dynarec_arm64_00.c','wine-nx-box64-core-dynarec.c'):
    assert (build/name).read_bytes()==(prior/name).read_bytes(),name
header=w/'pes13_perf21_callret.h';assert header.read_text()==policy_text(p)
assert header.read_text().replace('\n        pes26_configure(&pes21_env);','')==(p/'src/runtime/pes13_perf21.h').read_text()
ops=(build/'wine-nx-box64-core-dynarec_arm64_00.c').read_text()
assert ops.count('SUBx_REG(x3, xSavedSP, x3);')==3
assert ops.count('LSRx(x3, x3, 16);')==3
sdk=Path('/opt/devkitpro/devkitA64/bin');elf=build/'wine-nx-runtime.elf'
symbols=subprocess.check_output([str(sdk/'aarch64-none-elf-nm'),str(elf)],text=True)
for symbol in ('wine_nx_perf26_report','wine_nx_box64_callret_trap','wine_nx_box64_callret_clean','wine_nx_box64_callret_dirty'):
    assert any(line.endswith(' '+symbol) and ' U ' not in line for line in symbols.splitlines()),symbol
objects=list(build.rglob('wow64_box64_dynarec.c.obj'));assert len(objects)==1
dis=subprocess.check_output([str(sdk/'aarch64-none-elf-objdump'),'-dr',str(objects[0])],text=True)
assert 'pes26_mode' in dis
# Verify compiler dependency tracking includes the generated selection and mode.
deps=subprocess.check_output(['ninja','-C',str(build),'-t','deps'],text=True)
assert str(header) in deps and str(p/'src/runtime/pes13_perf26.h') in deps
report=json.loads((w/'verification.json').read_text())
report.update({'callret_tests':json.loads((w/'callret-tests.json').read_text()),
    'same_generated_native_and_opcode_sources_as_perf25':True,'three_64k_native_stack_guards_retained':True,
    'compiled_scoped_env_and_trap_verified':True,'header_only_adds_callret_configure':True,
    'changed_sources_sha256':{str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
        [p/'src/runtime/pes13_perf26.h',header,p/'tools/perf26_patches.py',p/'tests/perf26_callret.py',p/'tests/perf26_policy.c']}})
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF26 scoped policy, compiled trap/stack guards and unchanged math/opcode code verified',flush=True)
