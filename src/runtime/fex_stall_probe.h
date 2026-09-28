/* FEX-only, included at the end of Wine-NX thread_profile.c.
 * A bounded observer for a stopped presentation stream. Never starts the
 * continuous Box64 sampler, and never uses Box64's guest register mapping. */
#include "horizon_host.h"
#include "horizon_stall.h"

static struct nx_prof_row fex_stall_targets[4]; /* protected by profile_mutex */

static void wine_nx_fex_stall_remove(Handle handle)
{
    unsigned i;
    /* Caller already holds profile_mutex during thread unregister. */
    for (i = 0; i < 4; ++i)
        if (fex_stall_targets[i].handle == handle) fex_stall_targets[i].handle = 0;
}

static void wine_nx_fex_stall_targets(const struct nx_prof_row *rows, unsigned count)
{
    unsigned i, n = 0;
    pthread_mutex_lock(&profile_mutex);
    memset(fex_stall_targets, 0, sizeof(fex_stall_targets));
    /* Keep main even if blocked; fill remaining slots from busiest Wine threads. */
    for (i = 0; i < count && n < 4; ++i)
        if (rows[i].kind == 'w' && rows[i].tid == 4) fex_stall_targets[n++] = rows[i];
    for (i = 0; i < count && n < 4; ++i)
        if (rows[i].kind == 'w' && rows[i].tid != 4 && rows[i].permille >= 30)
            fex_stall_targets[n++] = rows[i];
    pthread_mutex_unlock(&profile_mutex);
}

static int fex_stall_read(uint64_t address, void *dest, size_t length)
{
    MemoryInfo info;
    if (!address || length > UINT64_MAX - address || !readable(address, &info) ||
        address < info.addr || address - info.addr > info.size ||
        length > info.size - (address - info.addr)) return 0;
    memcpy(dest, (const void *)(uintptr_t)address, length);
    return 1;
}

struct fex_stall_capture {
    unsigned tid, round;
    Result pause, read, resume;
    uint64_t pc, lr, state, block, last_rip, guest_block;
    uint64_t callers[NX_PROF_DEPTH], regs[29];
    unsigned caller_count, words_valid, is_jit, state_valid;
    uint32_t words[4];
};

void wine_nx_fex_stall_probe(unsigned presents, unsigned seconds)
{
    static struct pes13_fex_stall_gate gate;
    struct fex_stall_capture captured[8] = {{0}};
    unsigned i, round, n = 0;
    char line[960];
    if (!pes13_fex_stall_due(&gate, presents, seconds)) return;
    if (!envIsSyscallHinted(0x32) || !envIsSyscallHinted(0x33)) {
        wine_nx_runtime_trace("[FEX3-HANG] snapshot unavailable: pause/context SVC not granted");
        return;
    }

    for (round = 0; round < 2; ++round) {
        /* Exiting registered threads cannot close their handles until this
         * mutex is released. Each successful pause has one immediate resume. */
        pthread_mutex_lock(&profile_mutex);
        for (i = 0; i < 4; ++i) {
            const struct nx_prof_row *target = &fex_stall_targets[i];
            struct fex_stall_capture *out;
            ThreadContext ctx;
            unsigned tries;
            if (!target->handle) continue;
            out = &captured[n++];
            out->tid = target->tid;
            out->round = round;
            out->pause = svcSetThreadActivity(target->handle, ThreadActivity_Paused);
            if (R_FAILED(out->pause)) continue;
            for (tries = 0; R_FAILED(out->read = svcGetThreadContext3(&ctx, target->handle)) && tries < 4; ++tries)
                svcSleepThread(0);
            if (R_SUCCEEDED(out->read)) {
                void *alias;
                uint32_t tail_offset;
                struct pes13_fex_observed_tail tail;
                out->pc = ctx.pc.x;
                out->lr = ctx.lr;
                out->state = ctx.cpu_gprs[28].x;
                for (tries = 0; tries < 29; ++tries) out->regs[tries] = ctx.cpu_gprs[tries].x;
                out->caller_count = walk_callers(&ctx, out->callers);
                out->words_valid = fex_stall_read(out->pc, out->words, sizeof(out->words));
                alias = pes13_fex_native_host()->write_alias((void *)(uintptr_t)out->pc, 4);
                out->is_jit = alias && alias != (void *)(uintptr_t)out->pc;
                if (out->is_jit && out->state <= UINT64_MAX - PES13_FEX_FRAME_RIP_OFFSET) {
                    out->state_valid = fex_stall_read(out->state + PES13_FEX_FRAME_BLOCK_OFFSET, &out->block, 8) &&
                        fex_stall_read(out->state + PES13_FEX_FRAME_RIP_OFFSET, &out->last_rip, 8);
                    /* Read a block label, not an exact guest PC. Validate all
                     * offsets/ranges before looking at a JIT's inline tail. */
                    if (out->state_valid && fex_stall_read(out->block, &tail_offset, 4) &&
                        tail_offset < 16 * 1024 * 1024 && out->block <= UINT64_MAX - tail_offset &&
                        fex_stall_read(out->block + tail_offset, &tail, sizeof(tail)) &&
                        tail.size <= 16 * 1024 * 1024 && tail.size >= tail_offset + sizeof(tail) &&
                        out->pc >= out->block && out->pc - out->block < tail.size)
                        out->guest_block = tail.rip;
                }
            }
            out->resume = svcSetThreadActivity(target->handle, ThreadActivity_Runnable);
            /* Never leave a thread paused because the diagnostic read failed. */
            if (R_FAILED(out->resume)) out->resume = svcSetThreadActivity(target->handle, ThreadActivity_Runnable);
        }
        pthread_mutex_unlock(&profile_mutex);
        if (!round) svcSleepThread(2000000); /* two observations, two milliseconds apart */
    }

    /* All observations are complete and all threads resumed before any I/O. */
    snprintf(line, sizeof(line), "[FEX3-HANG] capture=%u seconds=%u presents=%u samples=%u observer=%llx; block labels are not exact guest PCs",
             gate.captures, seconds, presents, n, (unsigned long long)(uintptr_t)&wine_nx_fex_stall_probe);
    wine_nx_runtime_trace(line);
    for (i = 0; i < n; ++i) {
        const struct fex_stall_capture *s = &captured[i];
        unsigned j;
        int len;
        snprintf(line, sizeof(line),
                 "[FEX3-HANG-PC] tid=%u round=%u pause=%x read=%x resume=%x pc=%llx lr=%llx jit=%u state=%llx valid=%u block=%llx guest_block=%llx last_rip=%llx words=%u:%08x,%08x,%08x,%08x",
                 s->tid, s->round, s->pause, s->read, s->resume,
                 (unsigned long long)s->pc, (unsigned long long)s->lr, s->is_jit,
                 (unsigned long long)s->state, s->state_valid, (unsigned long long)s->block,
                 (unsigned long long)s->guest_block, (unsigned long long)s->last_rip,
                 s->words_valid, s->words[0], s->words[1], s->words[2], s->words[3]);
        wine_nx_runtime_trace(line);
        len = snprintf(line, sizeof(line), "[FEX3-HANG-REGS] tid=%u round=%u", s->tid, s->round);
        for (j = 0; j < 29; ++j)
            len += snprintf(line + len, sizeof(line) - len, " x%u=%llx", j, (unsigned long long)s->regs[j]);
        wine_nx_runtime_trace(line);
        len = snprintf(line, sizeof(line), "[FEX3-HANG-CALLERS] tid=%u round=%u", s->tid, s->round);
        for (j = 0; j < s->caller_count; ++j)
            len += snprintf(line + len, sizeof(line) - len, " %llx", (unsigned long long)s->callers[j]);
        wine_nx_runtime_trace(line);
    }
}
