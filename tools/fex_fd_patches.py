"""Route one-process Horizon client FD handoffs by their protocol identity."""
import re


def apply(read, replace):
    protocol = read('include/wine/server_protocol.h')
    requests = re.findall(r'\bREQ_\w+', protocol.split('enum request\n{', 1)[1].split('};', 1)[0])
    alloc_file_id = requests.index('REQ_alloc_file_handle')
    # Pin the wire layout as well as deriving its request number.
    assert re.search(r'struct alloc_file_handle_request\s*\{\s*struct request_header __header;\s*'
                     r'unsigned int access;\s*unsigned int attributes;\s*int\s+fd;\s*\};', protocol)
    name = 'dlls/ntdll/unix/horizon_private.h'
    replace(name, 'extern int horizon_server_take_client_fd( unsigned int *handle );',
            'extern int horizon_server_take_client_fd( int expected_fd );')
    name = 'dlls/ntdll/unix/horizon.c'
    replace(name, '#define HORIZON_REQ_NEW_THREAD 2',
            f'#define HORIZON_REQ_ALLOC_FILE_HANDLE {alloc_file_id}\n#define HORIZON_REQ_NEW_THREAD 2')
    replace(name, '    pthread_cond_signal( &queue->cond );\n    pthread_mutex_unlock( &queue->mutex );',
            '    /* Keyed waiters may need different descriptors. Waking only one\n'
            '     * can strand the matching waiter after an unrelated one wakes. */\n'
            '    if (queue == &horizon_client_to_server_fds) pthread_cond_broadcast( &queue->cond );\n'
            '    else pthread_cond_signal( &queue->cond );\n'
            '    pthread_mutex_unlock( &queue->mutex );')
    replace(name, '''int horizon_server_take_client_fd( unsigned int *handle )
{
    return horizon_fd_queue_pop( &horizon_client_to_server_fds, handle );
}''', r'''/* The client request carries the original native fd, not the duplicate.
 * All clients share this process's fd namespace. Startup keeps each original
 * open until its synchronous request completes. Request arrival order is NOT
 * descriptor arrival order when a parent creates threads while children init.
 * The reverse queue still carries Wine handles/protocol version and is FIFO. */
int __attribute__((noinline)) horizon_server_take_client_fd( int expected_fd )
{
    struct horizon_fd_queue *queue = &horizon_client_to_server_fds;
    struct horizon_fd_message *message, *previous;
    int fd;

    pthread_mutex_lock( &queue->mutex );
    for (;;)
    {
        previous = NULL;
        for (message = queue->head; message; previous = message, message = message->next)
            if (message->handle == (unsigned int)expected_fd) break;
        if (message) break;
        pthread_cond_wait( &queue->cond, &queue->mutex );
    }
    if (previous) previous->next = message->next;
    else queue->head = message->next;
    if (queue->tail == message) queue->tail = previous;
    pthread_mutex_unlock( &queue->mutex );

    fd = message->fd;
    free( message );
    return fd;
}''')
    replace(name, 'horizon_fd_queue_push_dup( &horizon_client_to_server_fds, fd, 0 );',
            'horizon_fd_queue_push_dup( &horizon_client_to_server_fds, fd, (unsigned int)fd );')
    replace(name, '''    unsigned int handle;
    int reply_fd, wait_fd;

    reply_fd = horizon_server_take_client_fd( &handle );
    wait_fd = horizon_server_take_client_fd( &handle );''',
            '''    int reply_fd, wait_fd;

    reply_fd = horizon_server_take_client_fd( request->reply_fd );
    wait_fd = horizon_server_take_client_fd( request->wait_fd );''', count=2)
    replace(name, '''    unsigned int fd_handle;
    pthread_t thread;
    int request_fd = horizon_server_take_client_fd( &fd_handle );''',
            '''    pthread_t thread;
    int request_fd = horizon_server_take_client_fd( request->request_fd );''')
    # This request is still unsupported. Consume only its own handed-off dup
    # so a later reuse of the original fd number cannot select an orphan.
    anchor = 'static int horizon_server_handle_init_process_done( struct horizon_server_connection *connection,'
    replace(name, anchor, r'''static int __attribute__((noinline)) horizon_server_discard_alloc_file_fd(
    struct horizon_server_connection *connection, const unsigned char *message )
{
    const struct
    {
        struct horizon_server_request_header header;
        unsigned int access, attributes;
        int fd;
    } *request = (const void *)message;
    _Static_assert(offsetof(__typeof__(*request), fd) == 20, "alloc_file_handle fd wire offset");
    close( horizon_server_take_client_fd( request->fd ) );
    return horizon_server_write_status( connection->reply_fd, HORIZON_STATUS_NOT_IMPLEMENTED );
}

''' + anchor)
    replace(name, '        case HORIZON_REQ_NEW_THREAD:',
            '''        case HORIZON_REQ_ALLOC_FILE_HANDLE:
            status = horizon_server_discard_alloc_file_fd( connection, message );
            break;
        case HORIZON_REQ_NEW_THREAD:''')
