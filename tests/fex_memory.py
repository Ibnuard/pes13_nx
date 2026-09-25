"""Execute the linked FEX lookup allocator and lazy-commit adapter in Unicorn.

Models fragmented NT reservations, page states and the configuration/syscall
interfaces. It does not execute the whole translator or a Horizon kernel.
--before reproduces the old 152 MiB reservation failure and null publication.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

from unicorn import UC_PROT_NONE, UC_PROT_READ, UC_PROT_WRITE
from unicorn import arm64_const as arm
from fex_alloc import Model, PARAM, STUBS, NO_MEMORY, INVALID, reg


MIB = 1024 * 1024
LOOKUP_BYTES = MIB
INDEX_BYTES = 8*MIB
L2_BYTES = 16*MIB
PAGE = 4096
RESERVE, COMMIT, FREE = 0x2000, 0x1000, 0x10000
CTOR = '_ZN7FEXCore11LookupCacheC2EPNS_7Context11ContextImplE'
DTOR = '_ZN7FEXCore11LookupCacheD2Ev'


class NullPublished(Exception):
    pass


class MemoryModel(Model):
    # Conservative subset of free ranges reported on the failing Switch run.
    # The other ranges overlap addresses used by this test harness itself.
    holes = ((0xbe200000, 105*MIB), (0x07044000, 79*MIB), (0xf2001000, 63*MIB))

    def __init__(self, dll, *, dynamic=True, l2_enabled=False, poison_native=False):
        self.dynamic = dynamic
        self.l2_enabled = l2_enabled
        self.poison_native = poison_native
        self.tracked = {}
        self.pages = {}
        self.requests = []
        self.query_override = None
        self.fail_query = False
        super().__init__(dll)
        self.ctx, handler, vtable = PARAM+0x1000, PARAM+0x1400, PARAM+0x1800
        self.writeq(self.ctx+0x30, 1 << 32)
        self.writeq(self.ctx+0xf8, handler)
        self.writeq(handler, vtable)
        self.writeq(vtable+0x28, STUBS+0xc000)
        self.writeq(vtable+0x30, STUBS+0xc100)
        self.config_hooks = {
            address for name, address in self.symbols.items()
            if name.startswith(('_ZN7FEXCore6Config5ValueIyE11GetIfExists',
                                '_ZN7FEXCore6Config5ValueIbE11GetIfExists'))
        }
        assert len(self.config_hooks) == 2

    def host_callbacks(self):
        return self.stop, STUBS+0xd000, self.alias, self.stop, self.logger

    def allocation_at(self, address):
        return next(((base, length) for base, length in self.regions.items()
                     if base <= address < base+length), None)

    def allocate(self, base_pointer, size_pointer, flags, params=0, count=0):
        assert not count and not params
        base, size = self.readq(base_pointer), self.readq(size_pointer)
        self.requests.append((base, size, flags))
        if self.fail_allocations:
            return NO_MEMORY
        size = (size+PAGE-1) & -PAGE
        if not size:
            return INVALID
        if flags & RESERVE:
            assert base == 0
            for hole, length in self.holes:
                candidate = (hole+0xffff) & -0x10000
                for used, amount in sorted(self.regions.items()):
                    if used+amount <= candidate:
                        continue
                    if candidate+size <= used:
                        break
                    candidate = (used+amount+0xffff) & -0x10000
                if candidate+size <= hole+length:
                    base = candidate
                    break
            else:
                return NO_MEMORY
            self.regions[base] = size
            self.vm.mem_map(base, size, UC_PROT_NONE)
        elif flags & COMMIT:
            allocation = self.allocation_at(base)
            if not allocation or base+size > sum(allocation):
                return INVALID
        else:
            raise AssertionError(f'Unexpected allocation flags {flags:x}')
        if flags & COMMIT:
            self.vm.mem_protect(base, size, UC_PROT_READ | UC_PROT_WRITE)
            for page in range(base, base+size, PAGE):
                self.pages[page] = (COMMIT, 4)
        self.writeq(base_pointer, base)
        self.writeq(size_pointer, size)
        return 0

    def query(self, address):
        if self.query_override is not None:
            return self.query_override
        allocation = self.allocation_at(address)
        if not allocation:
            return (address & -PAGE, 0, 0, 0, PAGE, FREE, 0, 0, 0)
        base, length = allocation
        page = address & -PAGE
        state, protection = self.pages.get(page, (RESERVE, 0))
        start, end = page, page+PAGE
        while start > base and self.pages.get(start-PAGE, (RESERVE, 0)) == (state, protection):
            start -= PAGE
        while end < base+length and self.pages.get(end, (RESERVE, 0)) == (state, protection):
            end += PAGE
        return (start, base, 4, 0, end-start, state, protection, 0x20000, 0)

    def hook(self, vm, pc, size, user):
        if pc == self.scratch_alloc:
            super().hook(vm, pc, size, user)
            address = vm.reg_read(reg(0))
            if address and self.poison_native:
                vm.mem_write(address, b'\xa5' * self.native_regions[address])
            return
        if pc in getattr(self, 'config_hooks', set()):
            option, default = vm.reg_read(reg(0)), vm.reg_read(reg(1))
            value = int(self.dynamic) if option == 27 else int(not self.l2_enabled) if option == 26 else default
            vm.reg_write(reg(0), value)
            self.host_return()
            return
        if pc in (STUBS+0xc000, STUBS+0xc100):
            base, amount = vm.reg_read(reg(1)), vm.reg_read(reg(2))
            if not base:
                raise NullPublished('failed lookup allocation entered overcommit tracking')
            if pc == STUBS+0xc000:
                assert base not in self.tracked and self.regions[base] == amount
                self.tracked[base] = amount
            else:
                assert self.tracked.pop(base) == amount
            self.host_return()
            return
        if pc == STUBS+0xd000:  # Data reservation is not a CodeMemory allocation.
            vm.reg_write(reg(0), 0)
            self.host_return()
            return
        name = self.hooks.get(pc)
        a = [vm.reg_read(reg(i)) for i in range(8)]
        if name == 'memset':
            vm.mem_write(a[0], bytes([a[1] & 255])*a[2])
            self.host_return()
            return
        if name == 'NtQueryVirtualMemory':
            assert a[2] == 0 and a[4] == 48
            if not self.fail_query:
                vm.mem_write(a[3], struct.pack('<QQIIQIIII', *self.query(a[1])))
                self.writeq(a[5], 48)
            vm.reg_write(reg(0), INVALID if self.fail_query else 0)
            self.host_return()
            return
        if name == 'NtFreeVirtualMemory':
            base, length = self.readq(a[1]), self.readq(a[2])
            if a[3] == 0x8000:
                length = self.regions[base]
            else:
                assert a[3] == 0x4000
            for page in range(base, base+length, PAGE):
                self.pages.pop(page, None)
            if a[3] == 0x4000:
                vm.mem_write(base, bytes(length))
                vm.mem_protect(base, length, UC_PROT_NONE)
                vm.reg_write(reg(0), 0)
                self.host_return()
                return
        super().hook(vm, pc, size, user)

    def create_lookup(self, slot):
        obj = PARAM+0x2000+slot*0x200
        self.vm.mem_write(obj, bytes(0x200))
        self.call(CTOR, obj, self.ctx)
        return obj

    def commit(self, fault, base, end):
        result = self.call('PES13FexCommitTrackedMemory', fault, base, end)
        assert not self.trapped
        return bool(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--before', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checks = []
    if args.before:
        old = MemoryModel(args.before)
        try:
            old.create_lookup(0)
        except NullPublished:
            assert old.requests[-1][1] == 152*MIB and not old.regions
        else:
            raise AssertionError('Old null reservation was not reproduced')
        checks.append('old DLL: 152 MiB request fails and publishes null in fragmented VA')

    # Match and exceed PES's observed worker count in the default L2-off mode.
    for dynamic, enabled in ((False, False), (True, False), (False, True), (True, True)):
        model = MemoryModel(args.dll, dynamic=dynamic, l2_enabled=enabled, poison_native=True)
        live = 5 if enabled else 32
        expected = 25*MIB if enabled else LOOKUP_BYTES
        for wave in range(4):
            objects = [model.create_lookup(slot) for slot in range(live)]
            assert not model.trapped and len(model.tracked) == (live if enabled else 0)
            assert sum(model.regions.values()) == (live*expected if enabled else 0) and not model.pages
            assert sum(model.native_regions.values()) == (0 if enabled else live*expected)
            for obj in objects:
                base, backing, l1, mask, size = struct.unpack('<5Q', model.vm.mem_read(obj+0x20, 40))
                assert size == expected
                assert backing-base == (INDEX_BYTES if enabled else 0)
                assert l1-backing == (L2_BYTES if enabled else 0)
                assert mask == (8192 if dynamic else 65536)-1
                if enabled:
                    # Enabling L2 still supports every x86 page separately.
                    assert base+((0xfffff000 >> 12)*8)+8 == backing
                assert model.readq(model.ctx+0x30) == 1 << 32
                if enabled:
                    assert model.commit(base+17, base, base+size)
                    assert model.requests[-1] == (base, 65536, COMMIT)
                else:
                    assert bytes(model.vm.mem_read(base, size)) == bytes(size)
            assert len(model.pages)*PAGE == (live*65536 if enabled else 0)
            for obj in reversed(objects):
                model.call(DTOR, obj)
                assert not model.trapped
            assert not model.regions and not model.tracked and not model.pages and not model.native_regions
    checks.append('296 actual constructors/destructors: 32 live L2-off caches use 32 MiB native resident memory; poisoned allocations cleared and no leaks')
    checks.append('L2-on retains 25 MiB and full 4 GiB indexing; L1 size/growth and guest config unchanged')

    model = MemoryModel(args.dll, l2_enabled=True)
    obj = model.create_lookup(0)
    base, length = model.readq(obj+0x20), model.readq(obj+0x40)
    end = base+length
    # First touch commits at the fault, not back from AllocationBase.
    assert model.commit(base+3*MIB+31, base, end)
    assert model.requests[-1] == (base+3*MIB, 65536, COMMIT)
    requests = len(model.requests)
    assert model.commit(base+3*MIB+31, base, end)
    assert len(model.requests) == requests  # Race/already committed: no new allocation.
    assert model.commit(end-7, base, end)
    assert model.requests[-1] == (end-PAGE, PAGE, COMMIT)
    assert model.commit(base+3*MIB-7, base, end)
    assert model.requests[-1] == (base+3*MIB-PAGE, PAGE, COMMIT)
    # Clip to a tracked subrange smaller than an NT reservation.
    assert model.commit(base+4*MIB, base+4*MIB, base+4*MIB+2*PAGE)
    assert model.requests[-1] == (base+4*MIB, 2*PAGE, COMMIT)
    checks.append('lazy commits <=64 KiB clipped to interval and NT region; committed race accepted')

    for fault, start, stop in ((0, 0, length), (base, base, base), (base-1, base, end),
                               (end, base, end), (base+PAGE, base+1, end),
                               (base+PAGE, base, end-1), (base, end, base)):
        requests = len(model.requests)
        assert not model.commit(fault, start, stop) and len(model.requests) == requests
    model.fail_query = True
    assert not model.commit(base+4*MIB+4*PAGE, base, end)
    model.fail_query = False
    model.fail_allocations = True
    assert not model.commit(base+4*MIB+4*PAGE, base, end)
    assert base+4*MIB+4*PAGE not in model.pages
    model.fail_allocations = False
    for state, protection, expected in ((FREE, 0, False), (COMMIT, 4, True),
                                        (COMMIT, 8, True), (COMMIT, 0x104, False),
                                        (COMMIT, 1, False), (COMMIT, 2, False),
                                        (COMMIT, 0x20, False)):
        model.query_override = (base, base, 4, 0, length, state, protection, 0x20000, 0)
        requests = len(model.requests)
        assert model.commit(base+7, base, end) == expected
        assert len(model.requests) == requests
    for region, size in ((base+PAGE, PAGE), (base, 0), (base, (1 << 64)-1), (base, 123)):
        model.query_override = (region, base, 4, 0, size, RESERVE, 0, 0x20000, 0)
        assert not model.commit(base+7, base, end)
    model.query_override = None
    checks.append('null/malformed/unowned/protected ranges, query failure and commit failure rejected')

    # Eviction must decommit only L2 + guest index and allow a later refill.
    l1 = model.readq(obj+0x30)
    assert model.commit(l1, base, end)
    model.vm.mem_write(l1, b'KEEP')
    model.vm.mem_write(base+3*MIB, b'DROP')
    model.writeq(obj+0x48, 65536)
    clear = next(name for name in model.symbols if '12ClearL2Cache' in name)
    model.call(clear, obj, PARAM+0x9000)
    assert not model.trapped and model.readq(obj+0x48) == 0
    assert model.vm.mem_read(l1, 4) == b'KEEP' and base+3*MIB not in model.pages
    assert model.commit(base+3*MIB, base, end)
    assert model.vm.mem_read(base+3*MIB, 4) == bytes(4)
    # A full code-buffer/cache reset must also rewind L2's allocation cursor.
    model.writeq(obj+0x48, L2_BYTES-65536)
    clear_all = next(name for name in model.symbols if '22ClearThreadLocalCaches' in name)
    model.call(clear_all, obj, PARAM+0x9000)
    assert not model.trapped and model.readq(obj+0x48) == 0 and not model.pages
    assert model.commit(l1, base, end) and model.vm.mem_read(l1, 4) == bytes(4)
    model.call(DTOR, obj)
    assert not model.regions and not model.tracked and not model.pages
    checks.append('actual L2 eviction retains L1; full reset clears L1 and rewinds backing cursor; zero refill')

    model = MemoryModel(args.dll)
    obj = model.create_lookup(0)
    base, size = model.readq(obj+0x20), model.readq(obj+0x40)
    assert size == MIB and model.native_regions[base] == MIB and not model.tracked
    model.vm.mem_write(base, b'KEEP')
    model.writeq(obj+0x48, 65536)
    requests = len(model.calls)
    model.call(clear, obj, PARAM+0x9000)
    assert model.vm.mem_read(base, 4) == b'KEEP' and model.readq(obj+0x48) == 0
    assert not any(name == 'NtFreeVirtualMemory' for name, _ in model.calls[requests:])
    model.call(clear_all, obj, PARAM+0x9000)
    assert not model.pages and not model.requests
    assert model.vm.mem_read(base, 4) == bytes(4)
    model.call(DTOR, obj)
    assert not model.regions and not model.tracked and not model.native_regions
    checks.append('L2-off clear is a no-op on L1; full clear zeroes resident memory without any NT commit/decommit; destructor frees it')

    model = MemoryModel(args.dll)
    model.fail_allocations = True
    model.create_lookup(0)
    assert model.trapped and not model.tracked and not model.regions and not model.native_regions
    assert any('STOP lookup reserve failed bytes=0x0000000000100000' in line for line in model.logs)
    checks.append('failed lookup allocation stops explicitly before publishing a null interval')
    report = {'passed': True, 'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'checks': checks, 'lookup_bytes_per_thread': LOOKUP_BYTES,
              'enabled_lookup_bytes_per_thread': 25*MIB, 'maximum_commit_bytes': 65536,
              'scope': 'Actual ARM64 DLL routines with bounded NT/config/syscall models; not full FEX or Horizon',
              'on_device_tested': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
