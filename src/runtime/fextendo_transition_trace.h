/* LGPL-2.1-or-later. Bounded evidence, opt-in. Producers never allocate,
 * write storage, block, suspend threads, or change guest/driver results. */
#ifndef FEXTENDO_TRANSITION_TRACE_H
#define FEXTENDO_TRANSITION_TRACE_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define FX_TR_STAGES 14
#define FX_TR_SLOTS 32
#define FX_TR_EVENTS 32
#define FX_TR_TEXT 2048
#define FX_TR_MESSAGES 12
#define FX_TR_MESSAGE_BYTES 512
static const char *const fx_tr_names[FX_TR_STAGES]={"acquire","present","submit","fence",
    "semaphore","graphics_pipeline","compute_pipeline","allocate_memory","create_image",
    "create_buffer","shader_module","device_idle","queue_idle","unused"};
struct fx_tr_slot {unsigned active,stage,thread;uint64_t begin,detail;};
struct fx_tr_event {unsigned kind,code,thread;uint64_t tick,detail,address;};
struct fx_tr_alloc_site {unsigned kind,thread,error;uint64_t tick,size,alignment,caller;};
struct fx_tr_message {unsigned thread,size;uint64_t tick;char text[FX_TR_MESSAGE_BYTES];};
struct fx_tr_snapshot {struct fx_tr_slot slots[FX_TR_SLOTS];struct fx_tr_event events[FX_TR_EVENTS];
    unsigned count,text_size;char text[FX_TR_TEXT+1];
    unsigned message_count;struct fx_tr_message messages[FX_TR_MESSAGES];
    unsigned alloc_count;struct fx_tr_alloc_site allocs[FX_TR_EVENTS];};
static unsigned fx_tr_enabled,fx_tr_lock,fx_tr_count,fx_tr_text_size;
static unsigned fx_tr_message_count;
static uint64_t fx_tr_fex_base,fx_tr_fex_size;
static uint64_t fx_tr_dropped,fx_tr_calls[FX_TR_STAGES],fx_tr_errors[FX_TR_STAGES],fx_tr_peak[FX_TR_STAGES];
static struct fx_tr_slot fx_tr_slots[FX_TR_SLOTS];
static struct fx_tr_event fx_tr_events[FX_TR_EVENTS];
static char fx_tr_text[FX_TR_TEXT];
static struct fx_tr_message fx_tr_messages[FX_TR_MESSAGES];
static unsigned fx_tr_alloc_count;
static struct fx_tr_alloc_site fx_tr_allocs[FX_TR_EVENTS];
static int fx_tr_try(void){unsigned expected=0;return __atomic_compare_exchange_n(&fx_tr_lock,&expected,1,0,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED);}
static void fx_tr_unlock(void){__atomic_store_n(&fx_tr_lock,0,__ATOMIC_RELEASE);}
static int fx_tr_on(void){return __atomic_load_n(&fx_tr_enabled,__ATOMIC_RELAXED);}
/* Bootstrap metadata only: no guest/thread lookup or loader lock at failure. */
void wine_nx_transition_fex_image(uint64_t base,uint64_t size){
    __atomic_store_n(&fx_tr_fex_size,size,__ATOMIC_RELAXED);
    __atomic_store_n(&fx_tr_fex_base,base,__ATOMIC_RELEASE);
}
static int fx_tr_has(const char *s,unsigned length,const char *word,unsigned n){
    for(unsigned i=0;i+n<=length;i++)if(!memcmp(s+i,word,n))return 1;
    return 0;
}
void wine_nx_transition_failure_line(const char *message){
    if(!fx_tr_on()||!message)return;
    if(strncmp(message,"[EXC]",5)&&strncmp(message,"[FEX",4))return;
    unsigned n=0;while(n<FX_TR_MESSAGE_BYTES&&message[n])n++;
    int exception=n>=5&&!memcmp(message,"[EXC]",5);
    int fex=n>=4&&!memcmp(message,"[FEX",4);
    if(!exception&&!(fex&&(fx_tr_has(message,n,"STOP",4)||fx_tr_has(message,n,"FAIL",4)||
                           fx_tr_has(message,n,"failed",6))))return;
    if(!fx_tr_try()){__atomic_add_fetch(&fx_tr_dropped,1,__ATOMIC_RELAXED);return;}
    if(fx_tr_message_count<FX_TR_MESSAGES){
        struct fx_tr_message *m=&fx_tr_messages[fx_tr_message_count++];
        m->thread=threadGetCurHandle();m->tick=armGetSystemTick();m->size=n;
        memcpy(m->text,message,n);
    }else __atomic_add_fetch(&fx_tr_dropped,1,__ATOMIC_RELAXED);
    fx_tr_unlock();
}
void wine_nx_transition_event(unsigned kind,unsigned code,uint64_t detail,uint64_t address){
    if(!fx_tr_on())return;
    if(!fx_tr_try()){__atomic_add_fetch(&fx_tr_dropped,1,__ATOMIC_RELAXED);return;}
    if(fx_tr_count<FX_TR_EVENTS)fx_tr_events[fx_tr_count++]=(struct fx_tr_event){kind,code,threadGetCurHandle(),armGetSystemTick(),detail,address};
    else __atomic_add_fetch(&fx_tr_dropped,1,__ATOMIC_RELAXED);
    fx_tr_unlock();
}
void wine_nx_transition_alloc_site(unsigned kind,uint64_t size,uint64_t alignment,uintptr_t caller,unsigned error){
    if(!fx_tr_on())return;
    if(!fx_tr_try()){__atomic_add_fetch(&fx_tr_dropped,1,__ATOMIC_RELAXED);return;}
    if(fx_tr_alloc_count<FX_TR_EVENTS)
        fx_tr_allocs[fx_tr_alloc_count++]=(struct fx_tr_alloc_site){kind,threadGetCurHandle(),error,armGetSystemTick(),size,alignment,caller};
    else __atomic_add_fetch(&fx_tr_dropped,1,__ATOMIC_RELAXED);
    fx_tr_unlock();
}
void wine_nx_transition_text(const char *text,size_t size){
    if(!fx_tr_on()||!size)return;
    if(!fx_tr_try()){__atomic_add_fetch(&fx_tr_dropped,1,__ATOMIC_RELAXED);return;}
    if(size>FX_TR_TEXT){text+=size-FX_TR_TEXT;size=FX_TR_TEXT;}
    if(fx_tr_text_size+size>FX_TR_TEXT){unsigned discard=fx_tr_text_size+size-FX_TR_TEXT;
        memmove(fx_tr_text,fx_tr_text+discard,fx_tr_text_size-discard);fx_tr_text_size-=discard;}
    memcpy(fx_tr_text+fx_tr_text_size,text,size);fx_tr_text_size+=size;fx_tr_unlock();
}
unsigned wine_nx_transition_begin(unsigned stage,uint64_t detail){
    if(!fx_tr_on()||stage>=FX_TR_STAGES)return 0;
    if(!fx_tr_try()){__atomic_add_fetch(&fx_tr_dropped,1,__ATOMIC_RELAXED);return 0;}
    unsigned token=0;
    for(unsigned i=0;i<FX_TR_SLOTS;i++)if(!__atomic_load_n(&fx_tr_slots[i].active,__ATOMIC_ACQUIRE)){
        struct fx_tr_slot *s=&fx_tr_slots[i];s->stage=stage;s->thread=threadGetCurHandle();s->begin=armGetSystemTick();s->detail=detail;
        __atomic_store_n(&s->active,1,__ATOMIC_RELEASE);token=i+1;break;
    }
    if(!token)__atomic_add_fetch(&fx_tr_dropped,1,__ATOMIC_RELAXED);
    fx_tr_unlock();return token;
}
void wine_nx_transition_end(unsigned token,int result){
    if(!token||token>FX_TR_SLOTS)return;
    struct fx_tr_slot *s=&fx_tr_slots[token-1];unsigned stage=s->stage;
    uint64_t end=armGetSystemTick(),us=end>=s->begin?armTicksToNs(end-s->begin)/1000:0;
    __atomic_add_fetch(&fx_tr_calls[stage],1,__ATOMIC_RELAXED);
    uint64_t peak=__atomic_load_n(&fx_tr_peak[stage],__ATOMIC_RELAXED);
    while(us>peak&&!__atomic_compare_exchange_n(&fx_tr_peak[stage],&peak,us,0,__ATOMIC_RELAXED,__ATOMIC_RELAXED)){}
    if(result<0){__atomic_add_fetch(&fx_tr_errors[stage],1,__ATOMIC_RELAXED);
        wine_nx_transition_event(5,(unsigned)result,stage,s->detail);}
    __atomic_store_n(&s->active,0,__ATOMIC_RELEASE);
}
static int fx_tr_snapshot(struct fx_tr_snapshot *out){
    if(!fx_tr_try())return 0;
    for(unsigned i=0;i<FX_TR_SLOTS;i++){
        struct fx_tr_slot *s=&fx_tr_slots[i],*d=&out->slots[i];
        d->active=__atomic_load_n(&s->active,__ATOMIC_ACQUIRE);
        d->stage=s->stage;d->thread=s->thread;d->begin=s->begin;d->detail=s->detail;
    }
    out->count=fx_tr_count;memcpy(out->events,fx_tr_events,sizeof(fx_tr_events));fx_tr_count=0;
    out->text_size=fx_tr_text_size;memcpy(out->text,fx_tr_text,fx_tr_text_size);
    out->text[fx_tr_text_size]=0;fx_tr_text_size=0;
    out->message_count=fx_tr_message_count;
    memcpy(out->messages,fx_tr_messages,fx_tr_message_count*sizeof(*fx_tr_messages));fx_tr_message_count=0;
    out->alloc_count=fx_tr_alloc_count;
    memcpy(out->allocs,fx_tr_allocs,fx_tr_alloc_count*sizeof(*fx_tr_allocs));fx_tr_alloc_count=0;
    fx_tr_unlock();return 1;
}
#endif
