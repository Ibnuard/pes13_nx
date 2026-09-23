/* Exercise native-map collisions, query/allocation failures and initialization
 * order; the production guard is compiled as a separate translation unit. */
#include <switch.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct VirtmemReservation { int held; } reservation;
static int scenario, locked, add_calls, applet_calls, query_calls, log_calls;
static char logs[1024];
extern Result __wrap_appletInitialize(void);
extern int wine_nx_pes13_preload_report(void);

void virtmemLock(void) { assert(!locked); locked = 1; }
void virtmemUnlock(void) { assert(locked); locked = 0; }

Result svcQueryMemory(MemoryInfo *info, u32 *page, uint64_t cursor)
{
    assert(locked);
    query_calls++;
    *page = 0;
    *info = (MemoryInfo){.addr = 0, .size = 0x20000000, .type = MemType_Unmapped};
    if (scenario == 3) return 0xdead;
    if (scenario == 7) { info->size = 0; return 0; }
    if (scenario == 2 || (scenario == 5 && applet_calls))
    {
        /* The first page is free; an occupied range inside the image is fatal. */
        if (cursor < 0x800000) info->size = 0x800000;
        else *info = (MemoryInfo){.addr = 0x800000, .size = 0x100000, .type = 3, .perm = 5};
    }
    if (scenario == 6)
    {
        /* Multiple adjacent unmapped entries must all be traversed. */
        info->addr = cursor;
        info->size = 0x200000;
    }
    return 0;
}

VirtmemReservation *virtmemAddReservation(void *start, size_t size)
{
    assert(locked && !applet_calls && !add_calls);
    assert((uintptr_t)start == 0x400000 && size == 0x189a000);
    add_calls++;
    if (scenario == 4) return NULL;
    reservation.held = 1;
    return &reservation;
}

Result __real_appletInitialize(void)
{
    assert(!locked && query_calls);
    if (scenario == 1 || scenario == 5 || scenario == 6) assert(reservation.held);
    else assert(!reservation.held);
    applet_calls++;
    return 0x55;
}

void wine_nx_runtime_trace(const char *message)
{
    assert(!locked);
    assert(strlen(logs) + strlen(message) + 2 < sizeof(logs));
    strcat(logs, message);
    strcat(logs, "\n");
    log_calls++;
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    scenario = atoi(argv[1]);
    assert(scenario >= 1 && scenario <= 7);
    assert(__wrap_appletInitialize() == 0x55);
    assert(__wrap_appletInitialize() == 0x55);
    assert(applet_calls == 2 && add_calls <= 1);
    int ready = wine_nx_pes13_preload_report();
    assert(ready == (scenario == 1 || scenario == 6));
    assert(log_calls == (ready ? 1 : 2));
    assert(strstr(logs, "hook_calls=2"));
    if (scenario == 2 || scenario == 5) assert(strstr(logs, "already mapped"));
    if (scenario == 3) assert(strstr(logs, "query_rc=0x0000dead"));
    if (scenario == 4) assert(strstr(logs, "reservation allocation failed"));
    if (scenario == 7) assert(strstr(logs, "invalid kernel memory range"));
    printf("preload guard scenario %d passed\n", scenario);
    return 0;
}
