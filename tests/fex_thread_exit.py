"""Check the native self-thread query and actual FEX cleanup entry gate.

The wire handler runs from the linked ELF. The FEX DLL runs its real access
check, handle duplication and TEB query; NT services are modeled. Full thread
destruction and reuse still require the four-wave test on Switch.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

from fex_reservations import Model as NativeModel, arm, reg
from fex_unwind import Model as PEModel


class WireModel(NativeModel):
    def __init__(self, path):
        super().__init__(path)
        self.locked = False
        self.reply = None
        self.writers = {a for n, a in self.symbols.items() if n.startswith('horizon_server_write_reply')}

    def hook(self, vm, pc, size, user):
        if pc == self.symbols.get('pthread_mutex_lock'):
            assert not self.locked
            self.locked = True
            self.ret()
        elif pc == self.symbols.get('pthread_mutex_unlock'):
            assert self.locked
            self.locked = False
            self.ret()
        elif pc in self.writers:
            assert not self.locked and vm.reg_read(reg(0)) == 7
            self.reply = bytes(vm.mem_read(vm.reg_read(reg(1)), 24))
            self.ret()
        elif pc == self.symbols.get('write'):
            assert not self.locked and vm.reg_read(reg(0)) == 7 and vm.reg_read(reg(2)) == 64
            wire = bytes(vm.mem_read(vm.reg_read(reg(1)), 64))
            assert wire[24:] == bytes(40)
            self.reply = wire[:24]
            self.ret(64)
        else:
            super().hook(vm, pc, size, user)

    def query(self, handle, valid=True, kind=11):
        connection, request, thread, entries = [self.data+i for i in (0x1000, 0x2000, 0x3000, 0x4000)]
        self.vm.mem_write(connection, bytes(80))
        self.vm.mem_write(connection+4, struct.pack('<I', 7))
        self.q(connection+24, thread if valid else 0)
        self.vm.mem_write(thread, struct.pack('<3I', 8, kind, 3))
        self.vm.mem_write(request, struct.pack('<4I', 248, 0, 0, handle))
        # Two handles reference the calling thread and one another object.
        for i, obj in enumerate((thread, thread+0x100, thread)):
            address = entries+i*48
            self.vm.mem_write(address, bytes(48))
            self.vm.mem_write(address, struct.pack('<I', 0x100+i*4))
            self.q(address+8, obj)
            self.q(address+16, address+48 if i != 2 else 0)
        self.q(self.symbols['horizon_server_handles'], entries)
        self.reply, self.returned = None, False
        self.vm.reg_write(arm.UC_ARM64_REG_SP, self.stack+0xf000)
        self.vm.reg_write(reg(30), self.stop)
        self.vm.reg_write(reg(0), connection)
        self.vm.reg_write(reg(1), request)
        target = next(a for n, a in self.symbols.items() if n.startswith('horizon_server_handle_get_object_info'))
        self.vm.emu_start(target, 0, count=10000)
        assert self.returned and self.reply is not None and not self.locked
        return struct.unpack('<6I', self.reply)


class ExitModel(PEModel):
    def hook(self, vm, pc, size, user):
        if pc == self.nt.get('NtQueryObject'):
            handle, kind, ptr, length = [vm.reg_read(reg(i)) for i in range(4)]
            assert handle == 0xfffffffffffffffe and kind == 0 and length == 56
            self.state['object_query'] = True
            status, _, access, refs, handles, _ = self.wire
            if not status:
                basic = bytearray(length)
                struct.pack_into('<3I', basic, 4, access, handles, refs)
                vm.mem_write(ptr, bytes(basic))
            self.ret(status)
        elif pc == self.nt.get('NtDuplicateObject'):
            assert vm.reg_read(reg(1)) == 0xfffffffffffffffe
            self.state['duplicate'] = True
            vm.mem_write(vm.reg_read(reg(3)), struct.pack('<Q', 0x124))
            self.ret()
        elif pc == self.nt.get('NtQueryInformationThread'):
            assert vm.reg_read(reg(0)) == 0x124 and vm.reg_read(reg(1)) == 0
            self.state['thread_query'] = True
            # Stop past the previously broken gate without synthesizing a live
            # FEX context/CRT heap. Their destruction is a separate device test.
            self.ret(0xc0000002)
        elif pc == self.nt.get('NtClose'):
            assert vm.reg_read(reg(0)) == 0x124
            self.state['closed'] = True
            self.ret()
        else:
            super().hook(vm, pc, size, user)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('ntdll', type=Path)
    parser.add_argument('fex', type=Path)
    parser.add_argument('wow64', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native = WireModel(args.elf)
    reply = native.query(0xfffffffe)
    assert reply == (0, 0, 0x1fffff, 3, 2, 0), reply
    for handle, valid, kind, status in ((0xfffffffe, False, 11, 0xc0000008),
                                       (0xfffffffe, True, 3, 0xc0000008),
                                       (0, True, 11, 0xc0000002),
                                       (0x100, True, 11, 0xc0000002)):
        assert native.query(handle, valid, kind) == (status, 0, 0, 0, 0, 0)
    fex = ExitModel(args.ntdll, args.fex, args.wow64)
    fex.wire = (0xc0000002, 0, 0, 0, 0, 0)
    fex.call('BTCpuThreadTerm', 0xfffffffffffffffe, 0, symbols=fex.fex)
    assert fex.state.get('object_query') and not fex.state.get('duplicate')
    fex.wire = reply
    fex.call('BTCpuThreadTerm', 0xfffffffffffffffe, 0, symbols=fex.fex)
    assert all(fex.state.get(k) for k in ('object_query', 'duplicate', 'thread_query', 'closed'))
    fex.wire = (0, 0, 0x40, 3, 2, 0)  # Valid query with no THREAD_TERMINATE.
    fex.call('BTCpuThreadTerm', 0xfffffffffffffffe, 0, symbols=fex.fex)
    assert fex.state.get('object_query') and not fex.state.get('duplicate')
    report = {'passed': True, 'native_elf_sha256': hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              'fex_sha256': hashlib.sha256(args.fex.read_bytes()).hexdigest(),
              'checks': ['Actual native self-thread wire reply reports implicit access and counted references/handles',
                         'Absent/wrong-type caller rejected; ordinary handles never receive invented access rights',
                         'Actual FEX DLL reproduces early return on unsupported object query',
                         'Native self-thread reply opens FEX cleanup path through duplication/TEB query; access denial still enforced'],
              'scope': 'Linked native wire handler + FEX entry gate; NT services modeled. Full destruction/reuse is a device test.'}
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
