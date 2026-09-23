"""WSL-only diagnostic build, restoring production sources and linked outputs."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

project = Path(__file__).resolve().parents[1]
root = Path(os.environ.get('PES_BUILD_ROOT', str(Path.home() / '.cache/pes13-nx')))
src = root / 'runtime-pes13-source'
out = root / 'runtime-pes13'
dest = project / 'dist/settings-debug/switch/pes13-nx'
runtime = src / 'wine-nx-probe/source/runtime.c'
file_source = src / 'dlls/ntdll/unix/file.c'
sdk = Path(os.environ.get('DEVKITPRO', '/opt/devkitpro'))

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected one source match: {old[:100]}')
    return text.replace(old, new)

text = runtime.read_text()
for old, new in (
    ('#define DEFAULT_TARGET WINE_DRIVE_C "/PES13/pes2013.exe"', '#define DEFAULT_TARGET WINE_DRIVE_C "/PES13/settings.exe"'),
    ('pes13-nx-0.2.0-vk1-production', 'pes13-settings-debug-0.2.0'),
    ('RUNTIME_DIR "/pes13-nx.log"', 'RUNTIME_DIR "/pes13-settings-debug.log"'),
    ('wine_nx_production = read_bool_file(RUNTIME_DIR "/production.txt");', 'wine_nx_production = 1;'),
    ('wine_nx_pes13_keyboard_only = read_bool_file(RUNTIME_DIR "/controller-keyboard.txt");', 'wine_nx_pes13_keyboard_only = 0;'),
    ('wine_nx_pes13_gamepad_only = read_bool_file(RUNTIME_DIR "/controller-gamepad.txt");', 'wine_nx_pes13_gamepad_only = 1;'),
    ('pes13_controller_trace_enabled = read_bool_file(RUNTIME_DIR "/controller-trace.txt");', 'pes13_controller_trace_enabled = 1;'),
):
    text = replace_once(text, old, new)

file_text = file_source.read_text()
start = file_text.index('NTSTATUS WINAPI NtCreateFile(')
end = file_text.index('NTSTATUS WINAPI NtOpenFile(', start)
part = file_text[start:end]
trace = r'''
#ifdef __SWITCH__
    {
        extern void wine_nx_runtime_trace(const char *msg);
        static unsigned int records;
        char name[600], lower[600], message[1500];
        unsigned int i, length = attr->ObjectName->Length / sizeof(WCHAR);
        if (length >= sizeof(name)) length = sizeof(name) - 1;
        for (i = 0; i < length; ++i)
        {
            WCHAR ch = attr->ObjectName->Buffer[i];
            name[i] = ch >= 32 && ch < 127 ? ch : '?';
            lower[i] = name[i] >= 'A' && name[i] <= 'Z' ? name[i] + 32 : name[i];
        }
        name[length] = lower[length] = 0;
        if ((strstr(lower, "settings.dat") || strstr(lower, "konami") ||
             strstr(lower, "documents")) && __atomic_fetch_add(&records, 1, __ATOMIC_RELAXED) < 128)
        {
            snprintf(message, sizeof(message),
                     "[PES13-SETTINGS-FILE] nt='%s' root=%p sd='%s' access=%08x disposition=%u status=%08x",
                     name, attr->RootDirectory, unix_name ? unix_name : "(unresolved)",
                     (unsigned)access, (unsigned)disposition, status);
            wine_nx_runtime_trace(message);
        }
    }
#endif
'''
part = replace_once(part, ' done:\n    free( unix_name );', ' done:\n' + trace + '    free( unix_name );')
file_text = file_text[:start] + part + file_text[end:]

dest.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, DEVKITPRO=str(sdk), DEVKITA64=str(sdk / 'devkitA64'))
env['PATH'] = f'{sdk}/devkitA64/bin:{sdk}/tools/bin:' + env['PATH']
protected = [runtime, file_source, out / 'wine-nx-runtime.elf', out / 'wine-nx-runtime.nro']
with tempfile.TemporaryDirectory(prefix='pes13-settings-backup-', dir=root) as tmp:
    saved = []
    for i, path in enumerate(protected):
        if path.exists():
            backup = Path(tmp) / str(i)
            shutil.copy2(path, backup)
            saved.append((path, backup))
    try:
        runtime.write_text(text)
        file_source.write_text(file_text)
        subprocess.run(['cmake', '--build', str(out), '--target', 'wine-nx-runtime', '-j4'], env=env, check=True)
        nacp = Path(tmp) / 'debug.nacp'
        subprocess.run([str(sdk / 'tools/bin/nacptool'), '--create', 'PES13 Settings Debug', 'PES13-NX', '0.2.0', str(nacp)], check=True)
        nro = dest / 'pes13-settings-debug.nro'
        subprocess.run([str(sdk / 'tools/bin/elf2nro'), str(out / 'wine-nx-runtime.elf'), str(nro),
                        f'--nacp={nacp}', f'--icon={project}/assets/icon.jpg'], check=True)
        # Preserve the exact corresponding debug sources for diagnosis/reproduction.
        source_copy = project / 'local/settings-debug-source'
        source_copy.mkdir(parents=True, exist_ok=True)
        (source_copy / 'runtime.c').write_text(text)
        (source_copy / 'file.c').write_text(file_text)
    finally:
        for path, backup in saved:
            shutil.copy2(backup, path)
        # Cached objects contain diagnostic code. Force the next production
        # build to recompile restored sources even when bytes are unchanged.
        runtime.touch()
        file_source.touch()
    for path, backup in saved:
        assert path.read_bytes() == backup.read_bytes(), f'Production restore failed: {path}'
print('Debug NRO:', nro)
print('Production sources and linked outputs restored byte-for-byte.')
