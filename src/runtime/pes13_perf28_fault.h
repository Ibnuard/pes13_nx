/* Read-only, bounded evidence for the recurring PES lookup failure.
 * Run after the emulator unwinds, never from a native exception handler.
 * Layout labels below are hypotheses from captured x86 instructions. */
#ifndef PES13_PERF28_FAULT_H
#define PES13_PERF28_FAULT_H
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#define PES28_RECORD_LIMIT 2048u
#define PES28_STRIDE 0xa4u
struct pes28_fault {
    uint32_t status, address, access, eip, esp, eax, ebx, ecx, edx, esi, edi, ebp;
    int identity;
};
typedef int (*pes28_read_fn)(void *, uint32_t, void *, size_t);
typedef void (*pes28_emit_fn)(void *, const char *);
struct pes28_io { pes28_read_fn read; pes28_emit_fn emit; void *opaque; };

static int pes28_read(const struct pes28_io *io, uint64_t at, void *out, size_t n)
{
    if (at > UINT32_MAX || n > UINT64_C(0x100000000) - at) return 0;
    return io->read(io->opaque, (uint32_t)at, out, n);
}

static void pes28_dump(const struct pes28_io *io, const char *kind, uint64_t at, size_t n)
{
    unsigned char bytes[32]; char line[176]; size_t offset, i;
    for (offset = 0; offset < n; offset += sizeof(bytes)) {
        size_t size = n - offset < sizeof(bytes) ? n - offset : sizeof(bytes);
        if (!pes28_read(io, at + offset, bytes, size)) {
            snprintf(line, sizeof(line), "[FAULT28] %s at=%llx read_failed bytes=%zu",
                     kind, (unsigned long long)(at + offset), size);
            io->emit(io->opaque, line); break;
        }
        int used = snprintf(line, sizeof(line), "[FAULT28] %s at=%08llx hex=",
                            kind, (unsigned long long)(at + offset));
        for (i = 0; i < size; ++i)
            used += snprintf(line + used, sizeof(line) - (size_t)used, "%02x", bytes[i]);
        io->emit(io->opaque, line);
    }
}

static int pes28_capture(unsigned int *once, const struct pes28_fault *f, const struct pes28_io *io)
{
    static const unsigned char signature[] = {
        0x83,0xc4,0x08,0x3b,0xc6,0x74,0x05,0x66,0x39,0x28,0x74,0x02,0x33,0xc0,
        0x8d,0x70,0x04,0xc7,0x44,0x24,0x14,0,0,0,0,0x8b,0x2e,0x85,0xed
    };
    unsigned int expected = 0;
    if (!f->identity || f->status != 0xc0000005u || f->eip != 0x115c36fu ||
        f->address != 4 || f->access != 0 ||
        !__atomic_compare_exchange_n(once, &expected, 1, 0, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) return 0;
    char line[256]; unsigned char actual[sizeof(signature)];
    if (!pes28_read(io, 0x115c356u, actual, sizeof(actual)) || memcmp(actual, signature, sizeof(actual))) {
        io->emit(io->opaque, "[FAULT28] skipped: runtime instruction fingerprint mismatch/unreadable");
        return 0;
    }
    snprintf(line, sizeof(line), "[FAULT28] begin read-only inferred-layout limit=%u stride=%u status=%08x access=%u address=%08x",
             PES28_RECORD_LIMIT, PES28_STRIDE, f->status, f->access, f->address);
    io->emit(io->opaque, line);
    snprintf(line, sizeof(line), "[FAULT28] eip=%08x esp=%08x eax=%08x ebx=%08x ecx=%08x edx=%08x esi=%08x edi=%08x ebp=%08x",
             f->eip, f->esp, f->eax, f->ebx, f->ecx, f->edx, f->esi, f->edi, f->ebp);
    io->emit(io->opaque, line);
    pes28_dump(io, "caller", 0x115c300u, 256);
    pes28_dump(io, "lookup", 0x438b40u, 1024);
    pes28_dump(io, "stack", f->esp, 128);
    uint32_t object = 0, count = 0;
    if (!pes28_read(io, (uint64_t)f->esp + 0x1c, &object, sizeof(object)) || !object ||
        !pes28_read(io, (uint64_t)object + 0x30, &count, sizeof(count))) {
        io->emit(io->opaque, "[FAULT28] inferred object/count unavailable; end"); return 1;
    }
    pes28_dump(io, "object", object, 64);
    uint64_t end = (uint64_t)f->ebx + (uint64_t)count * PES28_STRIDE;
    snprintf(line, sizeof(line), "[FAULT28] inferred table=%08x object=%08x count=%u end=%llx key=%04x range_valid=%u",
             f->ebx, object, count, (unsigned long long)end, f->ebp & 0xffffu,
             (unsigned int)(f->ebx != 0 && end <= UINT32_MAX));
    io->emit(io->opaque, line);
    if (!f->ebx || end > UINT32_MAX) {
        io->emit(io->opaque, "[FAULT28] invalid inferred range; end"); return 1;
    }
    uint32_t limit = count < PES28_RECORD_LIMIT ? count : PES28_RECORD_LIMIT;
    uint32_t scanned = 0, matches = 0, descending = 0, failed = 0, hash = 2166136261u;
    uint16_t previous = 0; int have_previous = 0;
    for (uint32_t i = 0; i < limit; ++i) {
        uint32_t at = f->ebx + i * PES28_STRIDE;
        unsigned char record[8]; uint16_t key; uint32_t value;
        if (!pes28_read(io, at, record, sizeof(record))) {
            have_previous = 0;
            if (++failed == 8) break;
            continue;
        }
        memcpy(&key, record, sizeof(key)); memcpy(&value, record + 4, sizeof(value));
        for (size_t j = 0; j < sizeof(record); ++j) hash = (hash ^ record[j]) * 16777619u;
        ++scanned;
        if (have_previous && key < previous) ++descending;
        previous = key; have_previous = 1;
        int match = key == (f->ebp & 0xffffu);
        if (match) ++matches;
        if (i < 16 || (count <= PES28_RECORD_LIMIT && count - i <= 8) || (match && matches <= 8)) {
            snprintf(line, sizeof(line), "[FAULT28] record index=%u at=%08x key=%04x value=%08x match=%d",
                     i, at, key, value, match);
            io->emit(io->opaque, line);
            if (match && matches <= 8) pes28_dump(io, "matching-record", at, 32);
        }
    }
    snprintf(line, sizeof(line), "[FAULT28] end scanned=%u expected=%u capped=%u matches=%u descending_adjacent=%u failed=%u prefix8_hash=%08x; concurrent mutation possible",
             scanned, count, (unsigned int)(count > limit), matches, descending, failed, hash);
    io->emit(io->opaque, line);
    return 1;
}
#endif
