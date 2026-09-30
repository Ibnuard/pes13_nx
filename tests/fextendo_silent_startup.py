"""Reproduce production v1's lazy Wine debug crash and check the linked fix.

Runs the delivered ARM64 channel lookup and real libc stderr fstat after
installing the null device. WINEDEBUG and the absent /dev/null SD path are
modeled; this does not boot PES13 or emulate Horizon kernel scheduling.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import UcError, UC_ERR_READ_UNMAPPED, UC_HOOK_MEM_INVALID

from fextendo_silent import Model, reg, arm


class StartupModel(Model):
    def __init__(self, path):
        super().__init__(path)
        self.debug_env = None
        self.debug_queries = []
        self.faults = []
        self.vm.hook_add(UC_HOOK_MEM_INVALID, self.invalid)

    def invalid(self, vm, access, address, size, value, user):
        self.faults.append({'address': address, 'pc': vm.reg_read(arm.UC_ARM64_REG_PC)})
        return False

    def hook(self, vm, pc, size, user):
        if pc == self.symbols.get('getenv'):
            key = self.string(vm.reg_read(reg(0)))
            assert key == 'WINEDEBUG', key
            self.debug_queries.append(key)
            pointer = 0
            if self.debug_env is not None:
                pointer = self.data + 0x800
                vm.mem_write(pointer, self.debug_env.encode() + b'\0')
            self.ret(pointer)
        elif pc == self.symbols.get('stat'):
            path = self.string(vm.reg_read(reg(0)))
            assert path == '/dev/null', path
            self.debug_queries.append(path)
            self.ret(-1)  # Horizon has the custom device, no Unix /dev/null.
        else:
            super().hook(vm, pc, size, user)

    def channel(self, flags):
        self.vm.mem_write(self.data, bytes([flags]) + b'file\0'.ljust(15, b'\0'))
        return self.call('__wine_dbg_get_channel_flags', self.data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    before = StartupModel(args.before)
    before.check_stdio()
    assert before.uq(before.symbols['main_argv']) == 0
    # Control: the same channel lookup succeeds without v1's new WINEDEBUG.
    assert before.channel(0x80) == 3
    assert before.debug_queries == ['WINEDEBUG', '/dev/null']
    before.vm.mem_write(before.symbols['nb_debug_options'], struct.pack('<i', -1))
    before.debug_env = '-all'
    try:
        before.channel(0x80)
    except UcError as error:
        assert error.errno == UC_ERR_READ_UNMAPPED, error
        assert before.faults[-1]['address'] == 8, before.faults
    else:
        raise AssertionError('Expected the original production v1 startup fault')
    old_fault = before.faults[-1]

    fixed = StartupModel(args.elf)
    fixed.check_stdio()
    assert fixed.uq(fixed.symbols['main_argv']) == 0
    for env in (None, '-all', '+all', 'help'):
        fixed.debug_env = env
        for flags in (0x80, 0xff, 0x0f, 0):
            assert fixed.channel(flags) == 0, (env, flags)
            assert bytes(fixed.vm.mem_read(fixed.data, 1)) == b'\0'
    assert fixed.debug_queries == []
    assert fixed.faults == []
    report = {
        'passed': True, 'hardware_tested': False,
        'native_elf_sha256': hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        'before_native_elf_sha256': hashlib.sha256(args.before.read_bytes()).hexdigest(),
        'before_fault': old_fault,
        'checks': [
            'Production v1 succeeds without WINEDEBUG, faults at address 0x8 with -all',
            'Real libc fstat runs against the installed production stderr sink',
            'Fixed lazy and initialized channels stay disabled with null main_argv',
            'Unset/-all/+all/help environments cannot invoke the native debug parser or I/O',
        ],
    }
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
