"""Run the real Wine protection syscall with modeled VM and trace services.

Compares the baseline and candidate return values and output parameters. The
observer must run after unlocking and only for the main SEC_IMAGE view.
Horizon protection behavior is tested separately in the ARM64 observer test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include <signal.h>
#define __SWITCH__ 1
#define WINAPI
typedef void *HANDLE, *PVOID, *LPVOID;
typedef size_t SIZE_T;
typedef uint32_t ULONG, DWORD, NTSTATUS;
typedef uint8_t BYTE;
typedef int BOOL;
typedef wchar_t WCHAR;
#define FALSE 0
#define STATUS_SUCCESS 0u
#define STATUS_ACCESS_VIOLATION 0xc0000005u
#define STATUS_NOT_COMMITTED 0xc000002du
#define STATUS_INVALID_PARAMETER 0xc000000du
#define PAGE_NOACCESS 1u
#define PAGE_WRITECOPY 8u
#define PAGE_EXECUTE_WRITECOPY 0x80u
#define SEC_IMAGE 0x1000000u
#define VPROT_COMMITTED 0x20u
#define VPROT_COPIED 0x80u
#define APC_VIRTUAL_PROTECT 1
#define TRACE(...) ((void)0)
#define FIXME(...) ((void)0)
#define VIRTUAL_DEBUG_DUMP_VIEW(v) ((void)(v))
#define ROUND_ADDR(a,m) ((char *)((uintptr_t)(a)&~(uintptr_t)(m)))
#define ROUND_SIZE(a,s,m) (((s)+((uintptr_t)(a)&(m))+(m))&~(size_t)(m))
#define NtCurrentProcess() ((HANDLE)(intptr_t)-1)
#define wcsicmp wcscasecmp
static size_t page_mask=4095,page_size=4096;
struct file_view { void *base; unsigned protect; } image;
struct params { struct { WCHAR *Buffer; } ImagePathName; } params;
struct peb { void *ImageBaseAddress; struct params *ProcessParameters; } peb;
struct teb { struct peb *Peb; } teb;
static struct teb *NtCurrentTeb(void) { return &teb; }
union apc_call { struct { unsigned type; uintptr_t addr; size_t size; ULONG prot; } virtual_protect; };
union apc_result { struct { unsigned status; uintptr_t addr; size_t size; ULONG prot; } virtual_protect; };
static uintptr_t wine_server_client_ptr(void *p) { return (uintptr_t)p; }
static void *wine_server_get_ptr(uintptr_t p) { return (void *)p; }
static unsigned server_queue_process_apc(HANDLE p,union apc_call *c,union apc_result *r) {
    (void)p; r->virtual_protect.status=0;r->virtual_protect.addr=c->virtual_protect.addr;
    r->virtual_protect.size=c->virtual_protect.size;r->virtual_protect.prot=0x40;return 0;
}
static int virtual_mutex,locked,view_exists,committed,simulate_writecopy,sets,traces;
static ULONG before_prot,requested;
static unsigned set_status;
static uintptr_t traced_base;
static size_t traced_size;
static ULONG traced_old,traced_new,traced_status;
static void server_enter_uninterrupted_section(void *m,sigset_t *s) { (void)m;(void)s;assert(!locked);locked=1; }
static void server_leave_uninterrupted_section(void *m,sigset_t *s) { (void)m;(void)s;assert(locked);locked=0; }
static struct file_view *find_view(void *base,size_t size) { (void)base;(void)size;assert(locked);return view_exists?&image:NULL; }
static size_t get_committed_size(struct file_view *v,void *b,size_t s,BYTE *p,BYTE mask) {
    (void)v;(void)b;(void)mask;*p=committed?VPROT_COMMITTED:0;return committed?s:0;
}
static ULONG get_win32_prot(BYTE p,unsigned view) { (void)p;(void)view;return before_prot; }
static unsigned set_protection(struct file_view *v,void *b,size_t s,ULONG prot) {
    (void)v;assert(locked);assert((uintptr_t)b==0x01c80000);assert(s==4096);sets++;requested=prot;return set_status;
}
static void set_page_vprot_bits(void *p,size_t s,unsigned set,unsigned clear) { (void)p;(void)s;(void)set;(void)clear; }
static void horizon_debug_vm_protect(void *base,size_t size,unsigned old,unsigned newp,unsigned status,void *caller) {
    assert(!locked);assert(caller);traces++;traced_base=(uintptr_t)base;traced_size=size;
    traced_old=old;traced_new=newp;traced_status=status;
}
'''

SUFFIX = r'''
int main(void) {
    peb.ImageBaseAddress=(void *)0x400000;peb.ProcessParameters=&params;teb.Peb=&peb;
    unsigned checks=0;
    for (unsigned test=0;test<8;test++) {
        image=(struct file_view){(void *)0x400000,SEC_IMAGE};
        view_exists=committed=1;sets=traces=0;before_prot=0x40;set_status=0;
        void *addr=(void *)0x01c80042;size_t size=4;ULONG old=0xdeadbeef;
        HANDLE process=NtCurrentProcess();ULONG *oldp=&old;
        if(test==1)set_status=0xc0000045u;
        if(test==2)committed=0;
        if(test==3)view_exists=0;
        if(test==4)image.base=(void *)0x500000;
        if(test==5)image.protect=0;
        if(test==6)process=(HANDLE)42;
        if(test==7)oldp=NULL;
        unsigned result=NtProtectVirtualMemory(process,&addr,&size,0x20,oldp);
        unsigned expected=test==1?0xc0000045u:test==2?STATUS_NOT_COMMITTED:
            test==3?STATUS_INVALID_PARAMETER:test==7?STATUS_ACCESS_VIOLATION:0;
        assert(result==expected);assert(!locked);
        if(test<6) {
            assert(sets==(test!=2&&test!=3));
            if(sets)assert(requested==0x20);
            assert(old==(expected?PAGE_NOACCESS:0x40));
            assert((uintptr_t)addr==(expected?0x01c80042:0x01c80000));
            assert(size==(expected?4:4096));
        }
#ifdef BASELINE
        assert(traces==0);
#else
        assert(traces==(test<=2));
        if(traces) {
            assert(traced_base==0x01c80000&&traced_size==4096);
            assert(traced_new==0x20&&traced_status==expected);
            assert(traced_old==(test==2?0:0x40));
        }
#endif
        checks++;
    }
    printf("PASS %u protection cases: outputs/status unchanged; observer after unlock; main-image filter\n",checks);
    return 0;
}
'''


def extract(path):
    text = path.read_text()
    start = text.index('NTSTATUS WINAPI NtProtectVirtualMemory(')
    return text[start:text.index('\n}\n', start) + 3]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--before', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    checks = []
    with tempfile.TemporaryDirectory(prefix='fextendo-protect-') as td:
        for old, path in ((True, a.before), (False, a.source)):
            source = Path(td) / ('before.c' if old else 'after.c')
            source.write_text(PREFIX + extract(path) + SUFFIX)
            binary = source.with_suffix('')
            subprocess.run(['gcc', '-std=gnu11', '-O1', '-g',
                            '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                            *(['-DBASELINE'] if old else []), str(source), '-o', str(binary)], check=True)
            run = subprocess.run([str(binary)], text=True, capture_output=True)
            print(run.stdout, run.stderr, end='', flush=True)
            run.check_returncode()
            checks.append({'baseline': old, 'passed': True, 'output': run.stdout})
    report = {'passed': True, 'hardware_tested': False, 'checks': checks,
              'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'],
              'virtual_source_sha256': hashlib.sha256(a.source.read_bytes()).hexdigest(),
              'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
