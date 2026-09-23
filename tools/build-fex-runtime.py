"""Build the isolated FEX2 Wine runtime and original x86 integration test (WSL)."""
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
    args = parser.parse_args()
    root = args.build_root.resolve()
    work = prepare(root, project)
    evidence = project / 'local/fex2'
    evidence.mkdir(parents=True, exist_ok=True)
    patches = apply(work, project)
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
    nacp = work / 'pes13-fex2.nacp'
    nro = work / 'pes13-fex2.nro'
    run([devkit / 'tools/bin/nacptool', '--create', 'PES13 FEX2 x86 Test',
         'PES13-NX / Wine / FEX-Emu', '0.2.0', nacp])
    run([devkit / 'tools/bin/elf2nro', build / 'wine-nx-runtime.elf', nro,
         '--nacp=' + str(nacp), '--icon=' + str(project / 'assets/icon.jpg')])
    from nro_assets import inspect_nro
    metadata = inspect_nro(nro.read_bytes(), (project / 'assets/icon.jpg').read_bytes(),
                           expected_title='PES13 FEX2 x86 Test', expected_version='0.2.0')
    payload = evidence / 'payload'
    payload.mkdir(exist_ok=True)
    shutil.copy2(nro, payload / nro.name)
    report = {'runtime': str(nro), 'nro_sha256': hashlib.sha256(nro.read_bytes()).hexdigest(),
              'metadata': metadata, 'fex_guest_hardware_tested': False,
              'native_source': str(source), 'box64_engine_linked': False}
    if not args.native_only:
        pe = work / 'pe-build'
        pe.mkdir(exist_ok=True)
        if not (pe / 'Makefile').exists():
            run([work / 'pe-source/configure', '-C', '--enable-archs=aarch64,i386',
                 '--enable-winebox64=aarch64', '--without-x', '--without-freetype'], cwd=pe)
        run(['make', '-C', pe, '-j', args.jobs, 'dlls/wow64/aarch64-windows/wow64.dll'])
        dll = pe / 'dlls/wow64/aarch64-windows/wow64.dll'
        shutil.copy2(dll, payload / dll.name)
        report['wow64_sha256'] = hashlib.sha256(dll.read_bytes()).hexdigest()
        exe = payload / 'fex-smoke.exe'
        run([tc / 'i686-w64-mingw32-clang', '-O2', '-msse2', '-mfpmath=sse', '-fno-builtin',
             '-fno-stack-protector', '-nostdlib', project / 'src/fex/guest_smoke.c',
             '-Wl,--entry,_probe_entry', '-Wl,--subsystem,console', '-Wl,--dynamicbase', '-Wl,--no-insert-timestamp',
             '-lkernel32', '-o', exe])
        report['guest_sha256'] = hashlib.sha256(exe.read_bytes()).hexdigest()
    (evidence / 'runtime-build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
