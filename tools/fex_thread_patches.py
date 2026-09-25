"""Provide the self-thread object query required by FEX's exit cleanup."""
import re


def apply(read, replace):
    protocol = read('include/wine/server_protocol.h')
    names = re.findall(r'\bREQ_\w+', protocol.split('enum request\n{', 1)[1].split('};', 1)[0])
    request_id = names.index('REQ_get_object_info')
    assert request_id == 248, 'Review wire layout if the pinned Wine protocol changes'
    name = 'dlls/ntdll/unix/horizon.c'
    replace(name, '#define HORIZON_REQ_SET_HANDLE_INFO 22',
            f'#define HORIZON_REQ_GET_OBJECT_INFO {request_id}\n#define HORIZON_REQ_SET_HANDLE_INFO 22')
    anchor = 'static int horizon_server_handle_set_handle_info( struct horizon_server_connection *connection )'
    replace(name, anchor, r'''
/* FEX validates THREAD_TERMINATE on its current-thread pseudo handle before
 * destroying per-thread caches and finalizing the CRT heap. An unsupported
 * get_object_info made BTCpuThreadTerm return before either cleanup. Real
 * handles need access-right bookkeeping; do not invent rights for them. */
static int __attribute__((noinline)) horizon_server_handle_get_object_info( struct horizon_server_connection *connection,
                                                 const unsigned char *message )
{
    const struct horizon_close_handle_request *request = (const void *)message;
    struct
    {
        struct horizon_server_reply_header header;
        unsigned int access, ref_count, handle_count;
        char pad[4];
    } reply = {0};
    struct horizon_server_handle_entry *entry;

    _Static_assert(sizeof(reply) == 24, "get_object_info wire reply");
    reply.header.error = HORIZON_STATUS_NOT_IMPLEMENTED;
    pthread_mutex_lock( &horizon_server_objects_mutex );
    if (request->handle == HORIZON_CURRENT_THREAD_HANDLE)
    {
        if (connection->thread && connection->thread->type == HORIZON_SERVER_OBJECT_THREAD)
        {
            reply.header.error = HORIZON_STATUS_SUCCESS;
            reply.access = THREAD_ALL_ACCESS;
            reply.ref_count = connection->thread->refs;
            for (entry = horizon_server_handles; entry; entry = entry->next)
                if (entry->object == connection->thread) ++reply.handle_count;
        }
        else reply.header.error = HORIZON_STATUS_INVALID_HANDLE;
    }
    pthread_mutex_unlock( &horizon_server_objects_mutex );
    return horizon_server_write_reply( connection->reply_fd, &reply, sizeof(reply), NULL, 0 );
}

''' + anchor)
    anchor = '        case HORIZON_REQ_SET_HANDLE_INFO:'
    replace(name, anchor, '''        case HORIZON_REQ_GET_OBJECT_INFO:
            status = horizon_server_handle_get_object_info( connection, message );
            break;
''' + anchor)
