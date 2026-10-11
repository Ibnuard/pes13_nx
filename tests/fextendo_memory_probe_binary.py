"""Run the real ARM64 memory probe with modeled Horizon permission states.

The model follows the pinned Atmosphere KPageTableBase: SetProcessMemoryPermission
requires FlagCode; RW changes AliasCode into AliasCodeData. Data reprotection
requires FlagCanReprotect and SetMemoryPermission. This is not a hardware test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from as39_probe_binary import Model, PAGE
from unicorn import UC_HOOK_INTR
from unicorn.arm64_const import UC_ARM64_REG_SP, UC_ARM64_REG_X30, UC_ARM64_REG_PC, UC_ARM64_REG_X0


class ProbeModel(Model):
    def __init__(self, path, failure=None, guard=True):
        super().__init__(path, failure)
        self.vm.mem_write(self.symbols['pes_guard'], struct.pack('<Q', self.data + 0x1000 if guard else 0))
        self.vm.hook_add(UC_HOOK_INTR, self.unmodeled_svc)

    @staticmethod
    def unmodeled_svc(vm, interrupt, _):
        raise AssertionError(f'Unmodeled ARM64 exception {interrupt} at {vm.reg_read(UC_ARM64_REG_PC):x}')

    def hook(self, vm, pc, size, _):
        name = self.names.get(pc)
        if name == 'svcSetMemoryPermission':
            address, length, perm = self.reg(0), self.reg(1), self.reg(2)
            self.events.append(('data-permission', perm))
            assert self.maps[address][1] == length == PAGE
            assert perm in (0, 3)
            if self.map_states[address] != 'AliasCodeData':
                self.ret(0xd401)
                return
            if self.failure == 'none' and perm == 0 or self.failure == 'restore' and perm == 3:
                self.ret(0xd401)
                return
            vm.mem_protect(address, length, perm)
            if self.failure == 'data' and perm == 3:
                vm.mem_write(address, struct.pack('<I', 0xdeadbeef))
            self.ret()
            return
        super().hook(vm, pc, size, _)

    def roundtrip(self, target):
        self.vm.reg_write(UC_ARM64_REG_SP, self.stack + 0x1f000)
        self.vm.reg_write(UC_ARM64_REG_X30, self.stop)
        self.vm.reg_write(UC_ARM64_REG_X0, target)
        self.vm.emu_start(self.symbols['roundtrip'], self.stop, count=1_000_000)
        assert self.vm.reg_read(UC_ARM64_REG_PC) == self.stop, 'Probe did not return'
        result = self.reg(0) & 0xffffffff
        return result if result < 0x80000000 else result - (1 << 32)

    def check_cleanup(self, retained=False):
        assert bool(self.allocations) == retained and bool(self.maps) == retained
        assert not self.reservations, 'Roundtrip must borrow the permanent guest guard'
        flag = struct.unpack('<I', self.vm.mem_read(self.symbols['cleanup_failed'], 4))[0]
        assert flag == int(retained)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    before, cases = [], []
    for target in (0x200000, 0xfffff000):
        model = ProbeModel(args.before)
        assert model.roundtrip(target) == 0
        assert [e for e in model.events if e[0] == 'permission'] == [('permission', 3), ('permission', 0)]
        assert not any(e[0] == 'data-permission' for e in model.events)
        model.check_cleanup()
        before.append({'target': hex(target), 'reproduced': 'AliasCodeData rejected by SetProcessMemoryPermission(NONE)'})

    for failure, target, guard, expected in (
        (None, 0x200000, True, 1), (None, 0xfffff000, True, 1),
        ('floor', 0x200000, True, 0), ('floor', 0xfffff000, True, 1),
        ('backing', 0x200000, True, -1), ('query', 0x200000, True, -1),
        ('occupied', 0x200000, True, -1), (None, 0x200000, False, -1),
        ('map', 0x200000, True, 0), ('rw', 0x200000, True, -1),
        ('none', 0x200000, True, -1), ('restore', 0x200000, True, -1),
        ('data', 0x200000, True, -1), ('unmap', 0x200000, True, -1),
    ):
        model = ProbeModel(args.elf, failure, guard)
        actual = model.roundtrip(target)
        assert actual == expected, (failure, hex(target), actual, expected)
        model.check_cleanup(retained=failure == 'unmap')
        permissions = [e for e in model.events if 'permission' in e[0]]
        if actual == 1:
            assert permissions == [('permission', 3), ('data-permission', 0), ('data-permission', 3)]
        if failure == 'none':
            assert permissions == [('permission', 3), ('data-permission', 0)], 'Restore attempted after NONE failure'
        if failure == 'rw':
            assert permissions == [('permission', 3)], 'Reprotection attempted after initial RW failure'
        cases.append({'failure': failure, 'target': hex(target), 'guard': guard,
                      'result': actual, 'permission_calls': permissions})

    # Preserve the separate executable path: never make AliasCode writable and
    # then executable. Execute real MOV/RET instructions at low and high VAs.
    executable = []
    for failure, target, expected in ((None, 0x400000, 1), (None, 0, 1), ('floor', 0x400000, 0)):
        model = ProbeModel(args.elf, failure)
        assert model.call(target, PAGE, 1) == expected
        assert not model.maps and not model.allocations and not model.reservations
        executable.append({'failure': failure, 'target': hex(target), 'result': expected})

    report = {'passed': True, 'hardware_tested': False,
              'elf_sha256': sha(args.elf), 'baseline_elf_sha256': sha(args.before),
              'before_reproductions': before, 'roundtrip_cases': cases, 'executable_cases': executable,
              'limitations': 'Actual ARM64 probe code; modeled Horizon SVCs. Device rerun still required.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS: {len(before)} old-binary failure reproductions, {len(cases)} roundtrips, {len(executable)} RX cases')


if __name__ == '__main__':
    main()
