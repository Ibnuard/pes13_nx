"""Compile the patched real resume handler with its actual thread-state helper."""
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]) / 'dlls/ntdll/unix'
text = (source / 'horizon.c').read_text()
start = text.index('static int horizon_server_handle_resume_thread(')
end = text.index('static int horizon_server_handle_suspend_thread(', start)
handler = text[start:end]
prefix = r'''
#include <assert.h>
#include <stdio.h>
#include "horizon_threads.h"
struct horizon_server_connection { int reply_fd; };
struct horizon_resume_thread_request { unsigned int handle; };
struct horizon_resume_thread_reply { struct { unsigned int error; } header; int count; };
struct horizon_server_object { struct horizon_thread_state thread; };
static struct horizon_server_object object;
static struct horizon_resume_thread_reply last;
static int wakeups;
static pthread_mutex_t horizon_server_objects_mutex = PTHREAD_MUTEX_INITIALIZER;
static struct horizon_server_object *horizon_server_get_thread_locked(unsigned int h, unsigned int *s)
{ *s = h == 1 ? 0 : 0xc0000008; return h == 1 ? &object : NULL; }
static void horizon_server_signal_changed_locked(void) { ++wakeups; }
static int horizon_server_write_reply(int fd, const void *data, size_t size, void *extra, int len)
{ last = *(const struct horizon_resume_thread_reply *)data; return 0; }
'''
main = r'''
int main(void) {
    struct horizon_server_connection connection = {0};
    struct horizon_resume_thread_request request = {1};
    for (int started=0; started<=1; ++started) {
        for (int count=0; count<=127; ++count) {
            object.thread.started=started; object.thread.suspend=count; wakeups=0;
            horizon_server_handle_resume_thread(&connection, (void *)&request);
            assert(last.header.error == 0 && last.count == count);
            assert(object.thread.suspend == (count ? count-1 : 0));
            assert(wakeups == (count == 1));
        }
    }
    request.handle=99; wakeups=0;
    horizon_server_handle_resume_thread(&connection, (void *)&request);
    assert(last.header.error == 0xc0000008 && wakeups == 0);
    puts("PERF10 resume: zero/nested/final suspend counts and invalid handle PASS");
}
'''
with tempfile.TemporaryDirectory(prefix='pes13-resume-test-') as tmp:
    c = Path(tmp) / 'resume.c'
    binary = Path(tmp) / 'resume'
    c.write_text(prefix + handler + main)
    subprocess.run(['cc', '-O2', '-pthread', '-I', str(source), str(c), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
