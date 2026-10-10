/* Exercise the production header with Wine-compatible NT data types. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint16_t WCHAR;
typedef uint32_t NTSTATUS;
typedef struct { uint16_t Length, MaximumLength; WCHAR *Buffer; } UNICODE_STRING;
typedef struct { void *RootDirectory; UNICODE_STRING *ObjectName; } OBJECT_ATTRIBUTES;
#define STATUS_SUCCESS 0
#define STATUS_NO_MEMORY 0xc0000017u
static int debug, reports, fail_alloc, outstanding;
static void *allocate(size_t n) { if (fail_alloc) return NULL; outstanding++; return malloc(n); }
static void release(void *p) { if (p) { outstanding--; free(p); } }
int wine_nx_launch_debug_active(void) { return debug; }
void wine_nx_runtime_trace(const char *s) { assert(debug && strstr(s, "[LW6-SETTINGS] alias=")); reports++; }
#define malloc allocate
#define free release
#include "../src/runtime/pes_settings_route.h"
#undef malloc
#undef free

static const struct { const char *path; int match; } cases[] = {
    {"\\??\\C:\\KONAMI\\FIFA World Cup 2026 Patch\\settings.dat", 1},
    {"\\??\\c:\\konami\\Different Patch\\SETTINGS.DAT", 1},
    {"\\DosDevices\\C:\\KONAMI\\Test\\settings.dat", 1},
    {"\\??\\C:\\PES13\\KONAMI\\Test\\settings.dat", 1},
    {"\\??\\C:\\users\\steamuser\\Documents\\KONAMI\\Test\\settings.dat", 1},
    {"\\??\\C:\\users\\Player 2\\Documents\\KONAMI\\Test\\settings.dat", 1},
    {"\\??\\C:\\KONAMI\\Pro Evolution Soccer 2013\\settings.dat", 0},
    {"\\??\\C:\\users\\steamuser\\Documents\\KONAMI\\Pro Evolution Soccer 2013\\settings.dat", 0},
    {"\\??\\C:\\PES13\\settings.dat", 0},
    {"\\??\\C:\\PES13\\KONAMI\\Test\\save\\EDIT.bin", 0},
    {"\\??\\C:\\KONAMI\\Test\\OPTION.bin", 0},
    {"\\??\\C:\\KONAMI\\Test\\settings.dat.old", 0},
    {"\\??\\C:\\KONAMI\\Test\\settings.dat:stream", 0},
    {"\\??\\C:\\KONAMI\\Test\\settings.dat\\", 0},
    {"\\??\\C:\\KONAMI\\Test", 0},
    {"\\??\\C:\\KONAMI\\Test\\", 0},
    {"\\??\\C:\\KONAMI\\.\\settings.dat", 0},
    {"\\??\\C:\\KONAMI\\..\\settings.dat", 0},
    {"\\??\\C:\\KONAMI\\Test\\..\\settings.dat", 0},
    {"\\??\\C:\\KONAMI\\Test.\\settings.dat", 0},
    {"\\??\\C:\\KONAMI\\Test \\settings.dat", 0},
    {"\\??\\C:\\KONAMI\\\\settings.dat", 0},
    {"\\??\\C:\\KONAMI\\Bad:Name\\settings.dat", 0},
    {"\\??\\C:\\KONAMI\\Bad/Name\\settings.dat", 0},
    {"\\??\\C:\\KONAMI\\Test\\dir\\settings.dat", 0},
    {"\\??\\C:\\AnotherGame\\KONAMI\\Test\\settings.dat", 0},
    {"\\??\\C:\\users\\..\\Documents\\KONAMI\\Test\\settings.dat", 0},
    {"\\??\\C:\\users\\a\\Downloads\\KONAMI\\Test\\settings.dat", 0},
    {"\\??\\D:\\KONAMI\\Test\\settings.dat", 0},
    {"\\??\\UNC\\C:\\KONAMI\\Test\\settings.dat", 0},
    {"KONAMI\\Test\\settings.dat", 0},
    {"settings.dat", 0}, {"", 0}
};
static UNICODE_STRING wide(const char *s, WCHAR *buffer)
{
    unsigned n = strlen(s);
    /* Deliberately no NUL terminator in the declared string. */
    for (unsigned i = 0; i < n; i++) buffer[i] = (unsigned char)s[i];
    buffer[n] = '!';
    return (UNICODE_STRING){n * 2, n * 2, buffer};
}
int main(void)
{
    WCHAR buffer[1024];
    for (unsigned i = 0; i < sizeof(cases)/sizeof(*cases); i++)
    {
        UNICODE_STRING name = wide(cases[i].path, buffer), owned = {0};
        OBJECT_ATTRIBUTES attr = {NULL, &name};
        assert(pes_settings_is_patch(buffer, name.Length / 2) == cases[i].match);
        assert(pes_settings_route(&attr, &owned) == 0);
        if (cases[i].match)
        {
            assert(attr.ObjectName == &owned && owned.MaximumLength == owned.Length + 2);
            assert(pes_settings_ascii(owned.Buffer, owned.Length / 2,
                "\\??\\C:\\KONAMI\\Pro Evolution Soccer 2013\\settings.dat"));
            assert(!owned.Buffer[owned.Length / 2]);
            WCHAR *first = owned.Buffer;
            assert(!pes_settings_route(&attr, &owned) && owned.Buffer == first);
            release(owned.Buffer);
        }
        else assert(attr.ObjectName == &name && !owned.Buffer);
        assert(!outstanding && !reports);
    }
    UNICODE_STRING name = wide(cases[0].path, buffer), owned = {0};
    OBJECT_ATTRIBUTES attr = {NULL, &name};
    fail_alloc = 1;
    assert(pes_settings_route(&attr, &owned) == STATUS_NO_MEMORY);
    assert(attr.ObjectName == &name && !owned.Buffer && !outstanding);
    fail_alloc = 0;
    attr.RootDirectory = (void *)1;
    assert(!pes_settings_route(&attr, &owned) && attr.ObjectName == &name);
    attr.RootDirectory = NULL;
    name.Length--;
    assert(!pes_settings_route(&attr, &owned) && attr.ObjectName == &name);
    name.Length++;
    /* Replacing Wine-owned NT names frees exactly the previous buffer. */
    owned = name; owned.Buffer = allocate(name.Length);
    memcpy(owned.Buffer, name.Buffer, name.Length); attr.ObjectName = &owned;
    fail_alloc = 1;
    WCHAR *previous = owned.Buffer;
    assert(pes_settings_route(&attr, &owned) == STATUS_NO_MEMORY && owned.Buffer == previous && outstanding == 1);
    fail_alloc = 0;
    assert(!pes_settings_route(&attr, &owned) && outstanding == 1);
    release(owned.Buffer);
    /* Unterminated Unicode patch name is legal; embedded NUL is not. */
    name = wide(cases[0].path, buffer); buffer[14] = 0x65e5;
    assert(pes_settings_is_patch(buffer, name.Length / 2));
    buffer[14] = 0; assert(!pes_settings_is_patch(buffer, name.Length / 2));
    debug = 1;
    for (unsigned i = 0; i < 20; i++)
    {
        name = wide(cases[0].path, buffer); owned = (UNICODE_STRING){0}; attr.ObjectName = &name;
        assert(!pes_settings_route(&attr, &owned)); release(owned.Buffer);
    }
    assert(reports == 8 && !outstanding);
    puts("PASS settings-only routing, DOS aliases/case/Unicode, unchanged save paths, bounded debug, owned-buffer cleanup and allocation failure");
}
