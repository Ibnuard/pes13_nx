/* Production pipe and server helpers, host handle bootstrap/transport only. */
#include <assert.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdatomic.h>
#include <stdio.h>
#include <time.h>
#include "horizon_anon_pipe.h"
#include "horizon_anon_pipe_api.h"
#include "horizon_file_access.h"
#define HORIZON_STATUS_SUCCESS 0u
#define HORIZON_STATUS_INVALID_PARAMETER 0xc000000du
#define HORIZON_STATUS_NOT_SUPPORTED 0xc00000bbu
#define HORIZON_STATUS_NO_MEMORY 0xc0000017u
#define HORIZON_STATUS_OBJECT_NAME_COLLISION 0xc0000035u
#define HORIZON_STATUS_OBJECT_NAME_NOT_FOUND 0xc0000034u
#define HORIZON_STATUS_ACCESS_DENIED 0xc0000022u
#define HORIZON_STATUS_BUFFER_TOO_SMALL 0xc0000023u
#define HORIZON_SERVER_OBJECT_FILE 8
struct horizon_server_request_header { int req;unsigned request_size,reply_size; };
struct horizon_server_reply_header { unsigned error,reply_size; };
struct horizon_open_file_object_request {
    struct horizon_server_request_header header;
    unsigned access,attributes,rootdir,sharing,options;
};
struct horizon_object_attributes { unsigned rootdir,attributes,sd_len,name_len; };
struct horizon_object_name { unsigned rootdir,name_len;const unsigned char *name; };
struct horizon_server_connection { int reply_fd; };
struct horizon_server_object {
    struct fxap_pipe *anon_pipe;
    unsigned anon_writer,anon_io_active,refs,name_len,file_access,file_options;
    unsigned char *name;
};
struct horizon_server_handle_entry {
    unsigned handle;struct horizon_server_object *object;struct horizon_server_handle_entry *next;
};
static struct horizon_server_handle_entry *horizon_server_handles;
static pthread_mutex_t horizon_server_objects_mutex=PTHREAD_MUTEX_INITIALIZER;
static unsigned next_handle=0x100,live_objects;
static unsigned char last_reply[64];
static int fail_allocation;
static struct horizon_server_handle_entry *horizon_server_find_handle_locked(unsigned h) {
    for (struct horizon_server_handle_entry *e=horizon_server_handles;e;e=e->next) if(e->handle==h)return e;
    return NULL;
}
static struct horizon_server_handle_entry *horizon_server_create_handle_locked(int type) {
    assert(type==8);
    if(fail_allocation)return NULL;
    struct horizon_server_handle_entry *e=calloc(1,sizeof(*e));assert(e);
    e->object=calloc(1,sizeof(*e->object));assert(e->object);e->object->refs=1;
    e->handle=(next_handle+=4);e->next=horizon_server_handles;horizon_server_handles=e;live_objects++;
    return e;
}
static void horizon_server_free_object(struct horizon_server_object *o) {
    fxap_close(o->anon_pipe,o->anon_writer);
    if(!--o->anon_pipe->owners)fxap_destroy(o->anon_pipe);
    free(o->name);free(o);live_objects--;
}
static void horizon_server_signal_changed_locked(void) {}
static void horizon_trace(const char *fmt,...) {(void)fmt;}
static int horizon_server_write_reply(int fd,const void *r,size_t len,const void *p,size_t n) {
    (void)fd;(void)p;assert(!n&&len<=64);memcpy(last_reply,r,len);return 0;
}
/* PARSE_ATTRIBUTES */
#include "horizon_anon_pipe_server.h"
static unsigned duplicate(unsigned h) {
    pthread_mutex_lock(&horizon_server_objects_mutex);
    struct horizon_server_handle_entry *e=calloc(1,sizeof(*e));assert(e);
    e->object=horizon_server_find_handle_locked(h)->object;e->object->refs++;
    e->handle=next_handle+=4;e->next=horizon_server_handles;horizon_server_handles=e;
    pthread_mutex_unlock(&horizon_server_objects_mutex);return e->handle;
}
static void close_handle(unsigned h) {
    pthread_mutex_lock(&horizon_server_objects_mutex);
    struct horizon_server_handle_entry **p=&horizon_server_handles,*e;
    for(;*p&&(*p)->handle!=h;p=&(*p)->next){}
    assert(*p);e=*p;*p=e->next;
    int others=0;
    for(struct horizon_server_handle_entry *i=horizon_server_handles;i;i=i->next)others|=i->object==e->object;
    if(!others)fxap_close(e->object->anon_pipe,e->object->anon_writer);
    if(!--e->object->refs)horizon_server_free_object(e->object);
    free(e);pthread_mutex_unlock(&horizon_server_objects_mutex);
}
static unsigned utf16(unsigned char *out,const char *s) {
    unsigned n=strlen(s);for(unsigned i=0;i<n;i++){out[2*i]=s[i];out[2*i+1]=0;}return n*2;
}
static unsigned create(unsigned size,unsigned *status) {
    unsigned char data[200]={0};struct horizon_object_attributes *a=(void *)data;
    struct horizon_server_connection c={0};
    a->name_len=utf16(data+sizeof(*a),"\\??\\pipe\\Win32.Pipes.00000032.00000001");
    struct fxap_create_request r={.access=0x80100100,.options=0x20,.sharing=2,.disposition=3,
        .maxinstances=1,.outsize=size,.insize=size};
    horizon_server_handle_create_anon_pipe(&c,(void *)&r,data,sizeof(*a)+a->name_len);
    struct fxap_create_reply *reply=(void *)last_reply;*status=reply->header.error;return reply->handle;
}
static unsigned connect(unsigned *status) {
    unsigned char name[160];unsigned len=utf16(name,"\\Device\\NamedPipe\\win32.pipes.00000032.00000001"),h;
    struct horizon_open_file_object_request r={.access=0x40100080,.options=0x60};
    *status=fxap_open_client(&r,name,len,&h);return h;
}
struct job { unsigned handle,writer,size,status,done;void *data;atomic_uint entered,finished; };
static void *worker(void *arg) {
    struct job *j=arg;unsigned options;
    atomic_store(&j->entered,1);
    assert(horizon_anon_pipe_io(j->handle,j->writer,j->data,j->size,&j->status,&j->done,&options));
    atomic_store(&j->finished,1);return NULL;
}
static void wait_started(struct job *j) {
    struct timespec slice={0,1000000};
    for(unsigned i=0;i<1000&&!atomic_load(&j->entered);i++)nanosleep(&slice,NULL);
    assert(atomic_load(&j->entered));
    slice.tv_nsec=20000000;nanosleep(&slice,NULL);assert(!atomic_load(&j->finished));
}
int main(void) {
    unsigned s,n,opt,r,w;unsigned char b[256];struct horizon_anon_pipe_info info;
    assert(!horizon_anon_pipe_io(0xdead,0,b,sizeof(b),&s,&n,&opt));
    r=create(64,&s);assert(r&&!s);w=connect(&s);assert(w&&!s);
    assert(horizon_anon_pipe_info(r,&info)&&info.capacity==64&&info.connected);
    assert(horizon_anon_pipe_io(w,1,"abc",3,&s,&n,&opt)&&!s&&n==3&&opt==0x60);
    assert(horizon_anon_pipe_peek(r,b,sizeof(b),&s,&n)&&!s&&n==19&&!memcmp(b+16,"abc",3));
    assert(horizon_anon_pipe_io(r,0,b,sizeof(b),&s,&n,&opt)&&!s&&n==3&&!memcmp(b,"abc",3));
    assert(horizon_anon_pipe_io(r,1,b,2,&s,&n,&opt)&&s==HORIZON_STATUS_ACCESS_DENIED);
    assert(horizon_anon_pipe_peek(w,b,sizeof(b),&s,&n)&&s==HORIZON_STATUS_ACCESS_DENIED);
    assert(!create(64,&s)&&s==HORIZON_STATUS_OBJECT_NAME_COLLISION);
    assert(!connect(&s)&&s==0xc00000aeu);
    unsigned dup=duplicate(w);close_handle(w);
    assert(horizon_anon_pipe_io(dup,1,"def",3,&s,&n,&opt)&&!s&&n==3);
    close_handle(dup);
    assert(horizon_anon_pipe_io(r,0,b,sizeof(b),&s,&n,&opt)&&!s&&n==3);
    assert(horizon_anon_pipe_io(r,0,b,sizeof(b),&s,&n,&opt)&&s==FXAP_BROKEN&&!n);
    close_handle(r);assert(!live_objects);
    /* Closing one duplicate reader must preserve bytes for the other. Only
     * the final reader discards storage, while the writer remains a valid handle. */
    r=create(2101740,&s);assert(r&&!s);w=connect(&s);assert(w&&!s);
    dup=duplicate(r);
    assert(horizon_anon_pipe_io(w,1,"abc",3,&s,&n,&opt)&&!s);
    close_handle(r);
    assert(fxap_metrics[FXAP_BYTES]==2101740);
    assert(horizon_anon_pipe_io(dup,0,b,2,&s,&n,&opt)&&!s&&n==2&&!memcmp(b,"ab",2));
    close_handle(dup);
    assert(fxap_metrics[FXAP_BYTES]==0&&fxap_metrics[FXAP_LIVE]==1);
    assert(horizon_anon_pipe_io(w,1,"x",1,&s,&n,&opt)&&s==FXAP_BROKEN&&!n);
    close_handle(w);assert(!live_objects&&!fxap_metrics[FXAP_LIVE]);
    /* Reader waits, close writer releases it. Closing own handle also wakes a retained I/O ref. */
    for(unsigned own=0;own<2;own++) {
        r=create(64,&s);w=connect(&s);struct job j={.handle=r,.size=10,.data=b};pthread_t t;
        assert(!pthread_create(&t,NULL,worker,&j));wait_started(&j);close_handle(own?r:w);
        assert(!pthread_join(t,NULL)&&j.status==(own?FXAP_CANCELLED:FXAP_BROKEN));
        close_handle(own?w:r);assert(!live_objects);
    }
    /* Full writer sleeps and wakes with a broken-pipe error on reader close. */
    r=create(64,&s);w=connect(&s);
    assert(horizon_anon_pipe_io(w,1,b,64,&s,&n,&opt)&&!s);
    struct job blocked={.handle=w,.writer=1,.size=1,.data=b};pthread_t thread;
    assert(!pthread_create(&thread,NULL,worker,&blocked));wait_started(&blocked);close_handle(r);
    assert(!pthread_join(thread,NULL)&&blocked.status==FXAP_BROKEN);close_handle(w);assert(!live_objects);
    /* Large transfer crosses buffer wrap/full boundaries, with partial reads. */
    unsigned total=2*1024*1024;unsigned char *input=malloc(total);assert(input);
    for(unsigned i=0;i<total;i++)input[i]=(i*17u+i/67u)&255;
    r=create(64,&s);w=connect(&s);struct job stream={.handle=w,.writer=1,.size=total,.data=input};
    assert(!pthread_create(&thread,NULL,worker,&stream));
    for(unsigned pos=0;pos<total;) {
        assert(horizon_anon_pipe_io(r,0,b,33,&s,&n,&opt)&&!s&&n>0&&n<=33);
        assert(!memcmp(input+pos,b,n));pos+=n;
    }
    assert(!pthread_join(thread,NULL)&&!stream.status&&stream.done==total);
    close_handle(r);close_handle(w);free(input);assert(!live_objects);
    /* Handle-allocation failure leaves no namespace or pipe owners. */
    fail_allocation=1;assert(!create(64,&s)&&s==FXAP_NO_MEMORY&&!live_objects);fail_allocation=0;
    r=create(0,&s);assert(r&&!s);assert(horizon_anon_pipe_info(r,&info)&&info.capacity==4096);
    fail_allocation=1;assert(!connect(&s)&&s==FXAP_NO_MEMORY);fail_allocation=0;
    w=connect(&s);assert(w&&!s);close_handle(r);close_handle(w);assert(!live_objects&&!horizon_server_handles);
    puts("PASS: real byte-pipe/server helpers; create/open, rights, duplicate lifetime, partial/peek, 2-MiB stream, close wakeups, allocation rollback");
    return 0;
}
