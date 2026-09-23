"""Build an isolated PERF2 cooperative-suspend overlay from the WSL tree."""
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
dest = project / 'dist/perf2/switch/pes13-nx'
runtime = src / 'wine-nx-probe/source/runtime.c'
thread = src / 'dlls/ntdll/unix/thread.c'
sdk = Path('/opt/devkitpro')


def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


original_runtime = runtime.read_text()
text = replace(original_runtime, 'pes13-nx-0.2.0-vk1-production', 'pes13-nx-0.2.0-perf2-suspend')
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
                log_line("[PERF2] vk_present_delta=%u interval_ms=%llu", presents - last_presents, ms);
            }
            last_tick = now;
            last_presents = presents;
        }
'''
text = replace(text, anchor, metric + anchor)

original_thread = thread.read_text()
begin = original_thread.index('NTSTATUS WINAPI NtSuspendThread(')
end = original_thread.index('NTSTATUS WINAPI NtResumeThread(', begin)
part = original_thread[begin:end]
fallback = '''#ifdef __SWITCH__
    /* A running Horizon pthread has no asynchronous stop primitive. PES 2013
     * retries STATUS_NOT_SUPPORTED millions of times, starving render threads.
     * The Horizon runtime is in-process, so report a no-op suspend with the
     * previous count at zero and leave every other result unchanged. */
    if (ret == STATUS_NOT_SUPPORTED)
    {
        extern void wine_nx_runtime_trace(const char *msg);
        static unsigned int emulated;
        unsigned int sample = __atomic_fetch_add(&emulated, 1, __ATOMIC_RELAXED);

        ret = STATUS_SUCCESS;
        count = 0;
        if (sample < 8 || !(sample & 0x7ffff))
        {
            char msg[192];
            snprintf(msg, sizeof(msg), "[PERF2-SUSPEND] emulated_success=%u tid=%p target=%p",
                     sample + 1, NtCurrentTeb()->ClientId.UniqueThread, handle);
            wine_nx_runtime_trace(msg);
        }
    }
#endif
'''
part = replace(part, '    if (!ret && ret_count) *ret_count = count;',
               fallback + '    if (!ret && ret_count) *ret_count = count;')
thread_text = original_thread[:begin] + part + original_thread[end:]

dest.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, DEVKITPRO=str(sdk), DEVKITA64=str(sdk / 'devkitA64'))
env['PATH'] = f'{sdk}/devkitA64/bin:{sdk}/tools/bin:' + env['PATH']
protected = [runtime, thread, out / 'wine-nx-runtime.elf', out / 'wine-nx-runtime.nro']
with tempfile.TemporaryDirectory(prefix='pes13-perf2-', dir=root) as tmp:
    saved = []
    for i, path in enumerate(protected):
        if path.exists():
            backup = Path(tmp) / str(i)
            shutil.copy2(path, backup)
            saved.append((path, backup))
    try:
        runtime.write_text(text)
        thread.write_text(thread_text)
        subprocess.run(['cmake', '--build', str(out), '--target', 'wine-nx-runtime', '-j4'], env=env, check=True)
        nacp = Path(tmp) / 'perf.nacp'
        subprocess.run([str(sdk / 'tools/bin/nacptool'), '--create', 'PES13-NX PERF2', 'PES13-NX', '0.2.0', str(nacp)], check=True)
        nro = dest / 'pes13-nx.nro'
        subprocess.run([str(sdk / 'tools/bin/elf2nro'), str(out / 'wine-nx-runtime.elf'), str(nro),
                        f'--nacp={nacp}', f'--icon={project}/assets/icon.jpg'], check=True)
    finally:
        for path, backup in saved:
            shutil.copy2(backup, path)
        runtime.touch()
        thread.touch()
    for path, backup in saved:
        assert path.read_bytes() == backup.read_bytes()

profile = dest / 'drive_c/PES13/pes2013.box64.txt'
profile.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(project / 'config/drive_c/PES13/pes2013.box64.txt', profile)
for name in ('production.txt', 'controller-gamepad.txt', 'controller-keyboard.txt', 'controller-trace.txt', 'vulkan-probe.txt'):
    shutil.copy2(project / 'config' / name, dest / name)
archive = project / 'dist/pes13-perf2-overlay.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for path in sorted(dest.rglob('*')):
        if path.is_file():
            z.write(path, path.relative_to(project / 'dist/perf2'))
    z.write(project / 'docs/PERF2.md', 'PERF2.md')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
blob = nro.read_bytes()
assert blob[16:20] == b'NRO0' and b'pes13-nx-0.2.0-perf2-suspend' in blob
assert b'DXVK_SHADER_CACHE_PATH=C:' in blob and b'[PERF2-SUSPEND]' in blob
assert 'BOX64_DYNAREC_BIGBLOCK=0' in profile.read_text()
print(json.dumps({'nro_sha256': hashlib.sha256(blob).hexdigest(), 'zip': str(archive),
                  'zip_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'hardware_tested': False}, indent=2))
