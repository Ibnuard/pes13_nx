"""Build the scoped FASTROUND experiment on top of the tested PERF20 recipe."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import perf17_patches
import perf21_patches
from perf17_patches import once

p=Path(__file__).resolve().parents[1]
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
work=p/'local/perf21'; work.mkdir(parents=True,exist_ok=True)
emitter_changes=perf21_patches.generate(root,p)

# The existing code-patching checks run unchanged alongside the new policy.
baseline_test=root/'perf21-baseline-check'
vendor=root/'runtime-perf11-source/wine-nx-probe/vendor/box64/src'
subprocess.run(['cc','-O2','-std=gnu11','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I'+str(vendor/'include'),'-I'+str(vendor),
                str(p/'tests/perf20_patch.c'),'-o',str(baseline_test)],check=True)
subprocess.run([str(baseline_test),str(p/'local/game/pes2013.exe'),str(p/'local/perf18/captures'),
                str(p/'local/perf20/captures'),str(work/'worker-c-fused.bin')],check=True)

# Reuse PERF20's validated transform functions without executing its build.
# Its baseline replay checks are evaluated and remain mandatory.
base_path=p/'tools/build-perf20.py'
base_text=base_path.read_text()
assert base_text.count('\nfuse_test=root/')==1
base_ns={'__file__':str(base_path),'__name__':'perf20_recipe'}
exec(compile(base_text.split('\nfuse_test=root/',1)[0],str(base_path),'exec'),base_ns)

def recipe(text):
    text=base_ns['recipe'](text)
    for old,new in [('runtime-perf20-roundfusion','runtime-perf21-fastmath'),
                    ('pes13-nx-0.2.0-perf20-roundfusion','pes13-nx-0.2.0-perf21-fastmath'),
                    ('PES13-NX PERF20','PES13-NX PERF21'),('local/perf20','local/perf21')]:
        text=text.replace(old,new)
    return text

def adapt(cmake,dynarec,runtime,project):
    cmake,dynarec,runtime=base_ns['adapt'](cmake,dynarec,runtime,project)
    anchor='#include "'+str(project/'src/runtime/pes13_perf20.h')+'"'
    dynarec=once(dynarec,anchor,anchor+'\n#include "'+str(project/'src/runtime/pes13_perf21.h')+'"')
    dynarec=once(dynarec,'    apply_box64_options();','''    apply_box64_options();
    {
        FILE *f = fopen("sdmc:/switch/pes13-nx/perf21-fastmath.txt", "r");
        if (f) { __atomic_store_n(&pes21_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }
    }''')
    dynarec=once(dynarec,'return pes17_select(addr, pes13_perf8_select_env(addr));',
                 'return pes21_select(addr);')
    runtime=once(runtime,'    wine_nx_thread_report();',
        '    { extern void wine_nx_perf21_report(void); wine_nx_perf21_report(); }\n    wine_nx_thread_report();')
    cmake=perf21_patches.adapt_cmake(cmake,project)
    cmake=once(cmake,'extern void wine_nx_perf20_capture(void*); wine_nx_perf20_capture(block);',
               'extern void wine_nx_perf21_completed(void*, const void*); wine_nx_perf21_completed(block, helper.env);')
    cmake=once(cmake,'extern uintptr_t wine_nx_perf17_block_end(uintptr_t, uintptr_t, const void*); helper.end = wine_nx_perf17_block_end(addr, helper.end, helper.env);',
               'extern uintptr_t wine_nx_perf21_block_end(uintptr_t, uintptr_t, const void*); helper.end = wine_nx_perf21_block_end(addr, helper.end, helper.env);')
    return cmake,dynarec,runtime

perf17_patches.adapt_recipe,perf17_patches.adapt=recipe,adapt
profile=root/'runtime-perf11-source/wine-nx-probe/source/thread_profile.c'
original=profile.read_bytes()
try:
    profile.write_text(once(original.decode(),'#define NX_PROF_PERIOD_NS    2000000',
                           '#define NX_PROF_PERIOD_NS    10000000'))
    path=p/'tools/build-perf17.py'
    driver=path.read_text().replace('tests/perf17_policy.c','tests/perf21_policy.c')
    driver=once(driver,"subprocess.run([exe, str(p / 'local/game/pes2013.exe')], env=env, check=True)",
                "subprocess.run([exe, str(p / 'local/game/pes2013.exe'), str(p / 'local/perf18/captures'), str(p / 'local/perf20/captures'), str(p / 'local/perf21/worker-c-fused.bin')], env=env, check=True)")
    exec(compile(driver,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
finally:
    profile.write_bytes(original)
    assert profile.read_bytes()==original
    print('PERF21 profiler source restored byte-for-byte',flush=True)

# Verify Ninja actually used all generated emitters in all four passes.
commands=subprocess.check_output(['ninja','-C',str(root/'runtime-perf21-fastmath'),'-t','commands'],text=True)
verified=[]
for entry in emitter_changes:
    file=str(work/'generated'/entry['name'])
    matches=[line for line in commands.splitlines() if ' -c '+file in line]
    assert len(matches)==4,(entry['name'],len(matches))
    assert all('-O1' in line for line in matches)
    assert not any(' -c ' in line and line.endswith('/vendor/box64/src/dynarec/arm64/'+entry['name']) for line in commands.splitlines())
    verified.append(entry['name'])
(work/'build-emitter-verification.json').write_text(json.dumps({'files':verified,'passes_per_file':4,
    'references_changed':sum(e['sites'] for e in emitter_changes),'only_macro_changes':True},indent=2)+'\n')
print('PERF21 generated FASTROUND emitters verified in all four passes',flush=True)
