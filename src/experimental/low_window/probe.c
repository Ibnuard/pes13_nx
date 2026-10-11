/* SPDX-License-Identifier: MIT
 * Separate ABI probe; reuses the existing verified AliasCode/JIT exercises.
 * Does not execute or inspect a game and does not change a Wine prefix.
 */
#define main reference_probe_main
#define __wrap_appletInitialize reference_applet_initialize
#include "../as39_probe.c"
#undef main
#undef __wrap_appletInitialize
#undef PROBE_DIR
#define PROBE_DIR "sdmc:/switch/fextendo-memory-probe"

Result __wrap_appletInitialize(void) {
    virtmemLock();
    if (!pes_guard)
        pes_guard = virtmemAddReservation((void *)UINT64_C(0x200000), UINT64_C(0xffe00000));
    virtmemUnlock();
    return __real_appletInitialize();
}

/* 1 = full roundtrip, 0 = mapping rejected, -1 = other failure. A permission
 * failure after a successful map must not count as an expected CONTROL denial. */
static __attribute__((noinline,used)) int roundtrip(uintptr_t target) {
    if (!pes_guard || !range_free(target, PAGE)) return -1;
    unsigned char *backing = aligned_alloc(PAGE, PAGE);
    if (!backing) return -1;
    *(uint32_t *)backing = 0x1239;
    Handle process = envGetOwnProcessHandle();
    Result map = svcMapProcessCodeMemory(process, target, (u64)backing, PAGE);
    int passed = 0;
    if (R_SUCCEEDED(map)) {
        Result protect = svcSetProcessMemoryPermission(process, target, PAGE, Perm_Rw);
        record("[PERM] target=%p api=SetProcessMemoryPermission stage=initial-rw rc=%08x", (void *)target, protect);
        /* The first RW permission converts AliasCode to AliasCodeData, which
         * has CanReprotect but no Code flag. Further data permissions use the
         * current-process API, as in the working Sleeping Dogs low window. */
        if (R_SUCCEEDED(protect)) {
            protect = svcSetMemoryPermission((void *)target, PAGE, Perm_None);
            record("[PERM] target=%p api=SetMemoryPermission stage=none rc=%08x", (void *)target, protect);
            if (R_SUCCEEDED(protect)) {
                protect = svcSetMemoryPermission((void *)target, PAGE, Perm_Rw);
                record("[PERM] target=%p api=SetMemoryPermission stage=restore-rw rc=%08x", (void *)target, protect);
            }
        }
        if (R_SUCCEEDED(protect)) {
            passed = *(volatile uint32_t *)target == 0x1239;
            *(volatile uint32_t *)target = 0x3912;
        }
        Result unmap = svcUnmapProcessCodeMemory(process, target, (u64)backing, PAGE);
        if (R_FAILED(unmap)) {
            cleanup_failed = 1;
            record("[ROUNDTRIP] unmap failed=%08x; retaining backing", unmap);
            return -1;
        }
        passed = passed && *(volatile uint32_t *)backing == 0x3912;
    }
    free(backing);
    record("[ROUNDTRIP] target=%p map=%08x result=%s", (void *)target, map,
           passed ? "PASS" : R_FAILED(map) ? "REJECTED" : "FAIL");
    return R_FAILED(map) ? 0 : passed ? 1 : -1;
}

int main(int argc, char **argv) {
    const char *tag = argc > 1 ? argv[1] : "direct";
    if (strcmp(tag, "control") && strcmp(tag, "optin-a") && strcmp(tag, "optin-b")) tag = "direct";
    const int expected = !strcmp(tag, "optin-a") || !strcmp(tag, "optin-b");
    console_ready = consoleInit(NULL) != NULL;
    mkdir(PROBE_DIR, 0777);
    char path[192], previous[192];
    snprintf(path, sizeof(path), PROBE_DIR "/%s.log", tag);
    snprintf(previous, sizeof(previous), PROBE_DIR "/%s.previous.log", tag);
    rename(path, previous);
    log_file = fopen(path, "w");
    record("FEXTendo memory ABI v1 probe-r2 | %s | no game execution", tag);
    Result rc;
    u64 base = info_value("aslr_base", InfoType_AslrRegionAddress, &rc);
    u64 size = info_value("aslr_size", InfoType_AslrRegionSize, &rc);
    u64 heap = info_value("heap_base", InfoType_HeapRegionAddress, &rc);
    info_value("heap_region_size", InfoType_HeapRegionSize, &rc);
    info_value("budget", InfoType_TotalMemorySize, &rc);
    info_value("used", InfoType_UsedMemorySize, &rc);
    extern char *fake_heap_start, *fake_heap_end;
    record("[NATIVE] pc=%p heap=%p capacity=%llu guest_guard=%d", (void *)&main,
        fake_heap_start, (unsigned long long)((uintptr_t)fake_heap_end - (uintptr_t)fake_heap_start), !!pes_guard);
    int setup = base && base < (UINT64_C(1) << 39) && size == (UINT64_C(1) << 39) - base &&
        (uintptr_t)&main >= UINT64_C(0x100000000) && pes_guard &&
        envGetOwnProcessHandle() != INVALID_HANDLE && envIsSyscallHinted(0x02) && envIsSyscallHinted(0x73) &&
        envIsSyscallHinted(0x77) && envIsSyscallHinted(0x78) && strcmp(tag, "direct");
    int rx = -1, high = -1, low = -1, top = -1, jit = 0;
    if (setup) {
        rx = test_mapping("low-RX-00400000", PES_BASE, PAGE, 1);
        if (!cleanup_failed) low = roundtrip(0x200000);
        if (!cleanup_failed) top = roundtrip(UINT64_C(0xfffff000));
        if (!cleanup_failed) high = test_mapping("native-high-RX", 0, PAGE, 1);
        if (!cleanup_failed) { pes13_fex_set_logger(jit_record); jit = test_fex_jit(); }
    }
    const int result = setup && !cleanup_failed && high == 1 && jit && top == 1 &&
        (expected ? rx == 1 && low == 1 && heap >= UINT64_C(0x100000000)
                  : rx == 0 && low == 0);
    record("[SUMMARY] %s tag=%s optin_expected=%d low_rx=%d low_rw=%d top_rw=%d native_rx=%d jit=%d",
        result ? "PASS" : "FAIL", tag, expected, rx, low, top, high, jit);
    record("This validates mappings only, not PES/Sleeping Dogs gameplay. Press + to exit.");
    if (log_file) { fclose(log_file); log_file = NULL; }
    PadState pad;
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    padInitializeDefault(&pad);
    while (appletMainLoop()) {
        padUpdate(&pad);
        if (padGetButtonsDown(&pad) & HidNpadButton_Plus) break;
        if (console_ready) consoleUpdate(NULL);
        svcSleepThread(20000000);
    }
    if (console_ready) consoleExit(NULL);
    return 0;
}
