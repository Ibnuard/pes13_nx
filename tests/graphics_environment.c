#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>

#define RUNTIME_DIR "sdmc:/switch/pes13-nx"
static const char *override;
static unsigned int reads;
static void log_line(const char *fmt, ...) { (void)fmt; }
static int read_first_line(const char *path, char *out, size_t size)
{
    assert(!strcmp(path, RUNTIME_DIR "/drive_c/PES13/pes2013.csmt.txt"));
    ++reads;
    if (!override) return 0;
    snprintf(out, size, "%s", override);
    return 1;
}
#include "pes13_test_environment.h"
#include "pes13_graphics.h"

static void check_block(const char *block, size_t bytes, char csmt)
{
    unsigned int entries = 0, d3d = 0;
    const char *cursor = block, *base = runtime_environment;
    uint16_t wide[512];
    size_t i;
    assert(bytes < sizeof(wide) / sizeof(wide[0]));
    assert(block[bytes - 1] == 0 && block[bytes - 2] == 0);
    /* Exercise the same widening and size accounting used by process params. */
    for (i = 0; i < bytes; ++i) wide[i] = (unsigned char)block[i];
    assert(!wide[bytes - 1] && !wide[bytes - 2]);
    while (*cursor)
    {
        if (!strncmp(cursor, "WINE_D3D_CONFIG=", 15))
        {
            char expected[96];
            snprintf(expected, sizeof(expected),
                     "WINE_D3D_CONFIG=csmt=%c,cs_spin_count=64,explicit_buffer_flush=1", csmt);
            assert(!strcmp(cursor, expected));
            ++d3d;
        }
        else assert(!strcmp(cursor, base));
        cursor += strlen(cursor) + 1;
        base += strlen(base) + 1;
        ++entries;
    }
    assert(entries == 7 && d3d == 1 && !*base);
    assert((size_t)(cursor - block) + 1 == bytes);
}

int main(void)
{
    const char *target = RUNTIME_DIR "/drive_c/PES13/pes2013.exe", *env;
    size_t bytes;
    override = "0";
    env = pes13_graphics_environment(target, &bytes);
    check_block(env, bytes, '0');
    override = "1";
    env = pes13_graphics_environment(target, &bytes);
    check_block(env, bytes, '1');
    override = "invalid";
    env = pes13_graphics_environment(target, &bytes);
    assert(env == runtime_environment && bytes == sizeof(runtime_environment));
    override = NULL;
    env = pes13_graphics_environment(target, &bytes);
    assert(env == runtime_environment && bytes == sizeof(runtime_environment));
    reads = 0;
    override = "0";
    env = pes13_graphics_environment(RUNTIME_DIR "/drive_c/PES13/settings.exe", &bytes);
    assert(env == runtime_environment && !reads);
    env = pes13_graphics_environment(RUNTIME_DIR "/drive_c/other.exe", &bytes);
    assert(env == runtime_environment && !reads);
    puts("Graphics environment: CSMT 0/1, default fallback, scope and NUL/UTF16 block boundaries passed");
    return 0;
}
