#include <assert.h>
#include <dirent.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define HORIZON_STATUS_INVALID_PARAMETER 0xc000000du
#define HORIZON_STATUS_NO_MEMORY 0xc0000017u
#define HORIZON_STATUS_INVALID_HANDLE 0xc0000008u
#define HORIZON_STATUS_OBJECT_TYPE_MISMATCH 0xc0000024u
#define HORIZON_STATUS_INFO_LENGTH_MISMATCH 0xc0000004u
#define HORIZON_SERVER_OBJECT_FILE 1
#define END_SCAN 0x80000006u
#define FIRST_MISS 0xc000000fu
#define IO_ERROR 0xc0000185u

struct horizon_server_request_header { unsigned request, request_size, reply_size; };
struct horizon_server_reply_header { unsigned error, reply_size; };
struct horizon_query_directory_file_request {
    struct horizon_server_request_header header;
    unsigned handle, restart_scan;
    char pad[4];
};
struct horizon_query_directory_file_reply {
    struct horizon_server_reply_header header;
    unsigned total_len;
    char pad[4];
};
struct horizon_directory_file_entry { unsigned name_len; };
struct horizon_server_object {
    int type, file_is_dir;
    char *file_name;
    /* OBJECT_FIELDS */
};
struct horizon_server_handle_entry { struct horizon_server_object *object; } handles[4];
struct horizon_server_connection { int reply_fd; };
static pthread_mutex_t horizon_server_objects_mutex = PTHREAD_MUTEX_INITIALIZER;
static uint64_t opens, reads, closes, traces;
static unsigned fail_open, fail_read, fail_alloc;
static struct {
    unsigned error, size, total;
    char name[256];
} replies[4];

static DIR *test_opendir(const char *path) {
    opens++;
    if (fail_open) { fail_open--; errno=EMFILE; return NULL; }
    return opendir(path);
}
static struct dirent *test_readdir(DIR *dir) {
    reads++;
    if (fail_read) { fail_read--; errno=EIO; return NULL; }
    return readdir(dir);
}
static int test_closedir(DIR *dir) { closes++; return closedir(dir); }
static void *test_calloc(size_t n, size_t size) {
    if (fail_alloc) { fail_alloc--; return NULL; }
    return calloc(n,size);
}
static struct horizon_server_handle_entry *horizon_server_find_handle_locked(unsigned h) {
    return h<4 && handles[h].object ? &handles[h] : NULL;
}
static unsigned horizon_server_errno_status(int e) { assert(e); return IO_ERROR; }
static unsigned horizon_dir_scan_end_status(int first) { return first?FIRST_MISS:END_SCAN; }
static int horizon_server_ascii_lower(int c) { return c>='A' && c<='Z' ? c+32:c; }
static void horizon_trace(const char *fmt,...) { (void)fmt; __atomic_add_fetch(&traces,1,__ATOMIC_RELAXED); }
static int horizon_server_write_reply(int fd, const void *reply, unsigned size,
                                      const void *data, unsigned count) {
    assert(size==sizeof(struct horizon_query_directory_file_reply));
    const struct horizon_query_directory_file_reply *r=reply;
    assert(fd>=0 && fd<4 && count<1024);
    replies[fd].error=r->header.error;
    replies[fd].total=r->total_len;
    replies[fd].size=count;
    replies[fd].name[0]=0;
    if (count) {
        const struct horizon_directory_file_entry *d=data;
        const unsigned char *name=(const unsigned char *)(d+1);
        assert(!r->header.error && count==r->header.reply_size);
        assert(count>=sizeof(*d)+d->name_len && d->name_len/2<256);
        for(unsigned i=0;i<d->name_len/2;i++) {
            assert(name[i*2+1]==0);replies[fd].name[i]=name[i*2];
        }
        replies[fd].name[d->name_len/2]=0;
#ifdef METADATA_REPLY
        unsigned id;
        if(sscanf(replies[fd].name,"unnamed_%u.bin",&id)==1)
            assert(d->metadata==1 && d->file_size==(uint64_t)id*0x100000001ULL);
        else assert(!d->metadata && !d->file_size);
#endif
    }
    return 0;
}
#define opendir test_opendir
#define readdir test_readdir
#define closedir test_closedir
#define calloc test_calloc
/* PRODUCTION_FUNCTIONS */
#undef opendir
#undef readdir
#undef closedir
#undef calloc

static void setup(struct horizon_server_object *o, const char *path, unsigned h) {
    memset(o,0,sizeof(*o));o->type=HORIZON_SERVER_OBJECT_FILE;o->file_is_dir=1;
    o->file_name=strdup(path);assert(o->file_name);handles[h].object=o;
}
static void cleanup(struct horizon_server_object *o) {
#ifndef BASELINE
    horizon_server_reset_directory(o);
    assert(!o->dir_stream && !o->dir_pending_name);
#endif
    free(o->file_name);free(o->dir_mask);
    for(unsigned i=0;i<4;i++)if(handles[i].object==o)handles[i].object=NULL;
}
static unsigned query(unsigned handle, unsigned restart, const char *mask, unsigned size, unsigned fd) {
    unsigned char utf16[512];unsigned n=mask?strlen(mask):0;assert(n<256);
    for(unsigned i=0;i<n;i++) { utf16[i*2]=mask[i];utf16[i*2+1]=0; }
    struct horizon_query_directory_file_request r={{0,0,size},handle,restart,{0}};
    struct horizon_server_connection c={(int)fd};
    assert(horizon_server_handle_query_directory_file(&c,(void *)&r,utf16,n*2)==0);
    return replies[fd].error;
}
static uint64_t hash_name(uint64_t hash, const char *name) {
    do { hash=(hash^(unsigned char)*name)*1099511628211ull; } while(*name++);
    return hash;
}
static unsigned seen[14258], shared_count;
static pthread_mutex_t collect_mutex=PTHREAD_MUTEX_INITIALIZER;
static void *worker(void *p) {
    unsigned fd=(uintptr_t)p;
    for (;;) {
        unsigned e=query(fd,0,NULL,1024,fd);
        if(e==END_SCAN)break;
        assert(!e);
        unsigned id=0;
        if(sscanf(replies[fd].name,"unnamed_%u.bin",&id)!=1)continue;
        assert(id<14258);
        pthread_mutex_lock(&collect_mutex);assert(!seen[id]);seen[id]=1;shared_count++;
        pthread_mutex_unlock(&collect_mutex);
    }
    return NULL;
}
int main(int argc,char **argv) {
    assert(argc==2);struct horizon_server_object o;
    setup(&o,argv[1],0);
    uint64_t hash=1469598103934665603ull;unsigned n=0,e;
    while(!(e=query(0,n==0,n==0?"*":NULL,1024,0))) {
        hash=hash_name(hash,replies[0].name);n++;
    }
    assert(n==14260 && e==END_SCAN);
    uint64_t benchmark_opens=opens, benchmark_reads=reads, benchmark_traces=traces;
    cleanup(&o);assert(opens==closes);
    unsigned checks=1;

    /* Buffer/heap failures must retain the pending entry; masks, synthetic
     * dots, duplicate handles and restart must preserve the stream position. */
    setup(&o,argv[1],0);handles[1].object=&o;
    assert(query(0,1,"*",1,0)==HORIZON_STATUS_INFO_LENGTH_MISMATCH);
    assert(query(1,0,NULL,1024,1)==0 && !strcmp(replies[1].name,"."));
    fail_alloc=1;
    assert(query(0,0,NULL,1024,0)==HORIZON_STATUS_NO_MEMORY);
    assert(query(0,0,NULL,1024,0)==0 && !strcmp(replies[0].name,".."));
    assert(query(0,0,NULL,1,0)==HORIZON_STATUS_INFO_LENGTH_MISMATCH);
    fail_alloc=1;assert(query(1,0,NULL,1024,1)==HORIZON_STATUS_NO_MEMORY);
    assert(query(0,0,NULL,1024,0)==0);
    char first[256];strcpy(first,replies[0].name);
    assert(query(0,1,"UNNAMED_*.BIN",1024,0)==0 && !strcmp(replies[0].name,first));
    assert(query(1,0,NULL,1024,1)==0 && strcmp(replies[1].name,first));
    assert(query(0,1,"does-not-exist",1024,0)==END_SCAN);
    assert(query(0,0,NULL,1024,0)==END_SCAN);
    assert(query(0,1,"*",1024,0)==0 && !strcmp(replies[0].name,"."));
    cleanup(&o);assert(opens==closes);checks++;

    /* New mask after a failed reply must rescan from the last delivered name,
     * including entries skipped by the old mask. A repeated mask stays O(n). */
    setup(&o,argv[1],0);
    assert(query(0,1,"*.bin",1,0)==HORIZON_STATUS_INFO_LENGTH_MISMATCH);
    assert(query(0,0,"*",1024,0)==0 && !strcmp(replies[0].name,"."));
    uint64_t same_mask_opens=opens;
    for(unsigned i=0;i<20;i++)assert(query(0,0,"*",1024,0)==0);
#ifndef BASELINE
    assert(opens==same_mask_opens);
#else
    (void)same_mask_opens;
#endif
    cleanup(&o);assert(opens==closes);checks++;

    setup(&o,argv[1],0);
    assert(query(0,1,"absent",1024,0)==FIRST_MISS);
    assert(query(0,0,NULL,1024,0)==END_SCAN);
    cleanup(&o);assert(opens==closes);checks++;

    setup(&o,argv[1],0);fail_open=1;
    assert(query(0,1,"*",1024,0)==IO_ERROR);
    assert(query(0,0,NULL,1024,0)==0 && !strcmp(replies[0].name,"."));
    cleanup(&o);assert(opens==closes+1);checks++;

    assert(query(3,1,"*",1024,0)==HORIZON_STATUS_INVALID_HANDLE);
    setup(&o,argv[1],0);o.file_is_dir=0;
    assert(query(0,1,"*",1024,0)==HORIZON_STATUS_OBJECT_TYPE_MISMATCH);
    o.file_is_dir=1;
    struct horizon_query_directory_file_request r={{0,0,1024},0,1,{0}};
    struct horizon_server_connection c={0};
    assert(horizon_server_handle_query_directory_file(&c,(void *)&r,(void *)"a",1)==0);
    assert(replies[0].error==HORIZON_STATUS_INVALID_PARAMETER);
    cleanup(&o);checks++;

#ifndef BASELINE
    setup(&o,argv[1],0);
    assert(query(0,1,"*",1024,0)==0);
    assert(query(0,0,NULL,1024,0)==0);
    fail_read=1;
    assert(query(0,0,NULL,1024,0)==IO_ERROR);
    assert(query(0,0,NULL,1024,0)==0 && !strcmp(replies[0].name,first));
    cleanup(&o);checks++;

    /* Two clients on duplicate handles share exactly one iterator; closing a
     * duplicate must not invalidate the remaining object's pending stream. */
    setup(&o,argv[1],0);handles[1].object=&o;
    pthread_t a,b;
    assert(!pthread_create(&a,NULL,worker,(void *)0));
    assert(!pthread_create(&b,NULL,worker,(void *)1));
    assert(!pthread_join(a,NULL) && !pthread_join(b,NULL));
    assert(shared_count==14258);
    assert(query(0,1,"*",1024,0)==0);handles[0].object=NULL;
    assert(query(1,0,NULL,1024,1)==0 && !strcmp(replies[1].name,".."));
    cleanup(&o);assert(opens==closes+1);checks++;

    /* Distinct file objects must not share cursor state. */
    struct horizon_server_object other;
    setup(&o,argv[1],0);setup(&other,argv[1],1);
    assert(query(0,1,"*",1024,0)==0 && !strcmp(replies[0].name,"."));
    assert(query(0,0,NULL,1024,0)==0 && !strcmp(replies[0].name,".."));
    assert(query(1,1,"*",1024,1)==0 && !strcmp(replies[1].name,"."));
    cleanup(&o);cleanup(&other);assert(opens==closes+1);checks++;
#endif
    printf("{\"passed\":true,\"cases\":%u,\"files\":%u,\"ordered_hash\":\"%016llx\","
           "\"open_calls\":%llu,\"read_calls\":%llu,\"trace_calls\":%llu}\n",
           checks,n,(unsigned long long)hash,(unsigned long long)benchmark_opens,
           (unsigned long long)benchmark_reads,(unsigned long long)benchmark_traces);
    return 0;
}
