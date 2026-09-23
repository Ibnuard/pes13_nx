"""Check the actual linked PES13-NX build and its required startup/backend paths."""
import argparse
import hashlib
import json
import os
import struct
import subprocess
from pathlib import Path
from nro_assets import inspect_nro

project = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--build-root', type=Path, default=Path(os.environ.get('PES_BUILD_ROOT', Path.home() / '.cache/pes13-nx')))
a = p.parse_args()
root = a.build_root
source = root / 'runtime-pes13-source'
out = root / 'runtime-pes13'
elf = out / 'wine-nx-runtime.elf'
nro = out / 'pes13-nx.nro'
sdk = Path(os.environ.get('DEVKITPRO', '/opt/devkitpro'))
nm = str(sdk / 'devkitA64/bin/aarch64-none-elf-nm')
objdump = str(sdk / 'devkitA64/bin/aarch64-none-elf-objdump')
symbols = subprocess.check_output([nm, str(elf)], text=True)
names = {line.split()[-1] for line in symbols.splitlines() if line.split()}
registry = [name for name in names if name.startswith('horizon_server_handle_registry')]
assert registry, 'Missing registry dispatch'
disasm = {name: subprocess.check_output([objdump, '-d', '--disassemble=' + name, str(elf)], text=True)
          for name in ('__appInit', '__wrap_appletInitialize', 'main', *registry)}
blob = nro.read_bytes()
assets = inspect_nro(blob, (project / 'assets/icon.jpg').read_bytes())
runtime = (source / 'wine-nx-probe/source/runtime.c').read_text()
main_source = runtime[runtime.index('int main( int argc, char **argv )'):]
virtual = (source / 'dlls/ntdll/unix/virtual.c').read_text()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
checks = {
    'libnx_calls_va_guard': '<__wrap_appletInitialize>' in disasm['__appInit'],
    'guard_calls_original_init': '<appletInitialize>' in disasm['__wrap_appletInitialize'],
    'guard_reserves_image': '<virtmemAddReservation>' in disasm['__wrap_appletInitialize'],
    'guard_before_virtual_init': disasm['main'].index('<wine_nx_pes13_preload_report>') < disasm['main'].index('<virtual_init>'),
    'registry_dispatch': all('<' + name + '>:' in disasm[name] for name in registry),
    'registry_selector': 'wine_nx_pes13_registry_enabled' in names,
    'registry_before_bootstrap': runtime.index('wine_nx_pes13_registry_enabled =') < runtime.index('virtual_init();'),
    'heartbeat_during_stall': 'if (++calls % 2) return;' in runtime and 'last_reads' not in runtime,
    'nro_header': blob[16:20] == b'NRO0',
    'forwarder_icon_and_nacp': bool(assets['icon_bytes']) and assets['nacp_bytes'] == 0x4000,
    'custom_build': b'pes13-nx-0.2.0-vk1-production' in blob,
    'controller_check': b'PES13-NX - Controller Check' in blob,
    'controller_trace': 'wine_nx_pes13_input_trace' in names,
    'controller_keyboard_fallback': b'/controller-keyboard.txt' in blob,
    'controller_gamepad_only': b'/controller-gamepad.txt' in blob and
                               'wine_nx_pes13_gamepad_only' in names,
    'controller_defaults': 'PES13_KEY_DEFAULTS' in runtime,
    'production_log_cadence': b'/production.txt' in blob and
                              'wine_nx_production' in runtime and
                              'ticks % 25 == 0' in runtime,
    'handled_faults_not_logged': runtime.index('wine_nx_production =') > 0 and
        (source / 'dlls/ntdll/unix/horizon.c').read_text().index('status = virtual_handle_fault') <
        (source / 'dlls/ntdll/unix/horizon.c').read_text().index('[EXC] desc='),
    'new_runtime_sd_path': b'sdmc:/switch/pes13-nx/drive_c' in blob,
    'direct_pes_target': '#define DEFAULT_TARGET WINE_DRIVE_C "/PES13/pes2013.exe"' in runtime and
                         b'sdmc:/switch/pes13-nx/drive_c/PES13/pes2013.exe' in blob,
    # Legacy ARM64 log messages mention run-entry.txt; they do not read it.
    'autorun_without_sidecars': 'const int autorun = 1;' in main_source and
                               'read_bool_file( RUNTIME_DIR "/run-entry.txt" )' not in main_source,
    'no_target_override': 'argv[1]' not in main_source.replace('previously tested argv[1]', '') and 'target.txt' not in main_source,
    'no_sdl_launcher': 'wine_nx_launcher_run' not in names and 'wine_nx_launcher_run' not in main_source,
    'no_next_load': 'envSetNextLoad' not in names,
    'single_nro_boot_log': b'[PES13-BOOT] single NRO; launching %s' in blob,
    'no_secondary_nro_path': b'pes13-nx-runtime.nro' not in blob,
    'new_log_path': b'/pes13-nx.log' in blob,
    'no_old_sd_path': all(old not in blob for old in (b'/switch/wine/', b'switch\\wine\\')),
    'winevulkan_x86_registration': '{ "winevulkan.dll", wine_nx_winevulkan_wow64_unix_funcs, &wine_nx_winevulkan_wow64_unix_count }' in virtual,
    'va_guard_unchanged': sha(project / 'src/runtime/pes13_preload.c') == '6bb8ecff9fea7e0e2b1e10a4a04b36705155b159d4584088257294a5b192f225',
}
for key, literal in {
    'installation_metadata': b'[PES13-REG] pes13-install.reg loaded',
    'installation_path': b'[PES13-REG] installdir=',
    'preload_exclusion': b'400000-1c9a000',
    'dxvk_selection': b'[PES13-GFX] DXVK Vulkan; WineD3D CSMT override inactive',
    'nvk_backend': b'Vulkan through NVK',
    'vulkan_window': b'a Vulkan surface has the screen',
}.items(): checks[key] = literal in blob
for name in ('vkGetInstanceProcAddr', 'vkCreateViSurfaceNN', 'wine_nx_vulkan_probe',
             'wine_nx_winevulkan_wow64_unix_count', 'wine_nx_winevulkan_wow64_unix_funcs'):
    checks['linked_' + name] = name in names
for helper_name, relative in (
    ('pes13_preload.c', 'wine-nx-probe/source/pes13_preload.c'),
    ('pes13_graphics.h', 'wine-nx-probe/source/pes13_graphics.h'),
    ('pes13_controller.h', 'wine-nx-probe/source/pes13_controller.h'),
    ('pes13_controller_ui.h', 'wine-nx-probe/source/pes13_controller_ui.h'),
    ('pes13_registry.h', 'dlls/ntdll/unix/pes13_registry.h')):
    checks['source_matches_' + helper_name] = sha(project / 'src/runtime' / helper_name) == sha(source / relative)
header = elf.read_bytes()[:64]
checks['elf_aarch64'] = header[:5] == b'\x7fELF\x02' and struct.unpack_from('<H', header, 18)[0] == 183
manifest = json.loads((project / 'dependencies.json').read_text())
mesa_revision = subprocess.check_output(['git', '-C', str(root / 'mesa-switch'), 'rev-parse', 'HEAD'], text=True).strip()
checks['mesa_revision'] = mesa_revision == manifest['mesa_switch']['commit']
report = {'checks': checks, 'assets': assets, 'nro': nro.name, 'nro_sha256': sha(nro),
          'elf_sha256': sha(elf), 'mesa_commit': mesa_revision, 'hardware_tested_single_nro': False}
dest = project / 'local/reports/verification.json'
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
if not all(checks.values()):
    raise SystemExit('Runtime verification failed')
