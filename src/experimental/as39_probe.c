/* SPDX-License-Identifier: MIT
 * Isolated address-space experiment. Never loads or edits a game or prefix.
 * Exercise the same AliasCode syscall pair as Wine and the real FEX JIT host.
 */
#include <switch.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "horizon_host.h"

#define PAGE 4096u
#define PES_BASE ((uintptr_t)0x00400000)
#define PES_SIZE ((size_t)0x0189a000)
#define PROBE_DIR "sdmc:/switch/pes13-as39-probe"
size_t __nx_heap_size = 64u * 1024u * 1024u;
static FILE *log_file;
static int console_ready, cleanup_failed;
static VirtmemReservation *pes_guard;

static void record(const char *format, ...) {
    char line[512];
    va_list args;
    va_start(args, format);
    vsnprintf(line, sizeof(line), format, args);
    va_end(args);
    puts(line);
    if (log_file) { fprintf(log_file, "%s\n", line); fflush(log_file); }
    if (console_ready) consoleUpdate(NULL);
}
static void jit_record(const char *message) { record("%s", message); }

/* Query the complete range. An existing mapping is never replaced. */
static int range_free(uintptr_t address, size_t size) {
    if (!size || size > UINTPTR_MAX - address) return 0;
    uintptr_t end = address + size;
    while (address < end) {
        MemoryInfo info;
        u32 page_info;
        if (R_FAILED(svcQueryMemory(&info, &page_info, address)) ||
            info.type != MemType_Unmapped || !info.size || info.addr > address ||
            info.size > UINTPTR_MAX - info.addr || info.addr + info.size <= address) return 0;
        address = info.addr + info.size;
    }
    return 1;
}

/* Match the production early guard on 32-bit, before applet/HID allocations.
 * On 39-bit this is deliberately NOT treated as a successful kernel mapping. */
extern Result __real_appletInitialize(void);
Result __wrap_appletInitialize(void) {
    if (!pes_guard) {
        virtmemLock();
        if (range_free(PES_BASE, PES_SIZE))
            pes_guard = virtmemAddReservation((void *)PES_BASE, PES_SIZE);
        virtmemUnlock();
    }
    return __real_appletInitialize();
}

/* 1 = mapped/read/written/released, 0 = kernel rejected the mapping,
 * -1 = inconclusive setup/permission/data/cleanup failure. */
static __attribute__((noinline,used)) int test_mapping(const char *tag, uintptr_t target,
                                                       size_t size, int execute) {
    unsigned char *backing = aligned_alloc(PAGE, size);
    if (!backing) { record("[MAP] %s backing allocation failed size=%zu", tag, size); return -1; }
    for (size_t i = 0; i < size; i += PAGE) *(uint32_t *)(backing + i) = 0x132039;
    if (execute) {
        /* SetProcessMemoryPermission(Rw) converts AliasCode to AliasCodeData,
         * which cannot be made executable with that syscall again. Prepare
         * native code in the source first, then map straight to RX. FEX's
         * writable JIT uses the separate CodeMemory test below. */
        uint32_t *code = (uint32_t *)backing;
        code[0] = 0x52800540; /* mov w0, #42 */
        code[1] = 0xd65f03c0; /* ret */
        armDCacheFlush(backing, size);
    }
    VirtmemReservation *reservation = NULL;
    int borrowed = target == PES_BASE && size <= PES_SIZE && pes_guard;
    virtmemLock();
    if (!target) target = (uintptr_t)virtmemFindCodeMemory(size, PAGE);
    if (target && range_free(target, size))
        reservation = borrowed ? pes_guard : virtmemAddReservation((void *)target, size);
    virtmemUnlock();
    if (!reservation) {
        record("[MAP] %s no free target/reservation at %p size=%zu", tag, (void *)target, size);
        free(backing);
        return -1;
    }

    Handle process = envGetOwnProcessHandle();
    Result rc = svcMapProcessCodeMemory(process, target, (u64)backing, size);
    record("[MAP] %s dst=%p src=%p bytes=%zu rc=%08x", tag, (void *)target, backing, size, rc);
    int result = 0, mapped = R_SUCCEEDED(rc);
    if (mapped) {
        result = -1;
        rc = svcSetProcessMemoryPermission(process, target, size, execute ? Perm_Rx : Perm_Rw);
        record("[%s] %s rc=%08x", execute ? "RX" : "RW", tag, rc);
        if (R_SUCCEEDED(rc)) {
            result = 1;
            if (execute) {
                armICacheInvalidate((void *)target, size);
                if (((uint32_t (*)(void))target)() != 42) result = -1;
            } else {
                for (size_t i = 0; i < size; i += PAGE) {
                    volatile uint32_t *word = (volatile uint32_t *)(target + i);
                    if (*word != 0x132039) result = -1;
                    *word = 0x392013;
                }
            }
        }
        rc = svcUnmapProcessCodeMemory(process, target, (u64)backing, size);
        record("[UNMAP] %s rc=%08x", tag, rc);
        if (R_FAILED(rc)) {
            /* Never free backing or reservation while a live alias may exist. */
            cleanup_failed = 1;
            record("[MAP] %s cleanup failed; retaining resources until process exit", tag);
            return -1;
        }
        if (result == 1 && !execute) {
            for (size_t i = 0; i < size; i += PAGE)
                if (*(volatile uint32_t *)(backing + i) != 0x392013) result = -1;
        }
    }
    if (!borrowed) { virtmemLock(); virtmemRemoveReservation(reservation); virtmemUnlock(); }
    free(backing);
    record("[MAP-RESULT] %s %s", tag, result == 1 ? "PASS" : result == 0 ? "REJECTED" : "INCONCLUSIVE");
    return result;
}

static __attribute__((noinline,used)) int test_fex_jit(void) {
    const struct pes13_fex_host *host = pes13_fex_native_host();
    void *rx = host->allocate_code(PAGE);
    if (!rx) return 0;
    uint32_t *rw = host->write_alias(rx, PAGE);
    int pass = rw && rw != rx;
    if (pass) {
        rw[0] = 0x52800540; rw[1] = 0xd65f03c0;
        pass = host->flush_code(rx, 8) && ((uint32_t (*)(void))rx)() == 42;
        if (pass) {
            rw[0] = 0x52800aa0; /* patch to return 85 through the same RX pointer */
            pass = host->flush_code(rx, 4) && ((uint32_t (*)(void))rx)() == 85;
        }
    }
    record("[JIT] rx=%p rw=%p rx_above_4g=%d execute_and_backpatch=%s", rx, rw,
           (uintptr_t)rx >= (1ull << 32), pass ? "PASS" : "FAIL");
    if (host->release_code(rx) != 1) { cleanup_failed = 1; pass = 0; }
    return pass;
}

static uint16_t get16(const unsigned char *p) { return p[0] | (uint16_t)p[1] << 8; }
static uint32_t get32(const unsigned char *p) { return get16(p) | (uint32_t)get16(p + 2) << 16; }

/* Header inspection only: no game code is executed or patched. */
static void inspect_game(void) {
    const char *paths[] = {
        "sdmc:/switch/pes13-fex/drive_c/PES13/pes2013.exe",
        "sdmc:/switch/pes13-fex/drive_c/Program Files/KONAMI/Pro Evolution Soccer 2013/pes2013.exe",
        "sdmc:/switch/pes13-fex/drive_c/KONAMI/Pro Evolution Soccer 2013/pes2013.exe"
    };
    for (size_t i = 0; i < sizeof(paths) / sizeof(paths[0]); ++i) {
        FILE *file = fopen(paths[i], "rb");
        if (!file) continue;
        unsigned char dos[64], nt[248];
        int valid = fread(dos, 1, sizeof(dos), file) == sizeof(dos) && get16(dos) == 0x5a4d;
        uint32_t off = valid ? get32(dos + 0x3c) : 0;
        valid = valid && off >= sizeof(dos) && off <= 16u * 1024u * 1024u &&
            !fseek(file, off, SEEK_SET) && fread(nt, 1, sizeof(nt), file) == sizeof(nt) &&
            get32(nt) == 0x4550 && get16(nt + 4) == 0x14c && get16(nt + 20) >= 224 &&
            get16(nt + 24) == 0x10b && get32(nt + 24 + 92) >= 6;
        fclose(file);
        record("[PE] read_only=%s valid_PE32=%d", paths[i], valid);
        if (valid) {
            record("[PE] base=%08x image_size=%08x relocs_stripped=%d reloc_rva=%08x reloc_bytes=%u",
                   get32(nt + 52), get32(nt + 80), !!(get16(nt + 22) & 1),
                   get32(nt + 160), get32(nt + 164));
            record("[PE] mapping probes use reference PES base=00400000 image_size=0189a000");
        }
        return;
    }
    record("[PE] game not found in standard paths; probing reference PES13 image range only");
}

static u64 info_value(const char *name, InfoType type, Result *result) {
    u64 value = 0;
    *result = svcGetInfo(&value, type, CUR_PROCESS_HANDLE, 0);
    record("[INFO] %s=%#llx rc=%08x", name, (unsigned long long)value, *result);
    return value;
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    console_ready = consoleInit(NULL) != NULL;
    u64 base = 0, size = 0, alias = 0;
    Result br = svcGetInfo(&base, InfoType_AslrRegionAddress, CUR_PROCESS_HANDLE, 0);
    Result sr = svcGetInfo(&size, InfoType_AslrRegionSize, CUR_PROCESS_HANDLE, 0);
    Result ar = svcGetInfo(&alias, InfoType_AliasRegionSize, CUR_PROCESS_HANDLE, 0);
    int mode = !br && !sr && !ar && size && base <= UINT64_MAX - size ?
        (base + size == (1ull << 39) ? 39 : base + size == (1ull << 32) && !alias ? 32 : 0) : 0;
    mkdir(PROBE_DIR, 0777);
    char path[192], previous[192];
    snprintf(path, sizeof(path), PROBE_DIR "/as%d-probe.log", mode);
    snprintf(previous, sizeof(previous), PROBE_DIR "/as%d-probe.previous.log", mode);
    /* Only our own diagnostic file rotates; the game directory is read-only. */
    rename(path, previous);
    log_file = fopen(path, "w");
    record("PES13 AS39 experiment 0.1.1 | memory/JIT preflight, NOT a game runtime");
    record("[MODE] bits=%d native=AArch64 aslr=%#llx+%#llx alias=%#llx rc=%x/%x/%x guard=%s",
           mode, (unsigned long long)base, (unsigned long long)size, (unsigned long long)alias,
           br, sr, ar, pes_guard ? "software-only" : "absent");
    if (!log_file) record("[LOG] Cannot open diagnostic file; screen output only");
    Result rc;
    info_value("heap_base", InfoType_HeapRegionAddress, &rc);
    info_value("heap_size", InfoType_HeapRegionSize, &rc);
    info_value("stack_base", InfoType_StackRegionAddress, &rc);
    info_value("stack_size", InfoType_StackRegionSize, &rc);
    info_value("budget", InfoType_TotalMemorySize, &rc);
    info_value("used", InfoType_UsedMemorySize, &rc);
    inspect_game();
    int caps = envGetOwnProcessHandle() != INVALID_HANDLE &&
        envIsSyscallHinted(0x73) && envIsSyscallHinted(0x77) && envIsSyscallHinted(0x78);
    record("[CAPS] own_handle=%x alias_code=%d fex_code_memory=%d", envGetOwnProcessHandle(), caps,
           envIsSyscallHinted(0x4b) && envIsSyscallHinted(0x4c));
    if (!mode || !caps) {
        record("[SUMMARY] INCONCLUSIVE: use one of the included HOME forwarders");
    } else {
        int fixed = test_mapping("pes-fixed-page", PES_BASE, PAGE, 0);
        int full = -1, low = -1, native = -1, jit = 0;
        if (!cleanup_failed && fixed == 1) full = test_mapping("pes-fixed-image", PES_BASE, PES_SIZE, 0);
        if (!cleanup_failed) low = test_mapping("relocatable-guest-window", 0x10000000, PES_SIZE, 0);
        if (!cleanup_failed) native = test_mapping("native-alias-code", 0, PAGE, 1);
        if (!cleanup_failed) { pes13_fex_set_logger(jit_record); jit = test_fex_jit(); }
        record("[RESULTS] fixed_page=%d fixed_image=%d low_window=%d native=%d jit=%d cleanup_failed=%d",
               fixed, full, low, native, jit, cleanup_failed);
        if (!cleanup_failed && fixed == 0 && low == 1 && native == 1 && jit && PES_BASE < base)
            record("[SUMMARY] BLOCKED: fixed PES address rejected; higher mappings and FEX JIT work");
        else if (!cleanup_failed && fixed == 1 && full == 1 && native == 1 && jit)
            record("[SUMMARY] MAPPING-PASS: prerequisites only; PES/Wine execution NOT tested");
        else record("[SUMMARY] INCONCLUSIVE: inspect per-stage results; no game execution attempted");
    }
    record("Log: %s", path);
    record("Press + to exit. This experiment does not change PES13 or F1 files.");
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
