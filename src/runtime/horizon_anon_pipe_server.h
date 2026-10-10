/* LGPL-2.1-or-later. Wine CreatePipe's single-instance synchronous byte pipes.
 * Included after Horizon handle/name helpers. The object lock owns namespace,
 * endpoint refs and connection state; the pipe lock owns bytes and close gates. */
struct fxap_create_request {
    struct horizon_server_request_header header;
    unsigned access,options,sharing,disposition,maxinstances,outsize,insize;
    long long timeout;
    unsigned flags,pad;
};
struct fxap_create_reply {
    struct horizon_server_reply_header header;
    unsigned handle,created;
};
_Static_assert(sizeof(struct fxap_create_request)==56,"create_named_pipe wire size");
_Static_assert(offsetof(struct fxap_create_request,timeout)==40,"create_named_pipe timeout");
_Static_assert(sizeof(struct fxap_create_reply)==16,"create_named_pipe reply");

static int fxap_ascii_prefix(const unsigned char *name,unsigned bytes,const char *prefix)
{
    unsigned i,n=strlen(prefix);
    if ((bytes&1)||bytes<2*n) return 0;
    for (i=0;i<n;i++) {
        unsigned c=name[i*2]|(name[i*2+1]<<8),p=(unsigned char)prefix[i];
        if (c>='A'&&c<='Z') c+='a'-'A';
        if (p>='A'&&p<='Z') p+='a'-'A';
        if (c!=p) return 0;
    }
    return n*2;
}
static int fxap_name(const unsigned char **name,unsigned *bytes)
{
    int skip=fxap_ascii_prefix(*name,*bytes,"\\??\\pipe\\");
    if (!skip) skip=fxap_ascii_prefix(*name,*bytes,"\\Device\\NamedPipe\\");
    if (!skip) return 0;
    *name+=skip;*bytes-=skip;
    return *bytes<=128&&*bytes>24&&fxap_ascii_prefix(*name,*bytes,"Win32.Pipes.")!=0;
}
static struct horizon_server_object *fxap_find_locked(const unsigned char *name,unsigned bytes)
{
    struct horizon_server_handle_entry *e;
    for (e=horizon_server_handles;e;e=e->next) {
        struct horizon_server_object *o=e->object;
        unsigned i;
        if (!o->anon_pipe||o->anon_writer||o->name_len!=bytes) continue;
        for (i=0;i<bytes;i+=2) {
            unsigned a=o->name[i]|(o->name[i+1]<<8),b=name[i]|(name[i+1]<<8);
            if (a>='A'&&a<='Z') a+='a'-'A';
            if (b>='A'&&b<='Z') b+='a'-'A';
            if (a!=b) break;
        }
        if (i==bytes) return o;
    }
    return NULL;
}
static void fxap_report(unsigned access,unsigned options,unsigned flags,unsigned size,
                       unsigned capacity,unsigned handle,unsigned status)
{
    static unsigned count,failures;
    unsigned ticket=__atomic_fetch_add(status?&failures:&count,1,__ATOMIC_RELAXED);
    if (ticket<12 || (status && ticket<1048576 && !(ticket&(ticket-1)))) {
        uint64_t s[FXAP_METRICS];
        for (unsigned i=0;i<FXAP_METRICS;i++) s[i]=__atomic_load_n(&fxap_metrics[i],__ATOMIC_RELAXED);
        horizon_trace("[ANON-PIPE] v3 handle=%x access=%x options=%x flags=%x requested=%u capacity=%u status=%08x",
                      handle,access,options,flags,size,capacity,status);
        horizon_trace("[ANON-MEM] v1 created=%llu live=%llu bytes=%llu peak=%llu reclaimed=%llu fail_meta=%llu fail_buffer=%llu fail_sync=%llu",
                      (unsigned long long)s[FXAP_CREATED],(unsigned long long)s[FXAP_LIVE],
                      (unsigned long long)s[FXAP_BYTES],(unsigned long long)s[FXAP_PEAK],
                      (unsigned long long)s[FXAP_RECLAIMED],(unsigned long long)s[FXAP_FAIL_META],
                      (unsigned long long)s[FXAP_FAIL_BUFFER],(unsigned long long)s[FXAP_FAIL_SYNC]);
    }
}
static int horizon_server_handle_create_anon_pipe(struct horizon_server_connection *connection,
    const unsigned char *message,const unsigned char *data,unsigned data_size)
{
    const struct fxap_create_request *r=(const void *)message;
    struct fxap_create_reply reply={0};
    struct horizon_object_name name;
    struct horizon_server_handle_entry *e;
    struct fxap_pipe *p=NULL;
    unsigned char *key=NULL;
    unsigned access=horizon_file_map_access(r->access),capacity=0;
    reply.header.error=horizon_server_parse_object_attributes(data,data_size,&name);
    if (!reply.header.error&&(name.rootdir||!fxap_name(&name.name,&name.name_len)||
        r->flags||r->sharing!=2||r->maxinstances!=1||r->disposition!=3||
        r->options!=0x20||!(access&1)||(access&2)))
        reply.header.error=HORIZON_STATUS_NOT_SUPPORTED;
    if (!reply.header.error&&(!(p=fxap_create(r->insize))||!(key=malloc(name.name_len))))
        reply.header.error=HORIZON_STATUS_NO_MEMORY;
    if (!reply.header.error) {
        memcpy(key,name.name,name.name_len);
        pthread_mutex_lock(&horizon_server_objects_mutex);
        if (fxap_find_locked(key,name.name_len)) reply.header.error=HORIZON_STATUS_OBJECT_NAME_COLLISION;
        else if (!(e=horizon_server_create_handle_locked(HORIZON_SERVER_OBJECT_FILE)))
            reply.header.error=HORIZON_STATUS_NO_MEMORY;
        else {
            e->object->anon_pipe=p;e->object->anon_writer=0;
            e->object->name=key;e->object->name_len=name.name_len;
            e->object->file_access=access;e->object->file_options=r->options;
            capacity=p->capacity;reply.handle=e->handle;reply.created=1;p=NULL;key=NULL;
        }
        pthread_mutex_unlock(&horizon_server_objects_mutex);
    }
    if (p) fxap_destroy(p);
    free(key);
    fxap_report(r->access,r->options,r->flags,r->insize,capacity,reply.handle,reply.header.error);
    return horizon_server_write_reply(connection->reply_fd,&reply,sizeof(reply),NULL,0);
}
static unsigned fxap_open_client(const struct horizon_open_file_object_request *r,
                                 const unsigned char *name,unsigned bytes,unsigned *handle)
{
    struct horizon_server_object *server;
    struct horizon_server_handle_entry *e;
    unsigned status=0,access=horizon_file_map_access(r->access);
    *handle=0;
    if (r->rootdir||!fxap_name(&name,&bytes)) return HORIZON_STATUS_OBJECT_NAME_NOT_FOUND;
    if (!(access&2)||(access&1)||r->sharing||r->options!=0x60) return HORIZON_STATUS_NOT_SUPPORTED;
    pthread_mutex_lock(&horizon_server_objects_mutex);
    server=fxap_find_locked(name,bytes);
    if (!server) status=HORIZON_STATUS_OBJECT_NAME_NOT_FOUND;
    else if (server->anon_pipe->connected) status=0xc00000aeu; /* STATUS_PIPE_BUSY */
    else if (!(e=horizon_server_create_handle_locked(HORIZON_SERVER_OBJECT_FILE)))
        status=HORIZON_STATUS_NO_MEMORY;
    else {
        e->object->anon_pipe=server->anon_pipe;e->object->anon_writer=1;
        server->anon_pipe->owners++;server->anon_pipe->connected=1;
        e->object->file_access=access;e->object->file_options=r->options;
        *handle=e->handle;
    }
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    return status;
}
int horizon_anon_pipe_io(unsigned handle,int writer,void *data,unsigned size,
                         unsigned *status,unsigned *done,unsigned *options)
{
    struct horizon_server_handle_entry *e;
    struct horizon_server_object *o;
    static unsigned trace_count;
    unsigned ticket;
    pthread_mutex_lock(&horizon_server_objects_mutex);
    e=horizon_server_find_handle_locked(handle);
    if (!e||!e->object->anon_pipe) { pthread_mutex_unlock(&horizon_server_objects_mutex);return 0; }
    o=e->object;*options=o->file_options;*done=0;
    if (o->anon_writer!=!!writer||!(o->file_access&(writer?2u:1u))) {
        *status=HORIZON_STATUS_ACCESS_DENIED;
        pthread_mutex_unlock(&horizon_server_objects_mutex);return 1;
    }
    o->refs++; /* Close wakes us; storage cannot disappear until this call returns. */
    o->anon_io_active++;
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    ticket=__atomic_fetch_add(&trace_count,1,__ATOMIC_RELAXED);
    if (ticket<24)
        horizon_trace("[ANON-IO] v2 begin handle=%x write=%u bytes=%u capacity=%u",
                      handle,!!writer,size,o->anon_pipe->capacity);
    *status=writer?fxap_write(o->anon_pipe,data,size,done):fxap_read(o->anon_pipe,data,size,done);
    if (ticket<24)
        horizon_trace("[ANON-IO] v2 end handle=%x write=%u done=%u status=%08x",handle,!!writer,*done,*status);
    pthread_mutex_lock(&horizon_server_objects_mutex);
    o->anon_io_active--;
    horizon_server_signal_changed_locked();
    if (!--o->refs) horizon_server_free_object(o);
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    return 1;
}
int horizon_anon_pipe_info(unsigned handle,struct horizon_anon_pipe_info *out)
{
    struct horizon_server_handle_entry *e;
    struct fxap_pipe *p;
    pthread_mutex_lock(&horizon_server_objects_mutex);
    e=horizon_server_find_handle_locked(handle);
    if (!e||!(p=e->object->anon_pipe)) { pthread_mutex_unlock(&horizon_server_objects_mutex);return 0; }
    pthread_mutex_lock(&p->lock);
    out->access=e->object->file_access;out->options=e->object->file_options;
    out->writer=e->object->anon_writer;out->connected=p->connected;
    out->capacity=p->capacity;out->available=p->used;
    out->read_open=p->read_open;out->write_open=p->write_open;
    pthread_mutex_unlock(&p->lock);pthread_mutex_unlock(&horizon_server_objects_mutex);
    return 1;
}
int horizon_anon_pipe_peek(unsigned handle,void *data,unsigned size,unsigned *status,unsigned *done)
{
    struct horizon_server_handle_entry *e;
    struct fxap_pipe *p;
    unsigned header[4],n,first;
    *done=0;
    pthread_mutex_lock(&horizon_server_objects_mutex);
    e=horizon_server_find_handle_locked(handle);
    if (!e||!(p=e->object->anon_pipe)) { pthread_mutex_unlock(&horizon_server_objects_mutex);return 0; }
    if (!(e->object->file_access&1)) *status=HORIZON_STATUS_ACCESS_DENIED;
    else if (size<16) *status=HORIZON_STATUS_BUFFER_TOO_SMALL;
    else {
        pthread_mutex_lock(&p->lock);
        header[0]=!p->connected?2:p->write_open?3:4;header[1]=p->used;header[2]=header[3]=0;
        memcpy(data,header,16);
        n=size-16;if (n>p->used) n=p->used;
        first=n<p->capacity-p->head?n:p->capacity-p->head;
        if (first) memcpy((char *)data+16,p->bytes+p->head,first);
        if (n>first) memcpy((char *)data+16+first,p->bytes,n-first);
        *done=16+n;*status=0;
        pthread_mutex_unlock(&p->lock);
    }
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    return 1;
}
