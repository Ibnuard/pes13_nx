/* LGPL-2.1-or-later. Debug-only evidence at memory failures, not on each
 * allocation or frame. Separate budgets prevent startup address probes from
 * hiding a later commit failure. Caller holds mapping_mutex. */
static void __attribute__((noinline)) horizon_memory_failure(unsigned stage,
        void *addr, void *source, size_t size, unsigned kernel_rc)
{
    extern int wine_nx_launch_debug_active(void);
    extern char *fake_heap_start, *fake_heap_end;
    static const char *const names[] = {"metadata", "backing", "reservation", "map", "permission", "commit"};
    static unsigned emitted[6];
    static uint64_t previous[6];
    int saved = errno;
    uint64_t now, capacity, arena, untaken, idle = 0, spare = 0, largest = 0;
    struct mallinfo heap;
    if (stage >= 6 || !wine_nx_launch_debug_active()) return;
    now = armGetSystemTick();
    if (emitted[stage] >= 32 || (emitted[stage] >= 2 && now - previous[stage] < 5 * 19200000ull)) return;
    previous[stage] = now; ++emitted[stage];
    heap = mallinfo();
    capacity = (uintptr_t)fake_heap_end - (uintptr_t)fake_heap_start;
    arena = (unsigned)heap.arena;
    untaken = capacity > arena ? capacity - arena : 0;
    for (unsigned i = 0; i < HORIZON_POOL_ARENAS; ++i) {
        struct horizon_page_arena *a = &backing_pages.arenas[i];
        unsigned run = 0;
        if (!a->memory) continue;
        spare += (uint64_t)a->free_pages * HORIZON_POOL_PAGE;
        if (a->free_pages == HORIZON_POOL_PAGES) idle += HORIZON_POOL_PAGE * HORIZON_POOL_PAGES;
        for (unsigned j = 0; j < HORIZON_POOL_PAGES; ++j) {
            run = a->used[j] ? 0 : run + 1;
            if ((uint64_t)run * HORIZON_POOL_PAGE > largest) largest = (uint64_t)run * HORIZON_POOL_PAGE;
        }
    }
    horizon_trace("[MEM-FAIL] v1 stage=%s addr=%p source=%p bytes=%zu errno=%d rc=%x "
                  "heap_free=%llu untaken=%llu top=%u pool_idle=%llu pool_spare=%llu pool_run=%llu",
                  names[stage], addr, source, size, saved, kernel_rc,
                  (unsigned long long)(unsigned)heap.fordblks, (unsigned long long)untaken,
                  (unsigned)heap.keepcost, (unsigned long long)idle,
                  (unsigned long long)spare, (unsigned long long)largest);
    if (stage == 3 || stage == 4) {
        MemoryInfo d = {0}, s = {0}; u32 page = 0;
        Result dr = svcQueryMemory(&d, &page, (u64)addr);
        Result sr = svcQueryMemory(&s, &page, (u64)source);
        horizon_trace("[MEM-KERNEL] dst_rc=%x base=%llx size=%llx type=%x perm=%x attr=%x "
                      "src_rc=%x base=%llx size=%llx type=%x perm=%x attr=%x",
                      dr, (unsigned long long)d.addr, (unsigned long long)d.size, d.type, d.perm, d.attr,
                      sr, (unsigned long long)s.addr, (unsigned long long)s.size, s.type, s.perm, s.attr);
    }
    errno = saved;
}
