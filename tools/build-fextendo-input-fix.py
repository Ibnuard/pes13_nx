"""Rebuild a local input preview from the hash-pinned keyboard-v4 source archive.

Uses the archived production Wine changes, never the active experiment stack.
An environment dependency diff is recorded; this does not promote a CI runtime.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WINE = '1bc4e45163f0d2328cdfd35c7f471dd9821bb879'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--wine', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--build-root', type=Path, required=True)
    p.add_argument('--jobs', type=int, default=4)
    p.add_argument('--prepare-only', action='store_true')
    p.add_argument('--transition-trace', action='store_true', help='Opt-in bounded HIGH freeze call/exit/allocation evidence')
    p.add_argument('--scratch-reserve',action='store_true',help='Preallocate a coalescing 32-MiB FEX compiler scratch arena')
    p.add_argument('--scratch-reserve-mib',type=int,choices=(32,64),default=32,help='Bounded startup scratch capacity; 64 targets HIGH compiler overlap')
    p.add_argument('--crash-log',action='store_true',help='Direct, bounded fatal file independent of the diagnostic worker')
    p.add_argument('--live-freeze',action='store_true',help='Sample registered thread contexts every six seconds, even while Present continues')
    p.add_argument('--page-store',action='store_true',help='Recover Wine backing allocations from fragmented free pages')
    p.add_argument('--thread-stack-reserve',action='store_true',help='Bounded fallback for native libnx stack allocation under fragmentation')
    p.add_argument('--scratch-pages',action='store_true',help='Recover FEX scratch, lookup and private heap allocations from fragmented native pages')
    p.add_argument('--rust-heap',action='store_true',help='Native Rust CPU-heap fallback plus bounded fatal call-stack/text evidence')
    p.add_argument('--production',action='store_true',help='Keep memory fixes; normal launch quiet, debug launch with startup console and error files')
    a = p.parse_args()
    assert not a.production or (a.rust_heap and a.scratch_reserve_mib==64),'Production retains the full-match memory checkpoint'
    assert not a.scratch_reserve or a.transition_trace,'Keep diagnostic evidence in the scratch candidate'
    assert a.scratch_reserve_mib==32 or a.scratch_reserve,'Capacity requires the scratch-reserve feature'
    assert not a.crash_log or a.transition_trace,'Keep transition context with the crash-log candidate'
    assert not a.live_freeze or a.crash_log,'Live snapshots require crash and transition context'
    assert not a.page_store or a.live_freeze,'Page-store candidate keeps allocation and live-thread evidence'
    assert not a.thread_stack_reserve or a.page_store,'Thread-stack candidate retains page-store and trace fixes'
    assert not a.scratch_pages or (a.thread_stack_reserve and a.scratch_reserve),'Scratch pages retain prior memory fixes'
    assert not a.rust_heap or a.scratch_pages,'Rust CPU fallback shares the general page store'
    cache=a.build_root.resolve()
    lock = json.loads((ROOT/'release/runtime-lock.json').read_text())
    assert lock['tag'] == 'runtime-keyboard-v4' and sha(a.archive) == lock['sha256']
    work = a.output.resolve();work.mkdir(parents=True, exist_ok=True)
    archive = work/'approved'
    if not archive.exists():
        with zipfile.ZipFile(a.archive) as z:z.extractall(archive)
    baseline = json.loads((archive/'evidence/keyboard-v4/build-report.json').read_text())
    source = work/'native-source'
    with tarfile.open(a.wine) as t:
        wine_root=t.getmembers()[0].name
        assert wine_root in ('wine-nx-'+WINE,'autorun-'+WINE)
    if not source.exists():
        with tarfile.open(a.wine) as t:
            assert all(m.name==wine_root or m.name.startswith(wine_root+'/') for m in t.getmembers())
            t.extractall(work, filter='data')
        (work/wine_root).rename(source)
    # Wine-NX's prepared PERF11 tree also includes PES platform glue added by
    # bootstrap, before the frozen FEX/production patch manifest starts.
    prepared=cache/'runtime-perf11-source'
    if not (work/'prepared-source.stamp').exists():
        shutil.copytree(prepared,source,dirs_exist_ok=True,symlinks=False,
                        ignore=shutil.ignore_patterns('.git','build*','*.o','*.a'))
        (work/'prepared-source.stamp').write_text(str(prepared)+'\n')
    # Restore the frozen generated files before applying the feature delta.
    frozen = archive/'source/generated/wine/native-source'
    manifest = json.loads((archive/'evidence/runtime/wine-patches.json').read_text())['native-source']
    for name,digest in manifest.items():
        path=frozen/name;assert sha(path)==digest,name
        (source/name).parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,source/name)
    # This upstream header predates the archived generated-file manifest.
    # Restore it on every run so an opt-out build cannot retain the fallback.
    with tarfile.open(a.wine) as t:
        name='dlls/ntdll/unix/horizon_memfile.h'
        header=t.extractfile(wine_root+'/'+name).read()
        assert hashlib.sha256(header).hexdigest()=='6c64279185e3a37bd3c9f82c250d3c0a394b9304843a9aab0691a639730a54cc'
        (source/name).write_bytes(header)
        name='dlls/ntdll/unix/horizon_pool.h'
        (source/name).write_bytes(t.extractfile(wine_root+'/'+name).read())
    # Files added by keyboard-v4 were previously untouched; restore them from
    # the pinned upstream tar, then apply the archived exact, reviewed diff.
    for name in baseline['generated_sources']:
        if name not in manifest:
            shutil.copy2(prepared/name,source/name)
    subprocess.run(['patch','--batch','--fuzz=0','-p1','-d',str(source),'-i',
                    str(archive/'source/keyboard-v4/generated-runtime-changes.patch')],check=True)
    for name,digest in baseline['generated_sources'].items():
        assert sha(source/name)==digest,('archived keyboard-v4 differs',name)
    before={n:(source/n).read_text() for n in baseline['generated_sources']}
    runtime=source/'wine-nx-probe/source/runtime.c'
    data=runtime.read_text()
    for name in ('fextendo_presets.h','fextendo_ui.h','fextendo_launcher.h'):
        old=(archive/'source/keyboard-v4/src/runtime'/name).read_text()
        new=(ROOT/'src/runtime'/name).read_text()
        old=old.replace('Check fex-runtime.log, then close and relaunch.','Check the game and runtime files, then close and relaunch.')
        new=new.replace('Check fex-runtime.log, then close and relaunch.','Check the game and runtime files, then close and relaunch.')
        assert data.count(old)==1,name
        data=data.replace(old,new)
    anchor='static void *log_flusher( void *arg )\n'
    assert data.count(anchor)==1
    data=data.replace(anchor,'#include "fextendo_diagnostics.h"\n'+anchor)
    anchor='        fx_production_maintenance_tick(++ticks);'
    assert data.count(anchor)==1
    data=data.replace(anchor,anchor+'\n        fx_diagnostics_tick(ticks);')
    runtime.write_text(data)
    feature=work/'feature/src/runtime';feature.mkdir(parents=True,exist_ok=True)
    paths={name for name in baseline['feature_sources'] if name.startswith('src/runtime/')}
    paths.add('src/runtime/fextendo_keyboard_options.h')
    paths.add('src/runtime/fextendo_settings.h')
    paths.add('src/runtime/fextendo_diagnostics.h')
    if a.production:paths.update(('src/runtime/fextendo_launch_debug.h','src/runtime/fextendo_debug_console.h',
        'src/runtime/fextendo_launch_memory.h','src/runtime/fextendo_startup_heap.h','src/runtime/fextendo_debug_file.h',
        'src/runtime/fextendo_virtmem.c'))
    if a.transition_trace:
        paths.update(('src/runtime/fextendo_transition_trace.h','src/runtime/fextendo_transition_alloc.h'))
    if a.crash_log:paths.add('src/runtime/fextendo_crash.h')
    if a.live_freeze:paths.update(('src/runtime/fextendo_live_trace.h','src/runtime/fextendo_live_threads.h'))
    if a.thread_stack_reserve:paths.add('src/runtime/fextendo_thread_stack.h')
    if a.rust_heap:paths.update(('src/runtime/fextendo_rust_heap.h','src/runtime/fextendo_mesa_heap.h'))
    for name in paths:shutil.copy2(ROOT/name,feature/Path(name).name)
    cmake=source/'wine-nx-probe/CMakeLists.txt';data=cmake.read_text()
    import re
    data=re.sub(r'"/Users/[^"\n]+/feature/src/runtime"','"'+str(feature)+'"',data)
    assert '/Users/' not in data
    cmake.write_text(data)
    # Archived generated C contains absolute includes from the production
    # builder. Rebase those paths onto the archived (not live) source files.
    for path in source.rglob('*'):
        if not path.is_file() or path.suffix not in ('.c','.h','.cpp','.S'):continue
        data=path.read_text(errors='surrogateescape')
        if '/Users/' not in data:continue
        def rebase(match):
            target=archive/'source'/match.group(1)
            assert target.is_file(),target
            return '#include "'+str(target)+'"'
        updated=re.sub(r'#include "/Users/[^"\n]+/project/(src/[^"\n]+)"',rebase,data)
        if updated!=data:path.write_text(updated,errors='surrogateescape')
    generated=set(baseline['generated_sources'])
    transition_counts={}
    if a.transition_trace:
        from fextendo_transition_patches import apply
        changed,transition_counts=apply(source,feature,crash_log=a.crash_log,live_freeze=a.live_freeze)
        generated.update(changed)
    fex_dir=archive/'source/src/fex';fex_sources={}
    if a.scratch_reserve:
        from fextendo_scratch_patches import apply as scratch_apply
        fex_dir,fex_sources=scratch_apply(archive,work/'feature',ROOT,a.scratch_reserve_mib,a.scratch_pages)
        runtime.write_text(runtime.read_text().replace('#define FX_TRANSITION_TRACE 1',
            '#define FX_TRANSITION_TRACE 1\n#define FX_SCRATCH_RESERVE 1\n#define FX_SCRATCH_RESERVE_VERSION '+
            ('3' if a.scratch_reserve_mib==64 else '2')))
    if a.page_store:
        from fextendo_page_store_patches import apply as page_apply
        generated.update(page_apply(source,ROOT))
        runtime.write_text(runtime.read_text().replace('#define FX_TRANSITION_TRACE 1',
            '#define FX_TRANSITION_TRACE 1\n#define FX_PAGE_STORE 1'))
    if a.scratch_pages:
        runtime.write_text(runtime.read_text().replace('#define FX_TRANSITION_TRACE 1',
            '#define FX_TRANSITION_TRACE 1\n#define FX_SCRATCH_PAGES 2'))
    if a.thread_stack_reserve:
        data=runtime.read_text()
        anchor='#include "fextendo_transition_trace.h"'
        assert data.count(anchor)==1
        data=data.replace(anchor,anchor+'\n#define FX_THREAD_STACK_RESERVE 1\n#include "fextendo_thread_stack.h"')
        anchor='    fx_crash_bootstrap();'
        assert data.count(anchor)==1
        runtime.write_text(data.replace(anchor,anchor+'\n    fx_thread_stack_init();'))
        cmake.write_text(cmake.read_text()+'\ntarget_link_options(wine-nx-runtime PRIVATE -Wl,--wrap=threadCreate -Wl,--wrap=__libnx_aligned_alloc -Wl,--wrap=__libnx_free)\n')
    rust_binding={}
    mesa_binding={}
    if a.rust_heap:
        from fextendo_rust_heap_patches import apply as rust_apply
        rust_binding=rust_apply(cache/'mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib/libnak_rs.a',feature,cmake)
        data=runtime.read_text()
        anchor='#define FX_TRANSITION_TRACE 1'
        assert data.count(anchor)==1
        data=data.replace(anchor,anchor+'\n#define FX_RUST_HEAP 1\n#define FX_NATIVE_ABORT_DETAIL 1')
        anchor='#include "fextendo_crash.h"'
        assert data.count(anchor)==1
        runtime.write_text(data.replace(anchor,anchor+'\n#include "fextendo_rust_heap.h"'))
        from fextendo_mesa_heap_patches import apply as mesa_apply
        mesa_binding=mesa_apply(cache/'mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib/libmesa_util.a',feature,cmake,Path('/opt/devkitpro'))
        runtime.write_text(runtime.read_text()+'\n#include "fextendo_mesa_heap.h"\n')
    if a.production:
        # Restore the pre-main image guard before injecting the rejection path.
        assert sha(ROOT/'src/runtime/pes13_preload.c')=='6bb8ecff9fea7e0e2b1e10a4a04b36705155b159d4584088257294a5b192f225'
        shutil.copy2(ROOT/'src/runtime/pes13_preload.c',source/'wine-nx-probe/source/pes13_preload.c')
        from fextendo_production_patches import apply as production_apply
        generated.update(production_apply(source))
        # All libnx/Wine/FEX users retain ONE reservation manager. Defining the
        # complete virtmem ABI here prevents the archive's virtmem.o extraction.
        cmake.write_text(cmake.read_text()+'\ntarget_sources(wine-nx-runtime PRIVATE "'+str(feature/'fextendo_virtmem.c')+'")\n')
    features={n:sha(ROOT/n) for n in sorted(paths)}
    if a.scratch_reserve:features['src/fex/horizon_scratch_reserve.h']=sha(ROOT/'src/fex/horizon_scratch_reserve.h')
    if a.scratch_pages:
        for name in ('horizon_scratch_pages.h','horizon_heap_pressure.h'):
            features['src/fex/'+name]=sha(ROOT/'src/fex'/name)
    if a.page_store:
        for name in ('horizon_page_store.h','horizon_store_backing.h','horizon_pool_pressure.h'):
            features['src/runtime/'+name]=sha(ROOT/'src/runtime'/name)
    spec=importlib.util.spec_from_file_location('runtime_builder',ROOT/'tools/build-fex-runtime.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sdk=Path('/opt/devkitpro');cache=a.build_root.resolve()
    mesa=cache/'mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib'
    deps=module.native_dependency_receipt(mesa,sdk)
    drift={n:{'production':baseline['native_dependencies'].get(n),'local':deps.get(n)}
           for n in sorted(set(deps)|set(baseline['native_dependencies']))
           if deps.get(n)!=baseline['native_dependencies'].get(n)}
    (work/'dependency-diff.json').write_text(json.dumps(drift,indent=2)+'\n')
    report={'passed':False,'hardware_tested':False,'native_keyboard_preview':True,
            'transition_trace':a.transition_trace,'transition_trace_version':3 if a.transition_trace else 0,'transition_calls':transition_counts,
            'live_keyboard_overlay':True,'baseline_nro_sha256':baseline['nro_sha256'],
            'feature_sources':features,'native_dependencies':deps,
            'generated_sources':{n:sha(source/n) for n in sorted(generated)}}
    report['build_scripts']={n:sha(ROOT/n) for n in ('tools/build-fextendo-input-fix.py',
        'tools/fextendo_transition_patches.py')}
    report['scratch_reserve']=a.scratch_reserve
    report['crash_log_version']=2 if a.crash_log else 0
    report['live_freeze_version']=1 if a.live_freeze else 0
    report['page_store_version']=1 if a.page_store else 0
    report['thread_stack_reserve_version']=1 if a.thread_stack_reserve else 0
    report['scratch_pages_version']=5 if a.scratch_pages else 0
    report['virtmem_exhaustive_version']=1 if a.production else 0
    report['private_heap_reserve_version']=2 if a.scratch_pages else 0
    report['idle_pool_recovery_version']=1 if a.page_store else 0
    report['mesa_heap_binding']=mesa_binding
    report['rust_heap_version']=1 if a.rust_heap else 0
    report['rust_heap_binding']=rust_binding
    report['production_screen_debug']=a.production
    report['diagnostic_file_writes']='debug-launch-only' if a.production else True
    report['debug_console_scope']='launcher-startup-only' if a.production else None
    report['debug_gameplay_overlay']=False if a.production else None
    report['launch_memory_gate']=a.production
    report['launch_memory_gate_version']=3 if a.production else 0
    report['scratch_reserve_version']=4 if a.scratch_reserve else 0
    report['scratch_reserve_mib']=a.scratch_reserve_mib if a.scratch_reserve else 0
    report['native_fex_sources']=fex_sources
    if a.scratch_reserve:report['build_scripts']['tools/fextendo_scratch_patches.py']=sha(ROOT/'tools/fextendo_scratch_patches.py')
    if a.page_store:report['build_scripts']['tools/fextendo_page_store_patches.py']=sha(ROOT/'tools/fextendo_page_store_patches.py')
    if a.rust_heap:report['build_scripts']['tools/fextendo_rust_heap_patches.py']=sha(ROOT/'tools/fextendo_rust_heap_patches.py')
    if a.rust_heap:report['build_scripts']['tools/fextendo_mesa_heap_patches.py']=sha(ROOT/'tools/fextendo_mesa_heap_patches.py')
    if a.production:report['build_scripts']['tools/fextendo_production_patches.py']=sha(ROOT/'tools/fextendo_production_patches.py')
    (work/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')
    if a.prepare_only:return
    env=dict(os.environ,DEVKITPRO=str(sdk),DEVKITA64=str(sdk/'devkitA64'),
             PATH=str(sdk/'devkitA64/bin')+':'+str(sdk/'tools/bin')+':'+os.environ['PATH'])
    def run(command):
        with (work/'build.log').open('a') as f:
            result=subprocess.run(list(map(str,command)),env=env,stdout=f,stderr=subprocess.STDOUT)
        if result.returncode:
            print('\n'.join((work/'build.log').read_text().splitlines()[-60:]),flush=True)
            result.check_returncode()
    exception=cache/'fex-experiment/wine3/libnx-exception.o'
    build=work/'native-build';project=source/'wine-nx-probe'
    run(['cmake','-S',project,'-B',build,'-G','Ninja',
         '-DCMAKE_TOOLCHAIN_FILE='+str(project/'cmake/switch-devkitA64.cmake'),
         '-DWINE_NX_PE_BUILD_DIR='+str(cache/'pe'),'-DWINE_NX_BOX64_DYNAREC=OFF',
         '-DWINE_NX_BOX64_INTERPRETER=OFF','-DWINE_NX_STOCK_MESA=OFF',
         '-DWINE_NX_MESA_SWITCH_DIR='+str(mesa),'-DPES13_FEX_DIR='+str(fex_dir),
         '-DPES13_LIBNX_EXCEPTION_OBJECT='+str(exception),'-DCMAKE_BUILD_TYPE=Release'])
    run(['cmake','--build',build,'--target','wine-nx-runtime','-j',a.jobs])
    nro=work/'pes13-fex.nro';nacp=work/'pes13-fex.nacp'
    run([sdk/'tools/bin/nacptool','--create','PES13 - FEXTendo','AndroSwitch Project','0.3.8-r6' if a.production else '0.3.8-test',nacp])
    run([sdk/'tools/bin/elf2nro',build/'wine-nx-runtime.elf',nro,'--nacp='+str(nacp),
         '--icon='+str(archive/'source/assets/fextendo-v3/nro-icon.jpg')])
    assert deps==module.native_dependency_receipt(mesa,sdk)
    assert features=={n:sha(ROOT/n) for n in features}
    report.update(passed=True,nro_sha256=sha(nro),native_elf_sha256=sha(build/'wine-nx-runtime.elf'))
    (work/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('passed','hardware_tested','nro_sha256')},indent=2))

if __name__=='__main__':main()
