/* LGPL-2.1-or-later. Fixed-size native thread observations for logical freezes. */
#ifndef FEXTENDO_LIVE_TRACE_H
#define FEXTENDO_LIVE_TRACE_H
#include <stdint.h>
#define FX_LIVE_THREADS 128
struct fx_live_thread {
    unsigned handle,tid,kind;
    unsigned ticks_result,pause_result,read_result,resume_result;
    uint64_t ticks,pc,lr,sp,fp,x0,x1,x2,x3,x19,x20,x28;
};
struct fx_live_snapshot {
    unsigned status,count,context_supported,disabled;
    uint64_t elapsed_us;
    struct fx_live_thread rows[FX_LIVE_THREADS];
};
void wine_nx_live_threads_snapshot(struct fx_live_snapshot *);
#endif
