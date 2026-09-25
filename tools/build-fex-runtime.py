"""Build isolated FEX2 bringup or FEX3 test/PES integration runtimes in WSL."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
from fex2_prepare import prepare
from fex_wine_patches import apply


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-root', type=Path, default=Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build')))
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--native-only', action='store_true')
    parser.add_argument('--integration', action='store_true', help='Isolated FEX3 worker/exception and PES integration build')
    parser.add_argument('--samecore-yield', action='store_true',
                        help='FEX3 experiment: Sleep(0) yields without core migration')
    args = parser.parse_args()
    if args.samecore_yield and not args.integration:
        parser.error('--samecore-yield requires --integration')
    root = args.build_root.resolve()
    work = prepare(root, project, 'wine3' if args.integration else 'wine2')
    evidence = project / ('local/fex3' if args.integration else 'local/fex2')
    evidence.mkdir(parents=True, exist_ok=True)
    patches = apply(work, project, integration=args.integration,
                    samecore_yield=args.samecore_yield)
    (evidence / 'wine-patches.json').write_text(json.dumps(patches, indent=2) + '\n')
    tc = root / 'toolchains/llvm-mingw-20260505-ucrt-ubuntu-22.04-x86_64/bin'
    devkit = Path('/opt/devkitpro')
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
         '-DWINE_NX_MESA_SWITCH_DIR=' + str(root / 'mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib'),
         '-DPES13_FEX_DIR=' + str(project / 'src/fex'),
         '-DPES13_LIBNX_EXCEPTION_OBJECT=' + str(exception),
         '-DCMAKE_BUILD_TYPE=Release'])
    run(['cmake', '--build', build, '--target', 'wine-nx-runtime', '-j', args.jobs])
    name = 'pes13-fex' if args.integration else 'pes13-fex2'
    title = 'PES13-NX FEX3' if args.integration else 'PES13 FEX2 x86 Test'
    version = '0.3.0' if args.integration else '0.2.0'
    nacp, nro = work / (name + '.nacp'), work / (name + '.nro')
    run([devkit / 'tools/bin/nacptool', '--create', title,
         'PES13-NX / Wine / FEX-Emu', version, nacp])
    run([devkit / 'tools/bin/elf2nro', build / 'wine-nx-runtime.elf', nro,
         '--nacp=' + str(nacp), '--icon=' + str(project / 'assets/icon.jpg')])
    from nro_assets import inspect_nro
    metadata = inspect_nro(nro.read_bytes(), (project / 'assets/icon.jpg').read_bytes(),
                           expected_title=title, expected_version=version)
    payload = evidence / 'payload'
    payload.mkdir(exist_ok=True)
    shutil.copy2(nro, payload / nro.name)
    report = {'runtime': str(nro), 'nro_sha256': hashlib.sha256(nro.read_bytes()).hexdigest(),
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
                                            'src/runtime/fex_stall_probe.h',
                                            'src/runtime/fex_suspend_observe.h')}
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
