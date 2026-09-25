"""Check the Box64-equivalent FEX suspend contract (no artificial delay)."""
from pathlib import Path
import subprocess
import tempfile

project = Path(__file__).resolve().parents[1]
header = project / 'src/runtime/fex_suspend_backoff.h'
source = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
typedef int32_t NTSTATUS;
typedef unsigned long ULONG;
typedef uintptr_t HANDLE;
typedef union { int64_t QuadPart; } LARGE_INTEGER;
#define STATUS_NOT_SUPPORTED ((NTSTATUS)0xc00000bb)
#define FALSE 0
static NTSTATUS result;
static int suspends, delays;
static HANDLE seen_handle;
static NTSTATUS pWow64SuspendLocalThread(HANDLE thread, ULONG *count)
{
    ++suspends;
    seen_handle = thread;
    if (!result && count) *count = 9;
    return result;
}
static NTSTATUS __attribute__((unused)) NtDelayExecution(int alertable, const LARGE_INTEGER *delay)
{
    assert(alertable == FALSE && delay->QuadPart == -10000);
    ++delays;
    return (NTSTATUS)0xc0000001; /* Must not replace the suspend status. */
}
'''
source += header.read_text()
source += r'''
int main(void)
{
    ULONG count = 123;
    result = STATUS_NOT_SUPPORTED;
    for (int i = 0; i < 10000; ++i)
        assert(pes13_fex_suspend_local_thread(42, &count) == result);
    assert(suspends == 10000 && delays == 0 && count == 123 && seen_handle == 42);
    result = (NTSTATUS)0xc0000008;
    assert(pes13_fex_suspend_local_thread(43, &count) == result);
    assert(delays == 0 && count == 123 && seen_handle == 43);
    result = 0;
    assert(pes13_fex_suspend_local_thread(44, &count) == 0);
    assert(delays == 0 && count == 9 && seen_handle == 44);
    assert(pes13_fex_suspend_local_thread(45, 0) == 0);
    puts("FEX suspend passthrough PASS: 10000 rejected calls, zero injected delays");
}
'''
with tempfile.TemporaryDirectory(prefix='fex-suspend-') as temporary:
    c = Path(temporary) / 'suspend.c'
    binary = Path(temporary) / 'suspend'
    c.write_text(source)
    subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
