"""Narrow Wine/Horizon backports; caller owns snapshot buffering and disk writes.

API: apply(read, replace, project), native-source horizon.c only.
read(name) -> current buffered text; replace(name, old, new) replaces one anchor.
project retained for sibling patcher API compatibility, no files read from it.
All edits validate before one callback write. Reapplying or source drift fails
closed. No queued sync, timing settings, clocks, build markers or FEX changes.

Timer origin: autorunhq/autorun 51f94949d738c978bfb80a5118d7ffa4cf6b98ae.
Base: 1bc4e45163f0d2328cdfd35c7f471dd9821bb879.
Deliberate deviations: preserve cancel signal, bound periodic catch-up, guard
deadline overflow, refresh polling after rearm while select sleeps.
CancelWaitableTimer preserves signaled state as documented by Microsoft:
https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-cancelwaitabletimer
"""
import re

HORIZON = 'dlls/ntdll/unix/horizon.c'
TIMER_COMMIT = '51f94949d738c978bfb80a5118d7ffa4cf6b98ae'

# Literal before/after content from the upstream horizon.c diff, scoped where
# context repeats. The first anchor omits neighbouring sleep implementation so
# fex_sync_patches can run before or after this module.
TIMER_EDITS = (
    (None,
     'static struct horizon_server_handle_entry *horizon_server_handles;\n',
     'static struct horizon_server_handle_entry *horizon_server_handles;\n/* Whether any waitable timer is running, so waits skip the walk otherwise. */\nstatic int horizon_server_timers_armed;\n'),
    (None,
     '    return horizon_server_current ? horizon_server_current->tid : 0;\n}\n\nstatic int horizon_server_object_is_signaled( const struct horizon_server_object *object )\n{\n    switch (object->type)\n',
     '    return horizon_server_current ? horizon_server_current->tid : 0;\n}\n\n/* Signals the timers whose time has come and moves a periodic one on. Need\n * for Speed Most Wanted paces its streaming thread with SetWaitableTimer and\n * WaitForSingleObject; signalling a timer as it was set returned every wait at\n * once, 70000 times a second on one core, and the game lost its pacing. */\nstatic void horizon_server_update_timers_locked(void)\n{\n    struct horizon_server_handle_entry *entry;\n    LARGE_INTEGER now;\n    int armed = 0;\n\n    if (!horizon_server_timers_armed) return;\n    NtQuerySystemTime( &now );\n    for (entry = horizon_server_handles; entry; entry = entry->next)\n    {\n        struct horizon_server_object *object = entry->object;\n\n        if (object->type != HORIZON_SERVER_OBJECT_TIMER || !object->timer_when) continue;\n        if (object->timer_when > now.QuadPart)\n        {\n            armed = 1;\n            continue;\n        }\n        object->signaled = 1;\n        if (!object->timer_period)\n        {\n            object->timer_when = 0;\n            continue;\n        }\n        /* A period is in milliseconds, and one that was missed does not repeat. */\n        do object->timer_when += (long long)object->timer_period * 10000;\n        while (object->timer_when <= now.QuadPart);\n        armed = 1;\n    }\n    horizon_server_timers_armed = armed;\n}\n\nstatic int horizon_server_object_is_signaled( const struct horizon_server_object *object )\n{\n    switch (object->type)\n'),
    ('horizon_server_handle_set_timer',
     '    status = horizon_server_find_typed_object_locked( request->handle, HORIZON_SERVER_OBJECT_TIMER, &object );\n    if (status == HORIZON_STATUS_SUCCESS)\n    {\n        reply.signaled = object->signaled;\n        object->timer_when = request->expire;\n        object->timer_period = request->period > 0 ? request->period : 0;\n        object->signaled = 1;\n        horizon_server_signal_changed_locked();\n    }\n    pthread_mutex_unlock( &horizon_server_objects_mutex );\n',
     "    status = horizon_server_find_typed_object_locked( request->handle, HORIZON_SERVER_OBJECT_TIMER, &object );\n    if (status == HORIZON_STATUS_SUCCESS)\n    {\n        LARGE_INTEGER now;\n\n        /* A waitable timer is signalled when it expires, not when it is set.\n         * expire is an absolute time, or a delay when it is not positive, as\n         * the wineserver's set_timer takes it. */\n        NtQuerySystemTime( &now );\n        reply.signaled = object->signaled;\n        object->timer_when = request->expire <= 0 ? now.QuadPart - request->expire\n                                                  : max( request->expire, now.QuadPart );\n        object->timer_period = request->period > 0 ? request->period : 0;\n        object->signaled = 0;\n        horizon_server_timers_armed = 1;\n        horizon_server_signal_changed_locked();\n    }\n    pthread_mutex_unlock( &horizon_server_objects_mutex );\n"),
    ('horizon_server_handle_cancel_timer',
     '    {\n        reply.signaled = object->signaled;\n        object->signaled = 0;\n        object->timer_period = 0;\n    }\n    pthread_mutex_unlock( &horizon_server_objects_mutex );\n',
     '    {\n        reply.signaled = object->signaled;\n        object->signaled = 0;\n        object->timer_when = 0;\n        object->timer_period = 0;\n    }\n    pthread_mutex_unlock( &horizon_server_objects_mutex );\n'),
    ('horizon_server_handle_get_timer_info',
     '\n    memset( &reply, 0, sizeof(reply) );\n    pthread_mutex_lock( &horizon_server_objects_mutex );\n    status = horizon_server_find_typed_object_locked( request->handle, HORIZON_SERVER_OBJECT_TIMER, &object );\n    if (status == HORIZON_STATUS_SUCCESS)\n    {\n',
     '\n    memset( &reply, 0, sizeof(reply) );\n    pthread_mutex_lock( &horizon_server_objects_mutex );\n    horizon_server_update_timers_locked();\n    status = horizon_server_find_typed_object_locked( request->handle, HORIZON_SERVER_OBJECT_TIMER, &object );\n    if (status == HORIZON_STATUS_SUCCESS)\n    {\n'),
    ('horizon_server_handle_polls_locked',
     '    return (entry = horizon_server_find_handle_locked( handle )) &&\n           entry->object->type == HORIZON_SERVER_OBJECT_MSG_QUEUE;',
     '    if (!(entry = horizon_server_find_handle_locked( handle ))) return 0;\n    /* Neither a message queue nor a timer that is running signals the waiter\n     * when it becomes ready: both are noticed by looking again. */\n    return entry->object->type == HORIZON_SERVER_OBJECT_MSG_QUEUE ||\n           (entry->object->type == HORIZON_SERVER_OBJECT_TIMER && entry->object->timer_when);'),
    ('horizon_server_handle_select',
     '        LARGE_INTEGER now;\n        long long timeout = HORIZON_SERVER_WAIT_SLICE;\n\n        reply.header.error = horizon_server_select_status( request, data, data_size, initial );\n        if (reply.header.error != HORIZON_STATUS_TIMEOUT || !request->timeout) break;\n        if (request->timeout != 0x7fffffffffffffffLL)',
     '        LARGE_INTEGER now;\n        long long timeout = HORIZON_SERVER_WAIT_SLICE;\n\n        horizon_server_update_timers_locked();\n        reply.header.error = horizon_server_select_status( request, data, data_size, initial );\n        if (reply.header.error != HORIZON_STATUS_TIMEOUT || !request->timeout) break;\n        if (request->timeout != 0x7fffffffffffffffLL)'),
 )


def _span(source, name):
    match = re.search(r'^static [^\n]*\b' + re.escape(name) +
                      r'\([^;{]*?\)\s*\n\{', source, re.M)
    if not match:
        raise RuntimeError('runtime fixes: missing function ' + name)
    end, depth = match.end(), 1
    while depth and end < len(source):
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    if depth:
        raise RuntimeError('runtime fixes: unclosed function ' + name)
    return match.start(), end


def _edit(source, scope, before, after):
    start, end = _span(source, scope) if scope else (0, len(source))
    body = source[start:end]
    count = body.count(before)
    if count != 1:
        raise RuntimeError(f'runtime fixes: {scope or HORIZON}: expected 1 anchor, got {count}')
    return source[:start] + body.replace(before, after, 1) + source[end:]


def apply(read, replace, project):
    """Validate all anchors; publish one buffered horizon.c replacement."""
    original = read(HORIZON)
    changed = original
    for scope, before, after in TIMER_EDITS:
        changed = _edit(changed, scope, before, after)
    changed = _edit(changed, 'horizon_server_handle_cancel_timer',
                    '        object->signaled = 0;\n', '')
    # A relative delay can exceed the representable NT deadline. Saturate
    # before subtracting (including INT64_MIN); never wrap into an overdue time.
    changed = _edit(changed, 'horizon_server_handle_set_timer',
                    '        object->timer_when = request->expire <= 0 ? now.QuadPart - request->expire\n'
                    '                                                  : max( request->expire, now.QuadPart );',
                    '        if (request->expire <= 0)\n'
                    '            object->timer_when = now.QuadPart > 0x7fffffffffffffffLL + request->expire\n'
                    '                                 ? 0x7fffffffffffffffLL : now.QuadPart - request->expire;\n'
                    '        else object->timer_when = max( request->expire, now.QuadPart );')
    # Skip missed periods in constant work while retaining the original phase.
    # Avoid both signed overflow and an unbounded loop holding the object lock.
    changed = _edit(changed, 'horizon_server_update_timers_locked',
                    '        do object->timer_when += (long long)object->timer_period * 10000;\n'
                    '        while (object->timer_when <= now.QuadPart);',
                    '        {\n'
                    '            long long period = (long long)object->timer_period * 10000;\n'
                    '            unsigned long long elapsed = (unsigned long long)now.QuadPart -\n'
                    '                                         (unsigned long long)object->timer_when;\n'
                    '            long long remaining = period - (long long)(elapsed % period);\n'
                    '\n'
                    '            /* No representable next deadline: preserve this signal only. */\n'
                    '            if (now.QuadPart > 0x7fffffffffffffffLL - remaining)\n'
                    '            {\n'
                    '                object->timer_when = 0;\n'
                    '                continue;\n'
                    '            }\n'
                    '            object->timer_when = now.QuadPart + remaining;\n'
                    '        }')
    # A timer may be armed by another client while select is asleep. Refresh
    # polling after every wake. Keep the entry-time anchor for fex_sync_patches
    # composition in either order; its router decoder attaches there.
    changed = _edit(changed, 'horizon_server_handle_select',
                    '        if (polls && timeout > HORIZON_SERVER_POLL_INTERVAL)',
                    '        polls = horizon_server_select_polls_locked(\n'
                    '            request, data, data_size );\n'
                    '        if (polls && timeout > HORIZON_SERVER_POLL_INTERVAL)')
    changed = _edit(changed, 'horizon_server_follow_client',
                    '    connection->core_mask = mask;\n'
                    '    svcSetThreadCoreMask( CUR_THREAD_HANDLE, lowest_set_core( mask ), mask );',
                    '    if (R_SUCCEEDED(svcSetThreadCoreMask( CUR_THREAD_HANDLE, lowest_set_core( mask ), mask )))\n'
                    '        connection->core_mask = mask;')
    replace(HORIZON, original, changed)
