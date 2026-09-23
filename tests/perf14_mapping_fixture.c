/* Host model for reservation ownership; not a Horizon kernel emulator. */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#define BOOL int
#define FALSE 0
#define ULONG_PTR uintptr_t
#define min(a,b) ((a)<(b)?(a):(b))
#define PROT_NONE 0
#define PROT_READ 1
#define PROT_WRITE 2
#define MAP_PRIVATE 2
#define MAP_ANON 0x1000
#define MAP_FIXED 0x10
#define MAP_FIXED_NOREPLACE 0x100000
#define MAP_FAILED ((void*)-1)
#define SECTION_NONE 0
#define SECTION_HOLE 1
#define SECTION_ALIASED 2
#define SECTION_ANCHOR 3
#define WARN(...) ((void)0)
#define horizon_trace(...) ((void)0)
static char arena[8*4096] __attribute__((aligned(4096)));
typedef struct { char *start; size_t size; int active; } VirtmemReservation;
struct horizon_memfile { int refs, uses; };
struct horizon_mapping {
    void *addr; size_t size; VirtmemReservation *reservation;
    struct horizon_memfile *section; size_t section_offset;
    unsigned char section_state; int prot;
};
static VirtmemReservation reservations[100];
static struct horizon_mapping mappings[100], root;
static struct horizon_memfile section;
static int slots, res_count, required, exposed, kernel[8], armed;
static int fail_res, fail_piece, pieces, fail_map, fail_split, fail_unmap;
static unsigned long long section_view_maps;
static pthread_mutex_t mapping_mutex = PTHREAD_MUTEX_INITIALIZER;
static void probe(void) {
    if (!armed) return;
    for (int p=0; p<8; p++) {
        if (!(required & (1<<p)) || kernel[p]) continue;
        int covered=0;
        for (int i=0; i<res_count; i++)
            if (reservations[i].active && arena+p*4096 >= reservations[i].start &&
                arena+p*4096 < reservations[i].start+reservations[i].size) covered=1;
        if (!covered) exposed |= 1<<p;
    }
}
static int active(void) { int n=0; for(int i=0;i<res_count;i++) n+=reservations[i].active; return n; }
static VirtmemReservation *reserve_fixed_range(void *addr, size_t size) {
    probe();
    if (fail_res && --fail_res == 0) { errno=ENOMEM; return NULL; }
    assert(res_count<100);
    reservations[res_count]=(VirtmemReservation){addr,size,1};
    return &reservations[res_count++];
}
static VirtmemReservation *reserve_fixed_range_locked(void *a,size_t n) { return reserve_fixed_range(a,n); }
static void remove_reservation(VirtmemReservation *r) { assert(r && r->active); r->active=0; probe(); }
static void virtmemLock(void) { }
static void virtmemUnlock(void) { probe(); }
static void list_remove_mapping(struct horizon_mapping *m) { }
static void list_add_mapping(struct horizon_mapping *m) { }
static void horizon_memfile_use(struct horizon_memfile *s,size_t o,size_t n,int change) { s->uses+=change; }
static int horizon_memfile_alias(struct horizon_memfile *s,void *a,size_t o,size_t n,int map) {
    int first=((char*)a-arena)/4096;
    for (int i=0;i<(int)n/4096;i++) kernel[first+i]=map;
    probe(); return 0;
}
static int horizon_memfile_map(struct horizon_memfile *s,void *a,size_t o,size_t n) {
    probe();
    if (fail_map) { armed=0; errno=EINVAL; return -1; }
    s->uses++;
    return horizon_memfile_alias(s,a,o,n,1);
}
static struct horizon_mapping *alloc_section_range(void *addr,size_t size,struct horizon_memfile *s,
    size_t offset,int prot,unsigned char state,VirtmemReservation *r) {
    if (fail_piece && ++pieces==fail_piece) { errno=ENOMEM; return NULL; }
    assert(slots<100);
    struct horizon_mapping *m=&mappings[slots++];
    *m=(struct horizon_mapping){addr,size,r,s,offset,state,prot}; s->refs++;
    return m;
}
static void free_section_range(struct horizon_mapping *m) {
    m->section->refs--; if(m->section_state==SECTION_ALIASED)m->section->uses--;
}
static struct horizon_mapping *section_range_piece(struct horizon_mapping *parent,char *addr,size_t size,
    unsigned char state,int prot,BOOL count_use) {
    VirtmemReservation *r=reserve_fixed_range(addr,size);
    if(!r)return NULL;
    struct horizon_mapping *m=alloc_section_range(addr,size,parent->section,
        parent->section_offset+(addr-(char*)parent->addr),prot,state,r);
    if(!m) { remove_reservation(r); return NULL; }
    if(count_use) m->section->uses++;
    return m;
}
static struct horizon_mapping *find_overlap_mapping(void *addr,size_t n) { return root.size ? &root : NULL; }
static int unmap_range_locked(void *addr,size_t n) {
    if(fail_unmap) { errno=EBUSY; return -1; }
    memset(kernel,0,sizeof(kernel)); remove_reservation(root.reservation); root.size=0;
    return 0;
}
static int split_reservation_mapping(struct horizon_mapping *m,char *start,size_t n) {
    if(fail_split) { errno=ENOMEM; return -1; }
    char *end=(char*)m->addr+m->size;
    if((char*)m->addr<start) assert(reserve_fixed_range(m->addr,start-(char*)m->addr));
    if(start+n<end) assert(reserve_fixed_range(start+n,end-(start+n)));
    remove_reservation(m->reservation); return 0;
}
static int map_backing_at(void *a,size_t n,int p,int fd,off_t off,int flags,int err) {
    probe();
    if(fail_map) { armed=0; errno=EINVAL; return -1; }
    assert(reserve_fixed_range(a,n));
    return horizon_memfile_alias(&section,a,0,n,1);
}
static int protect_section_range(struct horizon_mapping *m,char *s,size_t n,int p) { assert(0); return -1; }
static struct horizon_mapping *split_backing_mapping_metadata(struct horizon_mapping *m,char *s,size_t n) { assert(0); return NULL; }
static int protect_code_mapping(struct horizon_mapping *m,int p) { assert(0); return -1; }
static void *virtmemFindCodeMemory(size_t n,size_t align) { return arena; }
static size_t page_align_size(size_t n) { return (n+4095)&~4095; }
static void reset(int is_section,int occupied,int mask) {
    memset(reservations,0,sizeof(reservations)); memset(mappings,0,sizeof(mappings));
    slots=res_count=exposed=armed=0;
    fail_res=fail_piece=pieces=fail_map=fail_split=fail_unmap=0;
    for(int i=0;i<8;i++)kernel[i]=occupied;
    section=(struct horizon_memfile){1,occupied};
    root=(struct horizon_mapping){arena,sizeof(arena),reserve_fixed_range(arena,sizeof(arena)),
        is_section?&section:NULL,0,occupied?SECTION_ALIASED:SECTION_HOLE,0};
    required=mask; armed=1;
}
/* REAL_TRANSITIONS */
static void result(void) { assert(PATCHED ? !exposed : exposed); }
int main(void) {
    /* Decommitting an alias must preserve PROT_NONE reservations, including
     * when the unaliased area is the entire original section. */
    reset(1,1,255); assert(!change_section_range(&root,arena+2*4096,3*4096,SECTION_HOLE,0)); result();
    reset(1,1,255); assert(!change_section_range(&root,arena,sizeof(arena),SECTION_HOLE,0)); result();
    /* Partial removal releases only the middle; uncommitted side pieces
     * must never briefly become native allocation candidates. */
    reset(1,0,0xe3); assert(!change_section_range(&root,arena+2*4096,3*4096,SECTION_NONE,0)); result();
    reset(0,0,255); assert(!protect_range_locked(arena+2*4096,3*4096,3)); result();
    reset(0,0,255); assert(horizon_mmap_section(arena,sizeof(arena),3,MAP_FIXED,&section,0)==arena); result();
    if(PATCHED) {
        /* Failed piece creation restores the original reservation and refs. */
        for(int f=1;f<=3;f++) {
            reset(1,1,255); fail_piece=f;
            assert(change_section_range(&root,arena+2*4096,3*4096,SECTION_HOLE,0)==-1);
            assert(errno==ENOMEM && !exposed && active()==1 && root.reservation->active);
            assert(section.refs==1 && section.uses==1);
        }
        reset(0,0,255); fail_res=1;
        assert(protect_range_locked(arena,4096,3)==-1 && errno==ENOMEM && active()==1 && !exposed);
        reset(0,0,255); fail_split=1;
        assert(protect_range_locked(arena,4096,3)==-1 && errno==ENOMEM && active()==1 && !exposed);
        reset(0,0,255); fail_map=1;
        assert(protect_range_locked(arena,sizeof(arena),3)==-1 && errno==EINVAL && active()==0);
        reset(0,0,255); fail_unmap=1;
        assert(horizon_mmap_section(arena,sizeof(arena),3,MAP_FIXED,&section,0)==MAP_FAILED);
        assert(errno==EBUSY && active()==1 && !exposed);
        reset(0,0,255); fail_map=1;
        assert(horizon_mmap_section(arena,sizeof(arena),3,MAP_FIXED,&section,0)==MAP_FAILED);
        assert(errno==EINVAL && active()==0);
    }
    puts(PATCHED ? "PERF14 transitions PASS: ownership never exposed; failures release guards/restore original section" :
        "PERF14 control PASS: native allocation probes detect all three baseline reservation gaps");
}
