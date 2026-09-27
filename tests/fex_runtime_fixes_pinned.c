/*
 * ntdll Horizon host support
 *
 * Copyright 2026 Diogo Silva
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 */

/* Verbatim function slices from autorunhq/autorun at
 * 1bc4e45163f0d2328cdfd35c7f471dd9821bb879, dlls/ntdll/unix/horizon.c.
 * Noncontiguous excerpts, not a complete translation unit.
 * See fex_runtime_fixes_provenance.json for hashes and ranges. */

static unsigned int horizon_server_current_tid(void)
{
    return horizon_server_current ? horizon_server_current->tid : 0;
}

static int horizon_server_object_is_signaled( const struct horizon_server_object *object )
{
    switch (object->type)
    {
    case HORIZON_SERVER_OBJECT_EVENT:
        return object->signaled;
    case HORIZON_SERVER_OBJECT_MUTEX:
        return horizon_mutex_signaled( &object->mutex, horizon_server_current_tid() );
    case HORIZON_SERVER_OBJECT_SEMAPHORE:
        return object->count > 0;
    case HORIZON_SERVER_OBJECT_TIMER:
        return object->signaled;
    case HORIZON_SERVER_OBJECT_THREAD:
        return object->thread.terminated;
    case HORIZON_SERVER_OBJECT_MSG_QUEUE:
    {
        struct horizon_msgq *queue = horizon_msgq_find( &horizon_msg_queues, object->queue_tid );
        return queue && horizon_msgq_signaled( queue );
    }
    case HORIZON_SERVER_OBJECT_COMPLETION:
        return object->completion.depth > 0;
    case HORIZON_SERVER_OBJECT_COMPLETION_WAIT:
        return horizon_completion_wait_signaled( object->wait_port ? &object->wait_port->completion : NULL,
                                                 object->wait_port && object->wait_port->completion_closed );
    case HORIZON_SERVER_OBJECT_PROCESS:
    case HORIZON_SERVER_OBJECT_RESERVE:
    case HORIZON_SERVER_OBJECT_KEYED_EVENT:
        return 1;
    default:
        return 0;
    }
}

static int horizon_server_consume_signal( struct horizon_server_object *object )
{
    switch (object->type)
    {
    case HORIZON_SERVER_OBJECT_EVENT:
        if (!object->manual_reset) object->signaled = 0;
        break;
    case HORIZON_SERVER_OBJECT_MUTEX:
        return horizon_mutex_acquire( &object->mutex, horizon_server_current_tid() );
    case HORIZON_SERVER_OBJECT_SEMAPHORE:
        if (object->count) object->count--;
        break;
    case HORIZON_SERVER_OBJECT_TIMER:
        if (!object->manual_reset) object->signaled = 0;
        break;
    case HORIZON_SERVER_OBJECT_COMPLETION_WAIT:
        return horizon_completion_wait_satisfy( object->wait_port ? &object->wait_port->completion : NULL,
                                                object->wait_port && object->wait_port->completion_closed,
                                                &object->wait_msg, &object->wait_has_msg );
    default:
        break;
    }
    return 0;
}

static unsigned int horizon_server_signal_object_locked( unsigned int handle )
{
    struct horizon_server_handle_entry *entry;
    struct horizon_server_object *object;

    if (!handle) return HORIZON_STATUS_INVALID_HANDLE;
    if (!(entry = horizon_server_find_handle_locked( handle ))) return HORIZON_STATUS_INVALID_HANDLE;

    object = entry->object;
    switch (object->type)
    {
    case HORIZON_SERVER_OBJECT_EVENT:
        if (!object->signaled)
        {
            object->signaled = 1;
            horizon_server_signal_changed_locked();
        }
        return HORIZON_STATUS_SUCCESS;
    case HORIZON_SERVER_OBJECT_MUTEX:
    {
        unsigned int previous, status = horizon_mutex_release( &object->mutex, horizon_server_current_tid(), &previous );

        if (!status && !object->mutex.count) horizon_server_signal_changed_locked();
        return status;
    }
    case HORIZON_SERVER_OBJECT_SEMAPHORE:
        if (object->count == object->max) return HORIZON_STATUS_SEMAPHORE_LIMIT_EXCEEDED;
        object->count++;
        horizon_server_signal_changed_locked();
        return HORIZON_STATUS_SUCCESS;
    default:
        return HORIZON_STATUS_OBJECT_TYPE_MISMATCH;
    }
}

static int horizon_server_handle_event_op( struct horizon_server_connection *connection,
                                           const unsigned char *message )
{
    const struct horizon_event_op_request *request = (const void *)message;
    struct horizon_event_op_reply reply;
    struct horizon_server_object *object = NULL;
    unsigned int status;

    memset( &reply, 0, sizeof(reply) );
    pthread_mutex_lock( &horizon_server_objects_mutex );
    status = horizon_server_find_typed_object_locked( request->handle, HORIZON_SERVER_OBJECT_EVENT, &object );
    if (status == HORIZON_STATUS_SUCCESS)
    {
        reply.state = object->signaled;
        switch (request->op)
        {
        case HORIZON_PULSE_EVENT:
            object->signaled = 0;
            break;
        case HORIZON_SET_EVENT:
            /* Waiters need waking only when it becomes signaled. */
            if (!object->signaled)
            {
                object->signaled = 1;
                horizon_server_signal_changed_locked();
            }
            break;
        case HORIZON_RESET_EVENT:
            object->signaled = 0;
            break;
        default:
            status = HORIZON_STATUS_INVALID_PARAMETER;
            break;
        }
    }
    pthread_mutex_unlock( &horizon_server_objects_mutex );

    reply.header.error = status;
    return horizon_server_write_reply( connection->reply_fd, &reply, sizeof(reply), NULL, 0 );
}

static int horizon_server_handle_release_mutex( struct horizon_server_connection *connection,
                                                const unsigned char *message )
{
    const struct horizon_release_mutex_request *request = (const void *)message;
    struct horizon_release_mutex_reply reply;
    struct horizon_server_object *object = NULL;
    unsigned int status;

    memset( &reply, 0, sizeof(reply) );
    pthread_mutex_lock( &horizon_server_objects_mutex );
    status = horizon_server_find_typed_object_locked( request->handle, HORIZON_SERVER_OBJECT_MUTEX, &object );
    if (status == HORIZON_STATUS_SUCCESS)
        status = horizon_mutex_release( &object->mutex, connection->tid, &reply.prev_count );
    /* Only a release that frees the mutex lets a waiter take it. */
    if (status == HORIZON_STATUS_SUCCESS && !object->mutex.count) horizon_server_signal_changed_locked();
    pthread_mutex_unlock( &horizon_server_objects_mutex );

    reply.header.error = status;
    return horizon_server_write_reply( connection->reply_fd, &reply, sizeof(reply), NULL, 0 );
}

static int horizon_server_handle_release_semaphore( struct horizon_server_connection *connection,
                                                    const unsigned char *message )
{
    const struct horizon_release_semaphore_request *request = (const void *)message;
    struct horizon_release_semaphore_reply reply;
    struct horizon_server_object *object = NULL;
    unsigned int status;

    memset( &reply, 0, sizeof(reply) );
    pthread_mutex_lock( &horizon_server_objects_mutex );
    status = horizon_server_find_typed_object_locked( request->handle, HORIZON_SERVER_OBJECT_SEMAPHORE, &object );
    if (status == HORIZON_STATUS_SUCCESS)
    {
        if (!request->count) status = HORIZON_STATUS_INVALID_PARAMETER;
        else if (request->count > object->max || object->count > object->max - request->count)
            status = HORIZON_STATUS_SEMAPHORE_LIMIT_EXCEEDED;
        else
        {
            reply.prev_count = object->count;
            object->count += request->count;
            horizon_server_signal_changed_locked();
        }
    }
    pthread_mutex_unlock( &horizon_server_objects_mutex );

    reply.header.error = status;
    return horizon_server_write_reply( connection->reply_fd, &reply, sizeof(reply), NULL, 0 );
}

static int horizon_server_handle_set_timer( struct horizon_server_connection *connection,
                                            const unsigned char *message )
{
    const struct horizon_set_timer_request *request = (const void *)message;
    struct horizon_set_timer_reply reply;
    struct horizon_server_object *object = NULL;
    unsigned int status;

    memset( &reply, 0, sizeof(reply) );
    pthread_mutex_lock( &horizon_server_objects_mutex );
    status = horizon_server_find_typed_object_locked( request->handle, HORIZON_SERVER_OBJECT_TIMER, &object );
    if (status == HORIZON_STATUS_SUCCESS)
    {
        reply.signaled = object->signaled;
        object->timer_when = request->expire;
        object->timer_period = request->period > 0 ? request->period : 0;
        object->signaled = 1;
        horizon_server_signal_changed_locked();
    }
    pthread_mutex_unlock( &horizon_server_objects_mutex );

    reply.header.error = status;
    return horizon_server_write_reply( connection->reply_fd, &reply, sizeof(reply), NULL, 0 );
}

static int horizon_server_handle_cancel_timer( struct horizon_server_connection *connection,
                                               const unsigned char *message )
{
    const struct horizon_cancel_timer_request *request = (const void *)message;
    struct horizon_cancel_timer_reply reply;
    struct horizon_server_object *object = NULL;
    unsigned int status;

    memset( &reply, 0, sizeof(reply) );
    pthread_mutex_lock( &horizon_server_objects_mutex );
    status = horizon_server_find_typed_object_locked( request->handle, HORIZON_SERVER_OBJECT_TIMER, &object );
    if (status == HORIZON_STATUS_SUCCESS)
    {
        reply.signaled = object->signaled;
        object->signaled = 0;
        object->timer_period = 0;
    }
    pthread_mutex_unlock( &horizon_server_objects_mutex );

    reply.header.error = status;
    return horizon_server_write_reply( connection->reply_fd, &reply, sizeof(reply), NULL, 0 );
}

static int horizon_server_handle_get_timer_info( struct horizon_server_connection *connection,
                                                 const unsigned char *message )
{
    const struct horizon_get_timer_info_request *request = (const void *)message;
    struct horizon_get_timer_info_reply reply;
    struct horizon_server_object *object = NULL;
    unsigned int status;

    memset( &reply, 0, sizeof(reply) );
    pthread_mutex_lock( &horizon_server_objects_mutex );
    status = horizon_server_find_typed_object_locked( request->handle, HORIZON_SERVER_OBJECT_TIMER, &object );
    if (status == HORIZON_STATUS_SUCCESS)
    {
        reply.when = object->timer_when;
        reply.signaled = object->signaled;
    }
    pthread_mutex_unlock( &horizon_server_objects_mutex );

    reply.header.error = status;
    return horizon_server_write_reply( connection->reply_fd, &reply, sizeof(reply), NULL, 0 );
}

static int horizon_server_handle_polls_locked( unsigned int handle )
{
    struct horizon_server_handle_entry *entry;

    if (!handle || handle == HORIZON_CURRENT_THREAD_HANDLE) return 0;
    return (entry = horizon_server_find_handle_locked( handle )) &&
           entry->object->type == HORIZON_SERVER_OBJECT_MSG_QUEUE;
}

static int horizon_server_select_polls_locked( const struct horizon_select_request *request,
                                               const unsigned char *data, unsigned int data_size )
{
    const unsigned char *select_data;
    unsigned int count, i;
    int op;

    if (request->size < sizeof(op)) return 0;
    if (data_size >= HORIZON_APC_RESULT_SIZE + request->size)
        select_data = data + HORIZON_APC_RESULT_SIZE;
    else if (data_size >= request->size)
        select_data = data;
    else return 0;
    memcpy( &op, select_data, sizeof(op) );

    switch (op)
    {
    case HORIZON_SELECT_WAIT:
    case HORIZON_SELECT_WAIT_ALL:
    {
        const struct horizon_select_wait_op *wait = (const void *)select_data;

        if (request->size < offsetof( struct horizon_select_wait_op, handles[1] )) return 0;
        count = (request->size - offsetof( struct horizon_select_wait_op, handles )) / sizeof(wait->handles[0]);
        for (i = 0; i < count; i++)
            if (horizon_server_handle_polls_locked( wait->handles[i] )) return 1;
        return 0;
    }
    case HORIZON_SELECT_SIGNAL_AND_WAIT:
        if (request->size < sizeof(struct horizon_select_signal_and_wait_op)) return 0;
        return horizon_server_handle_polls_locked(
            ((const struct horizon_select_signal_and_wait_op *)select_data)->wait );
    default:
        return 0;
    }
}

static int horizon_server_handle_select( struct horizon_server_connection *connection,
                                         const unsigned char *message,
                                         const unsigned char *data, unsigned int data_size )
{
    const struct horizon_select_request *request = (const void *)message;
    struct horizon_select_reply reply;
    int polls;

    memset( &reply, 0, sizeof(reply) );
    /* Each client has its own server connection/thread. A pending wait sleeps on
     * horizon_server_objects_cond, which releases the object lock so other
     * clients can signal objects meanwhile and wake it
     * (horizon_server_signal_changed_locked). Message queues also change without
     * that wakeup (window timers), so waits on them recheck every millisecond.
     * Negative server deadlines are absolute performance-counter ticks (100ns),
     * positive deadlines use NT wall-clock time; INT64_MAX means infinite.
     * Signal-and-wait must perform its signal only on the first attempt. */
    pthread_mutex_lock( &horizon_server_objects_mutex );
    polls = horizon_server_select_polls_locked( request, data, data_size );
    for (int initial = 1;; initial = 0)
    {
        LARGE_INTEGER now;
        long long timeout = HORIZON_SERVER_WAIT_SLICE;

        reply.header.error = horizon_server_select_status( request, data, data_size, initial );
        if (reply.header.error != HORIZON_STATUS_TIMEOUT || !request->timeout) break;
        if (request->timeout != 0x7fffffffffffffffLL)
        {
            if (request->timeout < 0)
            {
                NtQueryPerformanceCounter( &now, NULL );
                if (now.QuadPart > -(request->timeout + 1)) break;
                timeout = -(request->timeout + 1) - now.QuadPart + 1;
            }
            else
            {
                NtQuerySystemTime( &now );
                if (now.QuadPart >= request->timeout) break;
                timeout = request->timeout - now.QuadPart;
            }
        }
        if (polls && timeout > HORIZON_SERVER_POLL_INTERVAL) timeout = HORIZON_SERVER_POLL_INTERVAL;
        horizon_server_sleep_locked( timeout );
    }
    pthread_mutex_unlock( &horizon_server_objects_mutex );
    reply.signaled = 1;

    TRACE( "Horizon server select size %u timeout %lld status %08x.\n",
           request->size, request->timeout, reply.header.error );
    return horizon_server_write_reply( connection->reply_fd, &reply, sizeof(reply), NULL, 0 );
}

static int lowest_set_core( ULONG_PTR mask )
{
    int i;

    for (i = 0; i < (int)(sizeof(mask) * 8); i++)
        if (mask & ((ULONG_PTR)1 << i)) return i;

    return 0;
}

static void horizon_server_follow_client( struct horizon_server_connection *connection )
{
    unsigned int mask;

    if (!connection->request_pipe) return;
    mask = __atomic_load_n( &connection->request_pipe->client_cores, __ATOMIC_RELAXED );
    if (!mask || mask == connection->core_mask) return;
    connection->core_mask = mask;
    svcSetThreadCoreMask( CUR_THREAD_HANDLE, lowest_set_core( mask ), mask );
}

static void horizon_server_signal_changed_locked(void)
{
    if (horizon_server_sleepers) pthread_cond_broadcast( &horizon_server_objects_cond );
}

static void horizon_server_sleep_locked( long long timeout )
{
    if (timeout > HORIZON_SERVER_WAIT_SLICE) timeout = HORIZON_SERVER_WAIT_SLICE;
    horizon_server_sleepers++;
    /* libnx's relative wait: newlib's pthread_cond_timedwait reads the realtime
     * clock, which fails until the time service has set the boot time. */
    condvarWaitTimeout( &horizon_server_objects_cond.cond, &horizon_server_objects_mutex.normal,
                        (u64)timeout * 100 );
    horizon_server_sleepers--;
}
static struct horizon_server_handle_entry *horizon_server_handles;
/* The same entries by handle value, which only grows. Requests look their
 * handles up, and walking every open handle made each lookup slower as the
 * number of handles grew. */
#define HORIZON_SERVER_HANDLE_HASH_SIZE 4096

static unsigned int horizon_server_wait_object_locked( unsigned int handle, int consume )
{
    struct horizon_server_handle_entry *entry;
    struct horizon_server_object *object;
    unsigned int status;

    if (!handle) return HORIZON_STATUS_INVALID_HANDLE;
    if (handle == HORIZON_CURRENT_THREAD_HANDLE)
    {
        /* The calling thread cannot terminate while it waits on itself. */
        return horizon_server_get_thread_locked( handle, &status ) ? HORIZON_STATUS_TIMEOUT : status;
    }
    if (!(entry = horizon_server_find_handle_locked( handle ))) return HORIZON_STATUS_INVALID_HANDLE;
    object = entry->object;
    if (object->type == HORIZON_SERVER_OBJECT_MSG_QUEUE) horizon_server_refresh_queues_locked();
    if (!horizon_server_object_is_signaled( object )) return HORIZON_STATUS_TIMEOUT;
    if (consume && horizon_server_consume_signal( object )) return HORIZON_STATUS_ABANDONED_WAIT_0;
    return HORIZON_STATUS_SUCCESS;
}

static unsigned int horizon_server_select_wait( const struct horizon_select_wait_op *op,
                                                unsigned int size, int wait_all )
{
    unsigned int count;
    unsigned int i;
    unsigned int status = HORIZON_STATUS_TIMEOUT;

    if (size < offsetof( struct horizon_select_wait_op, handles[1] ))
        return HORIZON_STATUS_INVALID_PARAMETER;

    count = (size - offsetof( struct horizon_select_wait_op, handles )) / sizeof(op->handles[0]);
    if (!count) return HORIZON_STATUS_INVALID_PARAMETER;

    if (wait_all)
    {
        status = HORIZON_STATUS_SUCCESS;
        for (i = 0; i < count; i++)
        {
            status = horizon_server_wait_object_locked( op->handles[i], FALSE );
            if (status != HORIZON_STATUS_SUCCESS) break;
        }
        if (status == HORIZON_STATUS_SUCCESS)
            for (i = 0; i < count; i++)
                if (horizon_server_wait_object_locked( op->handles[i], TRUE ) == HORIZON_STATUS_ABANDONED_WAIT_0)
                    status = HORIZON_STATUS_ABANDONED_WAIT_0;
    }
    else
    {
        for (i = 0; i < count; i++)
        {
            status = horizon_server_wait_object_locked( op->handles[i], TRUE );
            if (status == HORIZON_STATUS_SUCCESS || status == HORIZON_STATUS_ABANDONED_WAIT_0)
            {
                status += i;
                break;
            }
            if (status != HORIZON_STATUS_TIMEOUT) break;
        }
    }
    return status;
}

static unsigned int horizon_server_select_signal_and_wait( const struct horizon_select_signal_and_wait_op *op,
                                                           unsigned int size, int initial )
{
    unsigned int status;

    if (size < sizeof(*op)) return HORIZON_STATUS_INVALID_PARAMETER;

    status = initial ? horizon_server_signal_object_locked( op->signal ) : HORIZON_STATUS_SUCCESS;
    if (status == HORIZON_STATUS_SUCCESS)
        status = horizon_server_wait_object_locked( op->wait, TRUE );
    return status;
}

static unsigned int horizon_server_select_status( const struct horizon_select_request *request,
                                                  const unsigned char *data, unsigned int data_size, int initial )
{
    const unsigned char *select_data = NULL;
    int op;

    if (!request->size) return HORIZON_STATUS_TIMEOUT;
    if (data_size >= HORIZON_APC_RESULT_SIZE + request->size)
        select_data = data + HORIZON_APC_RESULT_SIZE;
    else if (data_size >= request->size)
        select_data = data;
    else return HORIZON_STATUS_INVALID_PARAMETER;

    if (request->size < sizeof(op)) return HORIZON_STATUS_INVALID_PARAMETER;
    memcpy( &op, select_data, sizeof(op) );

    switch (op)
    {
    case HORIZON_SELECT_WAIT:
        return horizon_server_select_wait( (const struct horizon_select_wait_op *)select_data,
                                           request->size, FALSE );
    case HORIZON_SELECT_WAIT_ALL:
        return horizon_server_select_wait( (const struct horizon_select_wait_op *)select_data,
                                           request->size, TRUE );
    case HORIZON_SELECT_SIGNAL_AND_WAIT:
        return horizon_server_select_signal_and_wait(
            (const struct horizon_select_signal_and_wait_op *)select_data, request->size, initial );
    case HORIZON_SELECT_KEYED_EVENT_WAIT:
    case HORIZON_SELECT_KEYED_EVENT_RELEASE:
        return HORIZON_STATUS_SUCCESS;
    default:
        return HORIZON_STATUS_SUCCESS;
    }
}
