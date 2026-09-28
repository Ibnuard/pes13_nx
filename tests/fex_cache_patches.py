"""Host regressions for isolated FEX shader-cache patches; no Switch/DXVK run."""
from pathlib import Path
import importlib.util
import errno
import os
import re
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
RUNTIME_NAME = 'wine-nx-probe/source/runtime.c'
ENVIRONMENT = re.compile(
    r'static const char runtime_environment\[\] =\n'
    r'(?:    "(?:[^"\\\n]|\\.)*"(?:\n|;\n))+')

# Reconstructed startup seam, not a complete Wine runtime. Entry names/paths
# exercise the existing frame patch and newer upstream user-profile variables.
FIXTURE = r'''
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>
#define WINE_ROOT "sdmc:/switch/pes13-fex"
#define RUNTIME_DIR WINE_ROOT
#define WINE_DRIVE_C WINE_ROOT "/drive_c"
static FILE *log_file;
static void log_line(const char *fmt, ...)
{
    va_list args;
    va_start(args, fmt);
    vprintf(fmt, args);
    va_end(args);
    putchar('\n');
}
static const char runtime_environment[] =
    "APPDATA=C:\\users\\steamuser\\AppData\\Roaming\0"
    "DXVK_CONFIG_FILE=C:\\PES13\\dxvk.conf\0"
    "DXVK_HUD=0\0"
    "HOMEDRIVE=C:\0"
    "HOMEPATH=\\users\\steamuser\0"
    "LOCALAPPDATA=C:\\users\\steamuser\\AppData\\Local\0"
    "PATH=C:\\windows\\system32;C:\\windows\0"
    "SystemDrive=C:\0"
    "SystemRoot=C:\\windows\0"
    "TEMP=C:\\windows\\temp\0"
    "TMP=C:\\windows\\temp\0"
    "USERNAME=steamuser\0"
    "USERPROFILE=C:\\users\\steamuser\0"
    "windir=C:\\windows\0"
    "WINE_D3D_CONFIG=cs_spin_count=64,explicit_buffer_flush=1\0";
static void wine_nx_runtime_platform_init(void)
{
    struct stat info;
    int present = !stat(WINE_DRIVE_C "/dxvk-cache", &info) && S_ISDIR(info.st_mode);
    printf("PRE_PE_DIR=%d\n", present);
}
int main(void)
{
    (void)runtime_environment;
    (void)log_line;
    mkdir( "sdmc:/switch", 0777 );
    mkdir( RUNTIME_DIR, 0777 );
    mkdir( WINE_DRIVE_C, 0777 );
    log_file = fopen( RUNTIME_DIR "/fex-runtime.log", "w" );
    wine_nx_runtime_platform_init();
    if (log_file) fclose(log_file);
    puts("PE_CONTINUED");
    return 0;
}
'''


def compile_c(source, directory, name):
    c_file = directory / (name + '.c')
    executable = directory / name
    c_file.write_text(source)
    subprocess.run(['cc', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', str(c_file), '-o', str(executable)],
                   check=True, capture_output=True, text=True, timeout=30)
    return executable


def environment_bytes(source, directory, name):
    declaration = ENVIRONMENT.search(source)
    if declaration is None:
        raise AssertionError('runtime environment declaration missing')
    harness = '#include <stdio.h>\n' + declaration.group() + '''
int main(void)
{
    return fwrite(runtime_environment, 1, sizeof(runtime_environment), stdout)
        == sizeof(runtime_environment) ? 0 : 1;
}
'''
    executable = compile_c(harness, directory, name)
    return subprocess.run([str(executable)], check=True, capture_output=True, timeout=30).stdout


class CachePatches(unittest.TestCase):
    def apply_patch(self, source):
        module_path = PROJECT / 'tools/fex_cache_patches.py'
        self.assertTrue(module_path.is_file(), 'missing isolated shader-cache patch generator')
        spec = importlib.util.spec_from_file_location('pes13_cache_patch_under_test', module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        files = {RUNTIME_NAME: source}

        def read(name):
            self.assertEqual(name, RUNTIME_NAME)
            return files[name]

        def replace(name, old, new):
            data = read(name)
            self.assertEqual(data.count(old), 1, f'expected one exact anchor: {old[:90]}')
            files[name] = data.replace(old, new)

        module.apply(read, replace, PROJECT)
        self.assertEqual(set(files), {RUNTIME_NAME})
        return files[RUNTIME_NAME]

    def test_startup_creates_sd_directory_before_pe_and_reports_only_directory_state(self):
        patched = self.apply_patch(FIXTURE)
        with tempfile.TemporaryDirectory(prefix='fex-cache-start-', dir=os.environ.get('TMPDIR')) as tmp:
            directory = Path(tmp)
            (directory / 'sdmc:').mkdir()
            executable = compile_c(patched, directory, 'startup')
            result = subprocess.run([str(executable)], cwd=directory, check=True,
                                    capture_output=True, text=True, timeout=30)
            cache = directory / 'sdmc:/switch/pes13-fex/drive_c/dxvk-cache'
            self.assertTrue(cache.is_dir(), 'native startup must create matching SD cache directory')
            self.assertEqual(list(cache.iterdir()), [], 'startup must not fabricate DXVK cache files')
        lines = result.stdout.splitlines()
        reports = [line for line in lines if line.startswith('[FEX-CACHE]')]
        self.assertEqual(len(reports), 1)
        self.assertIn('status=created', reports[0])
        self.assertIn('persistence=unverified', reports[0])
        self.assertLess(lines.index(reports[0]), lines.index('PRE_PE_DIR=1'))
        self.assertIn('PE_CONTINUED', lines)

    def test_existing_cache_and_legacy_shader_data_survive_repeat_launches(self):
        patched = self.apply_patch(FIXTURE)
        with tempfile.TemporaryDirectory(prefix='fex-cache-existing-', dir=os.environ.get('TMPDIR')) as tmp:
            directory = Path(tmp)
            drive = directory / 'sdmc:/switch/pes13-fex/drive_c'
            cache = drive / 'dxvk-cache'
            cache.mkdir(parents=True)
            payloads = {
                cache / 'example.dxvk.bin': b'existing binary shader data\x00\xff',
                cache / 'example.dxvk.lut': b'existing lookup data\x00\x01',
                drive / 'users/steamuser/AppData/Local/dxvk/legacy.dxvk.bin': b'legacy cache',
                drive / 'PES13/dxvk.conf': b'd3d9.presentInterval = 0\n',
                drive / 'PES13/settings.dat': b'known-good settings\x00',
            }
            for path, contents in payloads.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)
            executable = compile_c(patched, directory, 'existing')
            for _ in range(2):
                result = subprocess.run([str(executable)], cwd=directory, check=True,
                                        capture_output=True, text=True, timeout=30)
                reports = [line for line in result.stdout.splitlines() if line.startswith('[FEX-CACHE]')]
                self.assertEqual(len(reports), 1)
                self.assertIn('status=existing', reports[0])
                self.assertIn('persistence=unverified', reports[0])
                self.assertIn('PRE_PE_DIR=1\nPE_CONTINUED', result.stdout)
                for path, contents in payloads.items():
                    self.assertEqual(path.read_bytes(), contents, str(path))
            self.assertEqual({path.name for path in cache.iterdir()},
                             {'example.dxvk.bin', 'example.dxvk.lut'})

    def test_existing_non_directory_is_reported_nonfatal_without_destroying_file(self):
        patched = self.apply_patch(FIXTURE)
        with tempfile.TemporaryDirectory(prefix='fex-cache-file-', dir=os.environ.get('TMPDIR')) as tmp:
            directory = Path(tmp)
            cache = directory / 'sdmc:/switch/pes13-fex/drive_c/dxvk-cache'
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b'user file must remain')
            executable = compile_c(patched, directory, 'not-directory')
            result = subprocess.run([str(executable)], cwd=directory, check=True,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(cache.read_bytes(), b'user file must remain')
        reports = [line for line in result.stdout.splitlines() if line.startswith('[FEX-CACHE]')]
        self.assertEqual(len(reports), 1)
        self.assertIn('status=unavailable', reports[0])
        self.assertIn(f'errno={errno.ENOTDIR}', reports[0])
        self.assertIn('continuing', reports[0])
        self.assertIn('PRE_PE_DIR=0\nPE_CONTINUED', result.stdout)

    def test_filesystem_errors_are_bounded_nonfatal_and_keep_original_errno(self):
        # Permission/readonly/full-card and stat errors need deterministic fault
        # injection; chmod is unreliable under root and on non-POSIX SD drivers.
        fault_source = r'''
#include <string.h>
static int cache_test_mkdir(const char *path, mode_t mode)
{
    if (!strcmp(path, WINE_DRIVE_C "/dxvk-cache"))
    {
        errno = CACHE_MKDIR_ERROR;
        return -1;
    }
    return mkdir(path, mode);
}
static int cache_test_stat(const char *path, struct stat *info)
{
    if (!strcmp(path, WINE_DRIVE_C "/dxvk-cache"))
    {
        errno = CACHE_STAT_ERROR;
        return -1;
    }
    return stat(path, info);
}
#define mkdir(path, mode) cache_test_mkdir(path, mode)
#define stat(path, info) cache_test_stat(path, info)
'''
        for mkdir_error, stat_error, expected in [
                ('EACCES', 'EIO', errno.EACCES), ('EROFS', 'EIO', errno.EROFS),
                ('ENOSPC', 'EIO', errno.ENOSPC), ('EEXIST', 'EIO', errno.EIO)]:
            with self.subTest(mkdir_error=mkdir_error, stat_error=stat_error):
                source = FIXTURE.replace('static FILE *log_file;',
                    f'#define CACHE_MKDIR_ERROR {mkdir_error}\n'
                    f'#define CACHE_STAT_ERROR {stat_error}\n' + fault_source + '\nstatic FILE *log_file;')
                patched = self.apply_patch(source)
                with tempfile.TemporaryDirectory(prefix='fex-cache-error-', dir=os.environ.get('TMPDIR')) as tmp:
                    directory = Path(tmp)
                    (directory / 'sdmc:').mkdir()
                    executable = compile_c(patched, directory, 'error')
                    result = subprocess.run([str(executable)], cwd=directory, check=True,
                                            capture_output=True, text=True, timeout=30)
                reports = [line for line in result.stdout.splitlines() if line.startswith('[FEX-CACHE]')]
                self.assertEqual(len(reports), 1)
                self.assertLess(len(reports[0]), 256)
                self.assertIn('status=unavailable', reports[0])
                self.assertIn(f'errno={expected}', reports[0])
                self.assertIn('continuing', reports[0])
                self.assertIn('PE_CONTINUED', result.stdout)

    def test_existing_cache_override_is_rejected_instead_of_duplicated_or_silently_changed(self):
        for entry in [r'DXVK_SHADER_CACHE_PATH=C:\\dxvk-cache\0',
                      r'dxvk_shader_cache_path=C:\\user-cache\0']:
            with self.subTest(entry=entry):
                source = FIXTURE.replace('static const char runtime_environment[] =\n',
                    'static const char runtime_environment[] =\n    "' + entry + '"\n')
                with self.assertRaisesRegex(RuntimeError, 'DXVK_SHADER_CACHE_PATH already present'):
                    self.apply_patch(source)

    def test_environment_is_sorted_nul_terminated_and_preserves_existing_values(self):
        patched = self.apply_patch(FIXTURE)
        with tempfile.TemporaryDirectory(prefix='fex-cache-env-', dir=os.environ.get('TMPDIR')) as tmp:
            directory = Path(tmp)
            before = environment_bytes(FIXTURE, directory, 'before')
            after = environment_bytes(patched, directory, 'after')
        self.assertTrue(after.endswith(b'\0\0'))
        self.assertNotIn(b'\0\0', after[:-1])
        entries = after[:-2].split(b'\0')
        keys = [entry.split(b'=', 1)[0].lower() for entry in entries]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(keys), len(set(keys)))
        expected = before[:-2].split(b'\0') + [b'DXVK_SHADER_CACHE_PATH=C:\\dxvk-cache']
        self.assertCountEqual(entries, expected)
        self.assertIn(b'DXVK_CONFIG_FILE=C:\\PES13\\dxvk.conf', entries)


if __name__ == '__main__':
    unittest.main()
