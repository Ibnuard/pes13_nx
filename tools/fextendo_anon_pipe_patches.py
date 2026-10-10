"""Implement the synchronous anonymous-pipe path used by Wine CreatePipe."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def apply(source):
    changed=set()
    def one(data,old,new):
        assert data.count(old)==1,(old[:110],data.count(old))
        return data.replace(old,new)
    for name in ('horizon_anon_pipe.h','horizon_anon_pipe_api.h','horizon_anon_pipe_server.h'):
        rel='dlls/ntdll/unix/'+name
        (source/rel).write_bytes((ROOT/'src/runtime'/name).read_bytes());changed.add(rel)
    rel='dlls/ntdll/unix/horizon.c';p=source/rel;data=p.read_text()
    data=one(data,'#include "horizon_file_access.h"',
        '#include "horizon_file_access.h"\n#include "horizon_anon_pipe.h"\n#include "horizon_anon_pipe_api.h"')
    data=one(data,'#define HORIZON_REQ_IOCTL 140','#define HORIZON_REQ_IOCTL 140\n#define HORIZON_REQ_CREATE_NAMED_PIPE 142')
    anchor='    struct horizon_memfile *mapping_memfile; /* mapping: a section with no file, kept by file_fd */'
    data=one(data,anchor,anchor+'\n    struct fxap_pipe *anon_pipe;\n    unsigned anon_writer,anon_io_active;')
    anchor='    if (object->reg_key) horizon_reg_release( &horizon_registry, object->reg_key );'
    data=one(data,anchor,anchor+'''
    if (object->anon_pipe) {
        fxap_close(object->anon_pipe,object->anon_writer);
        if (!--object->anon_pipe->owners) fxap_destroy(object->anon_pipe);
    }
''')
    anchor='        if (object && object->reg_key)'
    data=one(data,anchor,'''        if (object && object->anon_pipe && !horizon_server_object_has_handles_locked(object))
            fxap_close(object->anon_pipe,object->anon_writer);
'''+anchor)
    anchor='static int horizon_server_handle_create_file('
    data=one(data,anchor,'#include "horizon_anon_pipe_server.h"\n\n'+anchor)
    anchor='        case HORIZON_REQ_CREATE_FILE:'
    data=one(data,anchor,'''        case HORIZON_REQ_CREATE_NAMED_PIPE:
            status=horizon_server_handle_create_anon_pipe(connection,message,request_data,header->request_size);
            break;
'''+anchor)
    anchor='    if (is_afd)\n'
    data=one(data,anchor,'''    {
        const unsigned char *name=data;unsigned bytes=data_size;
        if (fxap_name(&name,&bytes)) {
            reply.header.error=fxap_open_client(request,data,data_size,&reply.handle);
            return horizon_server_write_reply(connection->reply_fd,&reply,sizeof(reply),NULL,0);
        }
    }
'''+anchor)
    anchor='    else if ((entry->object->type != HORIZON_SERVER_OBJECT_FILE &&'
    data=one(data,anchor,'''    else if (entry->object->anon_pipe) {
        reply.access=entry->object->file_access;
        reply.options=entry->object->file_options;
        reply.header.error=HORIZON_STATUS_BAD_DEVICE_TYPE;
    }
'''+anchor)
    anchor='static int horizon_server_object_is_signaled( const struct horizon_server_object *object )\n{'
    data=one(data,anchor,anchor+'\n    if (object->anon_pipe) return !object->anon_io_active;')
    p.write_text(data);changed.add(rel)
    rel='dlls/ntdll/unix/file.c';p=source/rel;data=p.read_text()
    anchor='#include "unix_private.h"'
    assert anchor in data
    data=one(data,anchor,anchor+'\n#ifdef __SWITCH__\n#include "horizon_anon_pipe_api.h"\n#endif')
    for op in ('read','write'):
        old='''    if (status == STATUS_BAD_DEVICE_TYPE)
        return server_'''+op+'''_file( handle, event, apc, apc_user, io, buffer, length, offset, key );'''
        new='''    if (status == STATUS_BAD_DEVICE_TYPE) {
#ifdef __SWITCH__
        unsigned pipe_status,pipe_done,pipe_options;
        if (horizon_anon_pipe_io(wine_server_obj_handle(handle),'''+str(int(op=='write'))+''',
                                (void *)buffer,length,&pipe_status,&pipe_done,&pipe_options)) {
            file_complete_async(handle,pipe_options,event,apc,apc_user,io,pipe_status,pipe_done);
            return pipe_status;
        }
#endif
        return server_'''+op+'''_file( handle, event, apc, apc_user, io, buffer, length, offset, key );
    }'''
        data=one(data,old,new)
    anchor='''#ifdef __SWITCH__
        /* A Horizon directory: fd_get_file_info examines it by unix name. */'''
    data=one(data,anchor,'''#ifdef __SWITCH__
        struct horizon_anon_pipe_info pipe;
        if (horizon_anon_pipe_info(wine_server_obj_handle(handle),&pipe)) {
            if (!virtual_check_buffer_for_write(ptr,len)) return io->Status=STATUS_ACCESS_VIOLATION;
            switch (class) {
            case FilePipeInformation: {
                FILE_PIPE_INFORMATION *out=ptr;out->ReadMode=0;out->CompletionMode=0;break;
            }
            case FilePipeLocalInformation: {
                FILE_PIPE_LOCAL_INFORMATION *out=ptr;
                memset(out,0,sizeof(*out));out->NamedPipeConfiguration=0;
                out->MaximumInstances=out->CurrentInstances=1;
                out->InboundQuota=out->OutboundQuota=pipe.capacity;
                out->ReadDataAvailable=pipe.available;out->WriteQuotaAvailable=pipe.capacity-pipe.available;
                out->NamedPipeState=!pipe.connected?2:pipe.read_open&&pipe.write_open?3:4;
                out->NamedPipeEnd=pipe.writer?0:1;break;
            }
            case FileStandardInformation: {
                FILE_STANDARD_INFORMATION *out=ptr;memset(out,0,sizeof(*out));
                out->AllocationSize.QuadPart=pipe.capacity;out->EndOfFile.QuadPart=pipe.available;
                out->NumberOfLinks=1;break;
            }
            default: return io->Status=STATUS_INVALID_INFO_CLASS;
            }
            io->Information=info_sizes[class];return io->Status=STATUS_SUCCESS;
        }
        /* A Horizon directory: fd_get_file_info examines it by unix name. */''')
    # Wine routes these zero-sized table entries to get_file_info before the
    # unix-FD branch. Handle pipes here without changing the ordinary-file path.
    anchor='''    if (!info_sizes[class])
        return server_get_file_info( handle, io, ptr, len, class );'''
    data=one(data,anchor,'''#ifdef __SWITCH__
    if (class==FileAccessInformation || class==FileModeInformation) {
        struct horizon_anon_pipe_info pipe;
        if (horizon_anon_pipe_info(wine_server_obj_handle(handle),&pipe)) {
            if (len<sizeof(ULONG)) return io->Status=STATUS_INFO_LENGTH_MISMATCH;
            if (!virtual_check_buffer_for_write(ptr,sizeof(ULONG))) return io->Status=STATUS_ACCESS_VIOLATION;
            *(ULONG *)ptr=class==FileAccessInformation?pipe.access:pipe.options;
            io->Information=sizeof(ULONG);return io->Status=STATUS_SUCCESS;
        }
    }
#endif
'''+anchor)
    anchor='''    if (status == STATUS_BAD_DEVICE_TYPE)
    {
        fd = -1;
        fd_type = FD_TYPE_DIR;'''
    data=one(data,anchor,'''    if (status == STATUS_BAD_DEVICE_TYPE)
    {
        struct horizon_anon_pipe_info pipe;
        if (horizon_anon_pipe_info(wine_server_obj_handle(handle),&pipe)) {
            io->Information=0;
            if (info_class!=FileFsDeviceInformation) return io->Status=STATUS_INVALID_INFO_CLASS;
            if (length<sizeof(FILE_FS_DEVICE_INFORMATION)) return io->Status=STATUS_BUFFER_TOO_SMALL;
            if (!virtual_check_buffer_for_write(buffer,sizeof(FILE_FS_DEVICE_INFORMATION)))
                return io->Status=STATUS_ACCESS_VIOLATION;
            FILE_FS_DEVICE_INFORMATION *out=buffer;
            out->DeviceType=FILE_DEVICE_NAMED_PIPE;out->Characteristics=0;
            io->Information=sizeof(*out);return io->Status=STATUS_SUCCESS;
        }
        fd = -1;
        fd_type = FD_TYPE_DIR;''')
    start=data.index('NTSTATUS WINAPI NtFsControlFile(');end=data.index('\n}\n',start)+3
    block=data[start:end]
    anchor='    if (!io) return STATUS_INVALID_PARAMETER;'
    block=one(block,anchor,anchor+'''
#ifdef __SWITCH__
    if (code==FSCTL_PIPE_PEEK) {
        unsigned pipe_status,pipe_done;
        struct horizon_anon_pipe_info pipe;
        if (horizon_anon_pipe_info(wine_server_obj_handle(handle),&pipe)) {
            if (!virtual_check_buffer_for_write(out_buffer,out_size)) return STATUS_ACCESS_VIOLATION;
            if (horizon_anon_pipe_peek(wine_server_obj_handle(handle),out_buffer,out_size,&pipe_status,&pipe_done)) {
                file_complete_async(handle,pipe.options,event,apc,apc_context,io,pipe_status,pipe_done);
                return pipe_status;
            }
            return STATUS_INVALID_HANDLE;
        }
    }
#endif''')
    data=data[:start]+block+data[end:];p.write_text(data);changed.add(rel)
    return changed
