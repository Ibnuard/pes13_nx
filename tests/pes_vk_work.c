#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define PES_VK_WORK_NO_REPORT
#include "../src/runtime/pes_vk_work.h"
static void *worker(void *arg){
    unsigned tid=(uintptr_t)arg;
    for(unsigned i=0;i<10000;i++)pes_vk_work_add(tid,1,21);
    return NULL;
}
int main(void){
    pthread_t threads[8];uint64_t calls=0,ms=0,slow=0;
    for(unsigned i=0;i<8;i++)assert(!pthread_create(&threads[i],NULL,worker,(void*)(uintptr_t)(i+1)));
    for(unsigned i=0;i<8;i++)assert(!pthread_join(threads[i],NULL));
    for(unsigned i=0;i<PES_VK_WORK_SLOTS;i++){
        calls+=pes_vk_work[i].calls;ms+=pes_vk_work[i].wall_ms;slow+=pes_vk_work[i].slow;
    }
    assert(calls==80000&&ms==80000*21&&slow==80000&&!pes_vk_work_overflow);
    memset(pes_vk_work,0,sizeof(pes_vk_work));
    for(unsigned i=1;i<=PES_VK_WORK_SLOTS;i++)pes_vk_work_add(i,1,10);
    pes_vk_work_add(PES_VK_WORK_SLOTS+1,1,999);assert(pes_vk_work_overflow==1);
    pes_vk_work_add(1,1,20);calls=0;
    for(unsigned i=0;i<PES_VK_WORK_SLOTS;i++)calls+=pes_vk_work[i].calls;
    assert(calls==PES_VK_WORK_SLOTS+1);
    puts("PASS: eight concurrent writers keep call/wall/slow counters; full fixed table remains bounded and reports overflow; existing keys still update.");
}
