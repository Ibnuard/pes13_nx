"""Exercise the shipped wrapper against the actual Horizon suspend handler.

Host contract checks only; the delay stub does not measure Switch scheduling.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

p = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1])/'dlls/ntdll/unix'
text = (source/'horizon.c').read_text()
start = text.index('static int horizon_server_handle_suspend_thread(')
end = text.index('static int horizon_server_handle_terminate_thread(', start)
handler = text[start:end]
wrapper = (p/'src/runtime/pes13_suspend_backoff.h').read_text()
prefix = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "horizon_threads.h"
typedef int32_t NTSTATUS;
typedef uint32_t ULONG;
typedef uintptr_t HANDLE;
typedef union { int64_t QuadPart; } LARGE_INTEGER;
#define WINAPI
#define FALSE 0
#define STATUS_NOT_SUPPORTED ((NTSTATUS)0xc00000bb)
struct horizon_server_connection { int reply_fd; };
struct horizon_suspend_thread_request { unsigned int handle; };
struct horizon_suspend_thread_reply { struct { unsigned int error; } header; int count; };
struct horizon_server_object { struct horizon_thread_state thread; };
static struct horizon_server_object object;
static struct horizon_suspend_thread_reply last;
static pthread_mutex_t horizon_server_objects_mutex = PTHREAD_MUTEX_INITIALIZER;
static int calls, delays;
static NTSTATUS delay_result;
static struct horizon_server_object *horizon_server_get_thread_locked(unsigned int h, unsigned int *s)
{
    *s = h == 1 ? 0 : h == 2 ? 0xc0000022 : 0xc0000008;
    return h == 1 ? &object : NULL;
}
static void horizon_trace(const char *format, ...) { }
static int horizon_server_write_reply(int fd, const void *data, size_t size, void *extra, int len)
{ last = *(const struct horizon_suspend_thread_reply *)data; return 0; }
'''
bridge = r'''
/* Model only the native entry's request and output contract. The real
 * handler and thread-state helper determine its status/count below. */
static NTSTATUS NtSuspendThread(HANDLE handle, ULONG *count)
{
    struct horizon_server_connection connection = {0};
    struct horizon_suspend_thread_request request = {(unsigned int)handle};
    ++calls;
    horizon_server_handle_suspend_thread(&connection, (const void *)&request);
    if (!last.header.error && count) *count = last.count;
    return (NTSTATUS)last.header.error;
}
static NTSTATUS NtDelayExecution(int alertable, const LARGE_INTEGER *delay)
{
    assert(!alertable && delay->QuadPart == -10000);
    /* It must be safe to sleep here: the server has released its mutex. */
    assert(pthread_mutex_trylock(&horizon_server_objects_mutex) == 0);
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    ++delays;
    return delay_result;
}
'''
main = r'''
int main(void)
{
    ULONG count;
    /* Unstarted and nested suspensions retain old counts; no sleep. */
    for (int n=0; n<HORIZON_THREAD_MAX_SUSPEND; ++n) {
        memset(&object, 0, sizeof(object)); object.thread.suspend=n;
        count=0x12345678; calls=delays=0;
        assert(RtlWow64SuspendThread(1, &count) == 0);
        assert(count == (ULONG)n && object.thread.suspend == n+1);
        assert(calls == 1 && delays == 0);
    }
    memset(&object, 0, sizeof(object)); count=123; calls=delays=0;
    assert(RtlWow64SuspendThread(99, &count) == (NTSTATUS)0xc0000008);
    assert(RtlWow64SuspendThread(2, &count) == (NTSTATUS)0xc0000022);
    object.thread.terminated=1;
    assert(RtlWow64SuspendThread(1, &count) == (NTSTATUS)HORIZON_THREADS_STATUS_ACCESS_DENIED);
    object.thread.terminated=0; object.thread.suspend=HORIZON_THREAD_MAX_SUSPEND;
    assert(RtlWow64SuspendThread(1, &count) == (NTSTATUS)HORIZON_THREADS_STATUS_SUSPEND_EXCEEDED);
    assert(count == 123 && calls == 4 && delays == 0);
    /* Only unsupported running suspension delays; return/output unchanged
     * even if the delay function itself returns an error. */
    memset(&object, 0, sizeof(object)); object.thread.started=1; calls=delays=0;
    for (int n=0; n<10000; ++n) {
        delay_result=n%2 ? (NTSTATUS)0xc0000001 : 0;
        assert(RtlWow64SuspendThread(1, &count) == STATUS_NOT_SUPPORTED);
        assert(count == 123 && object.thread.suspend == 0);
    }
    assert(calls == 10000 && delays == 10000);
    assert(RtlWow64SuspendThread(1, NULL) == STATUS_NOT_SUPPORTED);
    /* The same handle can be reused for a new unstarted thread; no cached
     * rejection and no cross-call delay on success. */
    memset(&object, 0, sizeof(object)); calls=delays=0;
    assert(RtlWow64SuspendThread(1, NULL) == 0);
    assert(object.thread.suspend == 1 && calls == 1 && delays == 0);
    puts("PERF13 PASS: native counts/errors, failure backoff, released server mutex, handle reuse");
}
'''
with tempfile.TemporaryDirectory(prefix='pes13-suspend-test-') as tmp:
    c = Path(tmp)/'suspend.c'
    binary = Path(tmp)/'suspend'
    c.write_text(prefix+handler+bridge+wrapper+main)
    subprocess.run(['cc', '-O2', '-pthread', '-I', str(source), str(c), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
