"""Execute Wine's linked ARM64 VA search with modeled Horizon mappings.

This checks address selection, bounds and conflict recovery, not device RAM or
the full FEX guest workload. Kernel/native mapping calls are modeled explicitly.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm64_const as arm


def reg(i):
    return getattr(arm, f'UC_ARM64_REG_X{i}')


class Model:
    def __init__(self, path):
        self.vm = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.symbols = {}
        with path.open('rb') as stream:
            elf = ELFFile(stream)
            for symbol in elf.get_section_by_name('.symtab').iter_symbols():
                # Keep duplicate local names (e.g. mappings) out of the lookup.
                self.symbols.setdefault(symbol.name, 0x1000000 + symbol['st_value'])
            for segment in elf.iter_segments():
                if segment['p_type'] == 'PT_LOAD':
                    va, size = segment['p_vaddr'], segment['p_memsz']
                    low, high = va & ~4095, (va + size + 4095) & ~4095
                    self.vm.mem_map(0x1000000 + low, high - low)
                    self.vm.mem_write(0x1000000 + va, segment.data())
            for rel in elf.get_section_by_name('.relr.dyn').iter_relocations():
                addr = 0x1000000 + rel['r_offset']
                self.q(addr, self.uq(addr) + 0x1000000)
        self.data, self.stack, self.stop = 0x50000000, 0x51000000, 0x52000000
        for addr in (self.data, self.stack, self.stop):
            self.vm.mem_map(addr, 0x10000)
        for name, addr in self.symbols.items():
            if name.startswith('__wine_dbch_'):
                self.vm.mem_write(addr, b'\0')
        self.vm.hook_add(UC_HOOK_CODE, self.hook)
        self.probes, self.blocked = [], []
        self.hard_error = 0
        self.returned = False

    def q(self, addr, value):
        self.vm.mem_write(addr, struct.pack('<Q', value & 0xffffffffffffffff))

    def uq(self, addr):
        return struct.unpack('<Q', self.vm.mem_read(addr, 8))[0]

    def ret(self, value=0):
        self.vm.reg_write(reg(0), value & 0xffffffffffffffff)
        self.vm.reg_write(arm.UC_ARM64_REG_PC, self.vm.reg_read(reg(30)))

    def hook(self, vm, pc, size, user):
        s = self.symbols
        if pc == self.stop:
            self.returned = True
            vm.emu_stop()
        elif pc in {s.get('__errno'), s.get('__errno_location')}:
            self.ret(self.data + 0x100)
        elif pc in {s.get('horizon_mmap'), s.get('horizon_anon_mmap_reserved')}:
            start, length = [vm.reg_read(reg(i)) for i in range(2)]
            assert self.low <= start and start + length <= self.high, 'Probe outside caller bounds'
            assert not start & self.mask and length == self.size
            self.probes.append(start)
            error = self.hard_error
            if not error and any(start < b and a < start+length for a, b in self.blocked):
                error = 17  # EEXIST
            vm.mem_write(self.data+0x100, struct.pack('<I', error))
            self.ret(-1 if error else start)
        elif pc in {s.get('__wine_dbg_get_channel_flags'), s.get('__wine_dbg_output'),
                     s.get('horizon_trace'), s.get('wine_nx_runtime_trace')}:
            self.ret()

    def search(self, low, high, size, top=True, mask=0xffff, blocked=(), hard_error=0):
        self.low, self.high, self.size, self.mask = low, high, size, mask
        self.blocked, self.hard_error = blocked, hard_error
        self.probes, self.returned = [], False
        # One Wine reserved interval covering the test range. No guest views.
        head, area = self.symbols['reserved_areas'], self.data+0x200
        self.vm.mem_write(area, struct.pack('<4Q', head, head, low, high-low))
        self.vm.mem_write(head, struct.pack('<2Q', area, area))
        self.vm.mem_write(self.data, struct.pack('<QqiiQQQ', size,
                          -(mask+1) if top else mask+1, 0, int(top), mask, 0, 0))
        self.vm.reg_write(arm.UC_ARM64_REG_SP, self.stack+0xf000)
        self.vm.reg_write(reg(30), self.stop)
        for i, value in enumerate((self.data, low, high)):
            self.vm.reg_write(reg(i), value)
        self.vm.emu_start(self.symbols['alloc_free_area_in_range'], 0, count=4000000)
        assert self.returned, 'VA search failed to terminate'
        return self.vm.reg_read(reg(0))


class GuardModel(Model):
    """Run the real Horizon reservation replacement, mocking libnx/kernel only."""
    def __init__(self, path):
        super().__init__(path)
        self.vm.mem_write(self.symbols['horizon_kernel_region_count'], struct.pack('<I', 0))
        self.locks = []
        self.reservations = {}
        self.reservation_ops = []
        self.query_fail = False
        self.reserve_fail = False
        self.next_reservation = self.data + 0x4000

    def hook(self, vm, pc, size, user):
        s = self.symbols
        if pc == s.get('horizon_anon_mmap_reserved'):
            return  # Execute the mapper rather than modeling it.
        if pc in {s.get('pthread_mutex_lock'), s.get('virtmemLock')}:
            lock = 'mapping' if pc == s.get('pthread_mutex_lock') else 'virtmem'
            assert lock not in self.locks, 'Recursive lock/deadlock'
            if lock == 'virtmem':
                assert self.locks == ['mapping'], 'Lock order'
            self.locks.append(lock)
            self.ret()
        elif pc in {s.get('pthread_mutex_unlock'), s.get('virtmemUnlock')}:
            lock = 'mapping' if pc == s.get('pthread_mutex_unlock') else 'virtmem'
            assert self.locks.pop() == lock
            self.ret()
        elif pc == s.get('svcQueryMemory'):
            assert self.locks == ['mapping', 'virtmem']
            ptr, _, address = [vm.reg_read(reg(i)) for i in range(3)]
            if self.query_fail:
                self.ret(0xdead)
                return
            boundaries = sorted({0, 0x100000000, *(a for a, b in self.blocked), *(b for a, b in self.blocked)})
            begin = max(p for p in boundaries if p <= address)
            end = min(p for p in boundaries if p > address)
            kind = 8 if any(a <= address < b for a, b in self.blocked) else 0
            vm.mem_write(ptr, struct.pack('<2Q6I', begin, end-begin, kind, 0, 0, 0, 0, 0))
            self.ret()
        elif pc == s.get('virtmemAddReservation'):
            assert self.locks == ['mapping', 'virtmem']
            if self.reserve_fail:
                self.ret(0)
                return
            token = self.next_reservation
            self.next_reservation += 0x20
            interval = tuple(vm.reg_read(reg(i)) for i in range(2))
            self.reservations[token] = interval
            self.reservation_ops.append(('add', token, interval))
            self.ret(token)
        elif pc == s.get('virtmemRemoveReservation'):
            assert self.locks == ['mapping', 'virtmem']
            token = vm.reg_read(reg(0))
            assert token in self.reservations, 'Double free or unowned reservation'
            self.reservation_ops.append(('remove', token, self.reservations.pop(token)))
            self.ret()
        elif pc in {s.get('memset'), s.get('memcpy')}:
            dest, value, count = [vm.reg_read(reg(i)) for i in range(3)]
            assert count <= 4096
            vm.mem_write(dest, bytes([value & 255])*count if pc == s.get('memset') else bytes(vm.mem_read(value, count)))
            self.ret(dest)
        else:
            super().hook(vm, pc, size, user)

    def seed(self, begin, size, prot=0, backing=0, reservation=True, section=0, kind=0):
        node = self.uq(self.symbols['mapping_pool'])
        self.vm.mem_write(node, bytes(104))
        self.vm.mem_write(node, struct.pack('<3Qi4x4QB7x3Q', begin, size, 0, prot,
                         backing, self.data+0x3000 if reservation else 0, section, 0, kind, 0, 0, 0))
        self.q(self.symbols['mappings']+8, node+72)
        self.q(self.symbols['mapping_pool']+32, 1)
        if reservation:
            self.reservations[self.data+0x3000] = (begin, size)
        return node

    def reserve(self, start, size):
        self.returned = False
        self.vm.reg_write(arm.UC_ARM64_REG_SP, self.stack+0xf000)
        self.vm.reg_write(reg(30), self.stop)
        for i, value in enumerate((start, size, 0)):
            self.vm.reg_write(reg(i), value)
        self.vm.emu_start(self.symbols['horizon_anon_mmap_reserved'], 0, count=100000)
        assert self.returned and not self.locks
        return self.vm.reg_read(reg(0))


def guard_tests(path):
    failed = 0xffffffffffffffff
    start, size = 0x18100000, 0x4000000
    for options in ({'backing': 0xbeef, 'reservation': False, 'prot': 3},
                    {'kind': 3}, {'kind': 2, 'section': 0xbeef}, {'prot': 1}):
        m = GuardModel(path)
        node = m.seed(start+0x1000, 0x2000, **options)
        before = bytes(m.vm.mem_read(node, 104))
        assert m.reserve(start, size) == failed
        assert bytes(m.vm.mem_read(node, 104)) == before and not m.reservation_ops
    for reason in ('native-stack', 'query-failure', 'reserve-oom', 'kernel-region'):
        m = GuardModel(path)
        node = m.seed(start, size)
        if reason == 'native-stack':
            m.blocked = [(start, start+0x49000)]
        if reason == 'query-failure':
            m.query_fail = True
        if reason == 'reserve-oom':
            m.reserve_fail = True
        if reason == 'kernel-region':
            m.vm.mem_write(m.symbols['horizon_kernel_region_count'], struct.pack('<I', 1))
            m.vm.mem_write(m.symbols['horizon_kernel_regions'], struct.pack('<2Q', start+0x1000, 0x2000))
        before = bytes(m.vm.mem_read(node, 104))
        assert m.reserve(start, size) == failed
        assert bytes(m.vm.mem_read(node, 104)) == before and not m.reservation_ops
    for left, right in ((0, 0), (0x20000, 0), (0, 0x30000), (0x20000, 0x30000)):
        m = GuardModel(path)
        m.seed(start-left, size+left+right)
        assert m.reserve(start, size) == start
        expected = [(start, size)]
        if left:
            expected.append((start-left, left))
        if right:
            expected.append((start+size, right))
        assert sorted(m.reservations.values()) == sorted(expected)
        # The transition must cover the whole address until the final mapping
        # is installed, including while the old reservation is split/removed.
        transition = m.reservation_ops[0]
        assert transition[0] == 'add' and transition[2] == (start, size)
        assert m.reservation_ops[-1] == ('remove', transition[1], (start, size))
    return ['Native guarded mapper rejects live backing, anchors and section holes without mutation',
            'Native stacks, query failures, kernel regions and reservation OOM preserve original metadata',
            'Four real reservation split/replacement paths keep transition coverage and exact remaining intervals']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--expect-baseline-failure', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    model = Model(args.elf)
    result = model.search(0x02670000, 0x1c100000, 0x4000000,
                          blocked=[(0x18070000, 0x18149000)])
    tests = []
    if args.expect_baseline_failure:
        assert result == 0 and model.probes == [0x18100000], (result, model.probes)
        tests.append('Reproduced device address choice: one conflict at 0x18100000 skips a usable reserved arena')
    else:
        assert result == 0x14070000, hex(result)
        tests.append('64 MiB top-down allocation recovers around the logged native overlap')
        for top in (False, True):
            for mask in (0xfff, 0xffff, 0xfffff):
                low, high, size = 0x10001000, 0x1203f000, 0x200000
                for blocked in ([], [(0x10020000, 0x10121000)],
                                [(0x11f10000, 0x12000000)],
                                [(0x10120000, 0x10234000), (0x11e10000, 0x11f83000)],
                                [(low, high)]):
                    candidates = list(range((low+mask)&~mask, high-size+1, mask+1))
                    if top:
                        candidates.reverse()
                    expected = next((p for p in candidates if not any(p < b and a < p+size for a, b in blocked)), 0)
                    assert model.search(low, high, size, top, mask, blocked) == expected
        tests.append('30 independent layout/direction/alignment cases select the first legal address or bounded failure')
        for top in (False, True):
            for size in (0x800000, 0x2000000):
                low, high, mask = 0x30200000, 0x40000000, size-1
                for blocked in ([], [(0x30800000, 0x32100000)],
                                [(0x3e000000, 0x40000000)], [(low, high)]):
                    candidates = list(range((low+mask)&~mask, high-size+1, mask+1))
                    if top:
                        candidates.reverse()
                    expected = next((p for p in candidates if not any(p < b and a < p+size for a, b in blocked)), 0)
                    assert model.search(low, high, size, top, mask, blocked) == expected
        tests.append('16 span searches at 8/32 MiB alignment honor both directions, native conflicts and exhaustion')
        for top in (False, True):
            assert not model.search(0x10000000, 0x10010000, 0x20000, top)
            assert not model.probes
            assert not model.search(0x10000000, 0x12000000, 0x200000, top, hard_error=12)
            assert len(model.probes) == 1, 'Do not retry true ENOMEM as an address conflict'
        tests.append('Oversized allocations do not probe; real ENOMEM stops immediately')
        tests.extend(guard_tests(args.elf))
    report = {'passed': True, 'baseline_reproduction': args.expect_baseline_failure,
              'native_elf_sha256': hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              'checks': tests, 'scope': 'Linked Wine ARM64 VA search and guarded native mapper; modeled kernel/libnx services'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
