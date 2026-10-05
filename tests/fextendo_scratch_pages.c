/* Real shared mappings with inaccessible borrowed source pages. */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
typedef uint32_t Result;
typedef struct {void *address;size_t size;} VirtmemReservation;
typedef pthread_mutex_t host_mutex;
#define HOST_LOCK(x) pthread_mutex_lock(x)
#define HOST_UNLOCK(x) pthread_mutex_unlock(x)
#define PAGE_BYTES 4096
#define R_FAILED(x) ((x)!=0)
static void *test_alloc(size_t,size_t);
static void test_free(void *);
static void virtmemLock(void);
static void virtmemUnlock(void);
static void *virtmemFindStack(size_t,size_t);
static VirtmemReservation *virtmemAddReservation(void *,size_t);
static void virtmemRemoveReservation(VirtmemReservation *);
static Result svcMapMemory(void *,void *,size_t);
static Result svcUnmapMemory(void *,void *,size_t);
#define FX_SP_CODE_ALIAS 1
#define Perm_Rw 3
static int envIsSyscallHinted(unsigned);
static unsigned envGetOwnProcessHandle(void){return 0x1234;}
static void *virtmemFindCodeMemory(size_t,size_t);
static Result svcMapProcessCodeMemory(unsigned,uintptr_t,uintptr_t,size_t);
static Result svcUnmapProcessCodeMemory(unsigned,uintptr_t,uintptr_t,size_t);
static Result svcSetProcessMemoryPermission(unsigned,uintptr_t,size_t,unsigned);
#define aligned_alloc test_alloc
#define free test_free
#include "../src/fex/horizon_scratch_pages.h"
#undef free
#undef aligned_alloc
struct allocation {void *p,*alias;size_t size;int fd;};
static struct allocation allocations[FX_SP_PIECES];
static pthread_mutex_t alloc_lock=PTHREAD_MUTEX_INITIALIZER,vm_lock=PTHREAD_MUTEX_INITIALIZER;
static unsigned limit=1024*1024,remaining=~0u,used,map_calls,unmap_calls,fail_map,fail_unmap;
static int no_va,no_reservation;
static int code_disabled,no_stack_va;
static unsigned permission_calls,fail_permission;
static void *last_va;static size_t last_size;
#ifdef FX_TEST_VA_REUSE
static void (*after_vm_unlock)(void);
static int reuse_on_release;
static void *reuse_va;
static size_t reuse_size;
#endif
static struct allocation *find(void *p){for(unsigned i=0;i<FX_SP_PIECES;i++)if(allocations[i].p==p)return &allocations[i];assert(0);return NULL;}
static void *test_alloc(size_t alignment,size_t n){
    assert(alignment==4096&&n%4096==0);pthread_mutex_lock(&alloc_lock);
    if(n>limit||!remaining){pthread_mutex_unlock(&alloc_lock);return NULL;}
    remaining--;struct allocation *a=NULL;
    for(unsigned i=0;i<FX_SP_PIECES;i++)if(!allocations[i].p){a=&allocations[i];break;}
    assert(a);a->fd=memfd_create("scratch",0);assert(a->fd>=0&&!ftruncate(a->fd,n));
    a->p=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_SHARED,a->fd,0);assert(a->p!=MAP_FAILED);
    a->size=n;a->alias=NULL;used++;void *p=a->p;pthread_mutex_unlock(&alloc_lock);return p;
}
static void test_free(void *p){
    pthread_mutex_lock(&alloc_lock);struct allocation *a=find(p);assert(!a->alias);
    assert(!munmap(a->p,a->size));close(a->fd);memset(a,0,sizeof(*a));used--;pthread_mutex_unlock(&alloc_lock);
}
static void virtmemLock(void){pthread_mutex_lock(&vm_lock);}
static void virtmemUnlock(void){
    pthread_mutex_unlock(&vm_lock);
#ifdef FX_TEST_VA_REUSE
    if(after_vm_unlock&&reuse_va){void (*hook)(void)=after_vm_unlock;after_vm_unlock=NULL;hook();}
#endif
}
static void *virtmemFindStack(size_t n,size_t guard){
    assert(guard==4096);if(no_va||no_stack_va)return NULL;
#ifdef FX_TEST_VA_REUSE
    if(reuse_va){assert(n==reuse_size);last_va=reuse_va;last_size=n;reuse_va=NULL;return last_va;}
#endif
    last_va=mmap(NULL,n,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);assert(last_va!=MAP_FAILED);last_size=n;return last_va;
}
static int envIsSyscallHinted(unsigned svc){assert(svc==0x73||svc==0x77||svc==0x78);return !code_disabled;}
static void *virtmemFindCodeMemory(size_t n,size_t guard){
    int saved=no_stack_va;no_stack_va=0;void *p=virtmemFindStack(n,guard);no_stack_va=saved;return p;
}
static VirtmemReservation *virtmemAddReservation(void *p,size_t n){
    assert(p==last_va&&n==last_size);
    if(no_reservation){assert(!munmap(p,n));return NULL;}
    VirtmemReservation *r=malloc(sizeof(*r));assert(r);*r=(VirtmemReservation){p,n};return r;
}
static void virtmemRemoveReservation(VirtmemReservation *r){
    assert(!munmap(r->address,r->size));
#ifdef FX_TEST_VA_REUSE
    if(reuse_on_release){
        reuse_on_release=0;reuse_size=r->size;
        reuse_va=mmap(r->address,r->size,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        assert(reuse_va==r->address);
    }
#endif
    free(r);
}
static Result svcMapMemory(void *dst,void *src,size_t n){
    pthread_mutex_lock(&alloc_lock);unsigned call=++map_calls;
    if(call==fail_map){pthread_mutex_unlock(&alloc_lock);return 0xd401;}
    struct allocation *a=find(src);assert(a->size==n&&!a->alias);
    assert(mmap(dst,n,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,a->fd,0)==dst);
    assert(!mprotect(src,n,PROT_NONE));a->alias=dst;pthread_mutex_unlock(&alloc_lock);return 0;
}
static Result svcUnmapMemory(void *dst,void *src,size_t n){
    pthread_mutex_lock(&alloc_lock);unsigned call=++unmap_calls;
    if(call==fail_unmap){pthread_mutex_unlock(&alloc_lock);return 0xd401;}
    struct allocation *a=find(src);assert(a->size==n&&a->alias==dst);
    assert(mmap(dst,n,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0)==dst);
    assert(!mprotect(src,n,PROT_READ|PROT_WRITE));a->alias=NULL;pthread_mutex_unlock(&alloc_lock);return 0;
}
static Result svcMapProcessCodeMemory(unsigned h,uintptr_t dst,uintptr_t src,size_t n){
    assert(h==0x1234);Result r=svcMapMemory((void *)dst,(void *)src,n);
    if(!r)assert(!mprotect((void *)dst,n,PROT_NONE));
    return r;
}
static Result svcUnmapProcessCodeMemory(unsigned h,uintptr_t dst,uintptr_t src,size_t n){
    assert(h==0x1234);return svcUnmapMemory((void *)dst,(void *)src,n);
}
static Result svcSetProcessMemoryPermission(unsigned h,uintptr_t dst,size_t n,unsigned perm){
    assert(h==0x1234&&perm==Perm_Rw);
    unsigned call=__atomic_add_fetch(&permission_calls,1,__ATOMIC_RELAXED);
    if(call==fail_permission)return 0xd401;
    assert(!mprotect((void *)dst,n,PROT_READ|PROT_WRITE));return 0;
}
static void empty(void){assert(!used&&!fx_sp_held&&!fx_sp_stats[3]&&!fx_sp_stats[5]&&!fx_sp_stats[6]);}
static void contents(void *p,size_t n,unsigned char v){
    memset(p,v,n);
    for(size_t i=0;i<n;i+=4096)assert(((unsigned char *)p)[i]==v);
    assert(((unsigned char *)p)[n-1]==v);
}
static pthread_barrier_t barrier;
static unsigned successes;
static void *concurrent(void *arg){
    unsigned char v=(uintptr_t)arg;void *p=fx_scratch_pages_take(16*1024*1024);
    if(p){contents(p,16*1024*1024,v);__atomic_add_fetch(&successes,1,__ATOMIC_RELAXED);}
    pthread_barrier_wait(&barrier);
    if(p){for(size_t i=0;i<16*1024*1024;i+=4096)assert(((unsigned char *)p)[i]==v);assert(fx_scratch_pages_release(p));}
    return NULL;
}
int main(void){
    assert(!fx_scratch_pages_take(0)&&!fx_scratch_pages_take(SIZE_MAX));empty();
    struct fx_sp_failure reason;
    assert(!fx_scratch_pages_take_report(0,&reason)&&reason.stage==FX_SP_INVALID_SIZE);
    remaining=0;assert(!fx_scratch_pages_take_report(4096,&reason)&&reason.stage==FX_SP_SOURCE_ALLOC);empty();remaining=~0u;
    no_va=1;assert(!fx_scratch_pages_take_report(4096,&reason)&&reason.stage==FX_SP_VIRTUAL_RANGE);empty();no_va=0;
    no_reservation=1;assert(!fx_scratch_pages_take_report(4096,&reason)&&reason.stage==FX_SP_RESERVATION);empty();no_reservation=0;
    fail_map=map_calls+1;assert(!fx_scratch_pages_take_report(4096,&reason)&&reason.stage==FX_SP_MAP&&reason.result==0xd401);empty();fail_map=0;
    no_stack_va=1;void *wide=fx_scratch_pages_take(16*1024*1024);assert(wide);contents(wide,16*1024*1024,0x77);fx_scratch_pages_release(wide);empty();no_stack_va=0;
    code_disabled=1;wide=fx_scratch_pages_take(4096);assert(wide);fx_scratch_pages_release(wide);empty();code_disabled=0;
    fail_permission=permission_calls+3;
    assert(!fx_scratch_pages_take_report(16*1024*1024,&reason)&&reason.stage==FX_SP_PERMISSION);empty();fail_permission=0;
    fail_permission=permission_calls+3;fail_unmap=unmap_calls+3;
    assert(!fx_scratch_pages_take_report(16*1024*1024,&reason)&&reason.stage==FX_SP_PERMISSION);
    assert(used==16&&fx_sp_stats[10]==1);fail_permission=fail_unmap=0;
    for(unsigned i=0;i<FX_SP_SLOTS;i++)if(fx_sp_slots[i].state==FX_SP_QUARANTINE)assert(fx_sp_dispose(&fx_sp_slots[i]));
    empty();fx_sp_stats[10]=0;
    /* Arbitrary page-sized CPU buffers, including non-power-of-two tails.
     * One MiB used to fail unconditionally in the fallback; so did any size
     * below 8 MiB or fragmentation below 64 KiB. */
    const size_t sizes[]={4096,12288,65536,135168,1048576,1048576+135168,6225920,17*1024*1024+4096};
    const unsigned limits[]={4096,12288,65536,1024*1024};
    for(unsigned i=0;i<sizeof(sizes)/sizeof(sizes[0]);i++){
        for(unsigned j=0;j<sizeof(limits)/sizeof(limits[0]);j++){
            limit=limits[j];void *var=fx_scratch_pages_take(sizes[i]);assert(var);
            contents(var,sizes[i],(unsigned char)(i*4+j));assert(fx_scratch_pages_release(var));empty();
        }
    }
    /* Many concurrent lookup-sized buffers must share descriptors rather
     * than exhausting the old eight compiler slots. */
    limit=65536;void *lookups[32];
    for(unsigned i=0;i<32;i++){lookups[i]=fx_scratch_pages_take(1048576);assert(lookups[i]);contents(lookups[i],1048576,(unsigned char)i);}
    for(unsigned i=0;i<32;i++){assert(((unsigned char *)lookups[i])[1048575]==i);assert(fx_scratch_pages_release(lookups[i]));}empty();
    limit=1024*1024;
    void *p=fx_scratch_pages_take(16*1024*1024);assert(p&&used==16);contents(p,16*1024*1024,0x5a);
    assert(fx_scratch_pages_release((char *)p+4096));assert(used==16&&fx_sp_stats[11]==1);
    assert(fx_scratch_pages_release(p));empty();assert(!fx_scratch_pages_release((void *)12345));
    limit=64*1024;p=fx_scratch_pages_take(16*1024*1024);assert(p&&used==256);contents(p,16*1024*1024,0xa5);assert(fx_scratch_pages_release(p));empty();
    limit=1024*1024;remaining=3;assert(!fx_scratch_pages_take(16*1024*1024));empty();remaining=~0u;
    no_va=1;assert(!fx_scratch_pages_take(16*1024*1024));empty();no_va=0;
    no_reservation=1;assert(!fx_scratch_pages_take(16*1024*1024));empty();no_reservation=0;
    fail_map=map_calls+5;assert(!fx_scratch_pages_take(16*1024*1024));empty();fail_map=0;
    pthread_t ids[12];pthread_barrier_init(&barrier,NULL,12);
    for(uintptr_t i=0;i<12;i++)assert(!pthread_create(&ids[i],NULL,concurrent,(void *)(i+1)));
    for(unsigned i=0;i<12;i++)assert(!pthread_join(ids[i],NULL));
    pthread_barrier_destroy(&barrier);
    assert(successes==8);empty();
    void *big1=fx_scratch_pages_take(64*1024*1024),*big2=fx_scratch_pages_take(64*1024*1024);
    assert(big1&&big2&&!fx_scratch_pages_take(8*1024*1024));assert(fx_sp_held==128*1024*1024);
    assert(fx_scratch_pages_release(big1)&&fx_scratch_pages_release(big2));empty();
    fail_map=map_calls+5;fail_unmap=unmap_calls+2;
    assert(!fx_scratch_pages_take(16*1024*1024));assert(used==16&&fx_sp_stats[10]==1);
    struct fx_sp_slot *q=NULL;for(unsigned i=0;i<FX_SP_SLOTS;i++)if(fx_sp_slots[i].state==FX_SP_QUARANTINE)q=&fx_sp_slots[i];
    assert(q&&fx_scratch_pages_release(q->alias)&&fx_sp_stats[10]==1);
    /* Test teardown only: model process exit, releasing deliberately retained pages. */
    fail_map=fail_unmap=0;assert(fx_sp_dispose(q));empty();
    p=fx_scratch_pages_take(16*1024*1024);assert(p);fail_unmap=unmap_calls+4;
    assert(fx_scratch_pages_release(p)&&fx_sp_stats[10]==2&&used==16);
    for(unsigned i=0;i<FX_SP_SLOTS;i++)if(fx_sp_slots[i].state==FX_SP_QUARANTINE)q=&fx_sp_slots[i];
    fail_unmap=0;assert(fx_sp_dispose(q));empty();
    puts("PASS: varied page-rounded sizes, fragments down to 4 KiB, 32 live lookups, compiler concurrency, real shared aliases/source protection, budget bounds, all rollback and quarantine paths");
    return 0;
}
