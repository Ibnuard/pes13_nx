/* LGPL-2.1-or-later. Diagnostic counters only; syscall semantics stay in Wine.
 * One cache line per producer, retained after exit, read by the log flusher.
 * Slot exhaustion and nested observations use the original atomic counters.
 */
#include <stdint.h>
#define FEX_POLL_SLOTS 256
#define FEX_POLL_QPC 0x31u
#define FEX_POLL_DELAY 0x34u
int wine_nx_fex_polling = 1; /* immutable after platform startup */
struct fex_poll_slot { _Alignas(64) unsigned count[2]; };
static struct fex_poll_slot fex_poll_slots[FEX_POLL_SLOTS];
static unsigned fex_poll_claimed;
struct fex_poll_local { unsigned slot, value[2], initialized; volatile unsigned busy; };
static __thread struct fex_poll_local fex_poll_local;

static int fex_poll_count(unsigned id)
{
    if (!wine_nx_fex_polling || (id != FEX_POLL_QPC && id != FEX_POLL_DELAY)) return 0;
    struct fex_poll_local *local = &fex_poll_local;
    if (local->busy) return 0;
    local->busy = 1;
    if (!local->initialized) {
        unsigned slot = __atomic_load_n(&fex_poll_claimed, __ATOMIC_RELAXED);
        while (slot < FEX_POLL_SLOTS &&
               !__atomic_compare_exchange_n(&fex_poll_claimed, &slot, slot + 1, 1,
                                             __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
        local->slot = slot;
        local->initialized = 1;
    }
    if (local->slot >= FEX_POLL_SLOTS) { local->busy = 0; return 0; }
    const unsigned kind = id == FEX_POLL_DELAY;
    /* Only this producer writes its slot. Atomic stores allow concurrent
     * snapshots without read-modify-write contention or delayed tail flushes. */
    __atomic_store_n(&fex_poll_slots[local->slot].count[kind], ++local->value[kind], __ATOMIC_RELAXED);
    local->busy = 0;
    return 1;
}

void wine_nx_fex_poll_totals(unsigned out[2])
{
    unsigned count = __atomic_load_n(&fex_poll_claimed, __ATOMIC_RELAXED);
    if (count > FEX_POLL_SLOTS) count = FEX_POLL_SLOTS;
    out[0] = out[1] = 0;
    for (unsigned i = 0; i < count; ++i)
        for (unsigned k = 0; k < 2; ++k)
            out[k] += __atomic_load_n(&fex_poll_slots[i].count[k], __ATOMIC_RELAXED);
}
