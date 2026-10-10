/* LGPL-2.1-or-later. Included after the native pipe server implementation.
 * Called by the existing Debug-launch maintenance worker, never by game I/O.
 * Snapshot existing state only; no new producer hooks or guest memory reads. */
#ifndef HORIZON_ASSET_PROBE_H
#define HORIZON_ASSET_PROBE_H
extern int wine_nx_launch_debug_active(void);
void wine_nx_asset_pipe_report(void)
{
    struct snapshot { unsigned handle,writer,capacity,used,read_open,write_open,active,refs; } rows[8];
    struct horizon_server_handle_entry *entry;
    unsigned scanned=0,count=0,busy=0,omitted=0,truncated;
    if(!wine_nx_launch_debug_active())return;
    if(pthread_mutex_trylock(&horizon_server_objects_mutex)){
        horizon_trace("[ASSET-PIPES] object registry busy; snapshot skipped");return;
    }
    for(entry=horizon_server_handles;entry&&scanned<2048;entry=entry->next,scanned++){
        struct horizon_server_object *object=entry->object;
        struct fxap_pipe *pipe=object->anon_pipe;
        if(!pipe)continue;
        if(count==8){omitted++;continue;}
        if(pthread_mutex_trylock(&pipe->lock)){busy++;continue;}
        rows[count++]=(struct snapshot){entry->handle,object->anon_writer,pipe->capacity,pipe->used,
            pipe->read_open,pipe->write_open,object->anon_io_active,object->refs};
        pthread_mutex_unlock(&pipe->lock);
    }
    truncated=entry!=NULL;
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    /* Never invoke logging while holding the registry or pipe lock. */
    horizon_trace("[ASSET-PIPES] scanned=%u shown=%u busy=%u omitted=%u scan_truncated=%u",
                  scanned,count,busy,omitted,truncated);
    for(unsigned i=0;i<count;i++)
        horizon_trace("[ASSET-PIPE] handle=%x writer=%u capacity=%u queued=%u reader_open=%u writer_open=%u active_io=%u refs=%u",
            rows[i].handle,rows[i].writer,rows[i].capacity,rows[i].used,rows[i].read_open,
            rows[i].write_open,rows[i].active,rows[i].refs);
}
#endif
