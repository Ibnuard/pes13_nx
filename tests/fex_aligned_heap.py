"""Run the linked ARM64 rpmalloc against fragmented, bounded NT address space.

Reproduce padding-induced failure in the previous DLL, then exercise exact
aligned reservations, size-class boundaries, multiple live thread heaps,
cross-thread free and heap reuse. NT allocation/TLS services are modeled;
the allocator, size-class selection and free paths are real DLL instructions.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

from unicorn import UC_PROT_NONE, UC_PROT_READ, UC_PROT_WRITE
from unicorn import arm64_const as arm
from fex_alloc import Model, PARAM, TEB, PEB, INVALID, NO_MEMORY, reg


MIB, PAGE, SPAN = 1024*1024, 4096, 32*1024*1024


class HeapModel(Model):
    def __init__(self, path, holes):
        self.holes = holes
        self.requests = []
        self.committed = set()
        self.peak_reserved = 0
        super().__init__(path)
        self.vm.mem_map(0x20200000, 0x100000)
        self.thread(0)

    def thread(self, number):
        teb = TEB if not number else 0x20200000+number*0x4000
        self.writeq(teb+0x60, PEB)
        self.writeq(teb+0x48, number+1)
        self.vm.reg_write(reg(18), teb)

    def allocate(self, base_pointer, size_pointer, flags, params=0, count=0):
        base, size = self.readq(base_pointer), self.readq(size_pointer)
        alignment = 0x10000
        if count:
            assert count == 1
            kind, req = struct.unpack('<QQ', self.vm.mem_read(params, 16))
            assert kind == 1
            low, high, alignment = struct.unpack('<QQQ', self.vm.mem_read(req, 24))
            assert not low and not high, 'Heap must leave address bounds to Wine'
            if alignment < 0x10000 or alignment & (alignment-1):
                return INVALID
        self.requests.append((base, size, flags, alignment))
        if self.fail_allocations:
            return NO_MEMORY
        size = (size+PAGE-1) & -PAGE
        if not size:
            return INVALID
        if flags & 0x2000:
            assert not base
            candidates = []
            for begin, length in self.holes:
                for start in range((begin+alignment-1)&-alignment, begin+length-size+1, alignment):
                    if all(start+size <= p or p+amount <= start for p, amount in self.regions.items()):
                        candidates.append(start)
            if not candidates:
                return NO_MEMORY
            base = max(candidates) if flags & 0x100000 else min(candidates)
            self.vm.mem_map(base, size, UC_PROT_NONE)
            self.regions[base] = size
            self.peak_reserved = max(self.peak_reserved, sum(self.regions.values()))
        else:
            assert flags == 0x1000
            assert any(p <= base and base+size <= p+n for p, n in self.regions.items())
        if flags & 0x1000:
            self.vm.mem_protect(base, size, UC_PROT_READ | UC_PROT_WRITE)
            self.committed.update(range(base, base+size, PAGE))
        self.writeq(base_pointer, base)
        self.writeq(size_pointer, size)
        return 0

    def hook(self, vm, pc, size, user):
        if self.hooks.get(pc) == 'memset':
            dest, value, length = [vm.reg_read(reg(i)) for i in range(3)]
            assert all(p in self.committed for p in range(dest & -PAGE, dest+length, PAGE))
            vm.mem_write(dest, bytes([value & 255])*length)
            vm.reg_write(reg(0), dest)
            # A PE/NT helper preserves Wine x18. Only native host callbacks
            # may clobber it in models which enable clobber_host_x18.
            vm.reg_write(arm.UC_ARM64_REG_PC, vm.reg_read(reg(30)))
            return
        if self.hooks.get(pc) == 'NtFreeVirtualMemory':
            a = [vm.reg_read(reg(i)) for i in range(4)]
            base, length = self.readq(a[1]), self.readq(a[2])
            if a[3] == 0x8000:
                assert base in self.regions and not length, 'Release must use the real allocation base'
                length = self.regions[base]
            else:
                assert a[3] == 0x4000
                assert any(p <= base and base+length <= p+n for p, n in self.regions.items())
            self.committed.difference_update(range(base, base+length, PAGE))
            if a[3] == 0x4000:
                # Remap cleared PROT_NONE pages: reuse may not retain stale data.
                vm.mem_unmap(base, length)
                vm.mem_map(base, length, UC_PROT_NONE)
                vm.reg_write(reg(0), 0)
                vm.reg_write(arm.UC_ARM64_REG_PC, vm.reg_read(reg(30)))
                return
        super().hook(vm, pc, size, user)


def mapping(model, size, alignment):
    out = PARAM+0x500
    model.vm.mem_write(out, bytes(16))
    pointer = model.call('os_mmap', size, alignment, out, out+8)
    return pointer, model.readq(out), model.readq(out+8)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checks = []
    # Explicit synthetic Wine-usable holes, not raw kernel-free intervals:
    # the latter can include live Wine reservations or its excluded heap area.
    holes = [(0x30200000, 62*MIB), (0x34200000, 62*MIB)]
    old = HeapModel(args.before, holes)
    mapping(old, SPAN, SPAN)
    assert old.trapped and old.requests[-1][1] == 2*SPAN and not old.regions
    assert any('reserve failed bytes=0x0000000004000000' in s for s in old.logs)
    checks.append('Previous real DLL reproduces 64 MiB padding failure with usable aligned 32 MiB holes')
    new = HeapModel(args.dll, holes)
    for expected in (0x36000000, 0x32000000):
        pointer, offset, mapped = mapping(new, SPAN, SPAN)
        assert not new.trapped and (pointer, offset, mapped) == (expected, 0, SPAN)
        for edge in (pointer, pointer+SPAN-PAGE):
            assert new.call('VirtualAlloc', edge, PAGE, 0x1000, 4) == edge
            new.vm.mem_write(edge, b'edge')
    for base in list(new.regions):
        new.call('os_munmap', base, 0, SPAN)
    assert not new.regions
    checks.append('Exact aligned spans fit both holes; edge commits and original-base release pass')
    for size, alignment in ((4096, 0), (4096, 0x10000), (8*MIB+PAGE, SPAN),
                            (SPAN+PAGE, SPAN)):
        m = HeapModel(args.dll, [(0x30000000, 256*MIB)])
        pointer, offset, mapped = mapping(m, size, alignment)
        assert pointer and not m.trapped and offset == 0 and mapped == size
        assert not pointer & ((alignment or 0x10000)-1)
        assert m.regions[pointer] == size
        m.call('os_munmap', pointer, offset, mapped)
        assert not m.regions
    checks.append('Unaligned metadata, 64 KiB alignment and huge allocations reserve exact size and release correctly')
    exhausted = HeapModel(args.dll, [(0x30000000, 16*MIB)])
    mapping(exhausted, SPAN, SPAN)
    assert exhausted.trapped and not exhausted.regions
    checks.append('Genuine address exhaustion still stops before metadata or block writes')

    heap = HeapModel(args.dll, [(0x30000000, 0xc0000000)])
    config = PARAM+0x4000
    heap.vm.mem_write(config, bytes(40))
    # Enable rpmalloc's public opt-in unmap-on-finalize for the final teardown
    # check. Production normally leaves process-exit reclamation to the OS.
    heap.vm.mem_write(config+32, struct.pack('<I', 1))
    assert heap.call('rpmalloc_initialize_config', 0, config) == 0 and not heap.trapped
    heap.call('PES13FexHeapPreflight')
    assert not heap.trapped and any('[FEX3-HEAP] PASS' in s for s in heap.logs)
    # Every size class, its lower boundary and the transition to huge blocks.
    classes = heap.symbols['global_size_class']
    sizes = sorted({size for i in range(1, 117)
                    for size in (struct.unpack('<I', heap.vm.mem_read(classes+i*8, 4))[0],
                                 struct.unpack('<I', heap.vm.mem_read(classes+i*8, 4))[0]-1)
                    if size > 0} | {8*MIB+1, 32*MIB, 32*MIB+1})
    for size in sizes:
        pointer = heap.call('malloc', size)
        assert pointer and not heap.trapped, size
        heap.vm.mem_write(pointer, b'a')
        heap.vm.mem_write(pointer+size-1, b'z')
        assert heap.vm.mem_read(pointer, 1) == b'a'
        heap.call('free', pointer)
        assert not heap.trapped
    checks.append(f'{len(sizes)} size-class and huge boundaries allocate/write/free using actual rpmalloc')
    # Six game worker threads reached the old PES failure. Keep eight heaps
    # alive simultaneously; free on a different thread, then reuse all heaps.
    main_regions = sum(heap.regions.values())
    peaks = []
    for wave in range(3):
        allocations = []
        for tid in range(1, 9):
            heap.thread(tid)
            heap.call('rpmalloc_thread_initialize')
            for size in (24, 8192, 1024*1024):
                pointer = heap.call('malloc', size)
                assert pointer and not heap.trapped
                token = bytes([tid+wave])
                heap.vm.mem_write(pointer, token)
                heap.vm.mem_write(pointer+size-1, token)
                allocations.append((pointer, size, token))
        peaks.append(sum(heap.regions.values()))
        for pointer, size, token in allocations:
            assert heap.vm.mem_read(pointer, 1) == token
            assert heap.vm.mem_read(pointer+size-1, 1) == token
            heap.call('free', pointer)  # Actual cross-thread free path.
        for tid in range(1, 9):
            heap.thread(tid)
            heap.call('rpmalloc_thread_finalize')
        assert not heap.trapped
    assert peaks[0] == peaks[1] == peaks[2], peaks
    # Cached heaps are retained until process finalization, not leaked each wave.
    heap.thread(0)
    heap.call('rpmalloc_finalize')
    assert not heap.trapped and not heap.regions, (heap.trapped, heap.regions, heap.logs[-4:])
    checks.append('Eight live heaps over three waves: cross-thread frees, flat reuse and opt-in final release')
    report = {'passed': True, 'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'before_sha256': hashlib.sha256(args.before.read_bytes()).hexdigest(),
              'checks': checks, 'main_heap_reserved_bytes': main_regions, 'wave_reserved_bytes': peaks,
              'span_reserved_bytes_before': 2*SPAN, 'span_reserved_bytes_after': SPAN,
              'scope': 'Real ARM64 rpmalloc and adapter with modeled NT VM; not a Switch or PES run'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
