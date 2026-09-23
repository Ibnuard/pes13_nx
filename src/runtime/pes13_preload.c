/* PES13-specific address-space guard for the release-108 native runtime.
 * libnx has initialized TLS, malloc and virtmem before calling appletInitialize.
 * Keep the fixed-base image range out of subsequent libnx random placements.
 * Wine's own fixed mappings can use this software reservation. It neither maps
 * pages nor relocates/unmaps anything already installed by the hosting loader.
 */
#include <switch.h>
#include <stdint.h>
#include <stdio.h>

#define PES_IMAGE_BASE ((uintptr_t)0x00400000)
#define PES_IMAGE_SIZE ((size_t)0x0189a000)

static VirtmemReservation *pes_reservation;
static MemoryInfo blocker;
static Result query_error;
static const char *failure = "guard hook not called";
static unsigned int hook_calls;

extern Result __real_appletInitialize(void);
extern void wine_nx_runtime_trace(const char *message);

/* Caller holds virtmemLock, preventing a competing libnx address selection.
 * Stop at the first occupied range or failed query. Never disturb that mapping.
 */
static int image_range_is_free(void)
{
    const uintptr_t end = PES_IMAGE_BASE + PES_IMAGE_SIZE;
    uintptr_t cursor = PES_IMAGE_BASE;
    u32 page_info;

    while (cursor < end)
    {
        query_error = svcQueryMemory(&blocker, &page_info, cursor);
        if (R_FAILED(query_error))
        {
            failure = "kernel memory query failed";
            return 0;
        }
        if (blocker.type != MemType_Unmapped)
        {
            failure = "image range already mapped";
            return 0;
        }
        if (blocker.addr > cursor || blocker.size == 0 ||
            blocker.addr > UINTPTR_MAX - blocker.size ||
            blocker.addr + blocker.size <= cursor)
        {
            failure = "invalid kernel memory range";
            return 0;
        }
        cursor = blocker.addr + blocker.size;
    }
    return 1;
}

/* --wrap=appletInitialize intercepts the undefined reference from libnx init.o,
 * before applet/HID shared mappings, console buffers and the log-flush thread.
 * Calls from elsewhere are harmless: keep a single lifetime reservation.
 */
Result __wrap_appletInitialize(void)
{
    hook_calls++;
    if (hook_calls == 1)
    {
        virtmemLock();
        if (image_range_is_free())
        {
            pes_reservation = virtmemAddReservation((void *)PES_IMAGE_BASE, PES_IMAGE_SIZE);
            failure = pes_reservation ? NULL : "reservation allocation failed";
        }
        virtmemUnlock();
    }
    return __real_appletInitialize();
}

/* Run before Wine virtual_init, once file logging and the console are ready.
 * Confirm the range survived service/console initialization. A preexisting
 * native mapping is diagnostic evidence, not permission to overwrite it.
 */
int wine_nx_pes13_preload_report(void)
{
    char message[320];
    int ready = 0;

    if (pes_reservation)
    {
        virtmemLock();
        ready = image_range_is_free();
        virtmemUnlock();
    }
    snprintf(message, sizeof(message),
             "[PES13-VA] base=0x%lx size=0x%lx hook_calls=%u guard=%s range=%s",
             (unsigned long)PES_IMAGE_BASE, (unsigned long)PES_IMAGE_SIZE,
             hook_calls, pes_reservation ? "held" : "missing", ready ? "free" : "blocked");
    wine_nx_runtime_trace(message);
    if (!ready)
    {
        snprintf(message, sizeof(message),
                 "[PES13-VA] stopped: %s; query_rc=0x%08x region=0x%llx+0x%llx type=0x%x perm=0x%x",
                 failure ? failure : "unknown", (unsigned int)query_error,
                 (unsigned long long)blocker.addr, (unsigned long long)blocker.size,
                 (unsigned int)blocker.type, (unsigned int)blocker.perm);
        wine_nx_runtime_trace(message);
    }
    return ready;
}
