"""Run the NRO's linked ARM64 self-suspend handler with modeled kernel waits."""
from pathlib import Path
import argparse
import hashlib
import json
import struct
from elftools.elf.elffile import ELFFile

from fex_reservations import Model as NativeModel, arm, reg


class Model(NativeModel):
    def __init__(self, path):
        super().__init__(path)
        self.locked = False
        self.conn, self.obj, self.entry, self.request = [self.data + n for n in (0x200, 0x400, 0x800, 0x900)]
        self.tls = self.data + 0x1000
        # ARM64 ELF TLS uses a 16-byte TCB. Adding another native thread-local
        # variable moves this symbol; a hardcoded old offset tests the wrong
        # connection rather than the shipping pseudo-handle lookup.
        with path.open('rb') as f:
            syms = ELFFile(f).get_section_by_name('.symtab')
            sym = syms.get_symbol_by_name('horizon_server_current')[0]
            assert sym['st_info']['type'] == 'STT_TLS' and sym['st_size'] == 8
            self.current_tls_offset = 16 + sym['st_value']
        self.steps = []
        self.reply = None
        self.waits = 0

    def w(self, address, value):
        self.vm.mem_write(address, struct.pack('<I', value & 0xffffffff))

    def uw(self, address):
        return struct.unpack('<I', self.vm.mem_read(address, 4))[0]

    def hook(self, vm, pc, size, user):
        s = self.symbols
        if pc == s.get('pthread_mutex_lock'):
            assert not self.locked and vm.reg_read(reg(0)) == s['horizon_server_objects_mutex']
            self.locked = True
            self.ret()
        elif pc == s.get('pthread_mutex_unlock'):
            assert self.locked and vm.reg_read(reg(0)) == s['horizon_server_objects_mutex']
            self.locked = False
            self.ret()
        elif pc == s.get('__aarch64_read_tp'):
            self.ret(self.tls)
        elif pc == s.get('condvarWaitTimeout'):
            assert self.locked and self.reply is None and self.steps, 'Unexpected/early reply or unbounded wait'
            assert vm.reg_read(reg(0)) == s['horizon_server_objects_cond'] + 8
            assert vm.reg_read(reg(1)) == s['horizon_server_objects_mutex'] + 4
            assert vm.reg_read(reg(2)) == 20000000
            assert self.uw(self.obj + 40 + 56) == 1  # actual published safe-point flag
            assert self.uw(s['horizon_server_sleepers']) == 1
            self.locked = False
            count, terminated = self.steps.pop(0)
            self.w(self.obj + 40 + 52, count)
            self.w(self.obj + 40 + 48, terminated)
            self.locked = True
            self.waits += 1
            self.ret()
        elif pc == s.get('write'):
            fd, pointer, length = [vm.reg_read(reg(i)) for i in range(3)]
            assert not self.locked and fd == 7 and length == 64 and not self.steps
            self.reply = bytes(vm.mem_read(pointer, length))
            self.ret(length)
        else:
            super().hook(vm, pc, size, user)

    def run(self, *, self_request=True, started=1, count=0, terminated=0, kind=11,
            handle=0x100, steps=()):
        # Private ARM64 layouts checked by observed count/flag accesses below;
        # matching values come from the pinned native source, not PE structures.
        self.vm.mem_write(self.conn, bytes(80))
        self.w(self.conn + 4, 7)
        self.w(self.conn + 16, 72 if self_request else 4)
        self.q(self.conn + 24, self.obj if self_request else self.obj + 0x200)
        self.vm.mem_write(self.obj, bytes(256))
        self.w(self.obj + 4, kind)
        self.w(self.obj + 8, 3)
        self.w(self.obj + 40, 72)
        for offset, value in ((44, started), (48, terminated), (52, count)):
            self.w(self.obj + 40 + offset, value)
        self.vm.mem_write(self.entry, bytes(40))
        self.w(self.entry, 0x100)
        self.q(self.entry + 8, self.obj)
        self.q(self.symbols['horizon_server_handle_hash'] + (0x100 >> 2) * 8, self.entry)
        self.q(self.tls + self.current_tls_offset, self.conn)
        self.vm.mem_write(self.request, struct.pack('<6I', 0, 0, 0, handle, 0, 0))
        self.steps, self.reply, self.waits = list(steps), None, 0
        self.returned = False
        self.vm.reg_write(arm.UC_ARM64_REG_SP, self.stack + 0xf000)
        self.vm.reg_write(reg(30), self.stop)
        self.vm.reg_write(reg(0), self.conn)
        self.vm.reg_write(reg(1), self.request)
        self.vm.emu_start(self.symbols['horizon_server_handle_suspend_thread'], 0, count=100000)
        assert self.returned and self.reply is not None and not self.locked
        assert self.uw(self.symbols['horizon_server_sleepers']) == 0
        assert self.uw(self.obj + 40 + 56) == 0
        status, size, previous, wait_handle = struct.unpack('<4I', self.reply[:16])
        assert size == 0 and wait_handle == 0 and self.reply[16:] == bytes(48)
        assert previous == (count if handle == 0x100 or handle == 0xfffffffe else 0)
        return status, self.uw(self.obj + 40 + 52), self.waits


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    m = Model(a.elf)
    assert m.run(steps=((1, 0), (2, 0), (1, 0), (0, 0))) == (0, 0, 4)
    assert m.run(handle=0xfffffffe, steps=((0, 0),)) == (0, 0, 1)
    assert m.run(steps=((0, 1),)) == (0xc0000022, 0, 1)
    assert m.run(self_request=False) == (0xc00000bb, 0, 0)
    assert m.run(terminated=1) == (0xc0000022, 0, 0)
    assert m.run(count=127) == (0xc000004a, 127, 0)
    assert m.run(handle=99) == (0xc0000008, 0, 0)
    assert m.run(started=0, self_request=False, count=3) == (0, 4, 0)
    result = {'passed': True, 'native_elf_sha256': hashlib.sha256(a.elf.read_bytes()).hexdigest(),
              'scenarios': 8, 'hardware_tested': False,
              'scope': 'Real linked ARM64 handler, modeled pthread/kernel waits and pipe writes',
              'checks': ['self request delays reply until count zero', 'spurious/nested waits',
                         'pseudo handle', 'termination', 'remote running refusal',
                         'overflow', 'invalid handle', 'CREATE_SUSPENDED counts']}
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
