/* LGPL-2.1-or-later. Opt-in, bounded transition evidence on the existing
 * maintenance worker. No logging, allocation or waiting in Present/XInput. */
#ifdef FX_TRANSITION_TRACE
static void fx_diagnostics_escape(FILE *file,const char *s,unsigned n){
    for(unsigned i=0;i<n;i++){
        unsigned char c=s[i];
        if(c>=32&&c<127&&c!='\\')fputc(c,file);else fprintf(file,"\\x%02x",c);
    }
}
static void fx_diagnostics_details(FILE *file,uint64_t now){
    static uint64_t previous[FX_TR_STAGES];
    struct fx_tr_snapshot snap;
    struct mallinfo heap=mallinfo();
    extern char *fake_heap_start,*fake_heap_end;
    uint64_t capacity=(uintptr_t)fake_heap_end-(uintptr_t)fake_heap_start;
    uint64_t arena=(unsigned long long)heap.arena;
    uint64_t untaken=capacity>arena?capacity-arena:0;
    fprintf(file,"MEM heap_capacity=%llu arena=%llu allocator_free=%llu untaken=%llu total_free=%llu top_free=%llu observer_dropped=%llu\n",
        (unsigned long long)capacity,(unsigned long long)arena,(unsigned long long)heap.fordblks,
        (unsigned long long)untaken,(unsigned long long)(heap.fordblks+untaken),
        (unsigned long long)heap.keepcost,(unsigned long long)__atomic_load_n(&fx_tr_dropped,__ATOMIC_RELAXED));
#ifdef FX_SCRATCH_RESERVE
    uint64_t scratch[16];
    extern void pes13_fex_scratch_snapshot(uint64_t out[16]);
    pes13_fex_scratch_snapshot(scratch);
#if FX_SCRATCH_RESERVE_VERSION == 3
#define FX_SCRATCH_LOG_TAG "SCRATCH_V3"
#else
#define FX_SCRATCH_LOG_TAG "SCRATCH_V2"
#endif
    fprintf(file,FX_SCRATCH_LOG_TAG " capacity=%llu used=%llu live=%llu hits=%llu fallback=%llu failed=%llu peak_used=%llu returned=%llu init_failed=%llu largest_free=%llu max_request=%llu last_failed=%llu hits_8=%llu hits_16=%llu hits_larger=%llu invalid_release=%llu\n",
        (unsigned long long)scratch[0],(unsigned long long)scratch[1],(unsigned long long)scratch[2],
        (unsigned long long)scratch[3],(unsigned long long)scratch[4],(unsigned long long)scratch[5],
        (unsigned long long)scratch[6],(unsigned long long)scratch[7],(unsigned long long)scratch[8],
        (unsigned long long)scratch[9],(unsigned long long)scratch[10],(unsigned long long)scratch[11],
        (unsigned long long)scratch[12],(unsigned long long)scratch[13],(unsigned long long)scratch[14],
        (unsigned long long)scratch[15]);
#endif
#ifdef FX_PAGE_STORE
    uint64_t pages[8];
    extern void wine_nx_page_store_snapshot(uint64_t out[8]);
    wine_nx_page_store_snapshot(pages);
    fprintf(file,"PAGES_V1 recovered=%llu recovered_bytes=%llu live_bytes=%llu pieces=%llu failed=%llu rollback_failed=%llu peak_bytes=%llu released=%llu\n",
        (unsigned long long)pages[0],(unsigned long long)pages[1],(unsigned long long)pages[2],
        (unsigned long long)pages[3],(unsigned long long)pages[4],(unsigned long long)pages[5],
        (unsigned long long)pages[6],(unsigned long long)pages[7]);
#endif
#ifdef FX_SCRATCH_PAGES
    uint64_t sp[15];extern void pes13_fex_scratch_pages_snapshot(uint64_t out[15]);
    pes13_fex_scratch_pages_snapshot(sp);
    fprintf(file,"SCRATCH_PAGES_V1 attempts=%llu recovered=%llu failed=%llu held_bytes=%llu peak_bytes=%llu held_slots=%llu pieces=%llu returned=%llu map_failed=%llu unmap_failed=%llu quarantined=%llu invalid_release=%llu last_result=%llx last_request=%llu budget_refused=%llu\n",
        (unsigned long long)sp[0],(unsigned long long)sp[1],(unsigned long long)sp[2],
        (unsigned long long)sp[3],(unsigned long long)sp[4],(unsigned long long)sp[5],
        (unsigned long long)sp[6],(unsigned long long)sp[7],(unsigned long long)sp[8],
        (unsigned long long)sp[9],(unsigned long long)sp[10],(unsigned long long)sp[11],
        (unsigned long long)sp[12],(unsigned long long)sp[13],(unsigned long long)sp[14]);
#endif
#ifdef FX_RUST_HEAP
    uint64_t rh[7];for(unsigned i=0;i<7;i++)rh[i]=__atomic_load_n(&fx_rust_heap_stats[i],__ATOMIC_RELAXED);
    fprintf(file,"RUST_HEAP_V1 attempts=%llu recovered=%llu failed=%llu returned=%llu realloc_recovered=%llu last_size=%llu last_alignment=%llu\n",
        (unsigned long long)rh[0],(unsigned long long)rh[1],(unsigned long long)rh[2],
        (unsigned long long)rh[3],(unsigned long long)rh[4],(unsigned long long)rh[5],(unsigned long long)rh[6]);
#endif
#ifdef FX_THREAD_STACK_RESERVE
    uint64_t stacks[15];fx_thread_stack_snapshot(stacks);
    fprintf(file,"THREAD_STACK_V1 capacity=%llu slot_bytes=%llu used=%llu peak=%llu recovered=%llu returned=%llu exhausted=%llu quarantined=%llu invalid_release=%llu calls=%llu failed=%llu last_result=%llx last_stack=%llu init_failed=%llu alloc_failed=%llu\n",
        (unsigned long long)stacks[0],(unsigned long long)stacks[1],(unsigned long long)stacks[2],
        (unsigned long long)stacks[3],(unsigned long long)stacks[4],(unsigned long long)stacks[5],
        (unsigned long long)stacks[6],(unsigned long long)stacks[7],(unsigned long long)stacks[8],
        (unsigned long long)stacks[9],(unsigned long long)stacks[10],(unsigned long long)stacks[11],
        (unsigned long long)stacks[12],(unsigned long long)stacks[13],(unsigned long long)stacks[14]);
#endif
    for(unsigned i=0;i<FX_TR_STAGES;i++){
        uint64_t calls=__atomic_load_n(&fx_tr_calls[i],__ATOMIC_RELAXED);
        if(calls==previous[i])continue;previous[i]=calls;
        fprintf(file,"STAGE name=%s completed=%llu errors=%llu peak_us=%llu\n",fx_tr_names[i],
            (unsigned long long)calls,(unsigned long long)__atomic_load_n(&fx_tr_errors[i],__ATOMIC_RELAXED),
            (unsigned long long)__atomic_load_n(&fx_tr_peak[i],__ATOMIC_RELAXED));
    }
    if(!fx_tr_snapshot(&snap))return;
    for(unsigned i=0;i<FX_TR_SLOTS;i++)if(snap.slots[i].active){
        struct fx_tr_slot *s=&snap.slots[i];
        fprintf(file,"INFLIGHT name=%s thread=%x age_ms=%llu detail=%llu\n",fx_tr_names[s->stage],s->thread,
            (unsigned long long)(now>=s->begin?armTicksToNs(now-s->begin)/1000000:0),(unsigned long long)s->detail);
    }
    for(unsigned i=0;i<snap.count;i++){
        struct fx_tr_event *e=&snap.events[i];
        fprintf(file,"EVENT kind=%u code=%08x thread=%x age_ms=%llu detail=%llu address=%llx\n",e->kind,e->code,e->thread,
            (unsigned long long)(now>=e->tick?armTicksToNs(now-e->tick)/1000000:0),
            (unsigned long long)e->detail,(unsigned long long)e->address);
    }
    for(unsigned i=0;i<snap.alloc_count;i++){
        struct fx_tr_alloc_site *a=&snap.allocs[i];
        fprintf(file,"ALLOC_SITE kind=%u thread=%x age_ms=%llu size=%llu alignment=%llu caller=%llx errno=%u\n",
            a->kind,a->thread,(unsigned long long)(now>=a->tick?armTicksToNs(now-a->tick)/1000000:0),
            (unsigned long long)a->size,(unsigned long long)a->alignment,(unsigned long long)a->caller,a->error);
    }
    if(snap.text_size){
        /* Escape controls/newlines so a guest message cannot forge a log row. */
        fputs("TEXT ",file);
        fx_diagnostics_escape(file,snap.text,snap.text_size);
        fputc('\n',file);
    }
    for(unsigned i=0;i<snap.message_count;i++){
        struct fx_tr_message *m=&snap.messages[i];
        fprintf(file,"FAILMSG thread=%x age_ms=%llu ",m->thread,
            (unsigned long long)(now>=m->tick?armTicksToNs(now-m->tick)/1000000:0));
        fx_diagnostics_escape(file,m->text,m->size);
        fputc('\n',file);
    }
}
#endif
#ifdef FX_LIVE_TRACE
static void fx_diagnostics_live(FILE *file,uint64_t started){
    /* Snapshot returns only after attempting to resume every paused thread.
     * No file formatting or I/O occurs in the snapshot implementation. */
    static struct fx_live_snapshot snap;
    wine_nx_live_threads_snapshot(&snap);
    fprintf(file,"LIVE_V1 elapsed_ms=%llu status=%u count=%u context=%u disabled=%u capture_us=%llu\n",
        (unsigned long long)(armTicksToNs(armGetSystemTick()-started)/1000000),snap.status,snap.count,
        snap.context_supported,snap.disabled,(unsigned long long)snap.elapsed_us);
    for(unsigned i=0;i<snap.count;i++){
        const struct fx_live_thread *r=&snap.rows[i];
        fprintf(file,"THREAD handle=%x tid=%x kind=%u ticks=%llu ticks_rc=%x pause=%x read=%x resume=%x pc=%llx lr=%llx sp=%llx fp=%llx x0=%llx x1=%llx x2=%llx x3=%llx x19=%llx x20=%llx x28=%llx\n",
            r->handle,r->tid,r->kind,(unsigned long long)r->ticks,r->ticks_result,r->pause_result,r->read_result,r->resume_result,
            (unsigned long long)r->pc,(unsigned long long)r->lr,(unsigned long long)r->sp,(unsigned long long)r->fp,
            (unsigned long long)r->x0,(unsigned long long)r->x1,(unsigned long long)r->x2,(unsigned long long)r->x3,
            (unsigned long long)r->x19,(unsigned long long)r->x20,(unsigned long long)r->x28);
    }
}
#endif
static void fx_diagnostics_tick(unsigned ticks) {
    static int initialized;
    static FILE *file;
    static unsigned samples;
    static uint64_t started;
    if(!initialized){
        if(!__atomic_load_n(&fex_frame_ok,__ATOMIC_ACQUIRE))return;
        initialized=1;
        char enabled[2];
        if(fx_read(RUNTIME_DIR "/launcher/diagnostics.txt",enabled,2)!=2||
           memcmp(enabled,"1\n",2))return;
        /* Keep one previous reproduction; no game/render thread waits for it. */
        unlink(RUNTIME_DIR "/transition.previous.log");
        rename(RUNTIME_DIR "/transition.log",RUNTIME_DIR "/transition.previous.log");
        file=fopen(RUNTIME_DIR "/transition.log","wb");
        if(!file)return;
        started=armGetSystemTick();
#ifdef FX_CRASH_LOG
        fprintf(file,"CRASH_V2 ready=%u session_tick=%llx trace_start_tick=%llx file=crash.log previous=crash.previous.log\n",
            __atomic_load_n(&fx_crash_ready,__ATOMIC_ACQUIRE),
            (unsigned long long)fx_crash_start,(unsigned long long)started);
        fprintf(file,"NRO base=%llx\n",(unsigned long long)fx_crash_nro_base);
#endif
#ifdef FX_LIVE_TRACE
        fprintf(file,"LIVE_TRACE_V1 interval=6s thread_limit=128 registered_threads_only\n");
#endif
#ifdef FX_TRANSITION_TRACE
        fprintf(file,"TRACE_V3 events: 1=guest_exit 2=unhandled_native_exception 3=native_alloc_failure 4=section_failure 5=vulkan_error 6=exception_lr_sp; alloc_codes: 1=malloc 2=calloc 3=realloc 4=memalign 5=aligned_alloc; no timing/preset changes\n");
        fprintf(file,"MODULE name=libwow64fex.dll base=%llx size=%llu\n",
            (unsigned long long)__atomic_load_n(&fx_tr_fex_base,__ATOMIC_ACQUIRE),
            (unsigned long long)__atomic_load_n(&fx_tr_fex_size,__ATOMIC_RELAXED));
        __atomic_store_n(&fx_tr_enabled,1,__ATOMIC_RELEASE);
#endif
        fprintf(file,"FEXTendo input-fix preview; preset=%d renderer=%d; interval=2s limit=20min\n"
                     "elapsed_ms,presents,present_errors,frame_age_ms,used_memory,total_memory,native_used,native_free,input_blocked\n",
                     fx_ui_view.selected,fx_ui_view.renderer);
        fflush(file);
    }
    if(!file||ticks%10)return;
    uint64_t used=0,total=0,now=armGetSystemTick();
    Result ur=svcGetInfo(&used,InfoType_UsedMemorySize,CUR_PROCESS_HANDLE,0);
    Result tr=svcGetInfo(&total,InfoType_TotalMemorySize,CUR_PROCESS_HANDLE,0);
    struct mallinfo heap=mallinfo();
    uint64_t last=__atomic_load_n(&fex_frame_last,__ATOMIC_RELAXED);
    int rc=fprintf(file,"%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%d\n",
        (unsigned long long)(armTicksToNs(now-started)/1000000),
        (unsigned long long)__atomic_load_n(&fex_frame_ok,__ATOMIC_RELAXED),
        (unsigned long long)__atomic_load_n(&fex_frame_errors,__ATOMIC_RELAXED),
        (unsigned long long)(last&&now>=last?armTicksToNs(now-last)/1000000:0),
        (unsigned long long)(R_SUCCEEDED(ur)?used:0),(unsigned long long)(R_SUCCEEDED(tr)?total:0),
        (unsigned long long)heap.uordblks,(unsigned long long)heap.fordblks,fx_keyboard_input_blocked());
#ifdef FX_TRANSITION_TRACE
    fx_diagnostics_details(file,now);
#endif
#ifdef FX_LIVE_TRACE
    if(!(ticks%30))fx_diagnostics_live(file,started);
#endif
    if(rc<0||fflush(file)||++samples>=600){
#ifdef FX_TRANSITION_TRACE
        __atomic_store_n(&fx_tr_enabled,0,__ATOMIC_RELEASE);
#endif
        fclose(file);file=NULL;
    }
}
