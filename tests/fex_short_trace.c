/* Exercise production fixed queues and wait retirement under contention. */
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <pthread.h>
#include <assert.h>
#include <stdlib.h>
static uint64_t now=19200000;
static __thread struct { struct { void *UniqueThread; } ClientId; } test_teb;
#define TEB __typeof__(test_teb)
#define NtCurrentTeb() (&test_teb)
static uint64_t armGetSystemTick(void){return __atomic_load_n(&now,__ATOMIC_RELAXED);}
static uint64_t armTicksToNs(uint64_t t){return t*1000000000/19200000;}
static unsigned threadGetCurHandle(void){return (unsigned)(uintptr_t)test_teb.ClientId.UniqueThread+1000;}
static char lines[1024][640];static unsigned line_count;
static void log_line(const char *fmt,...){assert(line_count<1024);va_list a;va_start(a,fmt);vsnprintf(lines[line_count++],640,fmt,a);va_end(a);}
#include "../src/runtime/fex_short_trace.h"
static void *producer(void *p){
    unsigned id=(unsigned)(uintptr_t)p;test_teb.ClientId.UniqueThread=(void*)(uintptr_t)id;
    for(unsigned i=0;i<3000;i++){
        uint64_t start=wine_nx_fex_short_wait_begin(id);
        wine_nx_fex_short_alert(id,44,0);
        wine_nx_fex_short_wait_end(id,start,0x12345678,0x101);
    }return NULL;
}
int main(void){
    const char *prefixes[]={"[FEX3-JIT-THREAD] tid=4","[FEX3-JIT-SLOW] tid=4","[FEX3-JIT-CLOCK] origin_tick=1"};
    for(unsigned i=0;i<3;i++)assert(fex_short_enqueue_text(prefixes[i]));
    assert(!fex_short_enqueue_text("[FEX3-JIT] old aggregate"));
    assert(fex_short_text.count==0 && wine_nx_fex_short_wait_begin(4)==0);
    fex_short_enabled=1;test_teb.ClientId.UniqueThread=(void*)4;
    char message[64]="[FEX3-JIT-THREAD] tid=4";fex_short_enqueue_text(message);message[17]='X';
    fex_short_drain();assert(!strcmp(lines[0],prefixes[0]));
    char longline[600];memset(longline,'x',sizeof(longline));memcpy(longline,prefixes[0],strlen(prefixes[0]));longline[599]=0;
    assert(fex_short_enqueue_text(longline)&&fex_short_text.dropped==1);
    pthread_mutex_lock(&fex_short_text.mutex);assert(fex_short_enqueue_text(prefixes[0]));pthread_mutex_unlock(&fex_short_text.mutex);
    assert(fex_short_text.dropped==2);
    for(unsigned i=0;i<FEX_SHORT_TEXT+1;i++)fex_short_enqueue_text(prefixes[i%3]);
    assert(fex_short_text.count==FEX_SHORT_TEXT && fex_short_text.dropped==3);
    while(fex_short_text.count)fex_short_drain();
    uint64_t start=wine_nx_fex_short_wait_begin(4);now+=19200*25;
    wine_nx_fex_short_alert(4,164,0);wine_nx_fex_short_wait_end(4,start,0x12345678,0x101);
    struct fex_short_row r=fex_short_queue.rows[fex_short_queue.head];
    assert(r.tid==4&&r.handle==1004&&r.waker==164&&r.wakes==1&&r.result==0x101&&r.wake_tick==now&&r.object==0x12345678);
    fex_short_drain();
    // A busy metadata lock at completion must not leak the slot forever.
    start=wine_nx_fex_short_wait_begin(4);struct fex_short_wait_slot *s=&fex_short_waits[1];
    s->busy=1;now+=19200*30;wine_nx_fex_short_wait_end(4,start,0x12345678,0x102);assert(s->live==0);s->busy=0;
    start=wine_nx_fex_short_wait_begin(4);assert(s->live!=0);wine_nx_fex_short_wait_end(4,start,0x12345678,0x101);
    // Same bucket on another thread cannot retire the first wait.
    start=wine_nx_fex_short_wait_begin(4);uint64_t token=s->live;
    pthread_t t;assert(!pthread_create(&t,NULL,producer,(void*)516));pthread_join(t,NULL);assert(s->live==token);
    wine_nx_fex_short_wait_end(4,start,0x12345678,0x101);assert(s->live==0);
    // Stress concurrent alert/wait metadata without parking or allocation.
    pthread_t threads[8];for(unsigned i=0;i<8;i++)assert(!pthread_create(&threads[i],NULL,producer,(void*)(uintptr_t)(4+i*512)));
    for(unsigned i=0;i<8;i++)pthread_join(threads[i],NULL);assert(s->live==0);
    while(fex_short_queue.count)fex_short_drain();
    start=now;wine_nx_fex_short_stage(1,start,start+19200*19,0,0);assert(!fex_short_queue.count);
    wine_nx_fex_short_stage(1,start,start+19200*20,0,2);assert(fex_short_queue.count==1 && fex_short_queue.rows[fex_short_queue.head].tid==4);
    fex_short_present_map();assert(fex_short_queue.count==2);fex_short_present_map();assert(fex_short_queue.count==2);
    for(unsigned i=0;i<FEX_SHORT_ROWS;i++)wine_nx_fex_short_stage(1,start,start+19200*20,0,0);
    assert(fex_short_queue.count==FEX_SHORT_ROWS&&fex_short_queue.dropped==2);
    pthread_mutex_lock(&fex_short_queue.mutex);wine_nx_fex_short_stage(1,start,start+19200*20,0,0);pthread_mutex_unlock(&fex_short_queue.mutex);assert(fex_short_queue.dropped==3);
    while(fex_short_queue.count)fex_short_drain();fex_short_report();
    unsigned saved=line_count;fex_short_enabled=0;fex_short_report();wine_nx_fex_short_stage(1,start,start+19200*100,0,0);
    assert(line_count==saved&&!fex_short_queue.count);puts("PASS native queues, OFF, overflow, timing threshold, wait/alert pairing, retirement races, collisions and threads");
}
