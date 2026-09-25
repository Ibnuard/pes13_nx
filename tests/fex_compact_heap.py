"""Test the linked 8 MiB rpmalloc geometry against the previous 32 MiB DLL.

Execute ARM64 FEX allocator code and matching Wine memory helpers. NT VM/TLS
and thread interleaving are modeled; this is not hardware or PES execution.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

import pefile
from unicorn import arm64_const as arm, UcError, UC_HOOK_MEM_INVALID
from fex_aligned_heap import HeapModel, MIB, PAGE
from fex_alloc import PARAM, NO_MEMORY, reg


class CompactModel(HeapModel):
    def __init__(self, dll, ntdll, holes):
        self.fail_commit = False
        super().__init__(dll, holes)
        self.clobber_host_x18 = True
        pe = pefile.PE(data=ntdll.read_bytes())
        self.ntbase = 0x100000000
        pe.relocate_image(self.ntbase)
        self.vm.mem_map(self.ntbase, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&-PAGE)
        self.vm.mem_write(self.ntbase, bytes(pe.get_memory_mapped_image()))
        self.nt_exports = {s.name.decode(): self.ntbase+s.address
                           for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name}
        self.vm.hook_add(UC_HOOK_MEM_INVALID, self.bad_memory)

    def bad_memory(self, vm, access, address, size, value, user):
        print('MEMORY FAULT:', hex(vm.reg_read(arm.UC_ARM64_REG_PC)), hex(address), access, size,
              'x18=', hex(vm.reg_read(reg(18))), flush=True)
        return False

    def allocate(self, base_pointer, size_pointer, flags, params=0, count=0):
        if self.fail_commit and flags & 0x1000:
            return NO_MEMORY
        return super().allocate(base_pointer, size_pointer, flags, params, count)

    def hook(self, vm, pc, size, user):
        name = self.hooks.get(pc)
        if name in ('memcpy', 'memmove', 'memset', 'memcmp'):
            # Run the real Wine helper so it faults on uncommitted pages.
            vm.reg_write(arm.UC_ARM64_REG_PC, self.nt_exports[name])
            return
        super().hook(vm, pc, size, user)

    def initialize(self):
        cfg = PARAM+0x4000
        self.vm.mem_write(cfg, bytes(40))
        # Public opt-in for final teardown. No changes to production defaults.
        self.vm.mem_write(cfg+32, struct.pack('<I', 1))
        assert self.call('rpmalloc_initialize_config', 0, cfg) == 0 and not self.trapped

    def block(self, size, token):
        try:
            pointer = self.call('malloc', size)
        except UcError:
            print('Requested block size:', size, 'recent NT requests:', self.requests[-3:], flush=True)
            raise
        assert pointer and not pointer & 15 and not self.trapped, size
        assert self.call('rpmalloc_usable_size', pointer) >= size
        self.vm.mem_write(pointer, bytes([token]))
        self.vm.mem_write(pointer+size-1, bytes([token]))
        return pointer

    def finish(self):
        self.thread(0)
        self.call('rpmalloc_finalize')
        assert not self.trapped and not self.regions, (self.logs[-3:], self.regions)


def pressure(dll, ntdll, count=12):
    m = CompactModel(dll, ntdll, [(0x30000000, 0xc0000000)])
    m.initialize()
    peaks, commits = [], []
    for wave in range(3):
        blocks = []
        for tid in range(1, count+1):
            m.thread(tid)
            m.call('rpmalloc_thread_initialize')
            for size in (24, 8192, MIB):
                token = tid+wave
                blocks.append((m.block(size, token), size, token))
        peaks.append(sum(m.regions.values()))
        commits.append(len(m.committed)*PAGE)
        m.thread(0)
        for pointer, size, token in blocks:
            assert m.vm.mem_read(pointer, 1) == bytes([token])
            assert m.vm.mem_read(pointer+size-1, 1) == bytes([token])
            m.call('free', pointer)
        for tid in range(1, count+1):
            m.thread(tid)
            m.call('rpmalloc_thread_finalize')
        assert not m.trapped
    assert peaks[0] == peaks[1] == peaks[2], peaks
    assert commits[0] == commits[1] == commits[2], commits
    m.finish()
    return {'threads': count, 'wave_reserved_bytes': peaks, 'wave_committed_bytes': commits}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--ntdll', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checks = []

    def passed(message):
        checks.append(message)
        print('PASS:', message, flush=True)

    # Synthetic Wine-usable holes smaller than 32 MiB, not kernel-free ranges
    # which may overlap live uncommitted Wine views in the device log.
    holes = [(0x30400000, 28*MIB), (0x34400000, 28*MIB)]
    old = CompactModel(args.before, args.ntdll, holes)
    old.initialize()
    old.call('malloc', 24)
    assert old.trapped and old.requests[-1][1] == 32*MIB
    assert any('reserve failed bytes=0x0000000002000000' in s for s in old.logs)
    passed('Previous aligned-heap DLL stops on a 32 MiB span request in fragmented usable space')
    new = CompactModel(args.dll, args.ntdll, holes)
    new.initialize()
    new.call('PES13FexHeapPreflight')
    assert not new.trapped and any('[FEX3-HEAP] PASS' in s for s in new.logs), (new.logs, new.requests)
    assert max(size for _, size, flags, _ in new.requests if flags & 0x2000) == 8*MIB
    assert any(size == 2*MIB+PAGE and align == 8*MIB for _, size, flags, align in new.requests if flags & 0x2000)
    new.finish()
    passed('Full heap preflight fits 28 MiB holes, including pooled 2 MiB and direct 2 MiB+1 allocations')

    heap = CompactModel(args.dll, args.ntdll, [(0x30000000, 0xc0000000)])
    heap.initialize()
    table = heap.symbols['global_size_class']
    entries = [struct.unpack('<II', heap.vm.mem_read(table+i*8, 8)) for i in range(109)]
    assert entries[-1] == (2*MIB, 3)
    assert entries[72] == (4096, 15) and entries[96] == (256*1024, 3)
    assert all(blocks >= 2 for size, blocks in entries)
    # Include the removed 2..8 MiB classes from the old DLL. These requests
    # must remain valid via the direct allocation path rather than be capped.
    old_table = old.symbols['global_size_class']
    old_sizes = [struct.unpack('<I', old.vm.mem_read(old_table+i*8, 4))[0] for i in range(1, 117)]
    sizes = sorted({v for size in old_sizes for v in (size-1, size, size+1) if v > 0}
                   | {8*MIB+1, 32*MIB, 32*MIB+1})
    for index, size in enumerate(sizes):
        pointer = heap.block(size, index%200+1)
        heap.call('free', pointer)
        assert not heap.trapped
    passed(f'{len(sizes)} old/new class and huge boundaries: usable size, write and free pass; every pooled page holds multiple blocks')

    # Force maximum pooled pages full, grow over several spans, then free in
    # a different order. These paths previously broke with one-block pages.
    for size, count in ((4096, 40), (256*1024, 40), (2*MIB, 11)):
        blocks = [heap.block(size, 40+i) for i in range(count)]
        assert len(set(blocks)) == len(blocks)
        if size >= 256*1024:
            assert len({p & -(8*MIB) for p in blocks}) >= 2
        for i in list(range(0, count, 2))+list(range(1, count, 2)):
            assert heap.vm.mem_read(blocks[i]+size-1, 1) == bytes([40+i])
            heap.call('free', blocks[i])
            assert not heap.trapped
    passed('Full/available/free transitions across several pages and spans preserve all live blocks')

    pointer = heap.call('malloc', 2048)
    pattern = bytes(range(256))*8
    heap.vm.mem_write(pointer, pattern)
    for size in (MIB, 2*MIB+1, 4*MIB, MIB, 8192):
        pointer = heap.call('realloc', pointer, size)
        assert pointer and not heap.trapped and heap.vm.mem_read(pointer, 2048) == pattern
    heap.call('free', pointer)
    for alignment in (32, 64, 4096, 65536, 131072):
        for size in (12345, 2*MIB+1):
            pointer = heap.call('_aligned_malloc', size, alignment)
            assert pointer and pointer % alignment == 0 and not heap.trapped
            assert heap.call('rpmalloc_usable_size', pointer) >= size
            heap.vm.mem_write(pointer, b'a')
            heap.vm.mem_write(pointer+size-1, b'z')
            heap.call('_aligned_free', pointer)
            assert not heap.trapped
    for size in (8192, 2*MIB, 2*MIB+1):
        pointer = heap.call('calloc', 1, size)
        assert pointer and heap.vm.mem_read(pointer, size) == bytes(size) and not heap.trapped
        heap.vm.mem_write(pointer, b'\xff'*size)
        heap.call('free', pointer)
        pointer = heap.call('calloc', 1, size)
        assert pointer and heap.vm.mem_read(pointer, size) == bytes(size)
        heap.call('free', pointer)
    heap.finish()
    passed('realloc crosses pooled/direct boundaries; over-alignment and recycled calloc preserve contents/zeroing')

    before, after = pressure(args.before, args.ntdll), pressure(args.dll, args.ntdll)
    # Three pooled spans and a metadata page per worker, plus main metadata.
    metadata = 13*PAGE
    assert before['wave_reserved_bytes'][0] == 12*3*32*MIB+metadata
    assert after['wave_reserved_bytes'][0] == 12*3*8*MIB+metadata
    assert after['wave_committed_bytes'][0] < before['wave_committed_bytes'][0]/3
    passed('12 live heaps over three interleaved waves: lower reserved/committed memory, cross-thread free and flat reuse')
    for failure in ('reserve', 'commit'):
        bad = CompactModel(args.dll, args.ntdll, [(0x30000000, 256*MIB)])
        bad.initialize()
        if failure == 'reserve':
            bad.fail_allocations = True
        else:
            bad.fail_commit = True
        bad.call('malloc', 24)
        assert bad.trapped and '[FEX2-HEAP] STOP '+failure in bad.logs[-1]
    passed('True reserve/commit exhaustion still stops before invalid writes')
    report = {'passed': True, 'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'before_sha256': hashlib.sha256(args.before.read_bytes()).hexdigest(),
              'ntdll_sha256': hashlib.sha256(args.ntdll.read_bytes()).hexdigest(),
              'checks': checks, 'pressure_before': before, 'pressure_after': after,
              'span_reserved_bytes_before': 32*MIB, 'span_reserved_bytes_after': 8*MIB,
              'scope': 'Linked ARM64 allocator and Wine memory helpers; modeled NT VM/TLS and interleaving; not a Switch/PES run'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
