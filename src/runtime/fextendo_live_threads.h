/* LGPL-2.1-or-later. Included after thread_profile.c, using its existing
 * registry and handle lifetime guard. No file I/O, malloc, Wine/FEX helpers,
 * stack walks or foreign memory dereferences while a thread is paused. */
#include "fextendo_live_trace.h"
void wine_nx_live_threads_snapshot(struct fx_live_snapshot *out)
{
    static unsigned disabled;
    uint64_t start=armGetSystemTick();
    Handle self=threadGetCurHandle();
    out->status=out->count=out->context_supported=0;out->disabled=disabled;
    out->elapsed_us=0;
    if(pthread_mutex_trylock(&profile_mutex)){out->status=1;return;}
    /* Unregister releases registry_mutex before acquiring profile_mutex.
     * It cannot finish closing its handle while this observer holds profile. */
    if(pthread_mutex_trylock(&registry_mutex)){
        pthread_mutex_unlock(&profile_mutex);out->status=2;return;
    }
    for(unsigned i=0;i<NX_PROF_MAX_THREADS&&out->count<FX_LIVE_THREADS;i++){
        if(!registry[i].handle||registry[i].handle==self)continue;
        struct fx_live_thread *row=&out->rows[out->count++];
        memset(row,0,sizeof(*row));
        row->handle=registry[i].handle;row->tid=registry[i].tid;row->kind=registry[i].kind;
        row->pause_result=row->read_result=row->resume_result=~0u;
    }
    pthread_mutex_unlock(&registry_mutex);
    out->context_supported=envIsSyscallHinted(0x32)&&envIsSyscallHinted(0x33);
    for(unsigned i=0;i<out->count;i++){
        struct fx_live_thread *row=&out->rows[i];
        u64 ticks=0;
        row->ticks_result=svcGetInfo(&ticks,InfoType_ThreadTickCount,row->handle,UINT64_MAX);
        if(R_FAILED(row->ticks_result))
            row->ticks_result=svcGetInfo(&ticks,InfoType_ThreadTickCountDeprecated,row->handle,UINT64_MAX);
        row->ticks=ticks;
        if(!out->context_supported||disabled)continue;
        row->pause_result=svcSetThreadActivity(row->handle,ThreadActivity_Paused);
        if(R_FAILED(row->pause_result))continue;
        ThreadContext ctx;
        row->read_result=svcGetThreadContext3(&ctx,row->handle);
        if(R_SUCCEEDED(row->read_result)){
            row->pc=ctx.pc.x;row->lr=ctx.lr;row->sp=ctx.sp;row->fp=ctx.fp;
            row->x0=ctx.cpu_gprs[0].x;row->x1=ctx.cpu_gprs[1].x;
            row->x2=ctx.cpu_gprs[2].x;row->x3=ctx.cpu_gprs[3].x;
            row->x19=ctx.cpu_gprs[19].x;row->x20=ctx.cpu_gprs[20].x;row->x28=ctx.cpu_gprs[28].x;
        }
        /* Immediate unconditional resume, including a failed context read.
         * Do not sleep/retry reads or ask the FEX JIT for a lock-owned map. */
        row->resume_result=svcSetThreadActivity(row->handle,ThreadActivity_Runnable);
        if(R_FAILED(row->resume_result))
            row->resume_result=svcSetThreadActivity(row->handle,ThreadActivity_Runnable);
        if(R_FAILED(row->resume_result))disabled=1;
    }
    pthread_mutex_unlock(&profile_mutex);
    out->disabled=disabled;
    out->elapsed_us=armTicksToNs(armGetSystemTick()-start)/1000;
}
