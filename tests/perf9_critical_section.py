"""Exercise the pinned Wine entry routine with spinning enabled and bypassed.

Run in WSL with the Wine source tree as the first argument. The host harness
models the wait/wake backend; it does not claim to validate Horizon scheduling.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

wine = Path(sys.argv[1])
source = (wine / "dlls/ntdll/sync.c").read_text()
start = source.index("NTSTATUS WINAPI RtlEnterCriticalSection(")
end = source.index("/******************************************************************************", start)
enter = source[start:end].strip()
assert enter.count("if (crit->SpinCount)") == 1
start = source.index("BOOL WINAPI RtlTryEnterCriticalSection(")
end = source.index("/******************************************************************************", start)
try_enter = source[start:end].strip()

prefix = r'''
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define WINAPI
#define STATUS_SUCCESS 0
#define TRUE 1
#define FALSE 0
typedef int NTSTATUS;
typedef int BOOL;
typedef unsigned int ULONG;
typedef struct {
    _Atomic int LockCount;
    int RecursionCount;
    _Atomic unsigned int OwningThread;
    ULONG SpinCount;
    pthread_mutex_t mutex;
    pthread_cond_t condition;
    int signals;
} RTL_CRITICAL_SECTION;
static _Thread_local unsigned int current_tid;
static _Atomic unsigned int yields, waits;
#define GetCurrentThreadId() current_tid
#define ULongToHandle(x) (x)
static int InterlockedIncrement(_Atomic int *p) { return atomic_fetch_add(p, 1) + 1; }
static int InterlockedCompareExchange(_Atomic int *p, int value, int expected)
{
    atomic_compare_exchange_strong(p, &expected, value);
    return expected;
}
static void YieldProcessor(void) { atomic_fetch_add(&yields, 1); sched_yield(); }
static void RtlRaiseStatus(NTSTATUS status) { (void)status; abort(); }
static NTSTATUS RtlpWaitForCriticalSection(RTL_CRITICAL_SECTION *crit)
{
    atomic_fetch_add(&waits, 1);
    pthread_mutex_lock(&crit->mutex);
    while (!crit->signals) pthread_cond_wait(&crit->condition, &crit->mutex);
    --crit->signals;
    pthread_mutex_unlock(&crit->mutex);
    return 0;
}
static void leave(RTL_CRITICAL_SECTION *crit)
{
    assert(crit->OwningThread == current_tid && crit->RecursionCount > 0);
    if (--crit->RecursionCount) { atomic_fetch_sub(&crit->LockCount, 1); return; }
    crit->OwningThread = 0;
    if (atomic_fetch_sub(&crit->LockCount, 1) - 1 >= 0)
    {
        pthread_mutex_lock(&crit->mutex);
        ++crit->signals;
        pthread_cond_signal(&crit->condition);
        pthread_mutex_unlock(&crit->mutex);
    }
}
BOOL WINAPI RtlTryEnterCriticalSection(RTL_CRITICAL_SECTION *crit);
'''
suffix = r'''
static RTL_CRITICAL_SECTION crit;
static unsigned int protected_count;
static void *worker(void *arg)
{
    current_tid = (uintptr_t)arg;
    for (int i = 0; i < 2000; ++i)
    {
        assert(RtlEnterCriticalSection(&crit) == 0);
        assert(crit.OwningThread == current_tid);
        assert(RtlEnterCriticalSection(&crit) == 0);
        assert(crit.RecursionCount == 2);
        ++protected_count;
        leave(&crit);
        leave(&crit);
    }
    return NULL;
}
int main(void)
{
    pthread_t threads[4];
    current_tid = 1;
    crit.LockCount = -1;
    crit.SpinCount = 32;
    pthread_mutex_init(&crit.mutex, NULL);
    pthread_cond_init(&crit.condition, NULL);
    assert(RtlEnterCriticalSection(&crit) == 0);
    for (uintptr_t i = 0; i < 4; ++i)
        assert(pthread_create(&threads[i], NULL, worker, (void *)(i + 2)) == 0);
    /* Force real contention and wait/wake before letting workers proceed. */
    while (atomic_load(&waits) < 4) sched_yield();
    leave(&crit);
    for (int i = 0; i < 4; ++i) assert(pthread_join(threads[i], NULL) == 0);
    assert(protected_count == 8000);
    assert(crit.LockCount == -1 && crit.RecursionCount == 0 && crit.OwningThread == 0);
    assert(!crit.signals);
    assert(NO_SPIN ? !atomic_load(&yields) : atomic_load(&yields) > 0);
    /* SpinCount remains caller-visible; its value has not been overwritten. */
    assert(crit.SpinCount == 32);
    printf("mode=%s mutual exclusion, recursion, four waiters and final state PASS; yields=%u waits=%u\n",
           NO_SPIN ? "no-spin" : "original", atomic_load(&yields), atomic_load(&waits));
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="pes13-perf9-lock-") as tmp:
    tmp = Path(tmp)
    for no_spin in (0, 1):
        c = tmp / f"lock{no_spin}.c"
        c.write_text(prefix + (enter.replace("if (crit->SpinCount)", "if (0)") if no_spin else enter)
                     + "\n" + try_enter + suffix)
        exe = tmp / f"lock{no_spin}"
        subprocess.run(["cc", "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
                        f"-DNO_SPIN={no_spin}", str(c), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=20)
