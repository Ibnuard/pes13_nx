"""Build PERF4 using the validated PERF3 ntdll and a faster Box64 profile."""
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
src = root / 'runtime-pes13-source'
out = root / 'runtime-pes13'
dest = project / 'dist/perf4/switch/pes13-nx'
perf3 = project / 'dist/perf3/switch/pes13-nx'
runtime = src / 'wine-nx-probe/source/runtime.c'
sdk = Path('/opt/devkitpro')


def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


original_runtime = runtime.read_text()
text = replace(original_runtime, 'pes13-nx-0.2.0-vk1-production', 'pes13-nx-0.2.0-perf4-balanced')
text = replace(text, 'static const char runtime_environment[] =\n',
               'static const char runtime_environment[] =\n    "DXVK_SHADER_CACHE_PATH=C:\\\\dxvk-cache\\0"\n')
text = replace(text, '    mkdir( WINE_DRIVE_C, 0777 );',
               '    mkdir( WINE_DRIVE_C, 0777 );\n    mkdir( WINE_DRIVE_C "/dxvk-cache", 0777 );')
anchor = '        unsigned long long read_ms = &wine_nx_file_read_100ns'
metric = '''        {
            static u64 last_tick;
            static unsigned int last_presents;
            unsigned int presents = &wine_nx_vk_presents ? __atomic_load_n(&wine_nx_vk_presents, __ATOMIC_RELAXED) : 0;
            if (last_tick && now > last_tick)
            {
                unsigned long long ms = armTicksToNs(now - last_tick) / 1000000;
                log_line("[PERF4] vk_present_delta=%u interval_ms=%llu", presents - last_presents, ms);
            }
            last_tick = now;
            last_presents = presents;
        }
'''
text = replace(text, anchor, metric + anchor)

dest.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, DEVKITPRO=str(sdk), DEVKITA64=str(sdk / 'devkitA64'))
env['PATH'] = f'{sdk}/devkitA64/bin:{sdk}/tools/bin:' + env['PATH']
protected = [runtime, out / 'wine-nx-runtime.elf', out / 'wine-nx-runtime.nro']
with tempfile.TemporaryDirectory(prefix='pes13-perf4-', dir=root) as tmp:
    saved = []
    for i, path in enumerate(protected):
        if path.exists():
            backup = Path(tmp) / str(i)
            shutil.copy2(path, backup)
            saved.append((path, backup))
    try:
        runtime.write_text(text)
        subprocess.run(['cmake', '--build', str(out), '--target', 'wine-nx-runtime', '-j4'], env=env, check=True)
        nacp = Path(tmp) / 'perf.nacp'
        subprocess.run([str(sdk / 'tools/bin/nacptool'), '--create', 'PES13-NX PERF4', 'PES13-NX', '0.2.0', str(nacp)], check=True)
        nro = dest / 'pes13-nx.nro'
        subprocess.run([str(sdk / 'tools/bin/elf2nro'), str(out / 'wine-nx-runtime.elf'), str(nro),
                        f'--nacp={nacp}', f'--icon={project}/assets/icon.jpg'], check=True)
    finally:
        for path, backup in saved:
            shutil.copy2(backup, path)
        runtime.touch()
    for path, backup in saved:
        assert path.read_bytes() == backup.read_bytes()

profile = (project / 'config/drive_c/PES13/pes2013.box64.txt').read_text()
for old, new in (
    ('BOX64_DYNAREC_SAFEFLAGS=2', 'BOX64_DYNAREC_SAFEFLAGS=1'),
    ('BOX64_DYNAREC_FASTNAN=0', 'BOX64_DYNAREC_FASTNAN=1'),
    ('BOX64_DYNAREC_FASTROUND=0', 'BOX64_DYNAREC_FASTROUND=1'),
    ('BOX64_DYNAREC_BIGBLOCK=0', 'BOX64_DYNAREC_BIGBLOCK=1'),
    ('BOX64_DYNAREC_STRONGMEM=1', 'BOX64_DYNAREC_STRONGMEM=0'),
):
    profile = replace(profile, old, new)
profile_path = dest / 'drive_c/PES13/pes2013.box64.txt'
profile_path.parent.mkdir(parents=True, exist_ok=True)
profile_path.write_text(profile)

perf3_ntdll = perf3 / 'drive_c/windows/system32/ntdll.dll'
assert perf3_ntdll.exists() and b'pes13-nx-perf3-fast-suspend' in perf3_ntdll.read_bytes()
target_ntdll = dest / 'drive_c/windows/system32/ntdll.dll'
target_ntdll.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(perf3_ntdll, target_ntdll)
for name in ('production.txt', 'controller-gamepad.txt', 'controller-keyboard.txt', 'controller-trace.txt', 'vulkan-probe.txt'):
    shutil.copy2(project / 'config' / name, dest / name)

archive = project / 'dist/pes13-perf4-overlay.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for path in sorted(dest.rglob('*')):
        if path.is_file():
            z.write(path, path.relative_to(project / 'dist/perf4'))
    z.write(project / 'docs/PERF4.md', 'PERF4.md')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None

rollback = project / 'dist/pes13-perf4-rollback-to-perf3.zip'
with zipfile.ZipFile(rollback, 'w', zipfile.ZIP_DEFLATED) as z:
    for rel in ('pes13-nx.nro', 'drive_c/PES13/pes2013.box64.txt', 'drive_c/windows/system32/ntdll.dll'):
        z.write(perf3 / rel, 'switch/pes13-nx/' + rel.replace('\\', '/'))
with zipfile.ZipFile(rollback) as z:
    assert z.testzip() is None

nro_blob = (dest / 'pes13-nx.nro').read_bytes()
assert nro_blob[16:20] == b'NRO0' and b'pes13-nx-0.2.0-perf4-balanced' in nro_blob
assert b'DXVK_SHADER_CACHE_PATH=C:' in nro_blob
for setting in ('SAFEFLAGS=1', 'FASTNAN=1', 'FASTROUND=1', 'X87DOUBLE=1',
                'BIGBLOCK=1', 'STRONGMEM=0', 'CALLRET=0'):
    assert 'BOX64_DYNAREC_' + setting in profile
print(json.dumps({
    'nro_sha256': hashlib.sha256(nro_blob).hexdigest(),
    'ntdll_sha256': hashlib.sha256(target_ntdll.read_bytes()).hexdigest(),
    'zip': str(archive),
    'zip_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'rollback_sha256': hashlib.sha256(rollback.read_bytes()).hexdigest(),
    'hardware_tested': False,
}, indent=2))
