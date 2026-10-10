/* LGPL-2.1-or-later. Debug-only attribution of existing Vulkan probe calls.
 * The completion path stores counters in fixed RAM. It never allocates,
 * writes files, blocks, walks a guest stack, or pauses another thread. */
#ifndef PES_VK_WORK_H
#define PES_VK_WORK_H
#include <stdint.h>
#define PES_VK_WORK_SLOTS 256
static struct {uint64_t key,calls,wall_ms,slow;} pes_vk_work[PES_VK_WORK_SLOTS];
static uint64_t pes_vk_work_overflow;
static void pes_vk_work_add(unsigned thread,unsigned code,uint64_t wall_ms)
{
    uint64_t key=((uint64_t)thread<<32)|code;
    if(!thread)return;
    unsigned start=(thread^(code*2654435761u))%PES_VK_WORK_SLOTS;
    for(unsigned n=0;n<PES_VK_WORK_SLOTS;n++){
        unsigned i=(start+n)%PES_VK_WORK_SLOTS;
        uint64_t expected=0;
        if(__atomic_load_n(&pes_vk_work[i].key,__ATOMIC_ACQUIRE)!=key&&
           !__atomic_compare_exchange_n(&pes_vk_work[i].key,&expected,key,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))continue;
        __atomic_add_fetch(&pes_vk_work[i].calls,1,__ATOMIC_RELAXED);
        __atomic_add_fetch(&pes_vk_work[i].wall_ms,wall_ms,__ATOMIC_RELAXED);
        if(wall_ms>=20)__atomic_add_fetch(&pes_vk_work[i].slow,1,__ATOMIC_RELAXED);
        return;
    }
    __atomic_add_fetch(&pes_vk_work_overflow,1,__ATOMIC_RELAXED);
}
#ifndef PES_VK_WORK_NO_REPORT
static void pes_vk_work_report(void)
{
    static struct {uint64_t calls,wall_ms,slow;} previous[PES_VK_WORK_SLOTS];
    struct {uint64_t key,calls,wall_ms,slow;} top[6]={{0}};
    for(unsigned i=0;i<PES_VK_WORK_SLOTS;i++){
        uint64_t key=__atomic_load_n(&pes_vk_work[i].key,__ATOMIC_ACQUIRE);
        if(!key)continue;
        uint64_t calls=__atomic_load_n(&pes_vk_work[i].calls,__ATOMIC_RELAXED);
        uint64_t ms=__atomic_load_n(&pes_vk_work[i].wall_ms,__ATOMIC_RELAXED);
        uint64_t slow=__atomic_load_n(&pes_vk_work[i].slow,__ATOMIC_RELAXED);
        uint64_t dc=calls-previous[i].calls,dm=ms-previous[i].wall_ms,ds=slow-previous[i].slow;
        previous[i].calls=calls;previous[i].wall_ms=ms;previous[i].slow=slow;
        if(!dc&&!dm&&!ds)continue;
        for(unsigned j=0;j<6;j++)if(!top[j].key||dm>top[j].wall_ms||(dm==top[j].wall_ms&&dc>top[j].calls)){
            for(unsigned k=5;k>j;k--)top[k]=top[k-1];
            top[j].key=key;top[j].calls=dc;top[j].wall_ms=dm;top[j].slow=ds;break;
        }
    }
    for(unsigned j=0;j<6;j++)if(top[j].key)
        fx_launch_debug_log("[LW3-VKWORK] thread=%x code=%x calls=%llu wall_ms=%llu over20ms=%llu; completed-call wall time includes scheduling/waits, not GPU time",
            (unsigned)(top[j].key>>32),(unsigned)top[j].key,(unsigned long long)top[j].calls,
            (unsigned long long)top[j].wall_ms,(unsigned long long)top[j].slow);
    fx_launch_debug_log("[LW3-VKWORK] overflow=%llu cumulative; fixed RAM counters, Debug only",
        (unsigned long long)__atomic_load_n(&pes_vk_work_overflow,__ATOMIC_RELAXED));
}
#endif
#endif
