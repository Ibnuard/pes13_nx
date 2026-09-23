"""PERF33 FASTMATH with one unified configuration.ini switch source.

The old one-file-per-boolean format remains a read-only fallback in the NRO,
so an existing SD package can be tested without conversion.  New packages
ship only configuration.ini for these switches.
"""
from pathlib import Path
import re

import perf33_patches
from perf17_patches import once


adapt_profile = perf33_patches.adapt_profile


def _runtime_config_impl(project):
    header = project / "src/runtime/pes13_config.h"
    return r'''
#include "''' + str(header) + r'''"

struct wine_nx_config_entry
{
    char key[64];
    int value;
};

static struct wine_nx_config_entry wine_nx_config_entries[96];
static unsigned int wine_nx_config_count;
static int wine_nx_config_loaded;

static char *wine_nx_config_trim(char *text)
{
    char *end;
    while (*text == ' ' || *text == '\t' || *text == '\r' || *text == '\n') text++;
    end = text + strlen(text);
    while (end > text && (end[-1] == ' ' || end[-1] == '\t' ||
                          end[-1] == '\r' || end[-1] == '\n')) *--end = 0;
    return text;
}

static int wine_nx_config_bool_text(const char *text, int *value)
{
    if (!strcasecmp(text, "1") || !strcasecmp(text, "true") ||
        !strcasecmp(text, "yes") || !strcasecmp(text, "on") ||
        !strcasecmp(text, "run") || !strcasecmp(text, "enabled"))
    {
        *value = 1;
        return 1;
    }
    if (!strcasecmp(text, "0") || !strcasecmp(text, "false") ||
        !strcasecmp(text, "no") || !strcasecmp(text, "off") ||
        !strcasecmp(text, "disabled"))
    {
        *value = 0;
        return 1;
    }
    return 0;
}

static void wine_nx_config_key(char *key, size_t size, const char *path)
{
    const char *base = strrchr(path, '/');
    size_t i = 0;
    if (base) path = base + 1;
    while (*path && *path != '.' && i + 1 < size)
    {
        unsigned char c = (unsigned char)*path++;
        if (c == '-') c = '_';
        if (c >= 'A' && c <= 'Z') c = (unsigned char)(c + ('a' - 'A'));
        key[i++] = (char)c;
    }
    key[i] = 0;
}

static void wine_nx_config_load(void)
{
    FILE *file;
    char line[192];
    wine_nx_config_loaded = 1;
    file = fopen(RUNTIME_DIR "/configuration.ini", "r");
    if (!file)
    {
        log_line("[CONFIG] configuration.ini missing; legacy boolean files remain supported");
        return;
    }
    while (fgets(line, sizeof(line), file))
    {
        char *equals, *key, *value;
        int parsed;
        if (!strchr(line, '\n') && !feof(file))
        {
            int c;
            while ((c = fgetc(file)) != EOF && c != '\n') {}
        }
        key = wine_nx_config_trim(line);
        if (!*key || *key == '#' || *key == ';' || *key == '[') continue;
        equals = strchr(key, '=');
        if (!equals) continue;
        *equals++ = 0;
        key = wine_nx_config_trim(key);
        value = wine_nx_config_trim(equals);
        /* Inline comments are useful for a checked-in developer config. */
        equals = strpbrk(value, "#;");
        if (equals) *equals = 0;
        value = wine_nx_config_trim(value);
        if (!*key || !wine_nx_config_bool_text(value, &parsed)) continue;
        if (wine_nx_config_count >= sizeof(wine_nx_config_entries) /
                                      sizeof(wine_nx_config_entries[0]))
            continue;
        {
            size_t i;
            for (i = 0; key[i] && i + 1 < sizeof(wine_nx_config_entries[0].key); ++i)
            {
                unsigned char c = (unsigned char)key[i];
                if (c == '-') c = '_';
                if (c >= 'A' && c <= 'Z') c = (unsigned char)(c + ('a' - 'A'));
                wine_nx_config_entries[wine_nx_config_count].key[i] = (char)c;
            }
            wine_nx_config_entries[wine_nx_config_count].key[i] = 0;
        }
        wine_nx_config_entries[wine_nx_config_count].value = parsed;
        wine_nx_config_count++;
    }
    fclose(file);
    log_line("[CONFIG] configuration.ini loaded entries=%u; legacy boolean fallback enabled",
             wine_nx_config_count);
}

int wine_nx_config_file_bool(const char *legacy_path, int fallback)
{
    char key[64];
    unsigned int i;
    int legacy;
    if (!wine_nx_config_loaded) wine_nx_config_load();
    wine_nx_config_key(key, sizeof(key), legacy_path);
    for (i = 0; i < wine_nx_config_count; ++i)
        if (!strcmp(key, wine_nx_config_entries[i].key))
            return wine_nx_config_entries[i].value;
    legacy = read_bool_file(legacy_path);
    return legacy_path && legacy ? 1 : fallback;
}
'''


def _replace_runtime_flags(runtime, project):
    # All runtime-side switches historically used a RUNTIME_DIR/*.txt path.
    # Keep that path as the compatibility fallback while making the INI key
    # authoritative whenever it contains the corresponding option.
    runtime = re.sub(
        r'read_bool_file\(\s*RUNTIME_DIR\s*"([^"]+)"\s*\)',
        r'wine_nx_config_file_bool(RUNTIME_DIR "\1", 0)',
        runtime,
    )
    marker = 'static int read_bool_file( const char *path )'
    assert runtime.count(marker) == 1
    start = runtime.index(marker)
    # Insert after the whole legacy helper, before read_key_map.  The exact
    # closing brace is stable in the pinned Wine-NX source and this anchor
    # avoids touching any historical PERF source file.
    anchor = '''static int read_bool_file( const char *path )
{
    char line[32];

    if (!read_first_line( path, line, sizeof(line) )) return 0;
    return !strcmp( line, "1" ) || !strcasecmp( line, "true" ) ||
           !strcasecmp( line, "yes" ) || !strcasecmp( line, "run" );
}
'''
    assert runtime.count(anchor) == 1
    return runtime.replace(anchor, anchor + _runtime_config_impl(project), 1)


def _replace_dynarec_flags(dynarec):
    # The dynarec's existing flag reads are deliberately kept as fallbacks;
    # only the source of the boolean changes to the exported runtime helper.
    replacements = {
        '''FILE *f = fopen("sdmc:/switch/pes13-nx/perf19-matrix.txt", "r");
        if (f) { __atomic_store_n(&pes19_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }
        f = fopen("sdmc:/switch/pes13-nx/perf20-fusion.txt", "r");
        if (f) { __atomic_store_n(&pes20_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }''':
        '''__atomic_store_n(&pes19_mode, wine_nx_config_file_bool(
            "sdmc:/switch/pes13-nx/perf19-matrix.txt", 0), __ATOMIC_RELEASE);
        __atomic_store_n(&pes20_mode, wine_nx_config_file_bool(
            "sdmc:/switch/pes13-nx/perf20-fusion.txt", 0), __ATOMIC_RELEASE);''',
        '''FILE *f = fopen("sdmc:/switch/pes13-nx/perf19-matrix.txt", "r");
        if (f) { __atomic_store_n(&pes19_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }''':
        '''__atomic_store_n(&pes19_mode, wine_nx_config_file_bool(
            "sdmc:/switch/pes13-nx/perf19-matrix.txt", 0), __ATOMIC_RELEASE);''',
        '''FILE *f = fopen("sdmc:/switch/pes13-nx/perf21-fastmath.txt", "r");
        if (f) { __atomic_store_n(&pes21_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }''':
        '''__atomic_store_n(&pes21_mode, wine_nx_config_file_bool(
            "sdmc:/switch/pes13-nx/perf21-fastmath.txt", 0), __ATOMIC_RELEASE);''',
        '''FILE *f = fopen("sdmc:/switch/pes13-nx/perf22-floatmath.txt", "r");
        if (f) { __atomic_store_n(&pes22_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }''':
        '''__atomic_store_n(&pes22_mode, wine_nx_config_file_bool(
            "sdmc:/switch/pes13-nx/perf22-floatmath.txt", 0), __ATOMIC_RELEASE);''',
        '''FILE *profile = fopen("sdmc:/switch/pes13-nx/perf8-turbo.txt", "r");
        if (profile) { pes13_perf8_enabled = fgetc(profile) != '0'; fclose(profile); }''':
        '''pes13_perf8_enabled = wine_nx_config_file_bool(
            "sdmc:/switch/pes13-nx/perf8-turbo.txt", pes13_perf8_enabled);''',
        '''FILE *f = fopen("sdmc:/switch/pes13-nx/perf17-hotblocks.txt", "r");
        if (f) { __atomic_store_n(&pes17_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }
        f = fopen("sdmc:/switch/pes13-nx/perf17-capture.txt", "r");
        if (f) { __atomic_store_n(&pes17_capture, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }''':
        '''__atomic_store_n(&pes17_mode, wine_nx_config_file_bool(
            "sdmc:/switch/pes13-nx/perf17-hotblocks.txt", 0), __ATOMIC_RELEASE);
        __atomic_store_n(&pes17_capture, wine_nx_config_file_bool(
            "sdmc:/switch/pes13-nx/perf17-capture.txt", 0), __ATOMIC_RELEASE);''',
        '''FILE *f = fopen("sdmc:/switch/pes13-nx/perf18-roundguard.txt", "r");
        if (f) { __atomic_store_n(&pes18_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }''':
        '''__atomic_store_n(&pes18_mode, wine_nx_config_file_bool(
            "sdmc:/switch/pes13-nx/perf18-roundguard.txt", 0), __ATOMIC_RELEASE);''',
        '''FILE *f = fopen("sdmc:/switch/pes13-nx/perf25-paircopy.txt", "r");
        if (f) { __atomic_store_n(&pes25_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }''':
        '''__atomic_store_n(&pes25_mode, wine_nx_config_file_bool(
            "sdmc:/switch/pes13-nx/perf25-paircopy.txt", 0), __ATOMIC_RELEASE);''',
        '''FILE *f=fopen("sdmc:/switch/pes13-nx/perf29-worker-blocks.txt","r");
        if (f) { pes29_mode=fgetc(f)=='1'; fclose(f); }''':
        '''pes29_mode = wine_nx_config_file_bool(
            "sdmc:/switch/pes13-nx/perf29-worker-blocks.txt", 0);''',
        '''FILE *f=fopen("sdmc:/switch/pes13-nx/perf32-blocks.txt","r");
        if (f) { pes32_mode=fgetc(f)=='1'; fclose(f); }''':
        '''pes32_mode = wine_nx_config_file_bool(
            "sdmc:/switch/pes13-nx/perf32-blocks.txt", 0);''',
        '''FILE *f=fopen("sdmc:/switch/pes13-nx/perf33-blocks.txt","r");
        if (f) { pes33_mode=fgetc(f)=='1'; fclose(f); }''':
        '''pes33_mode = wine_nx_config_file_bool(
            "sdmc:/switch/pes13-nx/perf33-blocks.txt", 0);''',
    }
    for old, new in replacements.items():
        if old in dynarec:
            dynarec = dynarec.replace(old, new, 1)
    # The helper is provided by runtime.c and linked into the final NRO.
    declaration = 'extern int wine_nx_config_file_bool(const char *, int);\n'
    if 'extern int wine_nx_config_file_bool' not in dynarec:
        anchor = '#include <stdio.h>'
        if anchor in dynarec:
            dynarec = dynarec.replace(anchor, anchor + '\n' + declaration, 1)
        else:
            # The pinned generated dynarec source does not include stdio on
            # every build path; a declaration at byte zero is valid C and
            # avoids relying on an incidental include.
            dynarec = declaration + dynarec
    for name in ('perf19-matrix.txt', 'perf20-fusion.txt',
                 'perf21-fastmath.txt', 'perf22-floatmath.txt',
                 'perf25-paircopy.txt', 'perf33-blocks.txt'):
        assert ('wine_nx_config_file_bool(\n            "sdmc:/switch/pes13-nx/' + name + '",') in dynarec, name
    return dynarec


def adapt(cmake, dynarec, runtime, project):
    # Rebind PERF33's generated snapshots to PERF34 so the older experiment
    # remains immutable and its retained-header checks still refer to itself.
    path = project / 'tools/perf33_patches.py'
    ns = {'__file__': str(path), '__name__': 'perf34_base33'}
    exec(compile(path.read_text().replace('local/perf33', 'local/perf34'),
                 str(path), 'exec'), ns)
    cmake, dynarec, runtime = ns['adapt'](cmake, dynarec, runtime, project)
    runtime = _replace_runtime_flags(runtime, project)
    dynarec = _replace_dynarec_flags(dynarec)
    # Build identifier and the runtime package are versioned so PERF33 remains
    # an exact rollback candidate.
    runtime = runtime.replace('pes13-nx-0.2.0-perf33-fastmath',
                              'pes13-nx-0.2.0-perf34-config')
    return cmake, dynarec, runtime


def adapt_recipe(text):
    # PERF33's recipe is already the complete, tested build chain.  Only its
    # output names and archive directory are changed for this configuration
    # migration; no Mesa, Box64, or game tuning source is reselected here.
    text = perf33_patches.adapt_recipe(text)
    for old, new in (
        ('runtime-perf33-fastmath', 'runtime-perf34-config'),
        ('pes13-nx-0.2.0-perf33-fastmath', 'pes13-nx-0.2.0-perf34-config'),
        ('PES13-NX PERF33 FASTMATH', 'PES13-NX PERF34 CONFIG'),
        ('local/perf33', 'local/perf34'),
    ):
        text = text.replace(old, new)
    return text
