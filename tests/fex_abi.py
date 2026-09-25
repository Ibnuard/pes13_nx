"""Exercise the linked FEX DLL's PE/Horizon callback boundary.

Requires Unicorn, pefile and pyelftools. Deliberately clobbers volatile native
registers, and optionally executes the exact native log/printf instructions
and Wine loader prologue from the failed Switch build. NT APIs are bounded
mocks; this does not establish FEX guest execution on hardware.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

import pefile
from elftools.elf.elffile import ELFFile
from unicorn import UcError
from unicorn import arm64_const as arm
from fex_alloc import reg, TEB, PEB, PARAM, STACK, STUBS
from fex_counter import CounterModel


class AbiModel(CounterModel):
    def __init__(self, path):
        self.host_calls = []
        self.results = {'allocate': PARAM+0x6000, 'release': 1, 'flush': 1,
                        'scratch_allocate': PARAM+0x8000, 'scratch_release': 0}
        super().__init__(path, clobber_host_x18=True)

    def host_callbacks(self):
        self.native_hooks = {STUBS+0xe100: 'allocate', STUBS+0xe200: 'release',
                             STUBS+0xe300: 'flush', STUBS+0xe400: 'scratch_allocate',
                             STUBS+0xe500: 'scratch_release'}
        return (STUBS+0xe100, STUBS+0xe200, self.alias, STUBS+0xe300,
                self.logger, STUBS+0xe400, STUBS+0xe500)

    def host_return(self):
        # Native x0-x18 are volatile; x0 is the callback result. Do not let
        # mocks accidentally preserve the PE TEB, or the wrapper's arguments.
        for i in range(1, 18):
            self.vm.reg_write(reg(i), 0xbeef0000+i)
        super().host_return()

    def hook(self, vm, pc, size, user):
        if pc in getattr(self, 'native_hooks', {}):
            assert vm.reg_read(arm.UC_ARM64_REG_SP) % 16 == 0
            name = self.native_hooks[pc]
            args = [vm.reg_read(reg(i)) for i in range(2)]
            self.host_calls.append((name, args))
            vm.reg_write(reg(0), self.results[name] & ((1 << 64)-1))
            self.host_return()
            return
        return super().hook(vm, pc, size, user)


class NativeLoggerModel(AbiModel):
    def __init__(self, dll, native, ntdll, *, use_native_log=True):
        self.native = native
        self.ntdll_path = ntdll
        self.use_native_log = use_native_log
        super().__init__(dll)
        pe = pefile.PE(data=ntdll.read_bytes())
        self.ntbase = 0x100000000
        pe.relocate_image(self.ntbase)
        self.vm.mem_map(self.ntbase, (pe.OPTIONAL_HEADER.SizeOfImage+4095) & ~4095)
        self.vm.mem_write(self.ntbase, bytes(pe.get_memory_mapped_image()))
        # Match the tested runtime's disabled Wine loader trace channel; this
        # flag is normally initialized by Wine before the first PE call.
        self.vm.mem_write(self.ntbase+0xb02b8, b'\0')
        self.symbols['LdrGetDllFullName'] = next(self.ntbase+s.address for s in pe.DIRECTORY_ENTRY_EXPORT.symbols
                                                 if s.name == b'LdrGetDllFullName')
        # Exact failing instruction in the matched Wine DLL, not a substitute
        # TEB read in generated test code. Stop after that read succeeds.
        self.ntfault = self.ntbase+0x4211c
        assert bytes(self.vm.mem_read(self.ntfault, 4)) == struct.pack('<I', 0xf9403248)
        self.teb_read = False

    def host_callbacks(self):
        if not self.use_native_log:
            return super().host_callbacks()
        native_base = 0x40000000
        with self.native.open('rb') as stream:
            elf = ELFFile(stream)
            self.native_symbols = {s.name: native_base+s['st_value']
                                   for s in elf.get_section_by_name('.symtab').iter_symbols()}
            for segment in elf.iter_segments():
                if segment['p_type'] != 'PT_LOAD':
                    continue
                address, length = segment['p_vaddr'], segment['p_memsz']
                low, high = address & ~4095, (address+length+4095) & ~4095
                self.vm.mem_map(native_base+low, high-low)
                self.vm.mem_write(native_base+address, segment.data())
            # devkitA64 packs the native image's relative relocations as RELR.
            for relocation in elf.get_section_by_name('.relr.dyn').iter_relocations():
                address = native_base+relocation['r_offset']
                self.writeq(address, native_base+self.readq(address))
        self.logger = self.native_symbols['wine_nx_runtime_trace']
        self.vm.mem_write(self.native_symbols['wine_nx_console_active'], bytes(4))
        return super().host_callbacks()

    def hook(self, vm, pc, size, user):
        if self.use_native_log and pc == self.logger:
            self.logs.append(self.string(vm.reg_read(reg(0))))
            return  # Execute the real log_line -> vsnprintf -> _svfprintf_r.
        if self.use_native_log and pc == self.native_symbols['__getreent']:
            # Model only newlib's per-thread storage. Console logging is
            # disabled and the BSS log_file is null, so no SD I/O occurs.
            vm.reg_write(reg(0), PARAM+0x5000)
            vm.reg_write(arm.UC_ARM64_REG_PC, vm.reg_read(reg(30)))
            return
        if hasattr(self, 'ntfault') and pc == self.ntfault+4:
            assert vm.reg_read(reg(8)) == PEB
            self.teb_read = True
            vm.reg_write(arm.UC_ARM64_REG_PC, self.stop)
            return
        return super().hook(vm, pc, size, user)


def test_callbacks(dll, checks):
    model = AbiModel(dll)
    assert model.vm.reg_read(reg(18)) == TEB  # Includes first SetHost log.
    # Every invocation uses its incoming TEB, including a different thread
    # value; the bridge must never restore a global or cached main-thread TEB.
    for teb in (TEB, TEB+0x1000, 0x123456789abcdef0):
        model.vm.reg_write(reg(18), teb)
        model.vm.mem_write(PARAM+0x100, b'callback ABI regression\0')
        for i in range(19, 30):
            model.vm.reg_write(reg(i), 0x1234000000+i)
        expected = [model.vm.reg_read(reg(i)) for i in range(19, 30)]
        for name, args, result in (
            ('PES13FexLog', [PARAM+0x100], None),
            ('PES13FexAllocateCode', [0x8000], PARAM+0x6000),
            ('PES13FexReleaseCode', [PARAM+0x6000], 1),
            ('PES13FexWriteAlias', [PARAM+0x6000, 123], PARAM+0x6000),
            ('PES13FexFlushCode', [PARAM+0x6000, 123], None),
            ('PES13FexAllocateScratch', [16*1024*1024], PARAM+0x8000),
            ('PES13FexReleaseScratch', [PARAM+0x8000], None),
        ):
            got = model.call(name, *args)
            assert not model.trapped
            if result is not None: assert got == result, (name, got, result)
            assert model.vm.reg_read(reg(18)) == teb, name
            assert [model.vm.reg_read(reg(i)) for i in range(19, 30)] == expected, name
            assert model.vm.reg_read(arm.UC_ARM64_REG_SP) == STACK+0x3f000, name
    assert model.host_calls[-5:] == [('allocate', [0x8000, 0]), ('release', [PARAM+0x6000, 0]),
                                    ('flush', [PARAM+0x6000, 123]),
                                    ('scratch_allocate', [16*1024*1024, 0]),
                                    ('scratch_release', [PARAM+0x8000, 0])]
    checks.append('host installation and all seven callbacks preserve per-call x18, x19-x29, stack, arguments and results')
    if model.abi == 3:
        model.vm.reg_write(reg(18), TEB)
        pointer = model.call('PES13FexHeapAlloc', 123, 64)
        assert pointer and pointer % 64 == 0 and model.vm.reg_read(reg(18)) == TEB
        assert model.call('PES13FexHeapUsableSize', pointer) == 123
        model.call('PES13FexHeapFree', pointer)
        assert not model.heap_blocks and model.vm.reg_read(reg(18)) == TEB
        model.profile = 2
        assert model.call('PES13FexPerformanceProfile') == 2 and model.vm.reg_read(reg(18)) == TEB
        checks.append('ABI 3 heap allocation/free/profile callbacks preserve x18 with hostile native clobbers')
    model.results['release'] = 0
    assert model.call('PES13FexReleaseCode', PARAM+0x6000) == 0 and not model.trapped
    for callback, function, args in (
        ('allocate', 'PES13FexAllocateCode', [4096]),
        ('release', 'PES13FexReleaseCode', [PARAM+0x6000]),
        ('flush', 'PES13FexFlushCode', [PARAM+0x6000, 128]),
    ):
        bad = AbiModel(dll)
        bad.results[callback] = -1 if callback == 'release' else 0
        bad.call(function, *args)
        assert bad.trapped and '[FEX-HOST]' in bad.logs[-1]
        assert bad.vm.reg_read(reg(18)) == TEB
    checks.append('release not-owned status and allocation/release/flush failures keep their original semantics')

    # A native callback recursively logs with a DIFFERENT x18. The nested
    # boundary must restore that value, then the outer boundary restores TEB.
    code = PARAM+0x7000
    words = [0xa9bf7bfd,          # stp x29,x30,[sp,#-16]!
             0xd28acf12,          # mov x18,#0x5678
             0x58000100,          # ldr x0, literal message at +40
             0x58000130,          # ldr x16, literal PES13FexLog at +48
             0xd63f0200,          # blr x16
             0xaa1203e0,          # mov x0,x18
             0xd2800012,          # mov x18,#0
             0xa8c17bfd,          # ldp x29,x30,[sp],#16
             0xd65f03c0,          # ret
             0xd503201f]          # literal alignment
    model.vm.mem_write(code, struct.pack('<10I2Q', *words, PARAM+0x100, model.symbols['PES13FexLog']))
    model.vm.reg_write(reg(18), TEB)
    assert model.call('PES13FexCallHost', code, 0, 0) == 0x5678
    assert model.vm.reg_read(reg(18)) == TEB
    checks.append('nested host callback restores inner and outer x18 independently')

    crt = AbiModel(dll)
    crt.call('PES13FexHostPreflight')
    assert not crt.trapped and '[FEX2-ABI] PASS' in crt.logs[-1]
    crt.call('PES13FexAllocationPreflight')
    crt.call('PES13FexCounterPreflight')
    crt.call('_ZN3FEX7Windows14InitCRTProcessEv')
    assert not crt.trapped and crt.vm.reg_read(reg(18)) == TEB
    checks.append('ABI/memory/timer preflights and full linked CRT initializer pass with hostile host callbacks')


def test_native_logger(args, checks):
    old = NativeLoggerModel(args.before, args.native_elf, args.ntdll)
    old.vm.reg_write(reg(18), TEB)  # Match valid TEB at Wine -> BTCpuProcessInit.
    old.vm.mem_write(PARAM+0x100, b'[FEX2] thread handlers\0')
    old.call('PES13FexLog', PARAM+0x100)
    assert old.vm.reg_read(reg(18)) != TEB
    checks.append('old DLL loses x18 through the actual native log/printf instructions (console and SD I/O disabled)')
    # The real formatter leaves a stack temporary in x18. Later console/I/O
    # calls are not modeled here. Separately reproduce the zero value actually
    # observed on Switch using the legal native callback clobber model.
    old = NativeLoggerModel(args.before, args.native_elf, args.ntdll, use_native_log=False)
    old.vm.reg_write(reg(18), TEB)
    old.vm.mem_write(PARAM+0x100, b'[FEX2] thread handlers\0')
    old.call('PES13FexLog', PARAM+0x100)
    assert old.vm.reg_read(reg(18)) == 0
    try:
        old.call('LdrGetDllFullName', 0, PARAM+0x200)
    except UcError:
        assert old.vm.reg_read(arm.UC_ARM64_REG_PC) == old.ntfault
        assert old.vm.reg_read(reg(18)) == 0
    else:
        raise AssertionError('Old native-log -> Wine null-TEB fault was not reproduced')
    checks.append('old DLL + zero-x18 native callback reproduce the exact Wine fault RVA 0x4211c')
    fixed = NativeLoggerModel(args.dll, args.native_elf, args.ntdll)
    assert fixed.vm.reg_read(reg(18)) == TEB
    fixed.call('PES13FexHostPreflight')
    fixed.call('PES13FexAllocationPreflight')
    fixed.call('PES13FexCounterPreflight')
    fixed.call('_ZN3FEX7Windows14InitCRTProcessEv')
    fixed.vm.mem_write(PARAM+0x100, b'[FEX2] thread handlers\0')
    fixed.call('PES13FexLog', PARAM+0x100)
    fixed.call('_ZN3FEX7Windows19SetupThreadHandlersEv')
    assert fixed.vm.reg_read(reg(18)) == TEB and not fixed.trapped
    fixed.call('LdrGetDllFullName', 0, PARAM+0x200)
    assert fixed.teb_read
    checks.append('fixed DLL survives real native printf and reaches Wine TEB/PEB read after CRT/thread handlers')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--before', type=Path)
    parser.add_argument('--native-elf', type=Path)
    parser.add_argument('--ntdll', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    checks = []
    test_callbacks(args.dll, checks)
    if any((args.before, args.native_elf, args.ntdll)):
        assert all((args.before, args.native_elf, args.ntdll)), 'Native reproduction needs all three inputs'
        test_native_logger(args, checks)
    report = {'passed': True, 'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'checks': checks, 'scope': 'linked instructions and bounded API mocks; hardware retest required'}
    for key in ('before', 'native_elf', 'ntdll'):
        path = getattr(args, key)
        if path: report[key+'_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n')
    for check in checks: print('PASS:', check)
    print(report['scope'])


if __name__ == '__main__':
    main()
