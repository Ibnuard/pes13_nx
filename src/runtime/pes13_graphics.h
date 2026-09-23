/* Diagnostic CSMT A/B override for PES13 only. The Wine environment uses
 * NUL-separated entries plus a final NUL, not a single C string. */
#ifndef PES13_GRAPHICS_H
#define PES13_GRAPHICS_H

#define PES13_ENV_PREFIX \
    "PATH=C:\\windows\\system32;C:\\windows\0" \
    "SystemDrive=C:\0" \
    "SystemRoot=C:\\windows\0" \
    "TEMP=C:\\windows\\temp\0" \
    "TMP=C:\\windows\\temp\0"
#define PES13_ENV_SUFFIX \
    ",cs_spin_count=64,explicit_buffer_flush=1\0" \
    "windir=C:\\windows\0"

static const char pes13_environment_csmt0[] =
    PES13_ENV_PREFIX "WINE_D3D_CONFIG=csmt=0" PES13_ENV_SUFFIX;
static const char pes13_environment_csmt1[] =
    PES13_ENV_PREFIX "WINE_D3D_CONFIG=csmt=1" PES13_ENV_SUFFIX;

static const char *pes13_graphics_environment(const char *target, size_t *bytes)
{
    char setting[32];
    *bytes = sizeof(runtime_environment);
    if (strcmp(target, "sdmc:/switch/pes13-nx/drive_c/PES13/pes2013.exe"))
        return runtime_environment;
    if (!read_first_line(RUNTIME_DIR "/drive_c/PES13/pes2013.csmt.txt", setting, sizeof(setting)))
    {
        log_line("[PES13-GFX] csmt=default (no override file)");
        return runtime_environment;
    }
    if (!strcmp(setting, "0"))
    {
        *bytes = sizeof(pes13_environment_csmt0);
        log_line("[PES13-GFX] csmt=0 (single-thread command stream)");
        return pes13_environment_csmt0;
    }
    if (!strcmp(setting, "1"))
    {
        *bytes = sizeof(pes13_environment_csmt1);
        log_line("[PES13-GFX] csmt=1 (multithread command stream)");
        return pes13_environment_csmt1;
    }
    log_line("[PES13-GFX] invalid csmt override; using Wine default");
    return runtime_environment;
}

#undef PES13_ENV_PREFIX
#undef PES13_ENV_SUFFIX
#endif
