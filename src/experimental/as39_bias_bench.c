/* SPDX-License-Identifier: MIT
 * Isolated fixed-bias feasibility/overhead experiment. Never loads PES/Wine.
 * Reuses the original probe forwarder path, NOT the production NRO path.
 */
#include <switch.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "horizon_host.h"
#include "as39_bias_address.h"

#define PAGE 4096u
#define DATA_MAX (4u * 1024u * 1024u)
#define GUEST_DATA UINT32_C(0x10000000)
#define GUEST_SPACE (UINT64_C(1) << 32)
#define SAMPLES 9u
#define LOG_DIR "sdmc:/switch/pes13-as39-probe"
size_t __nx_heap_size = 64u * 1024u * 1024u;
static FILE *log_file;
static int console_ready, cleanup_failed, cancelled;
static PadState pad;
static volatile uint64_t checksum_sink;

static void record(const char *format, ...) {
    char line[768];
    va_list args;
    va_start(args, format);
    vsnprintf(line, sizeof(line), format, args);
    va_end(args);
    puts(line);
    if (log_file) { fprintf(log_file, "%s\n", line); fflush(log_file); }
    if (console_ready) consoleUpdate(NULL);
}
static void jit_record(const char *line) { record("%s", line); }

typedef uint64_t (*kernel_fn)(uintptr_t bias, uint32_t guest, uint32_t iterations, uint32_t mask);
#define DECLARE(n) extern const unsigned char n[], n##_end[]
DECLARE(as39_chase_direct); DECLARE(as39_chase_bias);
DECLARE(as39_scalar_direct); DECLARE(as39_scalar_bias);
DECLARE(as39_vector_direct); DECLARE(as39_vector_bias);
DECLARE(as39_pair_direct); DECLARE(as39_pair_bias);
DECLARE(as39_atomic_direct); DECLARE(as39_atomic_bias);
DECLARE(as39_wrap_read);
struct kernel {
    const char *name;
    const unsigned char *begin[2], *end[2];
    unsigned steps;
    kernel_fn fn[2];
};
#define KERNEL(n,s) {#n, {as39_##n##_direct, as39_##n##_bias}, \
    {as39_##n##_direct_end, as39_##n##_bias_end}, s, {NULL,NULL}}
static struct kernel kernels[] = {
    KERNEL(chase,8), KERNEL(scalar,1), KERNEL(vector,1), KERNEL(pair,1), KERNEL(atomic,1)
};
#define KERNEL_COUNT (sizeof(kernels) / sizeof(kernels[0]))

static int range_free(uintptr_t address, size_t bytes) {
    if (!bytes || bytes > UINTPTR_MAX - address) return 0;
    uintptr_t end = address + bytes;
    while (address < end) {
        MemoryInfo info;
        u32 page;
        if (R_FAILED(svcQueryMemory(&info, &page, address)) || info.type != MemType_Unmapped ||
            info.addr > address || !info.size || info.size > UINTPTR_MAX - info.addr ||
            info.addr + info.size <= address) return 0;
        address = info.addr + info.size;
    }
    return 1;
}

struct slice { unsigned char *backing; uintptr_t target; size_t bytes; int mapped; };

__attribute__((noinline,noclone)) int as39_bench_guest_span(uintptr_t bias, uint32_t guest,
                                                         uint64_t length, uintptr_t *host) {
    return as39_guest_span(bias, guest, length, host);
}
__attribute__((noinline,noclone)) int as39_bench_host_pointer(uintptr_t bias, uintptr_t host, uint32_t *guest) {
    return as39_host_pointer(bias, host, guest);
}

/* Externally visible for binary fault-injection tests. Backing belongs to the
 * caller and is inaccessible while MapProcessCodeMemory owns its pages. */
__attribute__((noinline)) int as39_bench_unmap(struct slice *s) {
    if (!s->mapped) return 1;
    Result rc = svcUnmapProcessCodeMemory(envGetOwnProcessHandle(), s->target,
                                          (u64)s->backing, s->bytes);
    if (R_FAILED(rc)) {
        cleanup_failed = 1;
        record("[CLEANUP] unmap rc=%08x; retain backing/reservations until process exits", rc);
        return 0;
    }
    s->mapped = 0;
    return 1;
}

__attribute__((noinline)) int as39_bench_map(struct slice *s, uintptr_t target, size_t bytes) {
    if (s->mapped || cleanup_failed || !bytes || bytes > DATA_MAX || (bytes & (PAGE-1)) ||
        (target & (PAGE-1)) || !range_free(target, bytes)) return 0;
    s->target = target;
    s->bytes = bytes;
    Result rc = svcMapProcessCodeMemory(envGetOwnProcessHandle(), target, (u64)s->backing, bytes);
    if (R_FAILED(rc)) { record("[MAP] target=%p size=%zu rc=%08x", (void *)target, bytes, rc); return 0; }
    s->mapped = 1;
    rc = svcSetProcessMemoryPermission(envGetOwnProcessHandle(), target, bytes, Perm_Rw);
    if (R_FAILED(rc)) {
        record("[MAP] permission target=%p rc=%08x", (void *)target, rc);
        as39_bench_unmap(s);
        return 0;
    }
    return 1;
}

static void init_data(void *address, size_t bytes, uint32_t guest) {
    uint32_t *words = address;
    for (size_t i = 0; i < bytes / 4; ++i) words[i] = (uint32_t)i * 2654435761u + 0x132039u;
    uint32_t count = (uint32_t)bytes / 32, mask = count - 1;
    /* An odd affine permutation makes one cycle through every node. */
    for (uint32_t i = 0; i < count; ++i) {
        uint32_t current = (i * 4051u) & mask;
        uint32_t next = ((i + 1) * 4051u) & mask;
        words[current * 8] = guest + next * 32;
    }
}

/* Independent C reference, used only outside timed regions. */
static uint64_t reference(unsigned kind, void *data, uint32_t guest, uint32_t loops, uint32_t mask) {
    uint32_t *words = data, index = 0, sum = 0, lanes[4] = {0};
    uint64_t pair_sum = 0;
    if (!kind) {
        uint32_t ptr = guest;
        for (uint64_t i = 0; i < (uint64_t)loops * 8; ++i) ptr = words[(ptr - guest) / 4];
        return ptr;
    }
    for (uint32_t i = 0; i < loops; ++i) {
        index = (index + 97) & mask;
        if (kind == 1 || kind == 4) sum ^= ++words[index * 8 + 1];
        else if (kind == 2) {
            for (unsigned lane = 0; lane < 4; ++lane) lanes[lane] ^= ++words[index * 8 + 4 + lane];
        } else {
            uint64_t values[2];
            memcpy(values, words + index * 8 + 4, sizeof(values));
            values[0]++; values[1] += 3;
            pair_sum ^= values[0] ^ values[1];
            memcpy(words + index * 8 + 4, values, sizeof(values));
        }
    }
    if (kind == 2) return (uint32_t)(lanes[0] + lanes[1] + lanes[2] + lanes[3]);
    return kind == 3 ? pair_sum : sum;
}

static kernel_fn install_kernel(const struct pes13_fex_host *host, unsigned char *rx,
                                size_t *offset, const unsigned char *start, const unsigned char *end) {
    size_t length = (uintptr_t)end - (uintptr_t)start;
    *offset = (*offset + 63) & ~(size_t)63;
    if (!length || length > PAGE - *offset) return NULL;
    unsigned char *destination = rx + *offset;
    void *rw = host->write_alias(destination, length);
    if (!rw) return NULL;
    memcpy(rw, start, length);
    if (!host->flush_code(destination, length)) return NULL;
    *offset += length;
    return (kernel_fn)destination;
}

static int correctness(struct slice *s, uintptr_t bias, kernel_fn wrap) {
    unsigned char *expected = malloc(PAGE);
    if (!expected) return 0;
    int pass = 1;
    for (unsigned kind = 0; kind < KERNEL_COUNT && pass; ++kind) {
        for (unsigned variant = 0; variant < 2 && pass; ++variant) {
            uintptr_t shift = variant ? bias : 0;
            if (!as39_bench_map(s, shift + GUEST_DATA, PAGE)) { pass = 0; break; }
            init_data((void *)s->target, PAGE, GUEST_DATA);
            init_data(expected, PAGE, GUEST_DATA);
            uint64_t want = reference(kind, expected, GUEST_DATA, 1009, PAGE / 32 - 1);
            uint64_t actual = kernels[kind].fn[variant](shift, GUEST_DATA, 1009, PAGE / 32 - 1);
            pass = actual == want && !memcmp((void *)s->target, expected, PAGE);
            record("[CHECK] kernel=%s variant=%s result=%s", kernels[kind].name,
                   variant ? "bias" : "direct", pass ? "PASS" : "FAIL");
            if (!as39_bench_unmap(s)) pass = 0;
        }
    }
    free(expected);
    if (!pass) return 0;
    /* Separate sparse pages demonstrate fixed PES address, high-bit addresses,
     * and x86-32 wraparound without allocating 4 GiB of physical memory. */
    const uint32_t guests[] = {0x00400000, 0x00010000, 0xfffff000};
    for (unsigned i = 0; i < 3; ++i) {
        uint32_t guest = guests[i], roundtrip = 0;
        uintptr_t native = 0;
        if (!as39_bench_guest_span(bias, guest, PAGE, &native) ||
            !as39_bench_host_pointer(bias, native, &roundtrip) || roundtrip != guest ||
            !as39_bench_map(s, native, PAGE)) return 0;
        volatile uint32_t *word = (volatile uint32_t *)(native + 0x20);
        *word = 0xcafe0000u + i;
        uint32_t input = guest, delta = 0x20;
        if (i == 1) { input = 0xfffffff0; delta = 0x10030; }
        if (i == 2) { input = 0x20; delta = 0xfffff000; }
        pass = wrap(bias, input, delta, 0) == *word;
        record("[CHECK] guest=%08x host=%p u32_wrap_and_roundtrip=%s", guest,
               (void *)native, pass ? "PASS" : "FAIL");
        if (!as39_bench_unmap(s) || !pass) return 0;
    }
    uintptr_t native = 123;
    uint32_t guest = 123;
    pass = as39_bench_guest_span(bias, 0, 0, &native) && !native &&
           as39_bench_host_pointer(bias, 0, &guest) && !guest &&
           !as39_bench_guest_span(bias, 0, 4, &native) &&
           !as39_bench_guest_span(bias, UINT32_MAX, 2, &native) &&
           !as39_bench_host_pointer(bias, bias + GUEST_SPACE, &guest) &&
           !as39_bench_host_pointer(bias, bias, &guest);
    record("[CHECK] null_and_invalid_boundary_rejection=%s", pass ? "PASS" : "FAIL");
    return pass;
}

/* Neither clock service is allowed to change a clock in this program. */
static int clocks_open;
static u32 read_clock(PcvModuleId module) {
    u32 hz = 0;
    if (clocks_open) {
        ClkrstSession session;
        if (R_SUCCEEDED(clkrstOpenSession(&session, module, 3))) {
            if (R_FAILED(clkrstGetClockRate(&session, &hz))) hz = 0;
            clkrstCloseSession(&session);
        }
    }
    return hz;
}

static uint64_t ticks(void) {
    __asm__ __volatile__("dsb ish\n\tisb" ::: "memory");
    return armGetSystemTick();
}

static uint64_t measure(struct kernel *k, unsigned variant, uintptr_t bias,
                        size_t bytes, uint32_t loops, uint64_t *checksum) {
    uintptr_t shift = variant ? bias : 0;
    uint32_t mask = (uint32_t)bytes / 32 - 1;
    init_data((void *)(shift + GUEST_DATA), bytes, GUEST_DATA);
    checksum_sink = k->fn[variant](shift, GUEST_DATA, 128, mask); /* warm code */
    init_data((void *)(shift + GUEST_DATA), bytes, GUEST_DATA);
    uint64_t start = ticks();
    uint64_t result = k->fn[variant](shift, GUEST_DATA, loops, mask);
    uint64_t elapsed = ticks() - start;
    checksum_sink = result;
    *checksum = result;
    return elapsed;
}

static int alive(void) {
    padUpdate(&pad);
    if (!appletMainLoop() || (padGetButtonsDown(&pad) & HidNpadButton_Plus)) cancelled = 1;
    return !cancelled;
}

static double median(double *values, unsigned count) {
    for (unsigned i = 1; i < count; ++i) {
        double value = values[i];
        unsigned j = i;
        while (j && values[j-1] > value) { values[j] = values[j-1]; --j; }
        values[j] = value;
    }
    return values[count / 2];
}

static int benchmark(struct slice *s, uintptr_t bias, int pinned) {
    const size_t footprints[] = {16u * 1024u, 256u * 1024u, DATA_MAX};
    uint64_t freq = armGetSystemTickFreq();
    if (!freq) return 0;
    unsigned completed = 0, changed_clocks = 0;
    for (unsigned f = 0; f < sizeof(footprints)/sizeof(footprints[0]); ++f) {
        size_t bytes = footprints[f];
        for (unsigned kind = 0; kind < KERNEL_COUNT; ++kind) {
            if (!alive()) return 0;
            struct kernel *k = kernels + kind;
            if (!as39_bench_map(s, GUEST_DATA, bytes)) return 0;
            uint32_t loops = 256;
            uint64_t elapsed, checksum;
            do {
                elapsed = measure(k, 0, bias, bytes, loops, &checksum);
                if (elapsed >= freq / 40 || loops >= (1u << 24)) break;
                loops *= 2;
            } while (alive());
            if (!as39_bench_unmap(s) || cancelled) return 0;
            record("[CASE] kernel=%s footprint=%zu loops=%u steps=%llu samples=%u", k->name,
                   bytes, loops, (unsigned long long)loops * k->steps, SAMPLES);
            double direct[SAMPLES], biased[SAMPLES], ratios[SAMPLES];
            unsigned valid = 0;
            for (unsigned sample = 0; sample < SAMPLES; ++sample) {
                if (!alive()) return 0;
                uint64_t times[2] = {0}, sums[2] = {0};
                u32 cpu[3], ram[3];
                cpu[0] = read_clock(PcvModuleId_CpuBus);
                ram[0] = read_clock(PcvModuleId_EMC);
                for (unsigned order = 0; order < 2; ++order) {
                    unsigned variant = (sample + order) & 1; /* AB / BA */
                    uintptr_t target = (variant ? bias : 0) + GUEST_DATA;
                    if (!as39_bench_map(s, target, bytes)) return 0;
                    times[variant] = measure(k, variant, bias, bytes, loops, sums + variant);
                    if (!as39_bench_unmap(s)) return 0;
                    cpu[order + 1] = read_clock(PcvModuleId_CpuBus);
                    ram[order + 1] = read_clock(PcvModuleId_EMC);
                }
                if (!times[0] || !times[1] || sums[0] != sums[1]) {
                    record("[FAIL] timed checksums/timer differ kernel=%s sample=%u", k->name, sample);
                    return 0;
                }
                int changed = (cpu[0] && cpu[1] && cpu[0] != cpu[1]) ||
                    (cpu[1] && cpu[2] && cpu[1] != cpu[2]) ||
                    (ram[0] && ram[1] && ram[0] != ram[1]) ||
                    (ram[1] && ram[2] && ram[1] != ram[2]);
                int known = cpu[0] && cpu[1] && cpu[2] && ram[0] && ram[1] && ram[2];
                record("[SAMPLE] kernel=%s bytes=%zu pair=%u order=%s loops=%u direct_ticks=%llu "
                       "bias_ticks=%llu checksum=%016llx cpu_hz=%u,%u,%u ram_hz=%u,%u,%u clock=%s",
                       k->name, bytes, sample, sample & 1 ? "BA" : "AB", loops,
                       (unsigned long long)times[0], (unsigned long long)times[1],
                       (unsigned long long)sums[0], cpu[0],cpu[1],cpu[2],ram[0],ram[1],ram[2],
                       changed ? "CHANGED" : known ? "STABLE" : "UNKNOWN");
                if (changed) { ++changed_clocks; continue; }
                double scale = 1e9 / ((double)freq * loops * k->steps);
                direct[valid] = times[0] * scale;
                biased[valid] = times[1] * scale;
                ratios[valid++] = (double)times[1] / times[0];
            }
            if (valid) {
                double a = median(direct, valid), b = median(biased, valid), r = median(ratios, valid);
                record("[TIMING] kernel=%s bytes=%zu pairs=%u direct_ns_step=%.3f bias_ns_step=%.3f "
                       "paired_overhead_pct=%.2f ratio_min=%.4f ratio_max=%.4f pinned=%d",
                       k->name, bytes, valid, a, b, 100.0 * (r-1.0), ratios[0], ratios[valid-1], pinned);
                ++completed;
            }
        }
    }
    record("[TIMING-END] cases=%u/15 clock_changed_pairs_excluded=%u pinned=%d", completed, changed_clocks, pinned);
    return completed == 15;
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    console_ready = consoleInit(NULL) != NULL;
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    padInitializeDefault(&pad);
    mkdir(LOG_DIR, 0777);
    rename(LOG_DIR "/as39-bias-bench.log", LOG_DIR "/as39-bias-bench.previous.log");
    log_file = fopen(LOG_DIR "/as39-bias-bench.log", "w");
    record("PES13 fixed-bias addressing benchmark 0.2.0 | NOT a game runtime");
    record("[SCOPE] synthetic ARM64 kernels through FEX native JIT adapter; not FEXCore/Wine/PES");
    record("[METHOD] paired AB/BA; same physical backing remapped low/high; mapping/init/log IO outside timing");
    record("[LIMIT] excludes full register pressure, dispatch, Wine callbacks, faults, SMC and rendering");
    record("Keep CPU/RAM clocks constant. No clock is changed by this NRO. + cancels between samples.");
    u64 base = 0, size = 0;
    Result a = svcGetInfo(&base, InfoType_AslrRegionAddress, CUR_PROCESS_HANDLE, 0);
    Result b = svcGetInfo(&size, InfoType_AslrRegionSize, CUR_PROCESS_HANDLE, 0);
    int mode39 = !a && !b && size && base <= UINT64_MAX-size && base+size == (1ull<<39);
    record("[MODE] bits=%d aslr=%#llx+%#llx rc=%08x/%08x", mode39 ? 39 : 0,
           (unsigned long long)base, (unsigned long long)size, a, b);
    VirtmemReservation *low_res = NULL, *high_res = NULL;
    uintptr_t bias = 0;
    struct slice slice = {0};
    const struct pes13_fex_host *host = pes13_fex_native_host();
    unsigned char *rx = NULL;
    int pass = 0;
    if (!mode39 || envGetOwnProcessHandle() == INVALID_HANDLE || !envIsSyscallHinted(0x73) ||
        !envIsSyscallHinted(0x77) || !envIsSyscallHinted(0x78) ||
        !envIsSyscallHinted(0x4b) || !envIsSyscallHinted(0x4c)) {
        record("[BLOCKED] Open PES13 39-bit Probe from HOME using the supplied AS39 NSP.");
        goto done;
    }
    virtmemLock();
    if (range_free(GUEST_DATA, DATA_MAX)) low_res = virtmemAddReservation((void *)GUEST_DATA, DATA_MAX);
    for (unsigned attempt = 0; low_res && !high_res && attempt < 8; ++attempt) {
        uintptr_t candidate = (uintptr_t)virtmemFindCodeMemory(GUEST_SPACE, PAGE);
        if (!candidate) break;
        if (candidate >= GUEST_SPACE && candidate <= UINTPTR_MAX-GUEST_SPACE && range_free(candidate, GUEST_SPACE)) {
            high_res = virtmemAddReservation((void *)candidate, GUEST_SPACE);
            if (high_res) bias = candidate;
        }
    }
    virtmemUnlock();
    if (!low_res || !high_res) { record("[BLOCKED] cannot reserve low control or full 4-GiB host window"); goto done; }
    record("[WINDOW] bias=%p virtual_bytes=%llu physical_data_max=%u null_page=unmapped",
           (void *)bias, (unsigned long long)GUEST_SPACE, DATA_MAX);
    slice.backing = aligned_alloc(PAGE, DATA_MAX);
    if (!slice.backing) { record("[BLOCKED] backing allocation failed"); goto done; }
    pes13_fex_set_logger(jit_record);
    rx = host->allocate_code(PAGE);
    if (!rx) goto done;
    size_t offset = 0;
    for (unsigned i = 0; i < KERNEL_COUNT; ++i)
        for (unsigned variant = 0; variant < 2; ++variant) {
            struct kernel *k = kernels + i;
            k->fn[variant] = install_kernel(host, rx, &offset, k->begin[variant], k->end[variant]);
            if (!k->fn[variant]) { record("[FAIL] JIT copy/flush"); goto done; }
        }
    kernel_fn wrap = install_kernel(host, rx, &offset, as39_wrap_read, as39_wrap_read_end);
    if (!wrap) goto done;
    record("[JIT] rx=%p above_4g=%d bytes=%zu", rx, (uintptr_t)rx >= GUEST_SPACE, offset);
    if (!correctness(&slice, bias, wrap)) { record("[FAIL] correctness; benchmark skipped"); goto done; }
    record("[CORRECTNESS] PASS all kernels, fixed guest 00400000, wraparound and boundary checks");
    Result pin = svcSetThreadCoreMask(CUR_THREAD_HANDLE, 2, 1u << 2);
    record("[CPU] pin_core=2 rc=%08x tick_frequency=%llu", pin, (unsigned long long)armGetSystemTickFreq());
    if (hosversionAtLeast(8,0,0)) clocks_open = R_SUCCEEDED(clkrstInitialize());
    record("[CLOCK] read_only_available=%d unknown clocks are reported, never inferred", clocks_open);
    pass = benchmark(&slice, bias, R_SUCCEEDED(pin));
done:
    if (!as39_bench_unmap(&slice)) pass = 0;
    if (rx && host->release_code(rx) != 1) { cleanup_failed = 1; pass = 0; }
    if (!cleanup_failed) {
        free(slice.backing);
        virtmemLock();
        if (high_res) virtmemRemoveReservation(high_res);
        if (low_res) virtmemRemoveReservation(low_res);
        virtmemUnlock();
    }
    if (clocks_open) clkrstExit();
    record("[SUMMARY] %s cleanup_failed=%d | synthetic timings only; no game FPS claim",
           cancelled ? "CANCELLED" : pass ? "BENCH-COMPLETE" : "INCOMPLETE", cleanup_failed);
    record("Log: " LOG_DIR "/as39-bias-bench.log");
    record("Press + to exit. Production PES files were not opened.");
    if (log_file) { fclose(log_file); log_file = NULL; }
    while (!cancelled && appletMainLoop()) {
        padUpdate(&pad);
        if (padGetButtonsDown(&pad) & HidNpadButton_Plus) break;
        if (console_ready) consoleUpdate(NULL);
        svcSleepThread(20000000);
    }
    if (console_ready) consoleExit(NULL);
    return 0;
}
