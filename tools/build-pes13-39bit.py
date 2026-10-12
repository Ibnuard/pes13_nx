"""Build the original main/r6 runtime with fxtmem-v1 and Player 1 OSK.

The immutable production NRO must match main's lock. No Kitserver source or
gameplay patches are imported. Build in a new directory; keep baseline intact.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from fextendo_low_window import ROOT
from pes_low_window_patches import apply, exact

VERSION = '0.4.2'
BUILD_REVISION = 'fastest-default'
NRO = 'pes13-fex.nro'
FEATURES = ('fextendo_keyboard_switch.h', 'fextendo_keyboard_wine.h',
            'fextendo_keyboard_options.h','fextendo_presets.h',
            'fextendo_osk.h', 'fextendo_osk_switch.h', 'fextendo_osk_display.h',
            'fextendo_osk_ui.h', 'fextendo_osk_frame.h', 'fextendo_osk_vulkan.h',
            'fextendo_keyboard_capture.h', 'fextendo_settings.h')


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
def write(p, data): p.write_text(json.dumps(data, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, default=Path('/home/blekjek/pes13-build/production-input-fix'))
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--cache', type=Path, default=Path('/home/blekjek/pes13-build'))
    p.add_argument('--jobs', type=int, default=4)
    a = p.parse_args()
    assert not a.work.exists(), 'Use a fresh isolated build directory'
    receipt = json.loads((a.base/'build-report.json').read_text())
    lock = json.loads((ROOT/'release/runtime-lock.json').read_text())
    approved = lock['binaries']['switch/pes13-fex/pes13-fex.nro']
    assert lock['runtime_version'] == '0.3.8-r6' and receipt['passed']
    assert sha(a.base/'pes13-fex.nro') == receipt['nro_sha256'] == approved
    assert sha(a.base/'native-build/wine-nx-runtime.elf') == receipt['native_elf_sha256']
    for n, h in receipt['generated_sources'].items():
        assert sha(a.base/'native-source'/n) == h, n
    for n, h in receipt['feature_sources'].items():
        candidate = a.base/'feature'/n
        if candidate.exists(): assert sha(candidate) == h, n
    for n, h in receipt['native_fex_sources'].items():
        assert sha(a.base/'feature/src/fex'/n) == h, n
    a.work.mkdir(parents=True)
    source, feature = a.work/'native-source', a.work/'feature'
    shutil.copytree(a.base/'native-source', source, symlinks=True)
    shutil.copytree(a.base/'feature', feature, symlinks=True)
    before, old_feature = inventory(source), inventory(feature)
    cmake = source/'wine-nx-probe/CMakeLists.txt'
    text = cmake.read_text()
    for name in ('native-source', 'feature'):
        text = text.replace(str(a.base/name), str(a.work/name))
    cmake.write_text(text)
    for name in FEATURES:
        shutil.copy2(ROOT/'src/runtime'/name, feature/'src/runtime'/name)
    from fextendo_startup_patches import apply as startup_apply
    startup_apply(source,feature/'src/runtime')
    from fextendo_osk_patches import apply as osk_apply
    osk_apply(source)
    from fextendo_startup_patches import FILES
    inputs=[
        'tools/build-pes13-39bit.py','tools/pes_low_window_patches.py','tools/fextendo_commit_patches.py','tools/fextendo_osk_patches.py',
        'src/runtime/horizon_commit.h','src/runtime/horizon_memory_failure.h','tools/fextendo_startup_patches.py',
        'src/runtime/fextendo_ui.h','src/runtime/fextendo_launcher.h',
        'tools/fextendo_startup_assets.py','assets/startup/font.dat','assets/startup/wordmark.rgba',
        *['src/runtime/'+n for n in FILES],
        'src/experimental/low_window/pes_low_window.c','src/experimental/low_window/pes_low_window.h',
        *['src/runtime/'+n for n in FEATURES]]
    input_hashes={n:sha(ROOT/n) for n in inputs}
    apply(source, feature/'src/runtime', base_version=VERSION, version=VERSION)
    # r6 removed the middle reservation before backing/map success. Under an
    # allocation failure it left an unusable hole. Keep guest ownership intact
    # throughout this native-memory transaction, including retry/rollback.
    from fextendo_commit_patches import apply as atomic_commit
    atomic_commit(source, ROOT)
    runtime = source/'wine-nx-probe/source/runtime.c'
    text = runtime.read_text()
    text = exact(text, '[STARTUP] FEXTendo 0.3.8-r6 /', '[STARTUP] FEXTendo '+VERSION+' '+BUILD_REVISION+' /')
    # Use Fastest for an absent setting too. Explicit configuration.ini = 0
    # remains a supported opt-out; graphics quality and OC do not select this.
    text = exact(text, 'wine_nx_config_file_bool(RUNTIME_DIR "/fex-fastest.txt", 0)',
                       'wine_nx_config_file_bool(RUNTIME_DIR "/fex-fastest.txt", 1)')
    runtime.write_text(text)
    after, new_feature = inventory(source), inventory(feature)
    write(a.work/'prepared.json', {'baseline_receipt_sha256': sha(a.base/'build-report.json'),
        'baseline_nro_sha256': approved, 'before': before, 'after': after,
        'feature_before': old_feature, 'feature_after': new_feature})
    sdk = Path('/opt/devkitpro')
    env = dict(os.environ, DEVKITPRO=str(sdk), DEVKITA64=str(sdk/'devkitA64'),
        PATH=str(sdk/'devkitA64/bin')+':'+str(sdk/'tools/bin')+':'+os.environ['PATH'])
    def run(cmd):
        with (a.work/'build.log').open('a') as f:
            result = subprocess.run(list(map(str, cmd)), env=env, stdout=f, stderr=subprocess.STDOUT)
        if result.returncode:
            print('\n'.join((a.work/'build.log').read_text().splitlines()[-60:]), flush=True)
            result.check_returncode()
    build, project = a.work/'native-build', source/'wine-nx-probe'
    run(['cmake','-S',project,'-B',build,'-G','Ninja',
        '-DCMAKE_TOOLCHAIN_FILE='+str(project/'cmake/switch-devkitA64.cmake'),
        '-DWINE_NX_PE_BUILD_DIR='+str(a.cache/'pe'), '-DWINE_NX_BOX64_DYNAREC=OFF',
        '-DWINE_NX_BOX64_INTERPRETER=OFF','-DWINE_NX_STOCK_MESA=OFF',
        '-DWINE_NX_MESA_SWITCH_DIR='+str(a.cache/'mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib'),
        '-DPES13_FEX_DIR='+str(feature/'src/fex'),
        '-DPES13_LIBNX_EXCEPTION_OBJECT='+str(a.cache/'fex-experiment/wine3/libnx-exception.o'),
        '-DCMAKE_BUILD_TYPE=Release'])
    run(['cmake','--build',build,'--target','wine-nx-runtime','-j',a.jobs])
    elf, nro, nacp = build/'wine-nx-runtime.elf', a.work/NRO, a.work/'pes13-fex.nacp'
    run([sdk/'tools/bin/nacptool','--create','PES13-FEXTendo','AndroSwitch Project',VERSION,nacp])
    run([sdk/'tools/bin/elf2nro',elf,nro,'--nacp='+str(nacp),
        '--icon='+str(a.base/'approved/source/assets/fextendo-v3/nro-icon.jpg')])
    for marker in (b'[PES13-LOWVA] v1',VERSION.encode(),b'Checking your installation before you play.',b'High requires an active FEXTendo Patch'):
        assert marker in nro.read_bytes(), marker
    for marker in (b'[ALLOC32]',b'[ASSET-OPEN]',b'[ASSET-READ]',b'[ASSET-FD]',b'[ASSET-VERIFY]'):
        assert marker not in nro.read_bytes(), 'Retired asset diagnostic: '+str(marker)
    assert not any(n.startswith('src/fex/') and old_feature.get(n)!=h for n,h in new_feature.items())
    assert inventory(source) == after and inventory(feature) == new_feature
    assert input_hashes=={n:sha(ROOT/n) for n in inputs},'Source changed during build; use a fresh build'
    write(a.work/'build.json', {'built':True,'hardware_tested':False,'version':VERSION,'build_revision':BUILD_REVISION,
        'edition':'original-39bit','abi':'fxtmem-v1','nro_filename':NRO,
        'nro_sha256':sha(nro),'elf_sha256':sha(elf),'baseline_nro_sha256':approved,
        'baseline_receipt_sha256':sha(a.base/'build-report.json'),
        'source_changes':{n:h for n,h in after.items() if before.get(n)!=h},
        'feature_changes':{n:h for n,h in new_feature.items() if old_feature.get(n)!=h},
        'input_sources':input_hashes})
    print('Built main/r6 original 39-bit runtime: '+sha(nro),flush=True)


if __name__ == '__main__': main()
