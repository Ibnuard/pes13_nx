"""WSL: retain PERF19 and fuse verified straight-line x87 guard runs."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import perf17_patches
from perf17_patches import once

p = Path(__file__).resolve().parents[1]
root = Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
work = p/'local/perf20'
checks = json.loads((work/'fusion-tests.json').read_text())
assert checks['whole_block_bit_identical'] and checks['cases']>=7680
assert checks['source_sha256']==hashlib.sha256((p/'src/runtime/pes13_perf20_fuse.h').read_bytes()).hexdigest()
matrix_checks=json.loads((p/'local/perf19/matrix-tests.json').read_text())
assert matrix_checks['whole_block_bit_identical'] and matrix_checks['cases']>=1728
old_recipe,old_adapt = perf17_patches.adapt_recipe,perf17_patches.adapt

def recipe(text):
    text=old_recipe(text)
    for old,new in [('runtime-perf17-hotblocks','runtime-perf20-roundfusion'),
                    ('pes13-nx-0.2.0-perf17-hotblocks','pes13-nx-0.2.0-perf20-roundfusion'),
                    ('PES13-NX PERF17','PES13-NX PERF20'),('local/perf17','local/perf20')]:
        text=text.replace(old,new)
    return text

def adapt(cmake,dynarec,runtime,project):
    cmake,dynarec,runtime=old_adapt(cmake,dynarec,runtime,project)
    anchor='#include "'+str(project/'src/runtime/pes13_perf17.h')+'"'
    dynarec=once(dynarec,anchor,anchor+'\n#include "'+str(project/'src/runtime/pes13_perf19.h')+'"\n#include "'+str(project/'src/runtime/pes13_perf20.h')+'"')
    dynarec=once(dynarec,'    apply_box64_options();','''    apply_box64_options();
    {
        FILE *f = fopen("sdmc:/switch/pes13-nx/perf19-matrix.txt", "r");
        if (f) { __atomic_store_n(&pes19_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }
        f = fopen("sdmc:/switch/pes13-nx/perf20-fusion.txt", "r");
        if (f) { __atomic_store_n(&pes20_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }
    }''')
    runtime=once(runtime,'    wine_nx_thread_report();',
        '    { extern void wine_nx_perf19_report(void); wine_nx_perf19_report(); }\n'
        '    { extern void wine_nx_perf20_report(void); wine_nx_perf20_report(); }\n    wine_nx_thread_report();')
    hook='''    wine_nx_box64_patch(native_source
        "            ClearCache(actual_p+sizeof(void*), native_size);   // need to clear the cache before execution..."
        "            { extern void wine_nx_perf19_patch(void *); wine_nx_perf19_patch(block); extern void wine_nx_perf20_patch(void *); wine_nx_perf20_patch(block); }\\n            ClearCache(actual_p+sizeof(void*), native_size);   // need to clear the cache before execution..."
        "PERF20 rounding fusion before cache flush")
'''
    cmake=once(cmake,'    set(native_generated "${CMAKE_CURRENT_BINARY_DIR}/${target}-dynarec_native.c")',
               hook+'    set(native_generated "${CMAKE_CURRENT_BINARY_DIR}/${target}-dynarec_native.c")')
    cmake=once(cmake,'extern void wine_nx_perf17_capture(void*, unsigned int); wine_nx_perf17_capture(block, helper.env->dynarec_bigblock);',
               'extern void wine_nx_perf20_capture(void*); wine_nx_perf20_capture(block);')
    return cmake,dynarec,runtime

fuse_test=root/'perf20-fuse-safety'
subprocess.run(['cc','-O2','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                str(p/'tests/perf20_fuse.c'),'-o',str(fuse_test)],check=True)
subprocess.run([str(fuse_test)],check=True)
perf17_patches.adapt_recipe,perf17_patches.adapt=recipe,adapt
profile=root/'runtime-perf11-source/wine-nx-probe/source/thread_profile.c'
original=profile.read_bytes()
try:
    profile.write_text(once(original.decode(),'#define NX_PROF_PERIOD_NS    2000000',
                           '#define NX_PROF_PERIOD_NS    10000000'))
    path=p/'tools/build-perf17.py'
    driver=path.read_text().replace('tests/perf17_policy.c','tests/perf20_patch.c')
    driver=once(driver,"subprocess.run([exe, str(p / 'local/game/pes2013.exe')], env=env, check=True)",
                "subprocess.run([exe, str(p / 'local/game/pes2013.exe'), str(p / 'local/perf18/captures'), str(p / 'local/perf20/captures'), str(p / 'local/perf20/worker-c-fused.bin')], env=env, check=True)")
    exec(compile(driver,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
finally:
    profile.write_bytes(original)
    assert profile.read_bytes()==original
    print('PERF20 profiler source restored byte-for-byte',flush=True)
