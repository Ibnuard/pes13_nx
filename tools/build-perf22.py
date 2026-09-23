"""WSL: retain PERF21 and try X87DOUBLE=0 in the same post-present scope."""
from pathlib import Path
import json, os, subprocess
import perf17_patches
from perf17_patches import once

p=Path(__file__).resolve().parents[1]
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
work=p/'local/perf22'; work.mkdir(parents=True,exist_ok=True)

# Reuse the preceding recipe and mandatory baseline checks without running
# its build or writing into the archived PERF21 experiment directory.
previous=p/'tools/build-perf21.py'
text=previous.read_text(); marker='\nperf17_patches.adapt_recipe,perf17_patches.adapt=recipe,adapt'
assert text.count(marker)==1
prefix=text.split(marker,1)[0]
prefix=once(prefix,'import perf21_patches','import perf22_patches as perf21_patches')
prefix=prefix.replace("work=p/'local/perf21'","work=p/'local/perf22'")
prefix=prefix.replace("root/'perf21-baseline-check'","root/'perf22-baseline-check'")
ns={'__file__':str(previous),'__name__':'perf21_recipe'}
exec(compile(prefix,str(previous),'exec'),ns)

def recipe(text):
    text=ns['recipe'](text)
    for old,new in [('runtime-perf21-fastmath','runtime-perf22-floatmath'),
                    ('pes13-nx-0.2.0-perf21-fastmath','pes13-nx-0.2.0-perf22-floatmath'),
                    ('PES13-NX PERF21','PES13-NX PERF22'),('local/perf21','local/perf22')]:
        text=text.replace(old,new)
    return text

def adapt(cmake,dynarec,runtime,project):
    cmake,dynarec,runtime=ns['adapt'](cmake,dynarec,runtime,project)
    anchor='#include "'+str(project/'src/runtime/pes13_perf21.h')+'"'
    dynarec=once(dynarec,anchor,anchor+'\n#include "'+str(project/'src/runtime/pes13_perf22.h')+'"')
    dynarec=once(dynarec,'    apply_box64_options();','''    apply_box64_options();
    {
        FILE *f = fopen("sdmc:/switch/pes13-nx/perf22-floatmath.txt", "r");
        if (f) { __atomic_store_n(&pes22_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }
    }''')
    dynarec=once(dynarec,'return pes21_select(addr);','return pes22_select(addr);')
    runtime=once(runtime,'    wine_nx_thread_report();',
        '    { extern void wine_nx_perf22_report(void); wine_nx_perf22_report(); }\n    wine_nx_thread_report();')
    cmake=once(cmake,'extern void wine_nx_perf21_completed(void*, const void*); wine_nx_perf21_completed(block, helper.env);',
               'extern void wine_nx_perf22_completed(void*, const void*); wine_nx_perf22_completed(block, helper.env);')
    cmake=once(cmake,'extern uintptr_t wine_nx_perf21_block_end(uintptr_t, uintptr_t, const void*); helper.end = wine_nx_perf21_block_end(addr, helper.end, helper.env);',
               'extern uintptr_t wine_nx_perf22_block_end(uintptr_t, uintptr_t, const void*); helper.end = wine_nx_perf22_block_end(addr, helper.end, helper.env);')
    return cmake,dynarec,runtime

perf17_patches.adapt_recipe,perf17_patches.adapt=recipe,adapt
profile=root/'runtime-perf11-source/wine-nx-probe/source/thread_profile.c'
original=profile.read_bytes()
try:
    profile.write_text(once(original.decode(),'#define NX_PROF_PERIOD_NS    2000000',
                           '#define NX_PROF_PERIOD_NS    10000000'))
    path=p/'tools/build-perf17.py'
    driver=path.read_text().replace('tests/perf17_policy.c','tests/perf22_policy.c')
    driver=once(driver,"subprocess.run([exe, str(p / 'local/game/pes2013.exe')], env=env, check=True)",
                "subprocess.run([exe, str(p / 'local/game/pes2013.exe'), str(p / 'local/perf18/captures'), str(p / 'local/perf20/captures'), str(p / 'local/perf22/worker-c-fused.bin')], env=env, check=True)")
    exec(compile(driver,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
finally:
    profile.write_bytes(original)
    assert profile.read_bytes()==original
    print('PERF22 profiler source restored byte-for-byte',flush=True)

build=root/'runtime-perf22-floatmath'
commands=subprocess.check_output(['ninja','-C',str(build),'-t','commands'],text=True)
verified=[]
for entry in ns['emitter_changes']:
    file=str(work/'generated'/entry['name'])
    matches=[line for line in commands.splitlines() if ' -c '+file in line]
    assert len(matches)==4,(entry['name'],len(matches))
    assert all('-O1' in line for line in matches)
    assert not any(' -c ' in line and line.endswith('/vendor/box64/src/dynarec/arm64/'+entry['name']) for line in commands.splitlines())
    verified.append(entry['name'])
native=list(build.glob('*-dynarec_native.c')); assert len(native)==1
generated=native[0].read_text()
assert generated.count('BOX64DRENV(dynarec_x87double)')==2
assert 'BOX64ENV(dynarec_x87double)' not in generated
assert 'wine_nx_perf22_completed(block, helper.env)' in generated
assert 'wine_nx_perf22_block_end(addr, helper.end, helper.env)' in generated
(work/'build-emitter-verification.json').write_text(json.dumps({'files':verified,'passes_per_file':4,
    'references_changed':sum(e['sites'] for e in ns['emitter_changes']),
    'native_x87double_references':2,'only_macro_changes_in_emitters':True},indent=2)+'\n')
print('PERF22 FASTROUND and X87DOUBLE scoped emitter reads verified in all four passes',flush=True)
