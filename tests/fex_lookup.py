"""Exercise the linked FEX lookup with L2 disabled and explicitly enabled.

Uses modeled NT VM, locks, time and container allocations. Cache and container
code executes from the delivered DLL; this is not a simultaneous kernel test.
"""
from pathlib import Path
import argparse
import hashlib
import json
import random
import struct

from fex_alloc import PARAM, STUBS, reg
from fex_memory import MemoryModel, MIB, PAGE, DTOR


class LookupModel(MemoryModel):
    def __init__(self, dll, *, dynamic=False, l2_enabled=False):
        self.fold_l1 = b'[FEX3-LOOKUP] v3' in dll.read_bytes()
        self.heap_base = 0x60000000
        self.heap_next = self.heap_base
        self.allocations = {}
        self.clock = 0
        super().__init__(dll, dynamic=dynamic, l2_enabled=l2_enabled)
        self.vm.mem_map(self.heap_base, 32*MIB)
        self.by_address = {value: key for key, value in self.symbols.items()}
        self.heap_hooks = {self.symbols[name]: operation for operation, names in (
            ('malloc', ('malloc', 'rpmalloc')), ('free', ('free', 'rpfree')),
            ('calloc', ('calloc', 'rpcalloc')), ('realloc', ('realloc', 'rprealloc')),
            ('aligned', ('rpaligned_alloc',)))
            for name in names}

    def method(self, part):
        names = [name for name in self.symbols if part in name]
        assert len(names) == 1, (part, names)
        return names[0]

    def heap_alloc(self, length, alignment=16):
        alignment = max(alignment, 16)
        address = (self.heap_next+alignment-1) & -alignment
        self.heap_next = address+max(length, 16)
        assert self.heap_next <= self.heap_base+32*MIB
        self.allocations[address] = length
        return address

    def hook(self, vm, pc, size, user):
        heap_name = getattr(self, 'heap_hooks', {}).get(pc)
        symbol = getattr(self, 'by_address', {}).get(pc, '')
        a = [vm.reg_read(reg(i)) for i in range(8)]
        if heap_name:
            if heap_name == 'free':
                if a[0]:
                    self.allocations.pop(a[0])
                result = 0
            else:
                length = a[0]*a[1] if heap_name == 'calloc' else a[1] if heap_name in ('realloc', 'aligned') else a[0]
                result = self.heap_alloc(length, a[0] if heap_name == 'aligned' else 16)
                if heap_name == 'realloc' and a[0]:
                    old = self.allocations.pop(a[0])
                    vm.mem_write(result, bytes(vm.mem_read(a[0], min(old, length))))
            vm.reg_write(reg(0), result)
            self.host_return()
            return
        if symbol in ('memcpy', 'memmove', 'memset'):
            data = bytes([a[1] & 255])*a[2] if symbol == 'memset' else bytes(vm.mem_read(a[1], a[2]))
            vm.mem_write(a[0], data)
            self.host_return()
            return
        if symbol == '_ZNSt3__16chrono12system_clock3nowEv':
            # Pinned libc++ uses microseconds. CRT normally installs its
            # clock function pointer; this model supplies deterministic time.
            vm.reg_write(reg(0), self.clock)
            self.host_return()
            return
        name = self.hooks.get(pc)
        if name == 'NtFreeVirtualMemory' and a[3] == 0x4000:
            # Lookup semantics use accessible zero pages, avoiding Unicorn's
            # paired-store retry on a protected page. The real decommit and
            # lazy fault path are covered with protected pages in fex_memory.
            address, length = self.readq(a[1]), self.readq(a[2])
            vm.mem_write(address, bytes(length))
            vm.reg_write(reg(0), 0)
            self.host_return()
            return
        if name in ('RtlInitializeSRWLock', 'RtlAcquireSRWLockExclusive', 'RtlReleaseSRWLockExclusive',
                    'RtlAcquireSRWLockShared', 'RtlReleaseSRWLockShared',
                    'RtlInitializeConditionVariable', 'RtlWakeConditionVariable', 'RtlWakeAllConditionVariable'):
            vm.reg_write(reg(0), 0)
            self.host_return()
            return
        if name == 'NtQuerySystemTime':
            self.writeq(a[0], self.clock)
            vm.reg_write(reg(0), 0)
            self.host_return()
            return
        super().hook(vm, pc, size, user)

    def setup(self, *, eager=True):
        self.obj = self.create_lookup(0)
        base, length = self.readq(self.obj+0x20), self.readq(self.obj+0x40)
        if eager and base in self.regions:
            assert self.call('VirtualAlloc', base, length, 0x1000, 4) == base
        self.shared, self.thread, self.frame, self.page_list = (PARAM+x for x in (0x8000, 0xa000, 0xc000, 0x9800))
        self.call('_ZN7FEXCore14GuestToHostMapC2Ev', self.shared)
        self.writeq(self.obj, self.shared)
        self.writeq(self.thread, self.frame)
        self.writeq(self.thread+0x20, self.obj)
        self.writeq(self.thread+0x40, 0)  # ThreadStats disabled.

    def add(self, guest, host):
        self.writeq(self.page_list, guest & -PAGE)
        self.call(self.method('11LookupCache15AddBlockMapping'),
                  self.obj, self.thread, guest, self.page_list, 1, host)
        assert not self.trapped

    def find(self, guest):
        result = self.call(self.method('11LookupCache9FindBlock'), self.obj, self.thread, guest)
        assert not self.trapped
        return result

    def clear_l1(self):
        base, length = self.readq(self.obj+0x30), MIB
        if base in self.native_regions:
            self.vm.mem_write(base, bytes(length))
        else:
            self.call('VirtualFree', base, length, 0x4000)
        assert not self.trapped

    def clear_l1_entry(self, guest):
        base, mask = self.readq(self.obj+0x30), self.readq(self.obj+0x38)
        self.vm.mem_write(base+self.l1_index(guest, mask)*16, bytes(16))

    def l1_index(self, guest, mask=None):
        if mask is None:
            mask = self.readq(self.obj+0x38)
        return (guest ^ (guest >> 16) if self.fold_l1 else guest) & mask

    def colliding_guest(self, guest):
        # Full tags differ but the selected L1 index is identical in both
        # historical low-address and current folded-address implementations.
        return guest ^ (0x10001 if self.fold_l1 else 0x10000)

    def invalidate(self, guest, erase=False):
        if erase:
            self.call(self.method('14GuestToHostMap5Erase'), self.shared, guest, 0)
        self.call(self.method('11LookupCache20InvalidateCacheRange'), self.obj, guest, 1)
        assert not self.trapped


def pressure(dll, target=32):
    model = MemoryModel(dll)
    live = []
    for slot in range(target):
        obj = model.create_lookup(slot)
        if model.trapped:
            assert not model.readq(obj+0x20) and len(model.tracked) == len(live)
            break
        live.append(obj)
    peak = sum(model.regions.values()) + sum(model.native_regions.values())
    result = {'live_caches': len(live), 'reserved_bytes': peak,
              'native_bytes': sum(model.native_regions.values()),
              'nt_reserved_bytes': sum(model.regions.values()), 'stopped': model.trapped}
    for obj in live:
        model.call(DTOR, obj)
    assert not model.regions and not model.tracked and not model.native_regions
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    before, after = pressure(args.before), pressure(args.dll)
    assert before['stopped'] and before['live_caches'] == 9
    assert not after['stopped'] and after['live_caches'] == 32 and after['reserved_bytes'] == 32*MIB
    checks = ['same fragmented model: old 25 MiB lookup stops at worker 10; 32 new 1 MiB caches fit and release']

    rng = random.Random(0xF3CA)
    addresses = [0x10000, 0x10001, 0x00401000, 0x10401000, 0x80401000,
                 0xfffdf000, 0xffffefff, 0xffffffff]
    addresses += [rng.randrange(0x10000, 0x100000000) for _ in range(64)]
    # Deliberate L1 collisions, including addresses on high x86 DLL pages.
    addresses += [0x00012345+i*0x10000000 for i in range(16)]
    lookups, invalidations, growth_steps = 0, 0, 0
    for enabled in (False, True):
        for dynamic in (False, True):
            model = LookupModel(args.dll, dynamic=dynamic, l2_enabled=enabled)
            model.setup()
            expected = {guest: 0x70000000+i*4096 for i, guest in enumerate(addresses)}
            for guest, host in expected.items():
                model.add(guest, host)
            for order in (addresses, list(reversed(addresses))):
                for guest in order:
                    host = expected[guest]
                    assert model.find(guest) == host
                    model.clear_l1_entry(guest)
                    assert model.find(guest) == host  # L2/L3 refill.
                    model.clear_l1_entry(guest)
                    assert model.find(guest) == host  # Warm L2 or repeated L3.
                    lookups += 3
            # Cache invalidation may refill from L3; erasing the full-address
            # map must not execute the previous compiled block.
            for guest in addresses[::3]:
                model.invalidate(guest)
                assert model.find(guest) == expected[guest]
                model.invalidate(guest, erase=True)
                assert model.find(guest) == 0
                expected[guest] += 0x100000
                model.add(guest, expected[guest])
                assert model.find(guest) == expected[guest]
                invalidations += 1
            if dynamic and enabled:
                update = model.method('20UpdateDynamicL1Stats')
                guest = addresses[0]
                for entries in (16384, 32768, 65536, 65536):
                    model.clock += 2_000_000
                    model.writeq(model.obj+0x68, 10000)
                    model.call(update, model.obj, model.thread, guest, expected[guest])
                    assert model.readq(model.obj+0x60) == entries
                    assert model.readq(model.obj+0x38) == entries-1
                    assert model.find(guest) == expected[guest]
                    growth_steps += 1
                for entries in (32768, 16384, 8192, 8192):
                    model.clock += 2_000_000
                    model.writeq(model.obj+0x68, 0)
                    model.call(update, model.obj, model.thread, guest, expected[guest])
                    assert model.readq(model.obj+0x60) == entries
                    assert model.readq(model.obj+0x38) == entries-1
                    model.clear_l1_entry(guest)
                    assert model.find(guest) == expected[guest]
                    growth_steps += 1
            clear = model.method('22ClearThreadLocalCaches')
            model.call(clear, model.obj, 0)
            assert model.readq(model.obj+0x48) == 0
            for guest, host in expected.items():
                assert model.find(guest) == host
                lookups += 1
            model.call(DTOR, model.obj)
            assert not model.tracked
    checks += [f'{lookups} linked lookups: L1 collisions, L2/L3 refill and high x86 addresses return exact host targets',
               f'{invalidations} invalidations/erasures/replacements never return stale code',
               f'{growth_steps} dynamic L1 growth/shrink/cap transitions retain targets within the 1 MiB reservation',
               'full clear rewinds backing allocation and refills from shared L3 in all four cache modes']
    report = {'passed': True, 'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'before_sha256': hashlib.sha256(args.before.read_bytes()).hexdigest(),
              'checks': checks, 'pressure_before': before, 'pressure_after': after,
              'lookup_count': lookups, 'invalidations': invalidations, 'dynamic_transitions': growth_steps,
              'scope': 'Linked ARM64 cache/container code with modeled VM, locks, container heap and time; not Switch/PES',
              'on_device_tested': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
