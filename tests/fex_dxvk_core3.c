/* Execute the production policy with explicit kernel failure injection. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <assert.h>
#include <stdlib.h>
typedef uint32_t Handle,Result,u32;typedef uint64_t u64;typedef int32_t s32;
#define R_SUCCEEDED(r) ((r)==0)
#define R_FAILED(r) ((r)!=0)
#define CUR_PROCESS_HANDLE 99
#define InfoType_CoreMask 0
#define InfoType_PriorityMask 1
#define NX_PROF_MAX_THREADS 8
struct nx_prof_thread {Handle handle;unsigned tid;char kind;int fixed;uint64_t teb;};
static struct nx_prof_thread registry[NX_PROF_MAX_THREADS];
static pthread_mutex_t registry_mutex=PTHREAD_MUTEX_INITIALIZER;
static u64 granted=15,priorities=UINT64_MAX,mask=2;static s32 priority=59;
static int calls,fail_priority,fail_core,fail_get,fail_restore;static unsigned following;
static uint64_t armGetSystemTick(void){return 19200000;}
static Result svcGetInfo(u64 *v,int type,Handle p,u64 x){(void)p;(void)x;*v=type?priorities:granted;return fail_get;}
static Result svcGetThreadCoreMask(s32 *c,u64 *m,Handle h){(void)h;*m=mask;*c=__builtin_ctzll(mask);return fail_get;}
static Result svcGetThreadPriority(s32 *p,Handle h){(void)h;*p=priority;return fail_get;}
static Result svcSetThreadCoreMask(Handle h,s32 c,u32 m){(void)h;calls++;assert(m&(1u<<c));assert(!(m&~granted));if((m==8&&fail_core)||(m!=8&&fail_restore))return 0xbad;mask=m;return 0;}
static Result svcSetThreadPriority(Handle h,s32 p){(void)h;calls++;if(fail_priority)return 0xbad;priority=p;return 0;}
static void follow(void *t,unsigned m){(void)t;following=m;}
static void (*horizon_follow_thread_cores)(void*,unsigned)=follow;
static char last_log[512];
static void wine_nx_runtime_trace(const char *line){assert(!pthread_mutex_trylock(&registry_mutex));pthread_mutex_unlock(&registry_mutex);snprintf(last_log,sizeof(last_log),"%s",line);}
#include "../src/runtime/fex_dxvk_core3.h"
static void reset(void){memset(registry,0,sizeof(registry));memset(fex_dxvk_slots,0,sizeof(fex_dxvk_slots));registry[0]=(struct nx_prof_thread){42,24,'w',0,123};mask=2;priority=59;granted=15;priorities=UINT64_MAX;calls=fail_core=fail_priority=fail_get=fail_restore=following=0;fex_dxvk_enabled=0;}
int main(void){
    reset();wine_nx_fex_dxvk_configure(0,0);wine_nx_fex_dxvk_name(24,"dxvk-cs");assert(!calls&&mask==2);
    for(int trial=0;trial<4;trial++){reset();if(trial==0)granted=7;if(trial==1)priorities&=~(UINT64_C(1)<<63);if(trial==2)fail_get=1;wine_nx_fex_dxvk_configure(1,trial==3);wine_nx_fex_dxvk_name(24,"dxvk-cs");assert(!calls&&!fex_dxvk_enabled);}
    reset();wine_nx_fex_dxvk_configure(1,0);
    const char *ordinary[]={"dxvk-submit","dxvk-queue","dxvk-cs-extra","DXVK-CS","game","","vkd3d_queue","wined3d_cs"};
    for(unsigned i=0;i<sizeof(ordinary)/sizeof(*ordinary);i++)wine_nx_fex_dxvk_name(24,ordinary[i]);assert(!calls);
    registry[0].fixed=1;wine_nx_fex_dxvk_name(24,"dxvk-cs");assert(!calls);registry[0].fixed=0;
    wine_nx_fex_dxvk_name(999,"dxvk-cs");assert(!calls);
    wine_nx_fex_dxvk_name(24,"dxvk-cs");assert(mask==8&&priority==63&&fex_dxvk_slots[0].active&&following==0);
    int n=calls;wine_nx_fex_dxvk_name(24,"dxvk-cs");assert(calls==n);
    wine_nx_fex_dxvk_name(24,"renamed");assert(mask==2&&priority==59&&!fex_dxvk_slots[0].active);
    wine_nx_fex_dxvk_name(24,"dxvk-cs");assert(wine_nx_fex_dxvk_affinity(24,4));assert(mask==4&&priority==59&&!fex_dxvk_slots[0].active&&registry[0].fixed&&following==4);
    assert(!wine_nx_fex_dxvk_affinity(999,4));
    reset();wine_nx_fex_dxvk_configure(1,0);fail_priority=1;wine_nx_fex_dxvk_name(24,"dxvk-cs");assert(mask==2&&priority==59&&!fex_dxvk_slots[0].active);
    reset();wine_nx_fex_dxvk_configure(1,0);fail_core=1;wine_nx_fex_dxvk_name(24,"dxvk-cs");assert(mask==2&&priority==59&&!fex_dxvk_slots[0].active);
    reset();wine_nx_fex_dxvk_configure(1,0);wine_nx_fex_dxvk_name(24,"dxvk-cs");fail_restore=1;wine_nx_fex_dxvk_name(24,"renamed");assert(mask==8&&priority==63&&fex_dxvk_slots[0].active);fail_restore=0;wine_nx_fex_dxvk_name(24,"renamed");assert(mask==2&&priority==59&&!fex_dxvk_slots[0].active);
    reset();wine_nx_fex_dxvk_configure(1,0);wine_nx_fex_dxvk_name(24,"dxvk-cs");fail_priority=1;assert(wine_nx_fex_dxvk_affinity(24,4));assert(mask==4&&priority==63&&fex_dxvk_slots[0].active);fail_priority=0;assert(wine_nx_fex_dxvk_affinity(24,4));assert(priority==59&&!fex_dxvk_slots[0].active);
    puts("PASS OFF, exact names, grants, fixed affinity, repeated names, rename/explicit restore, syscall failures, rollback retries and logging outside lock");
}
