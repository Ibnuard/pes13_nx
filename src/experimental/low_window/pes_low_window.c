/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Validate the ABI before Wine creates guest views. Native libnx allocations
 * are kept above 4 GiB by this build's single virtmem manager from virtmemSetup.
 * Probes alias high backing: they allocate one physical page, not two.
 */
#include <switch.h>
#include <stdio.h>
#include <stdlib.h>
#include "pes_low_window.h"

extern char *fake_heap_start, *fake_heap_end;
extern void wine_nx_runtime_trace(const char *);
static int fxt_checked, fxt_ready, fxt_retained;
static char fxt_error[256] = "memory preflight not run";
static uint64_t fxt_budget, fxt_heap;

static int fxt_fail(const char *stage, Result rc, uintptr_t address) {
    snprintf(fxt_error, sizeof(fxt_error), "%s: rc=%08x address=%llx retained=%d",
             stage, rc, (unsigned long long)address, fxt_retained);
    return 0;
}

static int fxt_guest_free(void) {
    uintptr_t at = FXT_GUEST_BASE;
    while (at < FXT_NATIVE_BASE) {
        MemoryInfo info; u32 page;
        Result rc = svcQueryMemory(&info, &page, at);
        if (R_FAILED(rc)) return fxt_fail("guest range query", rc, at);
        if (info.type != MemType_Unmapped || info.addr > at || !info.size ||
            info.size > UINT64_MAX - info.addr || info.addr + info.size <= at)
            return fxt_fail("guest range occupied/invalid", 0, at);
        at = info.addr + info.size;
    }
    return 1;
}

static __attribute__((noinline,used)) int fxt_probe_page(uintptr_t address, int executable) {
    const size_t size = 4096;
    u32 *backing = aligned_alloc(size, size);
    if (!backing) return fxt_fail("probe backing", 0, address);
    if ((uintptr_t)backing < FXT_NATIVE_BASE || (uintptr_t)backing > FXT_HOST_END - size) {
        free(backing);
        return fxt_fail("probe backing outside native range", 0, address);
    }
    backing[0] = executable ? 0x52800540 : 0x1239; /* mov w0,#42 */
    backing[1] = 0xd65f03c0; /* ret */
    if (executable) armDCacheFlush(backing, size);
    const Handle process = envGetOwnProcessHandle();
    const char *stage = "map";
    Result rc = svcMapProcessCodeMemory(process, address, (u64)backing, size);
    int passed = 0;
    if (R_SUCCEEDED(rc)) {
        stage = "initial permission";
        rc = svcSetProcessMemoryPermission(process, address, size, executable ? Perm_Rx : Perm_Rw);
        if (R_SUCCEEDED(rc) && !executable) {
            stage = "data NONE";
            rc = svcSetMemoryPermission((void *)address, size, Perm_None);
            if (R_SUCCEEDED(rc)) {
                stage = "data RW restore";
                rc = svcSetMemoryPermission((void *)address, size, Perm_Rw);
            }
        }
        if (R_SUCCEEDED(rc)) {
            stage = "readback/execute";
            if (executable) {
                armICacheInvalidate((void *)address, size);
                passed = ((unsigned (*)(void))address)() == 42;
            } else {
                passed = *(volatile u32 *)address == 0x1239;
                *(volatile u32 *)address = 0x3912;
            }
        }
        Result unmap = svcUnmapProcessCodeMemory(process, address, (u64)backing, size);
        if (R_FAILED(unmap)) {
            fxt_retained = 1; /* Kernel still owns these pages; never free them. */
            return fxt_fail("unmap; backing retained", unmap, address);
        }
        if (passed && !executable) passed = backing[0] == 0x3912;
    }
    free(backing);
    return passed ? 1 : fxt_fail(stage, rc, address);
}

int fxt_low_window_preflight(void) {
    if (fxt_checked) return fxt_ready;
    fxt_checked = 1;
    u64 base = 0, size = 0, region = 0;
    if (R_FAILED(svcGetInfo(&base, InfoType_AslrRegionAddress, CUR_PROCESS_HANDLE, 0)) ||
        R_FAILED(svcGetInfo(&size, InfoType_AslrRegionSize, CUR_PROCESS_HANDLE, 0)) ||
        !fxt_low_window_layout(base, size)) return fxt_fail("low-window ABI unavailable", 0, base);
    if (R_FAILED(svcGetInfo(&fxt_budget, InfoType_TotalMemorySize, CUR_PROCESS_HANDLE, 0)))
        return fxt_fail("process budget query", 0, 0);
    static const InfoType ids[] = {InfoType_HeapRegionAddress, InfoType_AliasRegionAddress, InfoType_StackRegionAddress};
    for (unsigned i = 0; i < sizeof(ids) / sizeof(ids[0]); ++i) {
        Result rc = svcGetInfo(&region, ids[i], CUR_PROCESS_HANDLE, 0);
        if (R_FAILED(rc) || region < FXT_NATIVE_BASE || region >= FXT_HOST_END)
            return fxt_fail("native region is not high", rc, region);
    }
    if ((uintptr_t)fake_heap_start < FXT_NATIVE_BASE || fake_heap_end <= fake_heap_start ||
        (uintptr_t)fake_heap_end > FXT_HOST_END || (uintptr_t)&base < FXT_NATIVE_BASE ||
        (uintptr_t)armGetTls() < FXT_NATIVE_BASE || (uintptr_t)fxt_low_window_preflight < FXT_NATIVE_BASE)
        return fxt_fail("native code/heap/stack/TLS is not high", 0, (uintptr_t)fake_heap_start);
    fxt_heap = fake_heap_end - fake_heap_start;
    if (envGetOwnProcessHandle() == INVALID_HANDLE || !envIsSyscallHinted(0x02) ||
        !envIsSyscallHinted(0x73) || !envIsSyscallHinted(0x77) || !envIsSyscallHinted(0x78))
        return fxt_fail("required mapping capability missing", 0, 0);
    virtmemLock();
    fxt_ready = fxt_guest_free() && fxt_probe_page(0x400000, 1) &&
        fxt_probe_page(FXT_GUEST_BASE, 0) && fxt_probe_page(FXT_NATIVE_BASE - 4096, 0) && fxt_guest_free();
    virtmemUnlock();
    if (fxt_ready) fxt_error[0] = 0;
    return fxt_ready;
}

const char *fxt_low_window_error(void) { return fxt_error; }
void fxt_low_window_report(void) {
    char line[320];
    snprintf(line, sizeof(line), "[PES13-LOWVA] v1 ready=%d budget_mib=%llu heap_mib=%llu native_floor=0x100000000 guest_base=0x200000 error=%s",
             fxt_ready, (unsigned long long)(fxt_budget >> 20), (unsigned long long)(fxt_heap >> 20), fxt_error);
    wine_nx_runtime_trace(line);
}
