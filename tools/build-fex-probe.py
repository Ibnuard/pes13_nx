"""Test the FEX dual-mapping adapter on the host, then build a standalone Switch probe."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-root', type=Path, default=Path(os.environ.get('PES_BUILD_ROOT', Path.home() / '.cache/pes13-nx')))
    parser.add_argument('--host-only', action='store_true')
    args = parser.parse_args()
    root = args.build_root.resolve()
    fex = root / 'fex-experiment/source-horizon'
    if 'PES13FexWriteAlias' not in (fex / 'CodeEmitter/CodeEmitter/Buffer.h').read_text():
        raise SystemExit('Build the --horizon FEX module first; probe must use its patched emitter.')
    out = root / 'fex-experiment/probe'
    out.mkdir(parents=True, exist_ok=True)
    evidence = project / 'local/fex1/probe'
    evidence.mkdir(parents=True, exist_ok=True)
    includes = ['-I' + str(project / 'src/fex'), '-I' + str(fex / 'CodeEmitter'),
                '-I' + str(fex / 'FEXCore/include'), '-I' + str(fex / 'FEXHeaderUtils'),
                '-I' + str(fex / 'External/fmt/include')]

    def run(argv, **kw):
        print('+', ' '.join(map(str, argv)), flush=True)
        return subprocess.run(list(map(str, argv)), check=True, **kw)

    sanitize = ['-g', '-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', *sanitize, *includes, '-c',
         project / 'src/fex/horizon_jit.c', '-o', out / 'host-jit.o'])
    run(['g++', '-std=c++20', '-Wall', '-Wextra', *sanitize, *includes,
         '-DPES13_FEX_FULL_EMITTER=1', '-DARCHITECTURE_x86_64=1',
         project / 'tests/fex_jit.cpp', project / 'src/fex/module_host.cpp',
         out / 'host-jit.o', '-pthread', '-o', out / 'host-tests'])
    result = run([out / 'host-tests'], capture_output=True, text=True)
    print(result.stdout)
    (evidence / 'host-tests.txt').write_text(result.stdout + result.stderr)
    report = {'host_alias_tests_passed': True, 'asan_ubsan': True,
              'fex_guest_execution_tested': False, 'hardware_tested': False}
    if not args.host_only:
        devkit = Path(os.environ.get('DEVKITPRO', '/opt/devkitpro'))
        env = dict(os.environ, DEVKITPRO=str(devkit))
        cc = devkit / 'devkitA64/bin/aarch64-none-elf-gcc'
        cxx = devkit / 'devkitA64/bin/aarch64-none-elf-g++'
        common = ['-O2', '-g', '-march=armv8-a+crc', '-mtune=cortex-a57', '-ffixed-x18',
                  '-fPIE', '-ffunction-sections', '-fdata-sections', '-D__SWITCH__',
                  '-isystem', str(devkit / 'libnx/include'), *includes]
        objects = []
        for name in ('src/fex/horizon_jit.c', 'src/fex/probe_main.c',
                     'src/fex/module_host.cpp', 'tests/fex_jit.cpp'):
            file = project / name
            obj = out / (file.stem + '.o')
            run([cxx if file.suffix == '.cpp' else cc, *common,
                 '-std=c++20' if file.suffix == '.cpp' else '-std=gnu11',
                 '-Wall', '-Wextra', '-c', file, '-o', obj], env=env)
            objects.append(obj)
        elf = out / 'pes13-fex-jit-probe.elf'
        run([cxx, *common, '-specs=' + str(devkit / 'libnx/switch.specs'),
             *objects, '-L' + str(devkit / 'libnx/lib'), '-lnx', '-o', elf], env=env)
        nacp = out / 'pes13-fex-jit-probe.nacp'
        nro = out / 'pes13-fex-jit-probe.nro'
        run([devkit / 'tools/bin/nacptool', '--create', 'PES13 FEX JIT Probe',
             'PES13-NX / FEX-Emu', '0.1.0', nacp], env=env)
        run([devkit / 'tools/bin/elf2nro', elf, nro, '--nacp=' + str(nacp),
             '--icon=' + str(project / 'assets/icon.jpg')], env=env)
        run([sys.executable, project / 'tools/nro_assets.py', nro, '--icon', project / 'assets/icon.jpg',
             '--title', 'PES13 FEX JIT Probe', '--version', '0.1.0'])
        package = project / 'dist/pes13-fex1-jit-probe'
        sd = package / 'switch/pes13-fex-probe'
        sd.mkdir(parents=True, exist_ok=True)
        shutil.copy2(nro, sd / nro.name)
        (package / 'README.txt').write_text(
            'FEX1 Horizon JIT probe — not a PES runtime replacement.\n'
            'Copy switch/ to the SD card; open pes13-fex-jit-probe.nro.\n'
            'Use full application mode with the same 32-bit/no-alias/4-core settings\n'
            'as PES13 if creating a separate Sphaira forwarder.\n'
            'Wait for PASS/FAIL; press + to exit. Return jit-probe.log from\n'
            'switch/pes13-fex-probe/. No game files or settings are touched.\n'
            'This tests FEX emitter writes, generated ARM64 execution, backpatch\n'
            'cache visibility, mapping bounds, allocation exhaustion/reuse.\n'
            'It does not yet execute an x86 guest through FEXCore.\n', encoding='utf-8')
        licenses = package / 'licenses'
        licenses.mkdir(exist_ok=True)
        shutil.copy2(fex / 'LICENSE', licenses / 'FEX-MIT.txt')
        shutil.copy2(project / 'src/fex/LICENSE', licenses / 'PES13-adapter-MIT.txt')
        shutil.copy2(project / 'src/fex/libnx-LICENSE', licenses / 'libnx-ISC.txt')
        archive = project / 'dist/pes13-fex1-jit-probe.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for file in sorted(package.rglob('*')):
                if file.is_file(): z.write(file, file.relative_to(package))
        report.update(nro_sha256=hashlib.sha256(nro.read_bytes()).hexdigest(),
                      nro_bytes=nro.stat().st_size, package=str(archive),
                      zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    (evidence / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
