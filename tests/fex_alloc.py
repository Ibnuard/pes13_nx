"""Run the actual ARM64 PE allocation/heap code against a bounded NT API model.

Requires pefile and Unicorn. Reproduces FEX2's first-heap crash with --before,
then checks the corrected DLL, caller constraints, failures and rpmalloc.
This checks DLL instructions and call contracts, not Horizon's VM implementation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

import pefile
from unicorn import Uc, UcError, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_INTR
from unicorn import arm64_const as arm


INVALID = 0xc000000d
NO_MEMORY = 0xc0000017
WOW_LIMIT = 0xffff0000
TEB, PEB, STACK, PARAM, STUBS = 0x20000000, 0x20100000, 0x21000000, 0x22000000, 0x23000000


def reg(index):
    return getattr(arm, f'UC_ARM64_REG_X{index}')


def coff_symbols(data, pe):
    start = pe.FILE_HEADER.PointerToSymbolTable
    count = pe.FILE_HEADER.NumberOfSymbols
    strings = start + 18 * count
    result = {}
    i = 0
    while i < count:
        name, value, section, _, _, aux = struct.unpack_from('<8sIhHBB', data, start + 18*i)
        if name[:4] == bytes(4):
            pos = strings + int.from_bytes(name[4:], 'little')
            name = data[pos:data.index(b'\0', pos)]
        else:
            name = name.rstrip(b'\0')
        if section > 0:
            result[name.decode()] = pe.OPTIONAL_HEADER.ImageBase + pe.sections[section-1].VirtualAddress + value
        i += 1 + aux
    return result


class Model:
    def __init__(self, path, *, clobber_host_x18=False):
        self.clobber_host_x18 = clobber_host_x18
        data = path.read_bytes()
        self.emitter_view_offset = 8 if b'[FEX3-EMIT] v1' in data else 0
        pe = pefile.PE(data=data)
        self.symbols = coff_symbols(data, pe)
        self.base = pe.OPTIONAL_HEADER.ImageBase
        self.vm = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.vm.mem_map(self.base, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
        self.vm.mem_write(self.base, pe.get_memory_mapped_image())
        for base, size in ((TEB, 0x4000), (PEB, 0x1000), (STACK, 0x40000),
                           (PARAM, 0x10000), (STUBS, 0x10000)):
            self.vm.mem_map(base, size)
        self.writeq(TEB + 0x60, PEB)
        self.vm.reg_write(reg(18), TEB)
        self.hooks = {}
        for dll in pe.DIRECTORY_ENTRY_IMPORT:
            for item in dll.imports:
                address = STUBS + 4 * len(self.hooks)
                self.hooks[address] = item.name.decode() if item.name else f'ordinal:{item.ordinal}'
                self.writeq(item.address, address)
        self.logger = STUBS + 0xf000
        self.alias = STUBS + 0xe000
        self.scratch_alloc = STUBS + 0xd200
        self.scratch_free = STUBS + 0xd204
        self.heap_alloc_callback = STUBS + 0xd208
        self.heap_free_callback = STUBS + 0xd20c
        self.profile_read = STUBS + 0xd210
        self.profile = 0
        self.heap_blocks = {}
        self.stop = STUBS + 0xff00
        self.logs, self.calls, self.regions = [], [], {}
        self.native_regions = {}
        self.native_next = 0x90000000
        self.next_base = 0x50000000
        self.next_tls = 1
        self.fail_allocations = False
        self.trapped = False
        self.vm.hook_add(UC_HOOK_CODE, self.hook)
        self.vm.hook_add(UC_HOOK_INTR, self.interrupt)
        callbacks = self.host_callbacks()
        if len(callbacks) == 5:
            callbacks += (self.scratch_alloc, self.scratch_free)
        assert len(callbacks) == 7
        host = struct.pack('<4I10Q', 0x46455848, 3, 96, 0, *callbacks,
                           self.heap_alloc_callback, self.heap_free_callback, self.profile_read)
        self.vm.mem_write(PARAM, host)
        if self.call('PES13FexSetHost', PARAM) == 1:
            self.abi = 3
        else:
            self.vm.mem_write(PARAM, struct.pack('<4I7Q', 0x46455848, 2, 72, 0, *callbacks))
            if self.call('PES13FexSetHost', PARAM) == 1:
                self.abi = 2
            else:
                # Historical controls used by before/after tests have ABI 1.
                self.abi = 1
                self.vm.mem_write(PARAM, struct.pack('<4I5Q', 0x46455848, 1, 56, 0,
                                                     *callbacks[:5]))
                assert self.call('PES13FexSetHost', PARAM) == 1

    def host_callbacks(self):
        return self.stop, self.stop, self.alias, self.stop, self.logger

    def host_return(self):
        if self.clobber_host_x18:
            self.vm.reg_write(reg(18), 0)
        self.vm.reg_write(arm.UC_ARM64_REG_PC, self.vm.reg_read(reg(30)))

    def readq(self, address):
        return int.from_bytes(self.vm.mem_read(address, 8), 'little')

    def writeq(self, address, value):
        self.vm.mem_write(address, struct.pack('<Q', value))

    def string(self, address):
        data = bytearray()
        while len(data) < 1024:
            byte = self.vm.mem_read(address + len(data), 1)
            if byte == b'\0':
                return data.decode()
            data.extend(byte)
        raise AssertionError('Unterminated diagnostic')

    def interrupt(self, vm, number, user):
        self.trapped = True
        vm.emu_stop()

    def call(self, name, *args):
        self.trapped = False
        for i in range(8):
            self.vm.reg_write(reg(i), args[i] if i < len(args) else 0)
        self.vm.reg_write(arm.UC_ARM64_REG_SP, STACK + 0x3f000)
        self.vm.reg_write(reg(30), self.stop)
        self.vm.emu_start(self.symbols[name], self.stop, count=500000)
        assert self.trapped or self.vm.reg_read(arm.UC_ARM64_REG_PC) == self.stop, name
        return self.vm.reg_read(reg(0))

    def allocate(self, base_pointer, size_pointer, flags, params=0, count=0):
        base, size = self.readq(base_pointer), self.readq(size_pointer)
        low, high, alignment = 0, WOW_LIMIT, 0x10000
        seen = set()
        if count and not params:
            return INVALID
        for i in range(count):
            kind, pointer = struct.unpack('<QQ', self.vm.mem_read(params + i*16, 16))
            if kind in seen:
                return INVALID
            seen.add(kind)
            if kind == 1:
                lo, hi, align = struct.unpack('<QQQ', self.vm.mem_read(pointer, 24))
                # Match this Wine revision's get_extended_params validation.
                if lo and (lo >= WOW_LIMIT or lo & 0xffff):
                    return INVALID
                if hi and (hi > WOW_LIMIT or hi <= lo or (hi+1) & 0xffe):
                    return INVALID
                if align and (align & (align-1) or align < 0x10000):
                    return INVALID
                low, high, alignment = lo, hi or WOW_LIMIT, align or 0x10000
            else:
                raise AssertionError(f'Unexpected test parameter {kind}')
        if self.fail_allocations:
            return NO_MEMORY
        size = (size + 4095) & ~4095
        if not size:
            return INVALID
        if base:
            if flags & 0x1000 and any(p <= base and base+size <= p+n for p, n in self.regions.items()):
                return 0
            return INVALID
        base = (max(self.next_base, low) + alignment-1) & ~(alignment-1)
        if base+size-1 > high:
            return NO_MEMORY
        self.vm.mem_map(base, size)
        self.regions[base] = size
        self.next_base = base + size + 0x10000
        self.writeq(base_pointer, base)
        self.writeq(size_pointer, size)
        return 0

    def hook(self, vm, pc, size, user):
        if pc == self.profile_read:
            vm.reg_write(reg(0), self.profile)
            self.host_return()
            return
        if pc == self.heap_alloc_callback:
            length, alignment = vm.reg_read(reg(0)), vm.reg_read(reg(1))
            alignment = max(alignment or 16, 16)
            length = max(length, 1)
            if self.fail_allocations or length > 0x10000000 or alignment > 0x10000000 or alignment & (alignment-1):
                vm.reg_write(reg(0), 0)
            else:
                base = (self.native_next+4095) & -4096
                address = (base+16+alignment-1) & -alignment
                total = (address-base+length+4095) & -4096
                self.native_next = base+total+4096
                vm.mem_map(base, total)
                vm.mem_write(address-16, struct.pack('<QQ', base, length))
                self.heap_blocks[address] = (base, total)
                vm.reg_write(reg(0), address)
            self.host_return()
            return
        if pc == self.heap_free_callback:
            address = vm.reg_read(reg(0))
            if address:
                base, total = self.heap_blocks.pop(address)
                vm.mem_unmap(base, total)
            self.host_return()
            return
        if pc == self.scratch_alloc:
            length = vm.reg_read(reg(0))
            if self.fail_allocations or not length or length > 0x10000000:
                vm.reg_write(reg(0), 0)
            else:
                length = (length + 4095) & ~4095
                address = (self.native_next + 4095) & ~4095
                self.native_next = address + length + 4096
                vm.mem_map(address, length)
                self.native_regions[address] = length
                vm.reg_write(reg(0), address)
            self.host_return()
            return
        if pc == self.scratch_free:
            address = vm.reg_read(reg(0))
            if address:
                vm.mem_unmap(address, self.native_regions.pop(address))
            self.host_return()
            return
        if pc == self.alias:
            # Identity alias for ordinary emitter test buffers. Dual-mapping
            # CodeMemory itself is covered by the separate FEX1 JIT tests.
            address, length = vm.reg_read(reg(0)), vm.reg_read(reg(1))
            assert length <= 0x10000
            vm.mem_read(address, length)
            self.host_return()
            return
        if pc == self.logger:
            self.logs.append(self.string(vm.reg_read(reg(0))))
            self.host_return()
            return
        if pc not in self.hooks:
            return
        name = self.hooks[pc]
        a = [vm.reg_read(reg(i)) for i in range(8)]
        self.calls.append((name, a))
        result = 0
        if name in ('memcpy', 'memmove', 'memset', 'memcmp'):
            if name == 'memset':
                vm.mem_write(a[0], bytes([a[1]&255])*a[2])
                result = a[0]
            elif name == 'memcmp':
                left, right = bytes(vm.mem_read(a[0], a[2])), bytes(vm.mem_read(a[1], a[2]))
                result = (left > right) - (left < right)
            else:
                vm.mem_write(a[0], bytes(vm.mem_read(a[1], a[2])))
                result = a[0]
        elif name == 'NtAllocateVirtualMemory':
            result = self.allocate(a[1], a[3], a[4])
        elif name == 'NtAllocateVirtualMemoryEx':
            result = self.allocate(a[1], a[2], a[3], a[5], a[6])
        elif name == 'NtFreeVirtualMemory':
            base = self.readq(a[1])
            assert a[3] in (0x4000, 0x8000)
            if a[3] == 0x8000:
                vm.mem_unmap(base, self.regions.pop(base))
                self.writeq(a[1], 0)
                self.writeq(a[2], 0)
        elif name == 'NtQuerySystemInformation':
            assert a[0] == 0 and a[2] >= 64
            info = bytearray(64)
            struct.pack_into('<7I', info, 0, 0, 156250, 4096, 0x80000, 0, 0x7ffff, 65536)
            struct.pack_into('<3Q', info, 32, 0x10000, WOW_LIMIT-1, 15)
            info[56] = 4
            vm.mem_write(a[1], bytes(info))
        elif name == 'RtlFindClearBitsAndSet':
            result = self.next_tls
            self.next_tls += 1
        elif name in ('RtlAcquirePebLock', 'RtlReleasePebLock', 'RtlClearBits', 'NtSetInformationThread'):
            pass
        elif name == 'RtlNtStatusToDosError':
            result = {INVALID: 87, NO_MEMORY: 8, 0xc0000022: 5}[a[0] & 0xffffffff]
        else:
            raise AssertionError(f'Unmodelled import {name}: {a}')
        vm.reg_write(reg(0), result)
        vm.reg_write(arm.UC_ARM64_REG_PC, vm.reg_read(reg(30)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--before', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    checks = []
    if args.before:
        old = Model(args.before)
        assert old.call('VirtualAlloc', 0, 4096, 0x102000, 4) == 0
        assert int.from_bytes(old.vm.mem_read(TEB + 0x68, 4), 'little') == 87
        try:
            old.call('rpmalloc_initialize', 0)
        except UcError:
            # RVA from the hardware log: 0xff78fcc4 - 0xff5d0000.
            assert old.vm.reg_read(arm.UC_ARM64_REG_PC) - old.base == 0x1bfcc4
            assert old.vm.reg_read(reg(20)) == 0
        else:
            raise AssertionError('Old first-heap crash was not reproduced')
        checks.append('old DLL reproduces invalid bound and exact crash RVA 0x1bfcc4')

    model = Model(args.dll)
    model.call('PES13FexAllocationPreflight')
    assert not model.trapped and not model.regions
    assert any('[FEX2-ALLOC] PASS' in line for line in model.logs)
    checks.append('pre-CRT reserve/commit/write/free and extended alignment pass')
    params, reqs = PARAM+0x100, PARAM+0x200
    model.vm.mem_write(params, struct.pack('<QQ', 1, reqs))
    for highest, alignment, expected in ((0, 0x20000, True), (0xffffffff, 0x10000, False),
                                          (0, 0x18000, False), (0, 0x1000, False)):
        model.vm.mem_write(reqs, struct.pack('<QQQ', 0, highest, alignment))
        result = model.call('VirtualAlloc2', 0, 0, 4096, 0x3000, 4, params, 1)
        assert bool(result) == expected
        if result:
            assert result % alignment == 0
            assert model.call('VirtualFree', result, 0, 0x8000)
        else:
            assert 'status=0x00000000c000000d' in model.logs[-1]
    checks.append('caller alignment preserved; invalid caller bounds/alignment still rejected')
    model.fail_allocations = True
    assert model.call('VirtualAlloc', 0, 4096, 0x3000, 4) == 0
    assert int.from_bytes(model.vm.mem_read(TEB+0x68, 4), 'little') == 8
    assert 'status=0x00000000c0000017' in model.logs[-1]
    model.call('PES13FexAllocationPreflight')
    assert model.trapped and 'STOP reserve failed before CRT' in model.logs[-1]
    checks.append('out-of-memory returns NULL/LastError and preflight stops explicitly')

    heap = Model(args.dll)
    if heap.abi < 3:
        assert heap.call('rpmalloc_initialize', 0) == 0 and not heap.trapped
    for size in (24, 4096, 1024*1024):
        pointer = heap.call('malloc', size)
        assert pointer and not heap.trapped
        heap.vm.mem_write(pointer, b'first')
        heap.vm.mem_write(pointer+size-4, b'last')
        assert heap.vm.mem_read(pointer, 5) == b'first'
        heap.call('free', pointer)
    if heap.abi < 3: heap.call('rpmalloc_thread_finalize')
    assert not heap.trapped
    checks.append('actual linked CRT allocates/frees 24 B/4 KB/1 MB through the selected heap backend')
    report = {'passed': True, 'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'checks': checks, 'scope': 'ARM64 DLL instructions with mocked NT APIs; Switch run still required'}
    if args.before:
        report['before_sha256'] = hashlib.sha256(args.before.read_bytes()).hexdigest()
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    for check in checks:
        print('PASS:', check)
    print(report['scope'])


if __name__ == '__main__':
    main()
