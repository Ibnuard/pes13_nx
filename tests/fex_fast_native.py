"""Execute the delivered ARM64 native heap and PE CRT/profile code.

Native malloc/free, NT APIs and memcpy are modeled. Real allocation arithmetic,
ownership/counters, PE callback ABI, CRT wrappers and FEX config getters run in
Unicorn. This is not a Switch performance or guest compatibility measurement.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct

from fex_counter import CounterModel
from fex_alloc import PARAM, TEB, reg
from fex_jit_native import JitModel
from unicorn import arm64_const as arm


class HeapCounterModel(CounterModel):
    def hook(self, vm, pc, size, user):
        # New linked compiler units can cause Clang to lower string-length
        # calls to the native CRT import instead of its local inline loop.
        if self.hooks.get(pc) == 'strlen':
            pointer = vm.reg_read(reg(0))
            count = 0
            while vm.mem_read(pointer + count, 1) != b'\0':
                count += 1
                assert count < 65536
            self.calls.append(('strlen', [pointer]))
            vm.reg_write(reg(0), count)
            vm.reg_write(arm.UC_ARM64_REG_PC, vm.reg_read(reg(30)))
            return
        super().hook(vm, pc, size, user)


class NativeHeapModel(JitModel):
    def __init__(self, path):
        super().__init__(path)
        self.raw = {}
        self.raw_next = 0x68000000
        self.fail_malloc = False
        self.malloc_calls = 0

    def hook(self, vm, pc, size, user):
        if pc == self.symbols.get('malloc'):
            amount = vm.reg_read(reg(0))
            self.malloc_calls += 1
            if self.fail_malloc:
                self.ret(0)
            else:
                total = (amount+4095) & -4096
                address = self.raw_next
                self.raw_next += total+4096
                vm.mem_map(address, total)
                # Force alignment arithmetic to handle a non-page-aligned malloc.
                result = address+16
                if amount+16 > total:
                    vm.mem_map(address+total, 4096)
                    total += 4096
                    self.raw_next += 4096
                self.raw[result] = (address, total, amount)
                self.ret(result)
            return
        if pc == self.symbols.get('free'):
            pointer = vm.reg_read(reg(0))
            if pointer:
                address, length, _ = self.raw.pop(pointer)
                vm.mem_unmap(address, length)
            self.ret()
            return
        super().hook(vm, pc, size, user)


def native_checks(elf):
    m = NativeHeapModel(elf)
    assert m.uq(m.host) == (3 << 32 | 0x46455848) and m.uq(m.host+8) == 96
    blocks = []
    for alignment in (0, 1, 8, 16, 32, 64, 4096, 65536):
        for size in (0, 1, 24, 4095, 8192, 1024*1024+1):
            pointer = m.callback(72, size, alignment)
            assert pointer and pointer % max(alignment, 16) == 0
            raw, usable = struct.unpack('<QQ', m.vm.mem_read(pointer-16, 16))
            assert raw in m.raw and usable == max(size, 1)
            m.vm.mem_write(pointer, b'a')
            m.vm.mem_write(pointer+usable-1, b'z')
            blocks.append((pointer, usable))
    assert m.uq(m.symbols['heap_live']) == sum(size for _, size in blocks)
    # Out-of-order frees mimic transfer to another worker without TLS ownership.
    for pointer, size in blocks[::2]+blocks[1::2]:
        assert m.vm.mem_read(pointer+size-1, 1) == b'z'
        m.callback(80, pointer)
    assert not m.raw and m.uq(m.symbols['heap_live']) == 0
    before = m.malloc_calls
    for size, align in ((1, 3), (1, 24), ((1 << 64)-1, 16), (1, 1 << 63)):
        # A huge alignment may pass arithmetic validation but malloc fails;
        # never ask the model to map an artificial exabyte region.
        m.fail_malloc = True
        assert m.callback(72, size, align) == 0
    m.callback(80, 0)
    assert m.uq(m.symbols['heap_live']) == 0
    # Exercise the actual linked startup selector, including ignored vector
    # flags in control/guest-test mode and the legacy Fastest precedence.
    for guest in (0, 1):
        for fast, fastest, vectors, expected in (
            (0, 0, 0, 0), (0, 0, 1, 0), (1, 0, 0, 1), (1, 0, 1, 3),
            (0, 1, 0, 2), (0, 1, 1, 2), (1, 1, 0, 2), (1, 1, 1, 2),
        ):
            actual = m.call(m.symbols['pes13_fex_select_performance_profile'],
                            guest, fast, fastest, vectors)
            assert actual == (0 if guest else expected), (guest, fast, fastest, vectors, actual)
    for profile in (0, 1, 2, 3, 4, 9):
        m.call(m.symbols['pes13_fex_set_performance_profile'], profile)
        assert m.callback(88) == (profile if profile <= 3 else 0)
    return ['48 native alignment/size combinations, header ownership and arbitrary free order',
            'overflow/invalid alignment/malloc failure return NULL without live-byte leak',
            '16 linked startup combinations preserve guest/control/fast/fastest/vector precedence',
            'native profile selection accepts 0/1/2/3 and rejects unknown values']


def pe_checks(dll, values):
    checks = []
    m = HeapCounterModel(dll, clobber_host_x18=True)
    assert m.abi == 3
    m.call('PES13FexHeapPreflight')
    assert not m.trapped and not m.heap_blocks and not m.regions and not m.calls
    checks.append('linked heap preflight uses no NT virtual reservations/commits')
    blocks = []
    for tid in range(32):
        m.vm.reg_write(reg(18), TEB+(tid % 4)*4096)
        for size in (24, 8192, 65536):
            p = m.call('malloc', size)
            assert p and p % 16 == 0
            m.vm.mem_write(p, bytes([tid]))
            blocks.append((p, size, tid))
    for p, _, tid in reversed(blocks):
        assert m.vm.mem_read(p, 1) == bytes([tid])
        m.call('free', p)
    assert not m.heap_blocks and not m.calls and not m.regions
    checks.append('32 worker identities allocate/free 96 live CRT blocks with zero guest-VM calls')
    m.vm.reg_write(reg(18), TEB)
    p = m.call('malloc', 128)
    m.vm.mem_write(p, bytes(range(128)))
    for size in (8192, 64, 4096):
        p = m.call('realloc', p, size)
        assert p and m.vm.mem_read(p, 64) == bytes(range(64))
    m.fail_allocations = True
    assert m.call('realloc', p, 40960) == 0
    assert m.vm.mem_read(p, 64) == bytes(range(64))
    m.fail_allocations = False
    assert m.call('realloc', p, 0) == 0 and not m.heap_blocks
    # Exercise retained capacity in the actual linked PE, including the exact
    # 1.5x bound. A forced allocator failure must not affect a no-op shrink.
    p = m.call('malloc', 150)
    m.vm.mem_write(p, bytes(range(150)))
    m.fail_allocations = True
    for size in (150, 149, 128, 100):
        assert m.call('realloc', p, size) == p
        assert m.call('PES13FexHeapUsableSize', p) == 150
        assert m.vm.mem_read(p, size) == bytes(range(size))
    assert m.call('realloc', p, 99) == 0
    assert m.vm.mem_read(p, 150) == bytes(range(150))
    m.fail_allocations = False
    smaller = m.call('realloc', p, 99)
    assert smaller and smaller != p
    assert m.call('PES13FexHeapUsableSize', smaller) == 99
    assert m.vm.mem_read(smaller, 99) == bytes(range(99))
    m.call('free', smaller)
    assert not m.heap_blocks
    checks.append('same-size and bounded shrink skip allocation/copy even under forced OOM; larger shrink releases old capacity')
    p = m.call('calloc', 17, 123)
    assert bytes(m.vm.mem_read(p, 17*123)) == bytes(17*123)
    m.call('free', p)
    assert m.call('calloc', (1 << 64)-1, 2) == 0
    p = m.call('_aligned_malloc', 12345, 65536)
    assert p and p % 65536 == 0
    assert m.call('PES13FexHeapUsableSize', p) == 12345
    m.call('_aligned_free', p)
    m.writeq(PARAM+0x400, 0x12345678)
    assert m.call('PES13FexHeapPosixAlign', PARAM+0x400, 24, 100) == 22
    assert m.readq(PARAM+0x400) == 0x12345678
    m.fail_allocations = True
    assert m.call('PES13FexHeapPosixAlign', PARAM+0x400, 64, 100) == 12
    assert m.readq(PARAM+0x400) == 0x12345678
    m.fail_allocations = False
    checks.append('realloc grow/shrink/failure preserves data; calloc overflow/zeroing; aligned and POSIX error contracts')
    # Initialize the REAL FEX config containers and read back through the same
    # typed Getter entry points consumed by Context. No mocked Set/Get calls.
    enums = re.findall(r'^OPT_\w+\s*\([^,]+,\s*(\w+),', values.read_text(), re.M)
    assert len(enums) == len(set(enums)) and 'X87REDUCEDPRECISION' in enums
    m.call('_ZN3FEX7Windows14InitCRTProcessEv')
    m.call('_ZN7FEXCore6Config10InitializeEv')
    for profile in (0, 1, 2, 3, 1, 3, 0):
        m.profile = profile
        m.call('PES13FexApplyPerformanceProfile')
        expected = {'X87REDUCEDPRECISION': int(profile != 0), 'TSOENABLED': int(profile != 2),
                    'VECTORTSOENABLED': int(profile not in (2, 3)), 'MEMCPYSETTSOENABLED': int(profile != 2), 'HALFBARRIERTSOENABLED': 1,
                    'MULTIBLOCK': 1, 'MAXINST': 5000, 'SMCCHECKS': 1}
        for name, value in expected.items():
            kind = 'i' if name == 'MAXINST' else 'h' if name == 'SMCCHECKS' else 'b'
            getter = f'_ZN7FEXCore6Config5ValueI{kind}E11GetIfExistsENS0_12ConfigOptionE{kind}'
            actual = m.call(getter, enums.index(name), 0)
            actual &= 0xffffffff if kind == 'i' else 0xff  # ARM64 narrow return ABI.
            assert actual == value, (profile, name, actual, value)
        assert not m.trapped and m.vm.reg_read(reg(18)) == TEB
    m.call('_ZN7FEXCore6Config8ShutdownEv')
    assert not any(name.startswith(('NtAllocateVirtualMemory', 'NtFreeVirtualMemory')) for name, _ in m.calls)
    checks.append('real FEX typed config getters confirm control/fast/fastest/fast-vector and restore strict vector TSO on return')
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--native-elf', type=Path, required=True)
    parser.add_argument('--config-values', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checks = native_checks(args.native_elf)+pe_checks(args.dll, args.config_values)
    report = {'passed': True, 'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'native_elf_sha256': hashlib.sha256(args.native_elf.read_bytes()).hexdigest(),
              'source_hashes': {str(p.relative_to(Path(__file__).resolve().parents[1])): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (Path(__file__).resolve(), *(Path(__file__).resolve().parent/n for n in
                                          ('fex_counter.py', 'fex_alloc.py', 'fex_jit_native.py')))},
              'checks': checks, 'scope': __doc__, 'hardware_tested': False}
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    for check in checks: print('PASS:', check)


if __name__ == '__main__':
    main()
