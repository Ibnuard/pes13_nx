/* Opt-in observer must preserve operation results and never wait for a lock. */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static uint64_t tick=1000;
static unsigned threadGetCurHandle(void){return 7;}
static uint64_t armGetSystemTick(void){return __atomic_fetch_add(&tick,1,__ATOMIC_RELAXED);}
static uint64_t armTicksToNs(uint64_t n){return n*1000000;}
#include "../src/runtime/fextendo_transition_trace.h"
static int fail_alloc,real_calls;
static void *old_seen;
static char allocation[64];
static void *allocation_result(void){real_calls++;errno=fail_alloc?ENOMEM:EBUSY;return fail_alloc?NULL:allocation;}
void *__real_malloc(size_t n){(void)n;return allocation_result();}
void *__real_calloc(size_t n,size_t s){(void)n;(void)s;return allocation_result();}
void *__real_realloc(void *p,size_t n){old_seen=p;(void)n;return allocation_result();}
void *__real_memalign(size_t a,size_t n){assert(a==16);(void)n;return allocation_result();}
void *__real_aligned_alloc(size_t a,size_t n){assert(a==16);(void)n;return allocation_result();}
#include "../src/runtime/fextendo_transition_alloc.h"
static void *worker(void *unused){
    (void)unused;
    for(unsigned i=0;i<10000;i++){
        unsigned t=wine_nx_transition_begin(i%13,i);
        wine_nx_transition_text("worker",6);
        wine_nx_transition_end(t,0);
    }
    return NULL;
}
int main(void){
    struct fx_tr_snapshot snap;
    /* A disabled sink must not even dereference the caller's memory. */
    wine_nx_transition_text((const char *)1,SIZE_MAX);
    wine_nx_transition_failure_line((const char *)1);
    wine_nx_transition_event(1,2,3,4);
    assert(!wine_nx_transition_begin(1,2)&&!fx_tr_count&&!fx_tr_dropped);
    __atomic_store_n(&fx_tr_enabled,1,__ATOMIC_RELEASE);
    fx_tr_lock=1;
    wine_nx_transition_text((const char *)1,SIZE_MAX);
    wine_nx_transition_event(1,2,3,4);
    assert(!wine_nx_transition_begin(1,2)&&fx_tr_dropped==3);
    fx_tr_lock=0;
    for(unsigned i=0;i<FX_TR_EVENTS+3;i++)wine_nx_transition_event(2,i,4,5);
    assert(fx_tr_snapshot(&snap)&&snap.count==FX_TR_EVENTS&&fx_tr_dropped==6);
    assert(snap.events[0].code==0&&snap.events[31].code==31&&!fx_tr_count);
    char longtext[FX_TR_TEXT+100];memset(longtext,'A',sizeof(longtext));
    memcpy(longtext+sizeof(longtext)-4,"tail",4);
    wine_nx_transition_text(longtext,sizeof(longtext));
    wine_nx_transition_text("END",3);
    assert(fx_tr_snapshot(&snap)&&snap.text_size==FX_TR_TEXT);
    assert(!memcmp(snap.text+FX_TR_TEXT-7,"tailEND",7)&&!snap.text[FX_TR_TEXT]);
    wine_nx_transition_failure_line("[FEX] routine frame");
    wine_nx_transition_failure_line("[other] STOP not a FEX message");
    assert(!fx_tr_message_count);
    wine_nx_transition_failure_line("[FEX2-HEAP] STOP compiler scratch failed bytes=0x1000");
    wine_nx_transition_failure_line("[EXC] register context");
    wine_nx_transition_failure_line("[FEX2-ALLOC] FAIL reserve");
    wine_nx_transition_failure_line("[FEX3-NHEAP] allocation failed");
    for(unsigned i=0;i<32;i++)wine_nx_transition_text(longtext,sizeof(longtext));
    assert(fx_tr_snapshot(&snap)&&snap.message_count==4);
    assert(!memcmp(snap.messages[0].text,"[FEX2-HEAP] STOP",15)&&snap.messages[0].thread==7);
    char large_message[800];memset(large_message,'A',sizeof(large_message));memcpy(large_message,"[EXC]",5);
    for(unsigned i=0;i<FX_TR_MESSAGES+1;i++)wine_nx_transition_failure_line(large_message);
    assert(fx_tr_snapshot(&snap)&&snap.message_count==FX_TR_MESSAGES);
    assert(snap.messages[0].size==FX_TR_MESSAGE_BYTES&&!fx_tr_message_count);
    unsigned tokens[FX_TR_SLOTS];
    for(unsigned i=0;i<FX_TR_SLOTS;i++){tokens[i]=wine_nx_transition_begin(2,i);assert(tokens[i]);}
    assert(!wine_nx_transition_begin(2,0));
    assert(fx_tr_snapshot(&snap));
    for(unsigned i=0;i<FX_TR_SLOTS;i++)assert(snap.slots[i].active&&snap.slots[i].detail==i);
    for(unsigned i=0;i<FX_TR_SLOTS;i++)wine_nx_transition_end(tokens[i],i==0?-4:0);
    assert(fx_tr_snapshot(&snap)&&snap.count==1&&snap.events[0].kind==5&&snap.events[0].code==(unsigned)-4);
    assert(fx_tr_calls[2]==32&&fx_tr_errors[2]==1&&fx_tr_peak[2]>0);
    for(unsigned i=0;i<FX_TR_SLOTS;i++)assert(!snap.slots[i].active);
    /* Success, failure, zero-size and failed realloc semantics. */
    assert(__wrap_malloc(8)==allocation&&errno==EBUSY);
    assert(__wrap_calloc(2,8)==allocation&&errno==EBUSY);
    assert(__wrap_realloc(allocation,8)==allocation&&old_seen==allocation&&errno==EBUSY);
    assert(__wrap_memalign(16,8)==allocation&&errno==EBUSY);
    assert(__wrap_aligned_alloc(16,16)==allocation&&errno==EBUSY);
    assert(!fx_tr_count);
    fail_alloc=1;memcpy(allocation,"preserved",10);
    assert(!__wrap_malloc(8)&&errno==ENOMEM);
    assert(!__wrap_calloc(SIZE_MAX,8)&&errno==ENOMEM);
    assert(!__wrap_realloc(allocation,8)&&old_seen==allocation&&errno==ENOMEM);
    assert(!strcmp(allocation,"preserved"));
    assert(!__wrap_memalign(16,8)&&errno==ENOMEM);
    assert(!__wrap_aligned_alloc(16,16)&&errno==ENOMEM);
    assert(fx_tr_snapshot(&snap)&&snap.count==5&&snap.events[1].detail==UINT64_MAX);
    assert(snap.alloc_count==5);
    for(unsigned i=0;i<5;i++)assert(snap.allocs[i].kind==i+1&&snap.allocs[i].caller&&snap.allocs[i].error==ENOMEM);
    assert(snap.allocs[3].alignment==16&&snap.allocs[3].size==8);
    assert(snap.events[4].code==5&&snap.events[4].address==16);
    assert(!__wrap_malloc(0)&&!__wrap_calloc(0,8)&&!__wrap_realloc(allocation,0)&&!__wrap_memalign(16,0));
    assert(!__wrap_aligned_alloc(16,0));
    assert(!fx_tr_count&&real_calls==15);
    fx_tr_lock=1;uint64_t dropped=fx_tr_dropped;
    wine_nx_transition_alloc_site(4,4096,16,0x12345678,ENOMEM);
    assert(!fx_tr_alloc_count&&fx_tr_dropped==dropped+1);fx_tr_lock=0;
    for(unsigned i=0;i<FX_TR_EVENTS+1;i++)wine_nx_transition_alloc_site(4,5242880,4096,0x12345678,ENOMEM);
    assert(fx_tr_snapshot(&snap)&&snap.alloc_count==FX_TR_EVENTS&&!fx_tr_alloc_count);
    assert(snap.allocs[0].caller==0x12345678&&snap.allocs[31].size==5242880);
    pthread_t workers[4];
    for(unsigned i=0;i<4;i++)assert(!pthread_create(&workers[i],NULL,worker,NULL));
    for(unsigned i=0;i<20000;i++)fx_tr_snapshot(&snap);
    for(unsigned i=0;i<4;i++)assert(!pthread_join(workers[i],NULL));
    assert(fx_tr_snapshot(&snap));
    for(unsigned i=0;i<FX_TR_SLOTS;i++)assert(!snap.slots[i].active);
    /* Disabling while a call is in flight still releases its slot. */
    unsigned t=wine_nx_transition_begin(0,0);assert(t);
    __atomic_store_n(&fx_tr_enabled,0,__ATOMIC_RELEASE);
    wine_nx_transition_end(t,0);assert(!fx_tr_slots[t-1].active);
    puts("PASS: bounded observer, contention, in-flight lifecycle, text tail and allocator semantics");
}
