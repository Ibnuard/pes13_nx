"""Build the controller preview from frozen production v1 + launch fix.

Requires that verified baseline locally. Does not regenerate FEX/Wine through
the current experiment patch set and never updates the approved CI runtime.
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

from fextendo_gamepad_patches import apply
from nro_assets import inspect_nro

ROOT = Path(__file__).resolve().parents[1]
BASE_NRO = 'fd0e0dbb047289421d3d8a03e05d04cfcfda1e38999cbcbb1e90e7332434d463'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=ROOT/'local/fex3/production-v1-launchfix')
    parser.add_argument('--output', type=Path, default=ROOT/'local/fex3/gamepads-v2')
    parser.add_argument('--build-root', type=Path, default=Path.home()/'.cache/pes13-nx-macos')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    base, work, cache = args.base.resolve(), args.output.resolve(), args.build_root.resolve()
    feature_paths = [ROOT/'tools/build-fextendo-gamepads.py',ROOT/'tools/fextendo_gamepad_patches.py',
                     *(ROOT/'src/runtime'/n for n in ('fextendo_gamepad.h','fextendo_gamepad_ui.h',
                        'fextendo_gamepad_switch.h','fextendo_ui.h','fextendo_launcher.h','fextendo_presets.h'))]
    feature_hashes = {str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in feature_paths}
    old = json.loads((base/'runtime/runtime-build.json').read_text())
    assert old['nro_sha256'] == BASE_NRO
    assert sha((base/'runtime/payload/pes13-fex.nro').read_bytes()) == BASE_NRO
    baseline_project = base/'project'
    for name, digest in old['patch_sources'].items():
        assert sha((baseline_project/name).read_bytes()) == digest, name
    for name, digest in old['adapter_sources'].items():
        assert sha((baseline_project/'src/fex'/name).read_bytes()) == digest, name
    manifest = json.loads((base/'runtime/wine-patches.json').read_text())['native-source']
    source = work/'native-source'
    work.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        # APFS clone avoids duplicating the large, unmodified Wine source tree.
        subprocess.run(['cp', '-cR', str(Path(old['native_source']).parent), str(source)], check=True)
    before = {}
    for name, digest in manifest.items():
        data = (baseline_project/'generated/wine/native-source'/name).read_bytes()
        assert sha(data) == digest, name
        before[name] = data.decode()
        (source/name).write_bytes(data)
    original_files = json.loads((Path(old['native_source']).parent.parent/'native-source.json').read_text())['files']
    # XInput was untouched by production v1 and therefore absent from its patch
    # manifest. Restore it explicitly, then verify every other original source.
    xinput = 'wine-nx-probe/source/xinput_unix.c'
    data = (Path(old['native_source']).parent/xinput).read_bytes()
    assert sha(data) == original_files[xinput]
    (source/xinput).write_bytes(data)
    for name, digest in original_files.items():
        if name not in manifest:
            assert sha((source/name).read_bytes()) == digest, name
    changed = {}
    def read(name):
        if name not in before:
            # Unpatched Wine inputs (not in the generated manifest), notably
            # XInput, must come from the baseline tree on every incremental build.
            before[name] = (Path(old['native_source']).parent/name).read_text()
        return changed.get(name, before[name])
    def replace(name, old_text, new_text):
        data = read(name)
        if data.count(old_text) != 1:
            raise ValueError(f'{name}: expected one patch anchor, found {data.count(old_text)}')
        changed[name] = data.replace(old_text, new_text)
    runtime = 'wine-nx-probe/source/runtime.c'
    for name in ('fextendo_presets.h', 'fextendo_ui.h', 'fextendo_launcher.h'):
        archived = (baseline_project/'src/runtime'/name).read_text()
        new = (ROOT/'src/runtime'/name).read_text()
        # This exact diagnostic wording was the silent production transformation.
        for_old = 'Check fex-runtime.log, then close and relaunch.'
        for_new = 'Check the game and runtime files, then close and relaunch.'
        archived = archived.replace(for_old, for_new)
        new = new.replace(for_old, for_new)
        if name == 'fextendo_launcher.h':
            new = (ROOT/'src/runtime/fextendo_gamepad_switch.h').read_text()+'\n'+new
        replace(runtime, archived, new)
    feature = work/'feature'
    (feature/'src/runtime').mkdir(parents=True, exist_ok=True)
    for name in ('fextendo_gamepad.h','fextendo_gamepad_ui.h'):
        shutil.copy2(ROOT/'src/runtime'/name, feature/'src/runtime'/name)
    apply(read, replace, feature)
    assert set(changed) == {runtime,'wine-nx-probe/source/xinput_unix.c','dlls/win32u/vulkan.c','wine-nx-probe/CMakeLists.txt'}
    diff = []
    for name, data in changed.items():
        (source/name).write_text(data)
        diff += difflib.unified_diff(before[name].splitlines(True), data.splitlines(True),
                                    fromfile='production-v1-launchfix/'+name, tofile='gamepads/'+name)
    (work/'generated-controller-changes.patch').write_text(''.join(diff))
    spec = importlib.util.spec_from_file_location('runtime_builder', ROOT/'tools/build-fex-runtime.py')
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sdk = Path('/opt/devkitpro');mesa = cache/'mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib'
    assert module.native_dependency_receipt(mesa,sdk) == old['native_dependencies']
    env = dict(os.environ,DEVKITPRO=str(sdk),DEVKITA64=str(sdk/'devkitA64'),
               PATH=str(sdk/'devkitA64/bin')+':'+str(sdk/'tools/bin')+':'+os.environ['PATH'])
    build=work/'native-build';project=source/'wine-nx-probe'
    exception=work/'libnx-exception.o'
    shutil.copy2(Path(old['native_source']).parent.parent/'libnx-exception.o',exception)
    def run(command):
        with (work/'build.log').open('a') as log:
            result=subprocess.run(list(map(str,command)),env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:
            print('\n'.join((work/'build.log').read_text().splitlines()[-70:]),flush=True)
            result.check_returncode()
    run(['cmake','-S',project,'-B',build,'-G','Ninja',
         '-DCMAKE_TOOLCHAIN_FILE='+str(project/'cmake/switch-devkitA64.cmake'),
         '-DWINE_NX_PE_BUILD_DIR='+str(cache/'pe'),'-DWINE_NX_BOX64_DYNAREC=OFF',
         '-DWINE_NX_BOX64_INTERPRETER=OFF','-DWINE_NX_STOCK_MESA=OFF',
         '-DWINE_NX_MESA_SWITCH_DIR='+str(mesa),'-DPES13_FEX_DIR='+str(baseline_project/'src/fex'),
         '-DPES13_LIBNX_EXCEPTION_OBJECT='+str(exception),'-DCMAKE_BUILD_TYPE=Release'])
    run(['cmake','--build',build,'--target','wine-nx-runtime','-j',args.jobs])
    nro,nacp=work/'pes13-fex.nro',work/'pes13-fex.nacp'
    icon=baseline_project/'assets/fextendo-v3/nro-icon.jpg'
    run([sdk/'tools/bin/nacptool','--create','PES13 - FEXTendo','AndroSwitch Project','0.3.7',nacp])
    run([sdk/'tools/bin/elf2nro',build/'wine-nx-runtime.elf',nro,'--nacp='+str(nacp),'--icon='+str(icon)])
    assert module.native_dependency_receipt(mesa,sdk) == old['native_dependencies']
    assert feature_hashes == {str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in feature_paths}, 'Feature sources changed during build'
    report={'passed':True,'hardware_tested':False,'baseline_nro_sha256':BASE_NRO,
            'nro_sha256':sha(nro.read_bytes()),'native_elf_sha256':sha((build/'wine-nx-runtime.elf').read_bytes()),
            'adapters':old['adapter_sources'],'native_dependencies':old['native_dependencies'],
            'generated_delta':sorted(changed),'generated_sources':{k:sha(v.encode()) for k,v in changed.items()},
            'feature_sources':feature_hashes,
            'metadata':inspect_nro(nro.read_bytes(),icon.read_bytes(),expected_title='PES13 - FEXTendo',expected_version='0.3.7')}
    (work/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k in ('passed','hardware_tested','nro_sha256','generated_delta')},indent=2))

if __name__=='__main__':main()
