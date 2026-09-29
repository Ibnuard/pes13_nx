"""Build isolated FEX2/FEX3 runtimes with devkitA64 and a host-native PE toolchain."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from fex2_prepare import prepare
from fex_wine_patches import apply
from fex_toolchain import wine_provenance


def native_dependency_receipt(mesa, sdk):
    """Record actual static inputs; never silently link a non-NVK SDK."""
    if not (mesa / 'libvulkan.a').is_file():
        raise FileNotFoundError(mesa / 'libvulkan.a')
    files = {'mesa/' + path.name: path for path in mesa.glob('*.a')}
    files['sdk/libnx/lib/libnx.a'] = sdk / 'libnx/lib/libnx.a'
    files.update({'sdk/' + path.relative_to(sdk).as_posix(): path
                  for path in (sdk / 'portlibs/switch/lib').glob('*.a')})
    return {name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in sorted(files.items())}


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-root', type=Path, default=Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build')))
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--native-only', action='store_true')
    parser.add_argument('--output-dir', type=Path,
                        help='Separate evidence/payload directory for candidate and control builds')
    parser.add_argument('--toolchain', type=Path,
                        help='LLVM-MinGW root (containing bin); use the build host variant')
    parser.add_argument('--integration', action='store_true', help='Isolated FEX3 worker/exception and PES integration build')
    parser.add_argument('--runtime-fixes', action='store_true',
                        help='Opt-in FEX3 shader cache, waitable timer and affinity retry backports')
    parser.add_argument('--diagnostic', action='store_true',
                        help='Read-only one-second event timeline on the FEX3 control')
    parser.add_argument('--samecore-yield', action='store_true',
                        help='FEX3 experiment: Sleep(0) yields without core migration')
    parser.add_argument('--resume-gate', action='store_true',
                        help='FEX3 isolated self-suspend wakeups; leave global select routing unchanged')
    parser.add_argument('--stability', action='store_true',
                        help='FEX3 combined validated timer/cache/affinity and isolated resume fixes')
    parser.add_argument('--hang-audit', action='store_true',
                        help='Post-stability: no scaled readback, checked blit submission, earlier idle-worker captures')
    parser.add_argument('--warm-audit', action='store_true',
                        help='Post-hang-audit: defer routine FEX flushes; observe pipeline creation and driver cache')
    parser.add_argument('--jit-latency', action='store_true',
                        help='Post-warm-audit: 500-instruction JIT candidate; INI selects 5000 control')
    parser.add_argument('--sleep-deadline', action='store_true',
                        help='Post-JIT-latency: monotonic relative sleeps and live self-wait age reports')
    parser.add_argument('--worker-cores', action='store_true',
                        help='Prefer cores 0-2 for automatic workers; preserve explicit guest affinity')
    parser.add_argument('--jit-log-queue', action='store_true',
                        help='Queue JIT timing reports for the existing logger, avoiding game-thread SD writes')
    parser.add_argument('--yield-burst', action='store_true',
                        help='Brief backoff only after dense ineffective yields; keep ordinary waits intact')
    parser.add_argument('--yield-adaptive', action='store_true',
                        help='Shorten sustained polling bursts after inexpensive pauses; cool down after oversleep')
    parser.add_argument('--stable-balance', action='store_true',
                        help='Preserve placement; move at most one worker per balance pass')
    parser.add_argument('--gap-audit', action='store_true',
                        help='Bounded present-thread CPU/wall timing and optional disk-cache environment')
    parser.add_argument('--launcher', action='store_true',help='Fextendo console launcher and preset selector')
    parser.add_argument('--memory-audit', action='store_true',help='Time native memory-budget queries on the launcher baseline')
    parser.add_argument('--memory-budget-filter', action='store_true',help='Decline costly optional memory-budget queries on Switch')
    parser.add_argument("--short-trace", action="store_true", help="Bounded per-thread JIT/wait timing on v3.2; supports OFF control")
    parser.add_argument("--dxvk-core3", action="store_true", help="Named dxvk-cs offload trial; requires short-trace baseline")
    parser.add_argument('--polling', action='store_true', help='Sharded polling counters and shared yield timing; runtime OFF control retained')
    parser.add_argument('--fast-api', action='store_true', help='Validated QPC/non-alertable delay gateway and bounded hotspot diagnostics')
    args = parser.parse_args()
    if args.fast_api and not args.polling:
        parser.error('--fast-api requires --polling')
    if args.polling and not args.dxvk_core3:
        parser.error('--polling requires --dxvk-core3')
    if args.dxvk_core3 and not args.short_trace:
        parser.error("--dxvk-core3 requires --short-trace")
    if args.short_trace and not args.memory_budget_filter:
        parser.error("--short-trace requires --memory-budget-filter")
    if args.memory_budget_filter and not args.memory_audit:
        parser.error('--memory-budget-filter requires --memory-audit')
    if args.memory_audit and not args.launcher:
        parser.error('--memory-audit requires --launcher')
    if args.launcher and not args.gap_audit:
        parser.error('--launcher requires --gap-audit')
    if args.gap_audit and not args.stable_balance:
        parser.error('--gap-audit requires --stable-balance')
    if args.stable_balance and (not args.yield_burst or args.yield_adaptive):
        parser.error('--stable-balance requires --yield-burst and excludes --yield-adaptive')
    if args.yield_adaptive and not args.yield_burst:
        parser.error('--yield-adaptive requires --yield-burst')
    if args.yield_burst and (not args.jit_log_queue or not args.samecore_yield):
        parser.error('--yield-burst requires --jit-log-queue --samecore-yield')
    if args.jit_log_queue and not args.worker_cores:
        parser.error('--jit-log-queue requires --worker-cores')
    if args.worker_cores and not args.sleep_deadline:
        parser.error('--worker-cores requires --sleep-deadline')
    if args.sleep_deadline and not args.jit_latency:
        parser.error('--sleep-deadline requires --jit-latency')
    if args.jit_latency and not args.warm_audit:
        parser.error('--jit-latency requires --warm-audit')
    if args.warm_audit and not args.hang_audit:
        parser.error('--warm-audit requires --hang-audit')
    if args.hang_audit and (not args.integration or not args.stability):
        parser.error('--hang-audit requires --integration --stability')
    if args.stability:
        if not args.integration:
            parser.error('--stability requires --integration')
        args.runtime_fixes = args.resume_gate = args.diagnostic = True
    if args.resume_gate and not args.integration:
        parser.error('--resume-gate requires --integration')
    if args.resume_gate and args.runtime_fixes and not args.stability:
        parser.error('--resume-gate excludes --runtime-fixes')
    if args.samecore_yield and not args.integration:
        parser.error('--samecore-yield requires --integration')
    if args.runtime_fixes and not args.integration:
        parser.error('--runtime-fixes requires --integration')
    if args.diagnostic and (not args.integration or (args.runtime_fixes and not args.stability)):
        parser.error('--diagnostic requires --integration and excludes --runtime-fixes')
    root = args.build_root.resolve()
    toolchain = (args.toolchain.resolve() if args.toolchain else
                 root / 'toolchains/llvm-mingw-20260505-ucrt-ubuntu-22.04-x86_64')
    tc = toolchain / 'bin'
    if not args.native_only and not all((tc / name).is_file() for name in
            ('aarch64-w64-mingw32-clang', 'i686-w64-mingw32-clang')):
        raise SystemExit(f'Missing LLVM-MinGW toolchain: {tc}')
    work = root / 'fex-experiment' / ('wine3' if args.integration else 'wine2')
    devkit = Path('/opt/devkitpro')
    env = dict(os.environ, DEVKITPRO=str(devkit), DEVKITA64=str(devkit / 'devkitA64'),
               PATH=f'{tc}:{devkit}/devkitA64/bin:{devkit}/tools/bin:' + os.environ['PATH'])
    wine_provenance(work / 'pe-build', toolchain, env)
    work = prepare(root, project, 'wine3' if args.integration else 'wine2')
    evidence = project / ('local/fex3' if args.integration else 'local/fex2')
    if args.output_dir:
        evidence = args.output_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    patches = apply(work, project, integration=args.integration,
                    samecore_yield=args.samecore_yield, runtime_fixes=args.runtime_fixes,
                    diagnostic=args.diagnostic, resume_gate=args.resume_gate, stability=args.stability,
                    hang_audit=args.hang_audit, warm_audit=args.warm_audit, jit_latency=args.jit_latency,
                    sleep_deadline=args.sleep_deadline, worker_cores=args.worker_cores,
                    jit_log_queue=args.jit_log_queue, yield_burst=args.yield_burst,
                    yield_adaptive=args.yield_adaptive, stable_balance=args.stable_balance, gap_audit=args.gap_audit, launcher=args.launcher,
                    memory_audit=args.memory_audit, memory_budget_filter=args.memory_budget_filter, short_trace=args.short_trace, dxvk_core3=args.dxvk_core3,
                    polling=args.polling, fast_api=args.fast_api)
    (evidence / 'wine-patches.json').write_text(json.dumps(patches, indent=2) + '\n')

    devkit = Path('/opt/devkitpro')
    mesa = root / 'mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib'
    native_dependencies = native_dependency_receipt(mesa, devkit)
    env = dict(os.environ, DEVKITPRO=str(devkit), DEVKITA64=str(devkit / 'devkitA64'),
               PATH=f'{tc}:{devkit}/devkitA64/bin:{devkit}/tools/bin:' + os.environ['PATH'])

    def run(argv, **kw):
        print('+', ' '.join(map(str, argv)), flush=True)
        if 'stdout' in kw:
            return subprocess.run(list(map(str, argv)), check=True, env=env, **kw)
        with (evidence / 'build.log').open('ab') as log:
            result = subprocess.run(list(map(str, argv)), env=env, stdout=log, stderr=subprocess.STDOUT, **kw)
        if result.returncode:
            print('\n'.join((evidence / 'build.log').read_text(errors='replace').splitlines()[-60:]), flush=True)
            result.check_returncode()
        return result

    # Leave installed libnx untouched. The strong FEX2 entry delegates ordinary
    # exceptions to this exact installed version under a private symbol name.
    exception = work / 'libnx-exception.o'
    with exception.open('wb') as output:
        run([devkit / 'devkitA64/bin/aarch64-none-elf-ar', 'p',
             devkit / 'libnx/lib/libnx.a', 'exception.o'], stdout=output)
    run([devkit / 'devkitA64/bin/aarch64-none-elf-objcopy',
         '--redefine-sym', '__libnx_exception_entry=pes13_libnx_exception_entry', exception])

    build = work / 'native-build'
    source = work / 'native-source/wine-nx-probe'
    run(['cmake', '-S', source, '-B', build, '-G', 'Ninja',
         '-DCMAKE_TOOLCHAIN_FILE=' + str(source / 'cmake/switch-devkitA64.cmake'),
         '-DWINE_NX_PE_BUILD_DIR=' + str(root / 'pe'),
         '-DWINE_NX_BOX64_DYNAREC=OFF', '-DWINE_NX_BOX64_INTERPRETER=OFF',
         '-DWINE_NX_STOCK_MESA=OFF',
         '-DWINE_NX_MESA_SWITCH_DIR=' + str(mesa),
         '-DPES13_FEX_DIR=' + str(project / 'src/fex'),
         '-DPES13_LIBNX_EXCEPTION_OBJECT=' + str(exception),
         '-DCMAKE_BUILD_TYPE=Release'])
    run(['cmake', '--build', build, '--target', 'wine-nx-runtime', '-j', args.jobs])
    if native_dependencies != native_dependency_receipt(mesa, devkit):
        raise RuntimeError('Native dependencies changed during build')
    name = 'pes13-fex' if args.integration else 'pes13-fex2'
    title = 'PES13-NX FEX3' if args.integration else 'PES13 FEX2 x86 Test'
    if args.launcher: title = 'PES13 - FEXTendo'
    version = '0.3.0' if args.integration else '0.2.0'
    if args.launcher:
        version = re.search(r'^#define FX_APP_VERSION "([0-9.]+)"',
                            (project/'src/runtime/fextendo_ui.h').read_text(), re.M).group(1)
    nacp, nro = work / (name + '.nacp'), work / (name + '.nro')
    run([devkit / 'tools/bin/nacptool', '--create', title,
         'AndroSwitch Project' if args.launcher else 'PES13-NX / Wine / FEX-Emu', version, nacp])
    icon = project / ('assets/fextendo-v3/nro-icon.jpg' if args.launcher else 'assets/icon.jpg')
    run([devkit / 'tools/bin/elf2nro', build / 'wine-nx-runtime.elf', nro,
         '--nacp=' + str(nacp), '--icon=' + str(icon)])
    from nro_assets import inspect_nro
    metadata = inspect_nro(nro.read_bytes(), icon.read_bytes(),
                           expected_title=title, expected_version=version)
    payload = evidence / 'payload'
    payload.mkdir(exist_ok=True)
    shutil.copy2(nro, payload / nro.name)
    report = {'runtime': str(nro), 'nro_sha256': hashlib.sha256(nro.read_bytes()).hexdigest(),
              'toolchain_path': str(toolchain),
              'runtime_fixes': args.runtime_fixes,
              'stability': args.stability,
              'hang_audit': args.hang_audit,
              'warm_audit': args.warm_audit,
              'jit_latency': args.jit_latency,
              'sleep_deadline': args.sleep_deadline,
              'worker_cores': args.worker_cores,
              'jit_log_queue': args.jit_log_queue,
              'yield_burst': args.yield_burst,
              'yield_adaptive': args.yield_adaptive,
              'stable_balance': args.stable_balance,
              'gap_audit': args.gap_audit,
              'launcher': args.launcher,
              'memory_audit': args.memory_audit,
              'memory_budget_filter': args.memory_budget_filter,
              'short_trace': args.short_trace,
              'dxvk_core3': args.dxvk_core3,
              'polling': args.polling,
              'fast_api': args.fast_api,
              'diagnostic': args.diagnostic,
              'resume_gate': args.resume_gate,
              'samecore_yield': args.samecore_yield,
              'native_dependencies': native_dependencies,
              'metadata': metadata, 'fex_guest_hardware_tested': False,
              'native_source': str(source), 'box64_engine_linked': False}
    reference = evidence / 'reference'
    reference.mkdir(exist_ok=True)
    shutil.copy2(build / 'wine-nx-runtime.elf', reference / (name + '.elf'))
    report['native_elf_sha256'] = hashlib.sha256((reference / (name + '.elf')).read_bytes()).hexdigest()
    report['adapter_sources'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (project / 'src/fex').iterdir() if p.is_file()}
    report['patch_sources'] = {name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                               for name in ('tools/build-fex-runtime.py', 'tools/fex_wine_patches.py',
                                            'tools/fex_reservation_patches.py', 'tools/fex_thread_patches.py',
                                            'tools/fex_fd_patches.py',
                                            'src/runtime/fex_suspend_backoff.h',
                                            'tools/fex_stall_patches.py',
                                            'tools/fex_self_suspend_patches.py',
                                            'src/runtime/fex_self_suspend.h',
                                            'tools/fex_frame_patches.py',
                                            'src/runtime/fex_frame_metrics.h',
                                            'src/runtime/fex_frame_runtime.h',
                                            'tools/fex_pipeline_patches.py',
                                            'src/runtime/fex_pipeline_runtime.h',
                                            'tools/fex_sync_patches.py',
                                            'src/runtime/fex_sync_horizon.h',
                                            'src/runtime/fex_sync_runtime.h',
                                            'tools/fex_game_timing_patches.py',
                                            'src/runtime/fex_game_timing.h',
                                            'src/runtime/fex_game_timing_runtime.h',
                                            'src/runtime/fex_log_policy.h',
                                            'src/runtime/pes13_perf27_wait.h',
                                            'src/runtime/fex_stall_probe.h',
                                            'src/runtime/fex_suspend_observe.h')}
    if args.runtime_fixes:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                        for name in ('tools/fex_cache_patches.py',
                                                     'src/runtime/fex_cache_runtime.h',
                                                     'tools/fex_runtime_fixes.py')})
    if args.diagnostic:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                        for name in ('src/runtime/fex_event_runtime.h',)})
    if args.resume_gate:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                        for name in ('tools/fex_resume_patches.py',
                                                     'src/runtime/fex_resume_runtime.h')})
    if args.hang_audit:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                       for name in ('tools/fex_hang_patches.py',
                                                    'src/runtime/fex_scaled_submit.h',
                                                    'src/runtime/fex_hang_gate.h',
                                                    'src/runtime/fex_hang_waiters.h')})
    if args.warm_audit:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                       for name in ('tools/fex_warm_patches.py',
                                                    'src/runtime/fex_warm_log.h',
                                                    'src/runtime/fex_warm_runtime.h')})
    if args.jit_latency:
        report['patch_sources']['tools/fex_jit_latency_patches.py'] = hashlib.sha256(
            (project / 'tools/fex_jit_latency_patches.py').read_bytes()).hexdigest()
    if args.sleep_deadline:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                       for name in ('tools/fex_sleep_patches.py',
                                                    'src/runtime/fex_relative_delay.h')})
    if args.worker_cores:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                       for name in ('tools/fex_worker_core_patches.py',
                                                    'src/runtime/fex_worker_cores.h')})
    if args.jit_log_queue:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                       for name in ('tools/fex_jit_log_patches.py',
                                                    'src/runtime/fex_jit_log_queue.h')})
    if args.yield_burst:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                       for name in ('tools/fex_yield_burst_patches.py',
                                                    'src/runtime/fex_yield_burst.h',
                                                    'src/runtime/fex_yield_runtime.h')})
    if args.gap_audit:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                       for name in ('tools/fex_gap_probe_patches.py', 'src/runtime/fex_gap_probe.h')})
    if args.launcher:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                       for name in ('tools/fextendo_launcher_patches.py','src/runtime/fextendo_presets.h',
                                                    'src/runtime/fextendo_renderers.h','src/runtime/fextendo_ui.h','src/runtime/fextendo_launcher.h','src/runtime/fextendo_logs.h',
                                                    'src/runtime/fextendo_timestamp_pixels.h','src/runtime/fextendo_timestamp.h',
                                                    'src/runtime/fextendo_overlay_layer.h','src/runtime/fextendo_display.h','src/runtime/fextendo_sfx.h')})
    if args.memory_audit:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                       for name in ('tools/fex_memory_probe_patches.py', 'src/runtime/fex_memory_probe.h')})
    if args.memory_budget_filter:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                       for name in ('tools/fex_memory_budget_patches.py', 'src/runtime/fex_memory_budget.h')})
    if args.stable_balance:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                       for name in ('tools/fex_balance_stable_patches.py',
                                                    'src/runtime/fex_balance_stable.h')})
    if args.yield_adaptive:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                       for name in ('tools/fex_yield_adaptive_patches.py',
                                                    'src/runtime/fex_yield_adaptive.h',
                                                    'src/runtime/fex_yield_adaptive_runtime.h')})
    if args.short_trace:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                       for name in ('tools/fex_short_trace_patches.py', 'src/runtime/fex_short_trace.h')})
    if args.dxvk_core3:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                                       for name in ('tools/fex_dxvk_core3_patches.py', 'src/runtime/fex_dxvk_core3.h')})
    if args.polling:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
            for name in ('tools/fex_polling_patches.py', 'src/runtime/fex_polling_counters.h', 'src/runtime/fex_polling_yield.h')})
    if args.fast_api:
        report['patch_sources'].update({name: hashlib.sha256((project / name).read_bytes()).hexdigest()
            for name in ('tools/fex_fast_api_patches.py', 'src/runtime/fex_fast_api.h', 'src/runtime/fex_hot_profile.h')})
    if not args.native_only:
        pe = work / 'pe-build'
        pe.mkdir(exist_ok=True)
        if not (pe / 'Makefile').exists():
            run([work / 'pe-source/configure', '-C', '--enable-archs=aarch64,i386',
                 '--enable-winebox64=aarch64', '--without-x', '--without-freetype'], cwd=pe)
        pe_modules = ['wow64'] + (['ntdll'] if args.integration else [])
        run(['make', '-C', pe, '-j', args.jobs,
             *[f'dlls/{name}/aarch64-windows/{name}.dll' for name in pe_modules]])
        for name in pe_modules:
            dll = pe / f'dlls/{name}/aarch64-windows/{name}.dll'
            shutil.copy2(dll, payload / dll.name)
            report[name+'_sha256'] = hashlib.sha256(dll.read_bytes()).hexdigest()
        exe = payload / ('fex-stress.exe' if args.integration else 'fex-smoke.exe')
        run([tc / 'i686-w64-mingw32-clang', '-O2', '-msse2', '-mfpmath=sse', '-fno-builtin',
             '-fno-stack-protector', '-nostdlib', project / 'src/fex' / ('guest_stress.c' if args.integration else 'guest_smoke.c'),
             '-Wl,--entry,_probe_entry', '-Wl,--subsystem,console', '-Wl,--dynamicbase', '-Wl,--no-insert-timestamp',
             '-lkernel32', '-o', exe])
        report['guest_sha256'] = hashlib.sha256(exe.read_bytes()).hexdigest()
    else:
        previous = json.loads((evidence / 'runtime-build.json').read_text())
        dependencies = [('wow64_sha256', payload / 'wow64.dll'),
                        ('guest_sha256', payload / ('fex-stress.exe' if args.integration else 'fex-smoke.exe'))]
        if args.integration:
            dependencies.append(('ntdll_sha256', payload / 'ntdll.dll'))
        for field, path in dependencies:
            if hashlib.sha256(path.read_bytes()).hexdigest() != previous[field]:
                raise RuntimeError(f'Changed prior dependency: {path}')
            report[field] = previous[field]
    (evidence / 'runtime-build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
