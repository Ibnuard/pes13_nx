"""Run the linked rpmalloc/CRT paths in a fragmented, bounded 32-bit VA model.

The two usable address ranges are conservative subsets of the ABI-fix Switch
log's largest free holes. Reservations are inaccessible until committed, and
decommit zeroes them. This exercises compiled heap logic, not Horizon services
or real simultaneous thread execution. Requires pefile and Unicorn.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

import pefile
from unicorn import UcError, UC_PROT_NONE, UC_PROT_READ, UC_PROT_WRITE
from unicorn import arm64_const as arm
from fex_alloc import reg, NO_MEMORY, TEB, PEB, PARAM
from fex_counter import CounterModel

MIB = 1024 * 1024
HOLES = ((0x3df80000, 0x54f00000), (0xe3260000, 0xff100000))


class HeapModel(CounterModel):
    def __init__(self, dll, ntdll):
        self.requests, self.reserves, self.commits = [], [], []
        self.fail_reserve = self.fail_commit = False
        self.peak_reserved = 0
        super().__init__(dll, clobber_host_x18=True)
        pe = pefile.PE(data=ntdll.read_bytes())
        self.ntbase = 0x100000000
        pe.relocate_image(self.ntbase)
        self.vm.mem_map(self.ntbase, (pe.OPTIONAL_HEADER.SizeOfImage+4095) & ~4095)
        self.vm.mem_write(self.ntbase, bytes(pe.get_memory_mapped_image()))
        self.nt_exports = {s.name.decode(): self.ntbase+s.address
                           for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name}

    def allocate(self, base_pointer, size_pointer, flags, params=0, count=0):
        base = self.readq(base_pointer)
        size = (self.readq(size_pointer)+4095) & ~4095
        self.requests.append((base, size, flags))
        if base and flags & 0x1000 and self.fail_commit:
            return NO_MEMORY
        if not base:
            if self.fail_reserve:
                return NO_MEMORY
            # The heap uses ordinary VirtualAlloc. Permit only the preflight's
            # known Ex alignment request; other validation lives in fex_alloc.
            if count:
                assert count == 1 and self.readq(params) == 1
                req = self.readq(params+8)
                assert self.readq(req) == self.readq(req+8) == 0
                assert self.readq(req+16) == 0x10000
            candidates = []
            for low, high in HOLES:
                free = [(low, high)]
                for used, length in sorted(self.regions.items()):
                    remaining = []
                    for a, b in free:
                        if used >= b or used+length <= a:
                            remaining.append((a, b))
                        else:
                            if a < used: remaining.append((a, used))
                            if used+length < b: remaining.append((used+length, b))
                    free = remaining
                for a, b in free:
                    candidate = (b-size) & ~0xffff
                    if candidate >= a:
                        candidates.append(candidate)
            if not candidates:
                return NO_MEMORY
            self.next_base = max(candidates)  # Match MEM_TOP_DOWN.
        status = super().allocate(base_pointer, size_pointer, flags, params, count)
        if status:
            return status
        address = self.readq(base_pointer)
        if not base:
            self.vm.mem_protect(address, size, UC_PROT_NONE)
            self.reserves.append((address, size))
            self.peak_reserved = max(self.peak_reserved, sum(self.regions.values()))
        if flags & 0x1000:
            self.vm.mem_protect(address, size, UC_PROT_READ | UC_PROT_WRITE)
            self.commits.append((address, size))
        return 0

    def hook(self, vm, pc, size, user):
        name = self.hooks.get(pc)
        if name in ('memcpy', 'memmove', 'memset', 'memcmp', 'strlen', 'strrchr'):
            # Execute the actual matching Wine helper, including its faults.
            vm.reg_write(arm.UC_ARM64_REG_PC, self.nt_exports[name])
            return
        if name == 'NtFreeVirtualMemory':
            a = [vm.reg_read(reg(i)) for i in range(4)]
            if a[3] == 0x4000:
                address, length = self.readq(a[1]), self.readq(a[2])
                assert any(p <= address and address+length <= p+n for p, n in self.regions.items())
                vm.mem_write(address, bytes(length))
                vm.mem_protect(address, length, UC_PROT_NONE)
        if name == 'LdrGetDllFullName':
            assert vm.reg_read(reg(0)) == 0
            descriptor = vm.reg_read(reg(1))
            data = 'C:\\fex-smoke.exe'.encode('utf-16-le')
            _, capacity = struct.unpack('<HH', vm.mem_read(descriptor, 4))
            assert capacity >= len(data)+2
            vm.mem_write(self.readq(descriptor+8), data+b'\0\0')
            vm.mem_write(descriptor, struct.pack('<H', len(data)))
            vm.reg_write(reg(0), 0)
            vm.reg_write(arm.UC_ARM64_REG_PC, vm.reg_read(reg(30)))
            return
        if name == 'RtlUnicodeStringToAnsiString':
            destination, source, allocate = [vm.reg_read(reg(i)) for i in range(3)]
            assert allocate == 1
            length = int.from_bytes(vm.mem_read(source, 2), 'little')
            data = bytes(vm.mem_read(self.readq(source+8), length)).decode('utf-16-le').encode('ascii')
            vm.mem_write(PARAM+0x8000, data+b'\0')
            vm.mem_write(destination, struct.pack('<HHIQ', len(data), len(data)+1, 0, PARAM+0x8000))
            vm.reg_write(reg(0), 0)
            vm.reg_write(arm.UC_ARM64_REG_PC, vm.reg_read(reg(30)))
            return
        if name == 'RtlFreeAnsiString':
            assert self.readq(vm.reg_read(reg(0))+8) == PARAM+0x8000
            vm.mem_write(vm.reg_read(reg(0)), bytes(16))
            vm.reg_write(arm.UC_ARM64_REG_PC, vm.reg_read(reg(30)))
            return
        return super().hook(vm, pc, size, user)

    def initialize(self):
        self.call('_ZN3FEX7Windows14InitCRTProcessEv')
        assert not self.trapped

    def check_block(self, pointer, size, pattern):
        assert pointer and pointer % 16 == 0 and not self.trapped
        assert self.call('rpmalloc_usable_size', pointer) >= size
        sample = bytes([pattern]) * min(size, 128)
        self.vm.mem_write(pointer, sample)
        self.vm.mem_write(pointer+size-len(sample), sample)
        assert bytes(self.vm.mem_read(pointer, len(sample))) == sample
        assert bytes(self.vm.mem_read(pointer+size-len(sample), len(sample))) == sample


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--ntdll', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    checks = []

    def passed(message):
        checks.append(message)
        print('PASS:', message, flush=True)

    old = HeapModel(args.before, args.ntdll)
    old.initialize()
    assert old.call('malloc', 24) == 0 and not old.trapped
    assert old.requests[-1] == (0, 512*MIB, 0x102000)
    assert 'c0000017' in old.logs[-1]
    passed('old DLL reproduces failed 512 MiB reservation for a 24-byte allocation')

    model = HeapModel(args.dll, args.ntdll)
    model.initialize()
    model.call('PES13FexHeapPreflight')
    assert not model.trapped and '[FEX2-HEAP] PASS' in model.logs[-1]
    assert max(n for _, n in model.reserves) == 64*MIB
    assert max(n for _, n in model.commits) == 32*MIB
    passed('heap preflight passes in fragmented holes: at most 64 MiB reserved per span and 32 MiB committed per page')
    model.vm.reg_write(reg(8), PARAM+0x3000)
    model.call('_ZN3FEX7Windows21GetExecutableFilePathEv')
    assert not model.trapped and model.vm.reg_read(reg(18)) == TEB
    passed('real FEX executable-path construction completes after CRT initialization')

    for index, size in enumerate((1, 16, 17, 24, 63, 64, 65, 1024, 4096, 4097,
                                 8192, 256*1024, 256*1024+1, MIB, 8*MIB, 8*MIB+1, 20*MIB)):
        pointer = model.call('malloc', size)
        model.check_block(pointer, size, index+1)
        model.call('free', pointer)
        assert not model.trapped
    passed('small/medium/large/huge class boundaries allocate, report usable size, write and free correctly')

    blocks = [model.call('malloc', 4*MIB) for _ in range(10)]
    assert len(set(blocks)) == len(blocks)
    assert len({p & ~(32*MIB-1) for p in blocks}) >= 2
    for i, p in enumerate(blocks): model.check_block(p, 4*MIB, 64+i)
    for i, p in enumerate(blocks):
        assert bytes(model.vm.mem_read(p, 128)) == bytes([64+i])*128
        model.call('free', p)
    passed('live blocks grow across multiple spans without overlap or data corruption')

    pointer = model.call('malloc', 2048)
    model.vm.mem_write(pointer, bytes(range(256))*8)
    pointer = model.call('realloc', pointer, MIB)
    assert not model.trapped and bytes(model.vm.mem_read(pointer, 2048)) == bytes(range(256))*8
    pointer = model.call('realloc', pointer, 8192)
    assert not model.trapped and bytes(model.vm.mem_read(pointer, 2048)) == bytes(range(256))*8
    model.call('free', pointer)
    for alignment in (32, 64, 4096, 65536):
        pointer = model.call('_aligned_malloc', 12345, alignment)
        assert pointer and pointer % alignment == 0
        model.check_block(pointer, 12345, 0x5a)
        model.call('_aligned_free', pointer)
    pointer = model.call('calloc', 1024, 16)
    assert pointer and bytes(model.vm.mem_read(pointer, 16384)) == bytes(16384)
    model.call('free', pointer)
    passed('realloc preserves contents across size classes; aligned allocation and calloc remain correct')

    # Deterministically interleave two TEBs. This checks cross-thread frees
    # and recycling, but is deliberately not a concurrent stress test.
    other_teb = 0x24000000
    model.vm.mem_map(other_teb, 0x4000)
    model.writeq(other_teb+0x60, PEB)
    main_block = model.call('malloc', 1024)
    model.check_block(main_block, 1024, 0x71)
    model.vm.reg_write(reg(18), other_teb)
    model.call('rpmalloc_thread_initialize')
    worker_block = model.call('malloc', 1024)
    assert worker_block != main_block
    model.check_block(worker_block, 1024, 0x72)
    model.call('free', main_block)
    model.vm.reg_write(reg(18), TEB)
    assert bytes(model.vm.mem_read(worker_block, 128)) == bytes([0x72])*128
    model.call('free', worker_block)
    model.vm.reg_write(reg(18), other_teb)
    model.call('rpmalloc_thread_finalize')
    model.vm.reg_write(reg(18), TEB)
    model.call('rpmalloc_thread_finalize')
    model.call('rpmalloc_thread_initialize')
    pointer = model.call('malloc', 1024)
    model.check_block(pointer, 1024, 0x73)
    model.call('free', pointer)
    passed('two interleaved thread heaps support cross-thread free, finalization and reuse')

    for failure in ('reserve', 'commit'):
        bad = HeapModel(args.dll, args.ntdll)
        bad.initialize()
        setattr(bad, 'fail_'+failure, True)
        bad.call('malloc', 24)
        assert bad.trapped and '[FEX2-HEAP] STOP '+failure in bad.logs[-1]
        assert bad.vm.reg_read(reg(18)) == TEB
    passed('forced reserve/commit failures stop with heap diagnostics before a null or uncommitted write')

    report = {'passed': True, 'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'before_sha256': hashlib.sha256(args.before.read_bytes()).hexdigest(),
              'ntdll_sha256': hashlib.sha256(args.ntdll.read_bytes()).hexdigest(),
              'checks': checks, 'modeled_free_holes': [[hex(a), hex(b)] for a,b in HOLES],
              'peak_reserved_bytes_in_test': model.peak_reserved,
              'scope': 'linked ARM64 heap instructions with bounded NT APIs; hardware and concurrent stress remain unverified'}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(report['scope'])


if __name__ == '__main__':
    main()
