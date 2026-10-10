"""Build PES low-window in a fresh tree; never mutate a tested native build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from pes_low_window_patches import apply
from fextendo_low_window import ROOT


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, data): path.write_text(json.dumps(data, indent=2) + '\n')
def files(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', type=Path, default=Path('/home/blekjek/pes13-build/runtime-fixer'))
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--jobs', type=int, default=3)
    ap.add_argument('--revision', type=int, choices=(1, 2, 3, 4, 5, 6), default=1)
    ap.add_argument('--edition', choices=('experimental', 'patch'), default='experimental')
    ap.add_argument('--patch-catalog', type=Path,
                    help='Verified patch-only Runtime Fixer catalog; required by --edition patch')
    ap.add_argument('--patch-version', default='0.3.9-patch1')
    args = ap.parse_args()
    version = f'0.3.9-lw{args.revision}'
    if args.edition == 'patch':
        if args.revision < 6 or args.patch_catalog is None:
            ap.error('Patch edition requires --revision 6 and --patch-catalog; no original-runtime fallback')
        from pes_patch_identity import validate_catalog, profile
        validate_catalog(args.patch_catalog.read_bytes())
        version = args.patch_version
    assert not args.work.exists(), 'Use a fresh isolated build directory'
    receipt = json.loads((args.base / 'build-report.json').read_text())
    assert receipt['passed'] and receipt['app_version'] == '0.3.9-kit15'
    assert sha(args.base / 'pes13-fex.nro') == receipt['nro_sha256']
    for name, digest in receipt['generated_sources'].items():
        assert sha(args.base / 'native-source' / name) == digest, name
    for name, digest in receipt['feature_sources'].items():
        candidate = args.base / 'feature' / name
        if candidate.is_file(): assert sha(candidate) == digest, name
    for name, digest in receipt['native_fex_sources'].items():
        assert sha(args.base / 'feature/src/fex' / name) == digest, name
    args.work.mkdir(parents=True)
    source, feature = args.work / 'native-source', args.work / 'feature'
    shutil.copytree(args.base / 'native-source', source, symlinks=True)
    shutil.copytree(args.base / 'feature', feature, symlinks=True)
    before = files(source)
    old_feature = files(feature)
    # The remaining archived include paths are read-only inputs. Only move the
    # live compiled source/object paths into our isolated build.
    cmake = source / 'wine-nx-probe/CMakeLists.txt'
    text = cmake.read_text()
    for name in ('native-source', 'feature'):
        text = text.replace(str(args.base / name), str(args.work / name))
    cmake.write_text(text)
    apply(source, feature / 'src/runtime')
    if args.revision >= 2:
        from pes_low_window_pacing import apply as pacing
        pacing(source, feature / 'src/runtime')
    if args.revision >= 3:
        from pes_low_window_live import apply as live
        live(source, feature / 'src/runtime')
    if args.revision >= 4:
        from pes_low_window_kitcontrol import apply as kitcontrol
        kitcontrol(source, feature / 'src/runtime')
    if args.revision >= 5:
        from pes_low_window_assets import apply as assets
        assets(source, feature / 'src/runtime')
    if args.revision >= 6:
        from pes_low_window_settings import apply as settings
        settings(source, feature / 'src/runtime')
    identity = None
    if args.edition == 'patch':
        from pes_patch_identity import apply as patch_identity
        identity = patch_identity(source, feature / 'src/runtime', args.patch_catalog, version)
    after, new_feature = files(source), files(feature)
    write(args.work / 'prepared.json', {'baseline_receipt_sha256': sha(args.base / 'build-report.json'),
        'baseline_nro_sha256': receipt['nro_sha256'], 'before': before, 'after': after,
        'feature_before': old_feature, 'feature_after': new_feature})
    sdk, cache = Path('/opt/devkitpro'), Path('/home/blekjek/pes13-build')
    env = dict(os.environ, DEVKITPRO=str(sdk), DEVKITA64=str(sdk / 'devkitA64'),
               PATH=str(sdk / 'devkitA64/bin') + ':' + str(sdk / 'tools/bin') + ':' + os.environ['PATH'])
    def run(command):
        with (args.work / 'build.log').open('a') as log:
            result = subprocess.run(list(map(str, command)), env=env, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            print('\n'.join((args.work / 'build.log').read_text().splitlines()[-70:]), flush=True)
            result.check_returncode()
    build, project = args.work / 'native-build', source / 'wine-nx-probe'
    run(['cmake', '-S', project, '-B', build, '-G', 'Ninja',
         '-DCMAKE_TOOLCHAIN_FILE=' + str(project / 'cmake/switch-devkitA64.cmake'),
         '-DWINE_NX_PE_BUILD_DIR=' + str(cache / 'pe'), '-DWINE_NX_BOX64_DYNAREC=OFF',
         '-DWINE_NX_BOX64_INTERPRETER=OFF', '-DWINE_NX_STOCK_MESA=OFF',
         '-DWINE_NX_MESA_SWITCH_DIR=' + str(cache / 'mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib'),
         '-DPES13_FEX_DIR=' + str(feature / 'src/fex'),
         '-DPES13_LIBNX_EXCEPTION_OBJECT=' + str(cache / 'fex-experiment/wine3/libnx-exception.o'),
         '-DCMAKE_BUILD_TYPE=Release'])
    run(['cmake', '--build', build, '--target', 'wine-nx-runtime', '-j', args.jobs])
    nro_name = profile()['nro'] if args.edition == 'patch' else 'pes13-fex.nro'
    title = profile()['nro_title'] if args.edition == 'patch' else 'PES13 - FEXTendo Low Window'
    elf, nro, nacp = build / 'wine-nx-runtime.elf', args.work / nro_name, args.work / (Path(nro_name).stem + '.nacp')
    run([sdk / 'tools/bin/nacptool', '--create', title, 'AndroSwitch Project', version, nacp])
    run([sdk / 'tools/bin/elf2nro', elf, nro, '--nacp=' + str(nacp), '--icon=' + str(ROOT / 'assets/fextendo-v3/nro-icon.jpg')])
    for marker in (b'[PES13-LOWVA] v1', version.encode(), b'requires verified 39-bit low-window'):
        assert marker in nro.read_bytes(), marker
    assert after == files(source) and new_feature == files(feature)
    inputs = [Path(__file__).resolve(), ROOT/'tools/pes_low_window_patches.py',
              ROOT/'src/experimental/low_window/pes_low_window.c', ROOT/'src/experimental/low_window/pes_low_window.h']
    if args.revision >= 2:
        inputs += [ROOT/p for p in ('tools/pes_low_window_pacing.py', 'src/runtime/fextendo_presets.h',
                   'src/runtime/fextendo_launcher.h', 'src/runtime/pes_low_window_diagnostics.h')]
    if args.revision >= 3:
        inputs += [ROOT/p for p in ('tools/pes_low_window_live.py', 'src/runtime/pes_live_settings.h',
                                   'src/runtime/pes_vk_work.h')]
    if args.revision >= 4:
        inputs += [ROOT/p for p in ('tools/pes_low_window_kitcontrol.py','src/runtime/pes_gameplaytool_control.h')]
    if args.revision >= 5:
        inputs += [ROOT/p for p in ('tools/pes_low_window_assets.py','src/runtime/fextendo_wait_probe.h',
                                   'src/runtime/horizon_asset_probe.h')]
    if args.revision >= 6:
        inputs += [ROOT/p for p in ('tools/pes_low_window_settings.py','src/runtime/pes_settings_route.h')]
    if args.edition == 'patch':
        inputs += [ROOT/'tools/pes_patch_identity.py', ROOT/'release/patch/channel.json']
    write(args.work / 'build.json', {'built': True, 'hardware_tested': False, 'version': version,
        'edition': args.edition, 'identity': identity, 'nro_filename': nro_name,
        'abi': 'fxtmem-v1', 'nro_sha256': sha(nro), 'elf_sha256': sha(elf),
        'baseline_receipt_sha256': sha(args.base / 'build-report.json'),
        'source_changes': {n: h for n, h in after.items() if before.get(n) != h},
        'feature_changes': {n: h for n, h in new_feature.items() if old_feature.get(n) != h},
        'inputs': {p.relative_to(ROOT).as_posix(): sha(p) for p in inputs}})
    print(f'Built isolated PES low-window v{args.revision}: ' + sha(nro), flush=True)


if __name__ == '__main__': main()
