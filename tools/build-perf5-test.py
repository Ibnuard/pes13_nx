"""Build an isolated Box64 -O2 experiment with the PERF3 Compatible profile."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile

project = Path(__file__).resolve().parents[1]
root = Path(os.environ.get('PES_BUILD_ROOT', str(Path.home() / '.cache/pes13-nx')))
source = root / 'runtime-pes13-source/wine-nx-probe'
cmake_source = source / 'cmake/Box64Core.cmake'
runtime_source = source / 'source/runtime.c'
build = root / 'runtime-perf5-o2'
mesa = root / 'mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib'
sdk = Path('/opt/devkitpro')
perf3 = project / 'dist/perf3/switch/pes13-nx'
dest = project / 'dist/perf5/switch/pes13-nx'


def replace_once(value, old, new):
    if value.count(old) != 1:
        raise ValueError(f'Expected one occurrence of {old!r}, found {value.count(old)}')
    return value.replace(old, new)


original_cmake = cmake_source.read_bytes()
original_runtime = runtime_source.read_bytes()
cmake_text = replace_once(original_cmake.decode(),
                          'set(private_options -O1 -ffunction-sections',
                          'set(private_options -O2 -ffunction-sections')
runtime_text = replace_once(original_runtime.decode(),
                            'pes13-nx-0.2.0-vk1-production',
                            'pes13-nx-0.2.0-perf5-box64-o2')
runtime_text = replace_once(runtime_text, 'static const char runtime_environment[] =\n',
                            'static const char runtime_environment[] =\n'
                            '    "DXVK_SHADER_CACHE_PATH=C:\\\\dxvk-cache\\0"\n')
runtime_text = replace_once(runtime_text, '    mkdir( WINE_DRIVE_C, 0777 );',
                            '    mkdir( WINE_DRIVE_C, 0777 );\n'
                            '    mkdir( WINE_DRIVE_C "/dxvk-cache", 0777 );')
anchor = '        unsigned long long read_ms = &wine_nx_file_read_100ns'
metric = '''        {
            static u64 last_tick;
            static unsigned int last_presents;
            unsigned int presents = &wine_nx_vk_presents ? __atomic_load_n(&wine_nx_vk_presents, __ATOMIC_RELAXED) : 0;
            if (last_tick && now > last_tick)
            {
                unsigned long long ms = armTicksToNs(now - last_tick) / 1000000;
                log_line("[PERF5] vk_present_delta=%u interval_ms=%llu", presents - last_presents, ms);
            }
            last_tick = now;
            last_presents = presents;
        }
'''
runtime_text = replace_once(runtime_text, anchor, metric + anchor)

env = dict(os.environ, DEVKITPRO=str(sdk), DEVKITA64=str(sdk / 'devkitA64'))
env['PATH'] = f'{sdk}/devkitA64/bin:{sdk}/tools/bin:' + env['PATH']
build.mkdir(parents=True, exist_ok=True)
dest.mkdir(parents=True, exist_ok=True)

try:
    cmake_source.write_text(cmake_text)
    runtime_source.write_text(runtime_text)
    subprocess.run([
        'cmake', '-S', str(source), '-B', str(build), '-G', 'Ninja',
        f'-DCMAKE_TOOLCHAIN_FILE={source}/cmake/switch-devkitA64.cmake',
        f'-DWINE_NX_PE_BUILD_DIR={root}/pe',
        '-DWINE_NX_BOX64_DYNAREC=ON', '-DWINE_NX_STOCK_MESA=OFF',
        f'-DWINE_NX_MESA_SWITCH_DIR={mesa}', '-DCMAKE_BUILD_TYPE=Release',
    ], env=env, check=True)
    command = subprocess.check_output(['ninja', '-C', str(build), '-t', 'commands'], env=env, text=True)
    box64_commands = [line for line in command.splitlines() if 'wine-nx-box64-core-pass0' in line and ' -c ' in line]
    if not box64_commands or not all(' -O3 ' in line and ' -O2 ' in line and ' -O1 ' not in line for line in box64_commands):
        raise RuntimeError('Box64 pass objects are not compiled with final -O2')
    subprocess.run(['cmake', '--build', str(build), '--target', 'wine-nx-runtime', '-j4'], env=env, check=True)
    with tempfile.TemporaryDirectory(prefix='pes13-perf5-nacp-', dir=root) as tmp:
        nacp = Path(tmp) / 'perf5.nacp'
        subprocess.run([str(sdk / 'tools/bin/nacptool'), '--create',
                        'PES13-NX PERF5', 'PES13-NX', '0.2.0', str(nacp)], check=True)
        nro = dest / 'pes13-nx.nro'
        subprocess.run([str(sdk / 'tools/bin/elf2nro'), str(build / 'wine-nx-runtime.elf'),
                        str(nro), f'--nacp={nacp}', f'--icon={project}/assets/icon.jpg'], check=True)
finally:
    cmake_source.write_bytes(original_cmake)
    runtime_source.write_bytes(original_runtime)

assert cmake_source.read_bytes() == original_cmake
assert runtime_source.read_bytes() == original_runtime

# PERF3's fast-suspend PE and all seven Box64 compatibility values are unchanged.
for rel in ('drive_c/PES13/pes2013.box64.txt', 'drive_c/windows/system32/ntdll.dll'):
    source_file = perf3 / rel
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, target)
    assert target.read_bytes() == source_file.read_bytes()
for name in ('production.txt', 'controller-gamepad.txt', 'controller-keyboard.txt',
             'controller-trace.txt', 'vulkan-probe.txt'):
    shutil.copy2(project / 'config' / name, dest / name)

archive = project / 'dist/pes13-perf5-overlay.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for path in sorted(dest.rglob('*')):
        if path.is_file():
            z.write(path, path.relative_to(project / 'dist/perf5'))
    z.write(project / 'docs/PERF5.md', 'PERF5.md')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None

nro_blob = (dest / 'pes13-nx.nro').read_bytes()
assert nro_blob[16:20] == b'NRO0'
assert b'pes13-nx-0.2.0-perf5-box64-o2' in nro_blob
assert b'DXVK_SHADER_CACHE_PATH=C:' in nro_blob
print(json.dumps({
    'nro_sha256': hashlib.sha256(nro_blob).hexdigest(),
    'zip': str(archive),
    'zip_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'perf3_compat_profile_unchanged': True,
    'perf3_ntdll_unchanged': True,
    'hardware_tested': False,
}, indent=2))
