"""Execute the shipped dispatcher emitter, emitted code, and real cache methods.

NT services, allocation, clock and locks are modeled. No Switch timing claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import struct

import capstone
from unicorn import arm64_const as arm
from fex_alloc import PARAM, STUBS, STACK, reg
from fex_lookup import LookupModel

CODE = 0x71000000
HIT = STUBS + 0xb000


class Model(LookupModel):
    def host_callbacks(self):
        return STUBS+0xd000, STUBS+0xd300, self.alias, STUBS+0xd304, self.logger

    def hook(self, vm, pc, size, user):
        if getattr(self, 'executing', False):
            self.instructions += 1
            if pc in self.destinations:
                self.outcome = self.destinations[pc]
                vm.emu_stop()
                return
        if hasattr(self, 'allowed') and pc not in self.allowed:
            return
        if pc == self.symbols.get('_ZNSt3__16chrono12system_clock3nowEv'):
            self.clock_reads = getattr(self, 'clock_reads', 0)+1
        if pc == STUBS+0xd000:
            assert vm.reg_read(reg(0)) == 0x4000
            vm.reg_write(reg(0), CODE)
            self.host_return()
            return
        if pc in (STUBS+0xd300, STUBS+0xd304):
            vm.reg_write(reg(0), 1)
            self.host_return()
            return
        super().hook(vm, pc, size, user)

    def emit(self):
        self.allowed = set(self.hooks) | self.config_hooks | set(self.heap_hooks) | {
            STUBS+x for x in (0xc000, 0xc100, 0xd000, 0xd300, 0xd304, 0xd200, 0xd204,
                              0xd208, 0xd20c, 0xd210, 0xe000, 0xf000)} | {
            self.symbols[n] for n in ('memcpy', 'memmove', 'memset',
                                      '_ZNSt3__16chrono12system_clock3nowEv')}
        self.vm.mem_map(CODE, 0x10000)
        # Pinned Context.Config.DisableVixlIndirectCalls, whose production
        # default is true. This is a native build, not a VIXL simulator.
        self.vm.mem_write(self.ctx+0x6e, b'\1')
        self.emitter = PARAM+0x3000
        self.vm.reg_write(reg(0), self.emitter)
        self.vm.reg_write(reg(1), self.ctx)
        self.vm.reg_write(arm.UC_ARM64_REG_SP, STACK+0x3f000)
        self.vm.reg_write(reg(30), self.stop)
        self.vm.emu_start(self.symbols[self.method('10DispatcherC2')], self.stop, count=5000000)
        assert not self.trapped and self.vm.reg_read(arm.UC_ARM64_REG_PC) == self.stop
        end = self.readq(self.emitter+8)
        assert CODE < end <= CODE+0x4000
        self.loop = self.readq(self.emitter+0xa0+self.emitter_view_offset)
        self.fill = self.readq(self.emitter+0xa8+self.emitter_view_offset)
        self.destinations = {HIT:'hit',
            self.symbols[self.method('ContextImpl12CompileBlock')]: 'fallback',
            self.symbols[self.method('ContextImpl17CompileSingleStep')]: 'single_step'}
        self.setup()
        assert not self.trapped
        self.writeq(self.frame+0xa0, self.readq(self.obj+0x30))
        self.writeq(self.frame+0xa8, self.readq(self.obj+0x38) << 4)
        dis = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        ins = list(dis.disasm(bytes(self.vm.mem_read(self.loop, 160)), self.loop))
        if self.l2_enabled:
            # The emitted L2 pointer load gives the actual pinned frame offset.
            load = next(i for i in ins if i.mnemonic == 'ldr' and i.op_str.startswith('x0, [x28,'))
            offset = int(re.search(r'#(0x[0-9a-f]+)', load.op_str)[1], 16)
            self.writeq(self.frame+offset, self.readq(self.obj+0x20))
        return hashlib.sha256(bytes(self.vm.mem_read(CODE, end-CODE))).hexdigest()

    def dispatch(self, guest, *, trap=False, single=False, flags=0xa0000000):
        self.writeq(self.frame+0x18, guest)
        self.vm.mem_write(self.frame+0x3f8, bytes([int(trap)]))
        self.vm.mem_write(self.frame+0x408, struct.pack('<I', flags))
        for n in range(4, 31):
            self.vm.reg_write(reg(n), 0x12340000+n)
        self.vm.reg_write(reg(28), self.frame)
        self.vm.reg_write(reg(1), int(single))
        self.vm.reg_write(arm.UC_ARM64_REG_SP, STACK+0x3f000)
        self.vm.reg_write(arm.UC_ARM64_REG_NZCV, flags)
        before = [self.vm.reg_read(reg(n)) for n in range(4, 31)]
        self.outcome = None
        self.instructions = 0
        self.executing = True
        try:
            self.vm.emu_start(self.fill if single else self.loop, self.stop, count=2000)
        finally:
            self.executing = False
        assert self.outcome is not None, (hex(self.vm.reg_read(arm.UC_ARM64_REG_PC)),
                                         self.trapped, self.instructions, self.logs[-3:])
        if self.outcome == 'hit':
            assert self.vm.reg_read(arm.UC_ARM64_REG_NZCV) == flags
            assert before == [self.vm.reg_read(reg(n)) for n in range(4, 31)]
            assert self.vm.reg_read(arm.UC_ARM64_REG_SP) == STACK+0x3f000
        return self.outcome


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('dll', type=Path)
    ap.add_argument('--before', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if not __debug__: raise RuntimeError('Assertions required')
    old = Model(args.before, dynamic=True)
    old_emit = old.emit()
    old.add(0x123456, HIT)
    assert old.find(0x123456) == HIT  # L1 is populated.
    old_l1_first = b'dispatcher=L1-first' in args.before.read_bytes()
    assert old.dispatch(0x123456) == ('hit' if old_l1_first else 'fallback')
    old_instructions = old.instructions
    del old
    checks = ['Previous binary L1 dispatch behavior verified: ' +
              ('L1-first hit' if old_l1_first else 'CompileBlock fallback despite matching L1')]
    emitted = []
    dispatches = 0
    for enabled in (False, True):
        m = Model(args.dll, dynamic=True, l2_enabled=enabled)
        emitted.append(m.emit())
        assert m.readq(m.obj+0x38) == (8191 if enabled else 65535), (enabled, m.readq(m.obj+0x38), m.logs)
        rng = random.Random(0xf3ca)
        addresses = [0x401000, 0x123456, 0xfff19510, 0xffffffff]
        addresses += [rng.randrange(0x10000, 0x100000000) for _ in range(128)]
        for address in addresses:
            m.add(address, HIT)
            for flags in (0, 0xf0000000, 0xa0000000):
                assert m.dispatch(address, flags=flags) == 'hit'
                dispatches += 1
            assert m.instructions == 12 + int(m.fold_l1)  # Includes hook at target.
            assert m.dispatch(address, trap=True) == 'single_step'
            assert m.dispatch(address, single=True) == 'single_step'
            m.invalidate(address, erase=True)
            assert m.find(address) == 0
            assert m.dispatch(address) == 'fallback'
            m.add(address, HIT)
            assert m.dispatch(address) == 'hit'
            dispatches += 4
        address = 0x401020
        m.add(address, HIT)
        m.add(m.colliding_guest(address), HIT)
        assert m.dispatch(address) == 'fallback'
        assert m.find(address) == HIT
        assert m.dispatch(address) == 'hit'
        m.clear_l1_entry(address)
        # L2 is populated by FindBlock only when explicitly enabled.
        assert m.dispatch(address) == ('hit' if enabled else 'fallback')
        m.find(address)
        m.call(m.method('22ClearThreadLocalCaches'), m.obj, 0)
        assert m.dispatch(address) == 'fallback'
        assert m.find(address) == HIT and m.dispatch(address) == 'hit'
        # A tag alone must never branch through a null host pointer.
        base, mask = m.readq(m.obj+0x30), m.readq(m.obj+0x38)
        m.vm.mem_write(base+m.l1_index(address, mask)*16, struct.pack('<QQ', 0, address))
        assert m.dispatch(address) == ('hit' if enabled else 'fallback')
        m.add(address, HIT)
        if enabled:
            update = m.method('20UpdateDynamicL1Stats')
            for count, sizes in ((10000, (16384, 32768, 65536, 65536)),
                                 (0, (32768, 16384, 8192, 8192))):
                for size in sizes:
                    m.clock += 2000000
                    m.writeq(m.obj+0x68, count)
                    m.call(update, m.obj, m.thread, address, HIT)
                    assert m.readq(m.obj+0x38) == size-1
                    assert m.find(address) == HIT
                    assert m.dispatch(address) == 'hit'
        else:
            reads = getattr(m, 'clock_reads', 0)
            for _ in range(16):
                m.clock += 2000000
                m.clear_l1_entry(address)
                assert m.find(address) == HIT
                assert m.readq(m.obj+0x38) == 65535
            assert getattr(m, 'clock_reads', 0) == reads
    checks += [f'{dispatches} dispatch cases with L2 off/on: exact high-address tags, flags/GPR/SP preservation, TF and forced single-step',
               'Invalidation plus L3 erase cannot execute stale code; collisions, clear/refill and null-host fallback',
               'Resident L1 uses all 65536 entries immediately without clock reads on L3 refill',
               'Optional L2 retains its dynamic start and eight grow/shrink transitions']
    report = {'passed':True, 'hardware_tested':False, 'checks':checks,
              'dll_sha256':hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'before_sha256':hashlib.sha256(args.before.read_bytes()).hexdigest(),
              'before_dispatch_outcome':'hit' if old_l1_first else 'fallback',
              'old_instructions_to_compileblock':None if old_l1_first else old_instructions,
              'before_instructions_to_target':old_instructions,
              'new_instructions_to_l1_target':12 + int(m.fold_l1),
              'emitted_sha256':emitted, 'before_emitted_sha256':old_emit,
              'test_sources':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
                              for name in ('fex_dispatch_cache.py', 'fex_lookup.py', 'fex_memory.py', 'fex_alloc.py')},
              'scope':'Real ARM64 dispatcher constructor and emitted code, cache methods; modeled host allocation/NT locks, no hardware timing'}
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
