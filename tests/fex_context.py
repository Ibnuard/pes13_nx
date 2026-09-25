"""Execute the linked ARM64 restore trampoline under Unicorn (not Horizon).

This checks all register stores/loads and the frame delivered at SVC 0x28.
Only the on-device preflight can establish Horizon's return behavior.
Usage: python tests/fex_context.py path/to/wine-nx-runtime.elf
Requires pyelftools and unicorn in the test environment.
"""
from pathlib import Path
import argparse
import struct
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_INTR, UC_HOOK_CODE
from unicorn import arm64_const as arm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    args = parser.parse_args()
    with args.elf.open('rb') as stream:
        elf = ELFFile(stream)
        symbols = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        images = [(s['p_vaddr'], s['p_memsz'], s.data()) for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    base, address, frame = 0x1000000, 0x20000000, 0x21000000
    start = base + symbols['__libnx_exception_entry']
    trap = base + symbols['pes13_fex_restore_context']
    fallback = base + symbols['pes13_fex_exception_enter' if 'pes13_fex_exception_enter' in symbols
                               else 'pes13_libnx_exception_entry']

    def create():
        vm = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        for va, size, data in images:
            low = va & ~4095
            high = (va + size + 4095) & ~4095
            vm.mem_map(base + low, high - low)
            vm.mem_write(base + va, data)
        vm.mem_map(address, 4096)
        vm.mem_map(frame, 4096)
        return vm

    for seed in (0, 0x0123456789abcdef, 0xfedcba9876543210):
        vm = create()
        expected = [(seed ^ ((i + 1) * 0x0102030405060708)) & ((1 << 64) - 1) for i in range(31)]
        vectors = [((seed << 64) | (seed ^ i)) for i in range(32)]
        context = bytearray(0x390)
        struct.pack_into('<II31Q2Q', context, 0, 0x400007, 0xa0000000, *expected, 0x25001000, 0x18000000)
        for i, value in enumerate(vectors):
            context[272 + 16*i:288 + 16*i] = value.to_bytes(16, 'little')
        struct.pack_into('<II', context, 784, 0x00400000, 0x10)
        vm.mem_write(address, bytes(context))
        vm.mem_write(frame, struct.pack('<Q', address))
        vm.mem_write(frame + 88, struct.pack('<Q', trap))
        vm.reg_write(arm.UC_ARM64_REG_X0, 0x104)
        vm.reg_write(arm.UC_ARM64_REG_X1, frame)
        stopped = []

        def svc(machine, number, user):
            pc = machine.reg_read(arm.UC_ARM64_REG_PC)
            instruction = int.from_bytes(machine.mem_read(pc - 4, 4), 'little')
            assert instruction == 0xd4000501, hex(instruction)  # svc #0x28
            assert machine.reg_read(arm.UC_ARM64_REG_X0) == 0
            restored = bytes(machine.mem_read(frame, 100))
            assert struct.unpack_from('<9Q', restored) == tuple(expected[:9])
            assert struct.unpack_from('<3Q', restored, 72) == (expected[30], 0x25001000, 0x18000000)
            assert struct.unpack_from('<I', restored, 96)[0] == 0xa0000000
            for i in range(9, 30):
                register = getattr(arm, 'UC_ARM64_REG_X' + str(i))
                assert machine.reg_read(register) == expected[i], f'x{i}'
            for i in range(32):
                assert machine.reg_read(getattr(arm, 'UC_ARM64_REG_Q' + str(i))) == vectors[i], f'q{i}'
            assert machine.reg_read(arm.UC_ARM64_REG_FPCR) == 0x00400000
            assert machine.reg_read(arm.UC_ARM64_REG_FPSR) == 0x10
            stopped.append(True)
            machine.emu_stop()

        vm.hook_add(UC_HOOK_INTR, svc)
        vm.emu_start(start, 0, count=1500)  # FEX3 also scans the bounded exception-slot pool.
        assert stopped == [True]
    for pointer in (0, frame):
        vm = create()
        vm.reg_write(arm.UC_ARM64_REG_X0, 0x104)
        vm.reg_write(arm.UC_ARM64_REG_X1, pointer)
        for i in range(9, 31):
            vm.reg_write(getattr(arm, 'UC_ARM64_REG_X' + str(i)), 0x1000 + i)
        arrived = []

        def stop_fallback(machine, pc, size, user):
            if pc == fallback:
                assert machine.reg_read(arm.UC_ARM64_REG_X0) == 0x104
                assert machine.reg_read(arm.UC_ARM64_REG_X1) == pointer
                for i in range(9, 31):
                    assert machine.reg_read(getattr(arm, 'UC_ARM64_REG_X' + str(i))) == 0x1000 + i
                arrived.append(True)
                machine.emu_stop()

        vm.hook_add(UC_HOOK_CODE, stop_fallback)
        vm.emu_start(start, 0, count=50)
        assert arrived == [True]
    print('PASS: linked ARM64 restore (3 register patterns), frame fields, NEON/FP status, ordinary/null-frame delegation')
    print('LIMIT: Unicorn validates instructions; on-device kernel roundtrip remains required.')


if __name__ == '__main__':
    main()
