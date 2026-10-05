/* SPDX-License-Identifier: MIT
 * Recovery for private FEX containers after malloc fails. Never grow the
 * process heap, discard a live cache or change the PE allocation/free ABI.
 */
#ifndef PES13_HORIZON_HEAP_PRESSURE_H
#define PES13_HORIZON_HEAP_PRESSURE_H
#ifdef __SWITCH__
#include <malloc.h>
extern char *fake_heap_start,*fake_heap_end;
extern void pes13_virtmem_snapshot(uint64_t out[4]) __attribute__((weak));
#endif

static void fx_heap_pressure_report(const char *owner,size_t requested,size_t alignment,
                                    unsigned stage,unsigned rc,size_t trimmed,int recovered){
    static unsigned reported;
    unsigned ticket=__atomic_fetch_add(&reported,1,__ATOMIC_RELAXED);
    if(ticket<8||!recovered){
        uint64_t scratch[FX_SC_METRICS];
        pes13_fex_scratch_snapshot(scratch);
        uint64_t heap_free=0,untaken=0,page_held=0,page_owners=0;
        uint64_t va[4]={0};
#ifdef __SWITCH__
        if(pes13_virtmem_snapshot)pes13_virtmem_snapshot(va);
        struct mallinfo heap=mallinfo();
        size_t heap_size=(uintptr_t)fake_heap_end-(uintptr_t)fake_heap_start;
        heap_free=(unsigned)heap.fordblks;
        untaken=heap_size>(unsigned)heap.arena?heap_size-(unsigned)heap.arena:0;
#ifdef FX_SCRATCH_PAGES
        page_held=__atomic_load_n(&fx_sp_stats[3],__ATOMIC_RELAXED);
        page_owners=__atomic_load_n(&fx_sp_stats[5],__ATOMIC_RELAXED);
#endif
#endif
        char message[512];
        snprintf(message,sizeof(message),
            "[FEX3-NHEAP-%s] owner=%s bytes=%llu align=%llu pages_stage=%u rc=%x trimmed=%llu "
            "heap_free=%llu untaken=%llu reserve_used=%llu reserve_free=%llu reserve_largest=%llu "
            "pages_held=%llu pages_owners=%llu va_scan=%llu va_ok=%llu va_fail=%llu va_largest=%llu",
            recovered?"RECOVER":"FAIL",owner,(unsigned long long)requested,(unsigned long long)alignment,stage,rc,(unsigned long long)trimmed,
            (unsigned long long)heap_free,(unsigned long long)untaken,
            (unsigned long long)scratch[FX_SC_USED],
            (unsigned long long)(scratch[FX_SC_CAPACITY]-scratch[FX_SC_USED]),
            (unsigned long long)scratch[FX_SC_LARGEST_FREE],
            (unsigned long long)page_held,(unsigned long long)page_owners,
            (unsigned long long)va[0],(unsigned long long)va[1],(unsigned long long)va[2],(unsigned long long)va[3]);
        host_log(message);
    }
}
static void *fx_private_heap_recover(size_t raw_size,uint64_t requested,uint64_t alignment){
    void *raw=NULL;size_t trimmed=0;
    unsigned stage=0,rc=0;
#if defined(FX_SCRATCH_PAGES) && defined(__SWITCH__)
    trimmed=fx_heap_pressure_trim();
    if(trimmed)raw=malloc(raw_size);
    struct fx_sp_failure failure={FX_SP_OK,0};
    if(!raw&&raw_size<=SIZE_MAX-(PAGE_BYTES-1))
        raw=fx_scratch_pages_take_report((raw_size+PAGE_BYTES-1)&~(size_t)(PAGE_BYTES-1),&failure);
    stage=failure.stage;rc=failure.result;
#endif
    if(!raw)raw=fx_scratch_reserve_try(raw_size,1);
    fx_heap_pressure_report("private",requested,alignment,stage,rc,trimmed,raw!=NULL);
    return raw;
}
#endif
