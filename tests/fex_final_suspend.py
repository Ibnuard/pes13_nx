"""Run both shipped ARM64 ntdll suspend wrappers with modeled NT results."""
from pathlib import Path
import argparse
import hashlib
import json
import struct

import pefile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm64_const as arm
from fex_alloc import coff_symbols, reg


def run(path):
    data = path.read_bytes()
    pe = pefile.PE(data=data)
    base = pe.OPTIONAL_HEADER.ImageBase
    symbols = coff_symbols(data, pe)
    symbols.update({s.name.decode(): base+s.address for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name})
    vm = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    vm.mem_map(base, (pe.OPTIONAL_HEADER.SizeOfImage+4095) & -4096)
    vm.mem_write(base, pe.get_memory_mapped_image())
    stack, teb, param, stub = 0x20000000, 0x21000000, 0x22000000, 0x23000000
    for address in (stack, teb, param, stub):
        vm.mem_map(address, 0x10000)
    vm.mem_write(teb+0x40, struct.pack('<QQ', 1234, 8))
    vm.mem_write(symbols['pWow64SuspendLocalThread'], struct.pack('<Q', stub+4))
    result = {'status': 0xc00000bb, 'delays': 0, 'suspends': 0, 'dup_failure': 0}
    by_pc = {symbols[n]: n for n in ('NtDuplicateObject', 'NtQueryInformationThread', 'NtClose', 'NtDelayExecution')}

    def ret(value):
        vm.reg_write(reg(0), value)
        vm.reg_write(arm.UC_ARM64_REG_PC, vm.reg_read(reg(30)))

    def hook(machine, pc, size, user):
        args = [machine.reg_read(reg(i)) for i in range(5)]
        if pc == stub:
            machine.emu_stop()
        elif pc == stub+4:
            assert args[0] == 42
            result['suspends'] += 1
            if result['status'] == 0 and args[1]:
                vm.mem_write(args[1], struct.pack('<I', 9))
            ret(result['status'])
        elif (name := by_pc.get(pc)):
            if name == 'NtDuplicateObject':
                assert args[1] == 42
                if not result['dup_failure']:
                    vm.mem_write(args[3], struct.pack('<Q', 99))
                ret(result['dup_failure'])
            elif name == 'NtQueryInformationThread':
                assert args[0] == 99 and args[1] == 0
                info = bytearray(48)
                struct.pack_into('<QQ', info, 16, 1234, 12)
                vm.mem_write(args[2], bytes(info))
                ret(0)
            elif name == 'NtClose':
                assert args[0] == 99
                ret(0)
            else:
                assert args[0] == 0 and struct.unpack('<q', vm.mem_read(args[1], 8))[0] == -10000
                result['delays'] += 1
                ret(0xc0000001)  # Delay's failure must not replace suspend result.

    vm.hook_add(UC_HOOK_CODE, hook)
    for status, count in ((0xc00000bb, param), (0xc0000008, param), (0, param), (0, 0)):
        result['status'] = status
        vm.mem_write(param, struct.pack('<I', 123))
        vm.reg_write(reg(0), 42)
        vm.reg_write(reg(1), count)
        vm.reg_write(reg(18), teb)
        vm.reg_write(reg(30), stub)
        vm.reg_write(arm.UC_ARM64_REG_SP, stack+0xf000)
        vm.emu_start(symbols['RtlWow64SuspendThread'], 0, count=10000)
        assert vm.reg_read(arm.UC_ARM64_REG_PC) == stub
        assert vm.reg_read(reg(0)) & 0xffffffff == status
        assert struct.unpack('<I', vm.mem_read(param, 4))[0] == (9 if status == 0 and count else 123)
        assert vm.reg_read(reg(18)) == teb
    assert result['suspends'] == 4
    return {'ntdll_sha256': hashlib.sha256(data).hexdigest(), 'calls': 4, 'injected_delays': result['delays']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('dll', type=Path)
    p.add_argument('--before', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    old, new = run(a.before), run(a.dll)
    assert old['injected_delays'] == 1 and new['injected_delays'] == 0
    report = {'passed': True, 'before': old, 'after': new,
              'ntdll_sha256': new['ntdll_sha256'],
              'scope': 'actual ARM64 RtlWow64SuspendThread; NT handle/suspend APIs modeled'}
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
