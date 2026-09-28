"""Execute linked FEX3 exception entries with modeled Horizon kernel frames.

Checks held/overlapping frames, nested faults, exhaustion and delayed release.
Unicorn does not emulate Horizon's kernel or simultaneous physical CPUs.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_INTR, UC_HOOK_MEM_WRITE
from unicorn import arm64_const as arm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.elf.open('rb') as stream:
        elf = ELFFile(stream)
        symbols = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        images = [(s['p_vaddr'], s['p_memsz'], s.data()) for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    base, frame = 0x1000000, 0x30000000
    stride, header, capacity = 69632, 4096, 64
    vm = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for va, size, data in images:
        lo, hi = va & ~4095, (va+size+4095) & ~4095
        vm.mem_map(base+lo, hi-lo)
        vm.mem_write(base+va, data)
    vm.mem_map(frame, 8192)
    pool = base+symbols['pes13_fex_exception_slots']
    entry = base+symbols['__libnx_exception_entry']
    private = base+symbols['pes13_fex_restore_context']
    handler = base+symbols['pes13_fex_exception_handler_entry']
    stopped = []

    def syscall(machine, interrupt, user):
        pc = machine.reg_read(arm.UC_ARM64_REG_PC)
        assert bytes(machine.mem_read(pc-4, 4)) == struct.pack('<I', 0xd4000501)
        stopped.append(machine.reg_read(arm.UC_ARM64_REG_X0))
        machine.emu_stop()
    vm.hook_add(UC_HOOK_INTR, syscall)

    def run():
        stopped.clear()
        vm.emu_start(entry, 0, count=5000)
        assert len(stopped) == 1, 'entry did not terminate in bounded instructions'
        return stopped[0]

    def incoming(seed, sp=0x31001000):
        regs = [((seed+1)*0x10000000000+i) for i in range(31)]
        vectors = [((seed+1) << 100) | i for i in range(32)]
        state = 0xa0000000
        saved = struct.pack('<9Q3Q4IQ', *regs[:9], regs[30], sp, 0x18000000+4*seed,
                            state, 0x123, 0x456, 0x92000046, 0xdead0000+seed)
        vm.mem_write(frame, saved)
        vm.reg_write(arm.UC_ARM64_REG_X0, 0x101)
        vm.reg_write(arm.UC_ARM64_REG_X1, frame)
        vm.reg_write(arm.UC_ARM64_REG_TPIDRRO_EL0, 0x38000000+seed*0x1000)
        for i in range(9, 31): vm.reg_write(getattr(arm, f'UC_ARM64_REG_X{i}'), regs[i])
        for i in range(32): vm.reg_write(getattr(arm, f'UC_ARM64_REG_Q{i}'), vectors[i])
        vm.reg_write(arm.UC_ARM64_REG_FPCR, 0x400000)
        vm.reg_write(arm.UC_ARM64_REG_FPSR, 0x10)
        return regs, vectors, saved

    held = []
    for seed in range(capacity):
        regs, vectors, saved = incoming(seed)
        prior = bytes(vm.mem_read(pool, capacity*stride))
        assert run() == 0
        slot = pool+seed*stride
        dump = bytes(vm.mem_read(slot+16, 824))
        assert struct.unpack_from('<4I', dump) == (0x101, 0x400000, 0x10, 0)
        assert struct.unpack_from('<31Q', dump, 16) == tuple(regs)
        assert struct.unpack_from('<2Q', dump, 264) == (0x31001000, 0x18000000+4*seed)
        for i, value in enumerate(vectors):
            assert int.from_bytes(dump[288+16*i:304+16*i], 'little') == value
        assert dump[800:824] == saved[96:120]
        changed = bytes(vm.mem_read(frame, 120))
        assert struct.unpack_from('<Q', changed)[0] == slot+16
        assert struct.unpack_from('<2Q', changed, 80) == (slot+stride, handler)
        assert bytes(vm.mem_read(pool, seed*stride)) == prior[:seed*stride], 'another live dump/stack overwritten'
        held.append((slot, dump, regs, vectors))
    incoming(100)
    full = bytes(vm.mem_read(pool, capacity*stride))
    assert run() == 0xf801 and bytes(vm.mem_read(pool, capacity*stride)) == full

    # Resume in reverse order. A hostile new owner overwrites the retired
    # dump and stack as soon as the release store executes. No subsequent
    # register/context load may rely on that memory.
    for seed in reversed(range(capacity)):
        slot, dump, regs, vectors = held[seed]
        address = slot+stride-2048
        context = bytearray(0x390)
        struct.pack_into('<II31Q2Q', context, 0, 0x400007, 0xa0000000,
                         *regs, 0x31001000, 0x18000000+4*seed)
        context[272:784] = dump[288:800]
        struct.pack_into('<II', context, 784, 0x400000, 0x10)
        vm.mem_write(address, bytes(context))
        vm.mem_write(frame, struct.pack('<Q', address))
        vm.mem_write(frame+80, struct.pack('<QQ', address-256, private))
        vm.reg_write(arm.UC_ARM64_REG_X0, 0x104)
        vm.reg_write(arm.UC_ARM64_REG_X1, frame)
        vm.reg_write(arm.UC_ARM64_REG_TPIDRRO_EL0, 0x38000000+seed*0x1000)
        released = []
        def poison(machine, access, target, size, value, user):
            if target == slot and size == 8 and value == 0:
                released.append(True)
                machine.mem_write(slot+16, b'\xa5'*(stride-16))
        hook = vm.hook_add(UC_HOOK_MEM_WRITE, poison)
        assert run() == 0
        vm.hook_del(hook)
        assert released == [True] and bytes(vm.mem_read(slot, 8)) == b'\0'*8
        assert bytes(vm.mem_read(frame, 72)) == struct.pack('<9Q', *regs[:9])
        assert struct.unpack('<3Q', vm.mem_read(frame+72, 24)) == (regs[30], 0x31001000, 0x18000000+seed*4)
        for i in range(9, 30): assert vm.reg_read(getattr(arm, f'UC_ARM64_REG_X{i}')) == regs[i]
        for i in range(32): assert vm.reg_read(getattr(arm, f'UC_ARM64_REG_Q{i}')) == vectors[i]
        assert vm.reg_read(arm.UC_ARM64_REG_FPCR) == 0x400000
        assert vm.reg_read(arm.UC_ARM64_REG_FPSR) == 0x10
        for other, data, _, _ in held[:seed]:
            assert bytes(vm.mem_read(other+16, 824)) == data

    # A nested exception must not reuse its outer handler's storage.
    incoming(0)
    assert run() == 0
    outer = bytes(vm.mem_read(pool, stride))
    incoming(0, pool+stride-128)
    assert run() == 0
    assert struct.unpack('<Q', vm.mem_read(frame, 8))[0] == pool+stride+16
    assert bytes(vm.mem_read(pool, stride)) == outer
    # Null frame is rejected without accessing or sharing a global dump.
    vm.reg_write(arm.UC_ARM64_REG_X1, 0)
    assert run() == 0xf801

    report = {'passed': True, 'native_elf_sha256': hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              'checks': ['64 held frames have distinct dump/stack and complete registers/status',
                         'pool exhaustion and null frame abort without corrupting live slots',
                         'release occurs after last context read; immediate reuse cannot corrupt restored registers',
                         'nested faults preserve outer storage; all completed slots reusable'],
              'scope': 'Linked ARM64 instructions and modeled kernel frames. Actual concurrent Switch run still required.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
