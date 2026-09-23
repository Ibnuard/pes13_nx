"""WSL: PERF22 math, secondary-core repair, and four retained previous logs."""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile
import perf22_patches
from perf17_patches import once

p=Path(__file__).resolve().parents[1]
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
work=p/'local/perf23'; work.mkdir(parents=True,exist_ok=True)
source=root/'runtime-perf11-source/wine-nx-probe'
with tempfile.TemporaryDirectory(prefix='perf23-tests-',dir=root) as tmp:
    tmp=Path(tmp)
    for test in ('balance','logs'):
        binary=tmp/test
        subprocess.run(['cc','-O2','-std=gnu11','-Wall','-Wextra','-Werror',
            '-fsanitize=address,undefined','-I'+str(source/'source'),
            str(p/f'tests/perf23_{test}.c'),'-o',str(binary)],check=True)
        args=[str(binary)]
        if test=='logs':
            logdir=tmp/'history'; logdir.mkdir(); args.append(str(logdir))
        subprocess.run(args,check=True)
    # Keep upstream's existing scheduler/profiler contract tests as well.
    binary=tmp/'upstream-profile'
    subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        str(source/'tests/thread_profile.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)

# Generate the same emitters into the new experiment directory, preserving
# the archived PERF22 files and hashes. Keep all math policy code identical.
patchfile=p/'tools/perf22_patches.py'
patchns={'__file__':str(patchfile),'__name__':'perf23_emitter_recipe'}
exec(compile(patchfile.read_text().replace('local/perf22','local/perf23'),str(patchfile),'exec'),patchns)
perf22_patches.generate=patchns['generate']
perf22_patches.adapt_cmake=patchns['adapt_cmake']

driver=p/'tools/build-perf22.py'; text=driver.read_text()
text=once(text,'import perf17_patches','import perf17_patches\nimport perf23_patches')
text=text.replace("work=p/'local/perf22'","work=p/'local/perf23'")
text=text.replace("root/'perf22-baseline-check'","root/'perf23-baseline-check'")
text=text.replace('runtime-perf22-floatmath','runtime-perf23-transitions')
text=text.replace('pes13-nx-0.2.0-perf22-floatmath','pes13-nx-0.2.0-perf23-transitions')
text=text.replace('PES13-NX PERF22','PES13-NX PERF23')
text=text.replace("('local/perf21','local/perf22')","('local/perf21','local/perf23')")
text=text.replace("local/perf22/worker-c-fused.bin","local/perf23/worker-c-fused.bin")
text=once(text,'    return cmake,dynarec,runtime',
          '    return perf23_patches.adapt(cmake,dynarec,runtime,project)')
text=once(text,"profile.write_text(once(original.decode(),'#define NX_PROF_PERIOD_NS    2000000',\n                           '#define NX_PROF_PERIOD_NS    10000000'))",
          "profile.write_text(perf23_patches.adapt_profile(once(original.decode(),'#define NX_PROF_PERIOD_NS    2000000',\n                           '#define NX_PROF_PERIOD_NS    10000000'),p))")
exec(compile(text,str(driver),'exec'),{'__file__':str(driver),'__name__':'__main__'})

old=list((root/'runtime-perf22-floatmath').glob('*-dynarec_native.c'))
new=list((root/'runtime-perf23-transitions').glob('*-dynarec_native.c'))
assert len(old)==len(new)==1 and old[0].read_bytes()==new[0].read_bytes()
for path in (work/'generated').glob('*.c'):
    assert path.read_bytes()==(p/'local/perf22/generated'/path.name).read_bytes()
report={'math_emitters_identical_to_perf22':True,'native_dynarec_identical_to_perf22':True,
        'new_policy':'one secondary-core migration at most every four seconds',
        'history':4,'new_host_tests':['balance 20000 randomized layouts','log rotation and failure preservation','upstream thread_profile'],
        'hardware_tested':False}
(work/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF23 build verified; native math sources byte-identical to PERF22',flush=True)
