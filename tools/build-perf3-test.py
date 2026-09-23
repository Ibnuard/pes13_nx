"""Build PERF3 with a matched NRO and ARM64 ntdll fast-suspend path."""
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
wine_src = root / 'source'
runtime_out = root / 'runtime-pes13'
pe_out = root / 'pe'
dest = project / 'dist/perf3/switch/pes13-nx'
runtime = src / 'wine-nx-probe/source/runtime.c'
signal = wine_src / 'dlls/ntdll/signal_arm64.c'
ntdll_obj = pe_out / 'dlls/ntdll/aarch64-windows/signal_arm64.o'
ntdll = pe_out / 'dlls/ntdll/aarch64-windows/ntdll.dll'
sdk = Path('/opt/devkitpro')
toolchain = root / 'toolchains/llvm-mingw-20260505-ucrt-ubuntu-22.04-x86_64'


def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


original_runtime = runtime.read_text()
runtime_text = replace(original_runtime, 'pes13-nx-0.2.0-vk1-production', 'pes13-nx-0.2.0-perf3-fast-suspend')
runtime_text = replace(runtime_text, 'static const char runtime_environment[] =\n',
                       'static const char runtime_environment[] =\n    "DXVK_SHADER_CACHE_PATH=C:\\\\dxvk-cache\\0"\n')
runtime_text = replace(runtime_text, '    mkdir( WINE_DRIVE_C, 0777 );',
                       '    mkdir( WINE_DRIVE_C, 0777 );\n    mkdir( WINE_DRIVE_C "/dxvk-cache", 0777 );')
anchor = '        unsigned long long read_ms = &wine_nx_file_read_100ns'
metric = '''        {
            static u64 last_tick;
            static unsigned int last_presents;
            unsigned int presents = &wine_nx_vk_presents ? __atomic_load_n(&wine_nx_vk_presents, __ATOMIC_RELAXED) : 0;
            if (last_tick && now > last_tick)
            {
                unsigned long long ms = armTicksToNs(now - last_tick) / 1000000;
                log_line("[PERF3] vk_present_delta=%u interval_ms=%llu", presents - last_presents, ms);
            }
            last_tick = now;
            last_presents = presents;
        }
'''
runtime_text = replace(runtime_text, anchor, metric + anchor)

original_signal = signal.read_text()
begin = original_signal.index('NTSTATUS WINAPI RtlWow64SuspendThread(')
end = original_signal.index('/*************************************************************************', begin)
fast_suspend = '''static volatile const char perf3_suspend_marker[] = "pes13-nx-perf3-fast-suspend";

NTSTATUS WINAPI RtlWow64SuspendThread( HANDLE thread, ULONG *count )
{
    /* Wine-NX/Horizon has one in-process Windows address space and cannot
     * asynchronously stop a running pthread. PES polls this call millions of
     * times, so avoid the duplicate/query/close/suspend server sequence. */
    if (perf3_suspend_marker[0] != 'p') return STATUS_UNSUCCESSFUL;
    if (count) *count = 0;
    return STATUS_SUCCESS;
}

'''
signal_text = original_signal[:begin] + fast_suspend + original_signal[end:]

dest.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, DEVKITPRO=str(sdk), DEVKITA64=str(sdk / 'devkitA64'))
env['PATH'] = f'{toolchain}/bin:{sdk}/devkitA64/bin:{sdk}/tools/bin:/usr/bin:/bin'
protected = [
    runtime,
    signal,
    ntdll_obj,
    ntdll,
    runtime_out / 'wine-nx-runtime.elf',
    runtime_out / 'wine-nx-runtime.nro',
]
with tempfile.TemporaryDirectory(prefix='pes13-perf3-', dir=root) as tmp:
    saved = []
    missing = []
    for i, path in enumerate(protected):
        if path.exists():
            backup = Path(tmp) / str(i)
            shutil.copy2(path, backup)
            saved.append((path, backup))
        else:
            missing.append(path)
    try:
        runtime.write_text(runtime_text)
        signal.write_text(signal_text)
        subprocess.run(['cmake', '--build', str(runtime_out), '--target', 'wine-nx-runtime', '-j4'], env=env, check=True)
        subprocess.run(['make', '-C', str(pe_out), '-j4', 'dlls/ntdll/aarch64-windows/ntdll.dll'], env=env, check=True)
        custom_ntdll = Path(tmp) / 'ntdll-perf3.dll'
        shutil.copy2(ntdll, custom_ntdll)
        nacp = Path(tmp) / 'perf.nacp'
        subprocess.run([str(sdk / 'tools/bin/nacptool'), '--create', 'PES13-NX PERF3', 'PES13-NX', '0.2.0', str(nacp)], check=True)
        nro = dest / 'pes13-nx.nro'
        subprocess.run([str(sdk / 'tools/bin/elf2nro'), str(runtime_out / 'wine-nx-runtime.elf'), str(nro),
                        f'--nacp={nacp}', f'--icon={project}/assets/icon.jpg'], check=True)
        target_ntdll = dest / 'drive_c/windows/system32/ntdll.dll'
        target_ntdll.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(custom_ntdll, target_ntdll)
    finally:
        for path, backup in saved:
            shutil.copy2(backup, path)
        for path in missing:
            if path.exists():
                path.unlink()
        runtime.touch()
        signal.touch()
    for path, backup in saved:
        assert path.read_bytes() == backup.read_bytes()

profile = dest / 'drive_c/PES13/pes2013.box64.txt'
profile.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(project / 'config/drive_c/PES13/pes2013.box64.txt', profile)
for name in ('production.txt', 'controller-gamepad.txt', 'controller-keyboard.txt', 'controller-trace.txt', 'vulkan-probe.txt'):
    shutil.copy2(project / 'config' / name, dest / name)

archive = project / 'dist/pes13-perf3-overlay.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for path in sorted(dest.rglob('*')):
        if path.is_file():
            z.write(path, path.relative_to(project / 'dist/perf3'))
    z.write(project / 'docs/PERF3.md', 'PERF3.md')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None

rollback = project / 'dist/pes13-perf3-rollback.zip'
production = project / 'dist/sd/switch/pes13-nx'
with zipfile.ZipFile(rollback, 'w', zipfile.ZIP_DEFLATED) as z:
    for rel in ('pes13-nx.nro', 'drive_c/PES13/pes2013.box64.txt', 'drive_c/windows/system32/ntdll.dll'):
        z.write(production / rel, 'switch/pes13-nx/' + rel.replace('\\', '/'))
with zipfile.ZipFile(rollback) as z:
    assert z.testzip() is None

nro_blob = (dest / 'pes13-nx.nro').read_bytes()
ntdll_blob = (dest / 'drive_c/windows/system32/ntdll.dll').read_bytes()
assert nro_blob[16:20] == b'NRO0' and b'pes13-nx-0.2.0-perf3-fast-suspend' in nro_blob
assert b'DXVK_SHADER_CACHE_PATH=C:' in nro_blob
assert b'pes13-nx-perf3-fast-suspend' in ntdll_blob
assert 'BOX64_DYNAREC_BIGBLOCK=0' in profile.read_text()
print(json.dumps({
    'nro_sha256': hashlib.sha256(nro_blob).hexdigest(),
    'ntdll_sha256': hashlib.sha256(ntdll_blob).hexdigest(),
    'zip': str(archive),
    'zip_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'rollback_sha256': hashlib.sha256(rollback.read_bytes()).hexdigest(),
    'hardware_tested': False,
}, indent=2))
