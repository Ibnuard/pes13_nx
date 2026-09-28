"""Execute linked ARM64 worker placement with modeled kernel grants/tick counts.

Runs the real startup, balancer and server-mask publication, not a scheduler or
game simulation. The registry layout is checked against generated C; TEB/pipe
ABI offsets are exercised by readback through the unmodified ARM64 publisher.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from unicorn import arm64_const as arm
from fex_reservations import Model as NativeModel, reg
from fex_resume_gate import function

ROOT = Path(__file__).resolve().parents[1]


class Model(NativeModel):
    def __init__(self, path, grant=15, control=False):
        super().__init__(path)
        self.grant, self.now = grant, 100000
        self.sets, self.follow, self.locks = [], [], []
        self.ticks, self.masks = {}, {}
        self.set_error = self.info_error = 0
        self.fixed = 0
        self.q(self.symbols['cached_affinity_mask'], grant)
        self.u32(self.symbols['next_core_index'], 0)
        if 'wine_nx_fex_auto_core3' in self.symbols:
            self.u32(self.symbols['wine_nx_fex_auto_core3'], int(control))
        self.teb, self.handle, self.filep = self.data+0x1000, self.data+0x3000, self.data+0x3100
        self.pipefile, self.pipe = self.data+0x3200, self.data+0x3300
        self.u32(self.teb+900, 42)  # ntdll request_fd within TEB
        self.u32(self.symbols['horizon_pipe_device'], 77)
        self.u32(self.handle, 77)
        self.q(self.handle+8, self.filep)
        self.q(self.filep, self.pipefile)
        self.q(self.pipefile, self.pipe)
        self.append = {v for k, v in self.symbols.items() if k == 'appendf' or k.startswith('appendf.')}

    def u32(self, p, v):
        self.vm.mem_write(p, struct.pack('<I', v & 0xffffffff))

    def read32(self, p):
        return struct.unpack('<I', self.vm.mem_read(p, 4))[0]

    def hook(self, vm, pc, size, user):
        s = self.symbols
        # armGetSystemTick is inlined; register allocation varies across builds.
        instruction = int.from_bytes(vm.mem_read(pc, 4), 'little')
        if instruction & ~31 == 0xd53be020:  # mrs Xt, cntpct_el0
            if instruction & 31 != 31:
                vm.reg_write(reg(instruction & 31), self.now)
            vm.reg_write(arm.UC_ARM64_REG_PC, pc+4)
        elif pc == s.get('svcGetInfo'):
            out, kind, handle = [vm.reg_read(reg(i)) for i in range(3)]
            if kind == 0:
                self.q(out, self.grant)
                self.ret(self.info_error)
            else:
                assert kind in (25, 0x10000), ('unexpected info', kind)
                self.q(out, self.ticks.get(handle, 0))
                self.ret()
        elif pc == s.get('svcGetThreadCoreMask'):
            corep, maskp, handle = [vm.reg_read(reg(i)) for i in range(3)]
            mask = self.masks[handle]
            self.u32(corep, (mask & -mask).bit_length()-1)
            self.q(maskp, mask)
            self.ret()
        elif pc == s.get('svcSetThreadCoreMask'):
            handle, core, mask = [vm.reg_read(reg(i)) & 0xffffffff for i in range(3)]
            assert mask and not mask & ~self.grant and mask & (1 << core)
            self.sets.append((handle, core, mask))
            if not self.set_error:
                self.masks[handle] = mask
            self.ret(self.set_error)
        elif pc == s.get('wine_nx_thread_affinity_fixed'):
            self.fixed += 1
            self.ret()
        elif pc == s.get('NtCurrentTeb'):
            self.ret(self.teb)
        elif pc == s.get('__get_handle'):
            assert vm.reg_read(reg(0)) == 42
            self.ret(self.handle)
        elif pc == s.get('horizon_follow_thread_cores'):
            self.follow.append((vm.reg_read(reg(0)), vm.reg_read(reg(1))))
            # Execute the actual pipe publication after successful placement.
        elif pc == s.get('pthread_mutex_lock'):
            p = vm.reg_read(reg(0))
            assert p not in self.locks
            self.locks.append(p)
            self.ret()
        elif pc == s.get('pthread_mutex_unlock'):
            assert self.locks.pop() == vm.reg_read(reg(0))
            self.ret()
        elif pc in self.append:
            self.ret(vm.reg_read(reg(1)))
        else:
            super().hook(vm, pc, size, user)

    def call(self, name, *args):
        self.returned = False
        self.vm.reg_write(arm.UC_ARM64_REG_SP, self.stack+0xf000)
        self.vm.reg_write(reg(30), self.stop)
        for i, value in enumerate(args):
            self.vm.reg_write(reg(i), value)
        self.vm.emu_start(self.symbols[name], 0, count=300000)
        assert self.returned and not self.locks, 'Unbounded call / held mutex'
        return self.vm.reg_read(reg(0))

    def startup(self, requested=0):
        self.call('horizon_pin_current_thread', requested)
        return self.sets[-1][2]

    def balance(self, workers):
        # (handle, mask, permille, fixed); steady synthetic load across two calls.
        for i, (handle, mask, load, fixed) in enumerate(workers):
            self.masks[handle] = mask
            self.ticks[handle] = 0
            self.vm.mem_write(self.symbols['registry']+48*i,
                             struct.pack('<IIc3xii4xQQQ', handle, 400+4*i, b'w',
                                         (mask & -mask).bit_length()-1, fixed, self.teb, 0, 0))
        self.call('wine_nx_thread_balance')
        self.now += 100000
        for handle, _, load, _ in workers:
            self.ticks[handle] += load*100
        self.call('wine_nx_thread_balance')


def source_layout(source):
    text = (source/'wine-nx-probe/source/thread_profile.c').read_text()
    a = text.index('struct nx_prof_thread\n')
    declaration = text[a:text.index('};', a)+2]
    check = '''
#include <stdint.h>
#include <stddef.h>
typedef uint32_t Handle;
typedef int32_t s32;
'''+declaration+'''
_Static_assert(sizeof(struct nx_prof_thread)==48, "registry size");
_Static_assert(offsetof(struct nx_prof_thread,kind)==8, "kind");
_Static_assert(offsetof(struct nx_prof_thread,fixed)==16, "fixed");
_Static_assert(offsetof(struct nx_prof_thread,teb)==24, "teb");
_Static_assert(offsetof(struct nx_prof_thread,balance_ticks)==40, "ticks");
int main(void) { return 0; }
'''
    with tempfile.TemporaryDirectory(prefix='fex-cores-layout-') as tmp:
        p = Path(tmp)/'layout.c'; p.write_text(check)
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsyntax-only', str(p)], check=True)
    # No executable-byte substitutions: the model's TEB +900 and pipe +96 are
    # also exercised by the unchanged real publisher, checking readback below.


def coremap_report(source):
    text = (source/'wine-nx-probe/source/thread_profile.c').read_text()
    structs = []
    for name in ('nx_prof_thread', 'nx_prof_row'):
        a = text.index('struct '+name+'\n')
        structs.append(text[a:text.index('};', a)+2])
    pre = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
typedef uint32_t Handle;
typedef int32_t s32;
typedef uint64_t u64;
#define R_FAILED(r) ((r)!=0)
#define NX_PROF_MAX_THREADS 128
#define NX_PROF_LINE 1000
'''
    pre += '#include "'+str(source/'wine-nx-probe/source/thread_profile.h')+'"\n'
    stubs = r'''
static pthread_mutex_t registry_mutex=PTHREAD_MUTEX_INITIALIZER;
static struct nx_prof_thread registry[NX_PROF_MAX_THREADS];
static int profiling;
static uint64_t now;
static char output[8192];
static uint64_t armGetSystemTick(void) { return now; }
static uint64_t thread_ticks(Handle handle) { return now*(130-handle)/200; }
static int svcGetThreadCoreMask(s32* core,u64* mask,Handle handle) {
  if(handle==2) return 1;
  *core=3; *mask=8; return 0;
}
static void wine_nx_runtime_trace(const char* line) {
  assert(strlen(line)<NX_PROF_LINE);
  assert(pthread_mutex_trylock(&registry_mutex)==0); /* log outside lock */
  pthread_mutex_unlock(&registry_mutex);
  assert(strlen(output)+strlen(line)+2<sizeof(output));
  strcat(output,line);strcat(output,"\n");
}
static void server_report(void) {}
static void wine_nx_fex_suspend_report(void) {}
static void wine_nx_fex_self_suspend_report(void) {}
static void wine_nx_fex_stall_targets(const struct nx_prof_row* rows,unsigned n) {
  assert(n==128 && rows[0].tid==400);
}
static void profile_report(const struct nx_prof_row* rows,unsigned n) { (void)rows;(void)n; }
'''
    body = r'''
int main(void) {
  for(unsigned i=0;i<128;i++) {
    registry[i].handle=i+1;registry[i].tid=400+4*i;
    registry[i].kind='w';registry[i].core=1;registry[i].fixed=1;
  }
  now=100000;wine_nx_thread_report();assert(!output[0]);
  now=200000;wine_nx_thread_report();
  assert(strstr(output,"[FEX3-COREMAP] 400:mask=8,fixed=1 404:mask=0,fixed=1"));
  assert(strstr(output,"444:mask=8,fixed=1"));
  assert(!strstr(output,"448:mask="));
}
'''
    with tempfile.TemporaryDirectory(prefix='fex-coremap-') as tmp:
        p, exe = Path(tmp)/'report.c', Path(tmp)/'report'
        p.write_text(pre+'\n'.join(structs)+stubs+function(text,'appendf')+
                     function(text,'wine_nx_thread_report')+body)
        subprocess.run(['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                        '-pthread','-fsanitize=address,undefined','-fno-sanitize-recover=all',
                        str(p),'-o',str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=30)


def main():
    if not __debug__:
        raise RuntimeError('Assertions required')
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf', type=Path)
    ap.add_argument('--before', type=Path, required=True)
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    source_layout(args.source)
    coremap_report(args.source)
    old = Model(args.before)
    assert [old.startup() for _ in range(12)] == [1, 2, 4, 8]*3
    checks = []
    for grant, control, cycle in ((15, False, [1,2,4]), (7, False, [1,2,4]),
                                  (5, False, [1,4]), (8, False, [8]),
                                  (12, False, [4]), (15, True, [1,2,4,8])):
        m = Model(args.elf, grant, control)
        expected = (cycle*12)[:12]
        assert [m.startup() for _ in range(12)] == expected
        assert m.fixed == 0 and m.read32(m.pipe+96) == expected[-1]
        assert m.call('horizon_get_processor_count') == grant.bit_count()
        checks.append({'grant': grant, 'control': control, 'automatic_masks': expected})
    for requested in (8, 10, 15):
        m = Model(args.elf)
        assert m.startup(requested) == requested and m.fixed == 1
        assert m.read32(m.pipe+96) == requested
    m = Model(args.elf, 7)
    assert m.startup(8) == 1 and m.fixed == 0  # Existing invalid-mask fallback.
    m = Model(args.elf); m.set_error = 0xdead
    m.u32(m.pipe+96, 123)
    m.startup()
    assert m.read32(m.pipe+96) == 123
    # A max-load-only balancer used to leave the underfed core-3 worker alone:
    # moving it cannot reduce the dominant fixed main thread's 65% load.
    workers = [(11, 1, 650, 1), (22, 2, 200, 0), (33, 4, 150, 0), (44, 8, 437, 0)]
    old = Model(args.before); old.balance(workers)
    assert old.masks[44] == 8 and not old.sets
    m = Model(args.elf); m.balance(workers)
    assert m.masks[44] in (2, 4) and m.masks[11] == 1
    assert m.follow and m.read32(m.pipe+96) == m.follow[-1][1]
    assert all(mask & 7 == mask for _, _, mask in m.sets)
    for control, fixed, disabled, failed in ((True,0,False,False), (False,1,False,False),
                                             (False,0,True,False), (False,0,False,True)):
        m = Model(args.elf, control=control)
        m.u32(m.symbols['wine_nx_balance_enabled'], int(not disabled))
        if failed: m.set_error = 0xdead
        variant = workers[:-1]+[(44, 8, 437, fixed)]
        m.balance(variant)
        assert m.masks[44] == 8 and not m.follow
    for grant in (5, 12, 8):
        m = Model(args.elf, grant)
        first = grant & -grant
        m.balance([(11, first, 650, 1), (44, grant, 437, 0)])
        assert all(mask & grant == mask for _, _, mask in m.sets)
    m = Model(args.elf); m.info_error = 0xdead; m.balance(workers)
    assert not m.sets
    # Ensure the patch preserves startup explicit-affinity branch and real
    # server mask error handling, and does not alter guest CPU-count API.
    native = args.source/'dlls/ntdll/unix/horizon.c'
    profile = args.source/'wine-nx-probe/source/thread_profile.c'
    assert 'fex_auto_worker_mask' not in function(native.read_text().replace(
        'unsigned int horizon_get_processor_count', 'static unsigned int horizon_get_processor_count'),
        'horizon_get_processor_count')
    report = {'passed': True, 'hardware_tested': False, 'scope': __doc__,
              'native_elf_sha256': hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              'before_native_elf_sha256': hashlib.sha256(args.before.read_bytes()).hexdigest(),
              'startup_cases': checks,
              'checks': ['Old binary selects core 3 every fourth automatic startup; new uses 0-2',
                         'Sparse/three-core grants, core-3-only fallback, four-core control',
                         'Explicit single/multiple-core guest affinity and processor count preserved',
                         'Failed startup affinity does not publish a false server mask',
                         'Real balancer moves automatic core-3 worker despite dominant fixed main thread',
                         'Explicit affinity, disabled balancer, control and failed SVC remain unchanged',
                         'Successful balancer move publishes mask through actual server pipe path',
                         'ASan/UBSan COREMAP snapshot: 128 workers, 12-row bound, failed-query sentinel, log outside mutex'],
              'generated_source_hashes': {str(p.relative_to(args.source)): hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in (native, profile)},
              'source_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (Path(__file__).resolve(), ROOT/'src/runtime/fex_worker_cores.h',
                                          ROOT/'tools/fex_worker_core_patches.py', ROOT/'tests/fex_reservations.py')}}
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
