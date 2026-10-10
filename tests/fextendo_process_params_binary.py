"""Execute the linked ARM64 startup parameter constructor, then guest chdir.

SD access and allocation are modeled; buffer sizing, UTF-16 layout, pointers
and writes execute from the delivered ELF. The x86 Wine test then exercises
the resulting capacity with the shipped ntdll's SetCurrentDirectory.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from fextendo_silent import Model as Base, reg
from fextendo_current_directory import DirectoryModel


class Model(Base):
    def __init__(self, path):
        super().__init__(path)
        self.allocations = []
        self.vm.reg_write(reg(18), self.data+0x1000)
        self.vm.mem_write(self.data+0x1040, struct.pack('<Q', 1))
        self.vm.mem_write(self.symbols['runtime_d3d9_dxvk'], struct.pack('<I', 1))
        constructors = [name for name in self.symbols
                        if name == 'runtime_create_process_params' or
                        name.startswith('runtime_create_process_params.constprop.')]
        assert len(constructors) == 1, constructors
        self.constructor = constructors[0]

    def hook(self, vm, pc, size, user):
        x = lambda i: vm.reg_read(reg(i))
        if pc in {self.symbols.get('calloc'), self.symbols.get('malloc')}:
            n = x(0)*x(1) if pc == self.symbols.get('calloc') else x(0)
            dest = self.heap_next
            self.heap_next += (n+15 & -16)+64
            assert self.heap_next < self.data+0xf000
            vm.mem_write(dest, bytes(n))
            vm.mem_write(dest+n, b'\xa5'*64)
            self.allocations.append((dest, n))
            self.ret(dest)
        elif pc == self.symbols.get('snprintf'):
            dest, capacity, fmt = x(0), x(1), self.string(x(2))
            assert all(not part or part.startswith('s') for part in fmt.split('%')[1:]), fmt
            values = [self.string(x(i+3)) for i in range(fmt.count('%s'))]
            text = (fmt % tuple(values)).encode()
            if capacity: vm.mem_write(dest, text[:capacity-1]+b'\0')
            self.ret(len(text))
        elif pc == self.symbols.get('fopen'):
            assert self.string(x(0)).endswith('/args.txt')
            self.ret(0)  # no per-launch argument override
        elif pc == self.symbols.get('read_first_line'):
            self.ret(0)
        elif pc == self.symbols.get('threadTlsGet'):
            self.ret(self.data+0x1000)  # native NtCurrentTeb / process ID
        elif pc == self.symbols.get('open_unix_file'):
            vm.mem_write(x(0), struct.pack('<Q', 0x444))
            self.ret(0)
        elif pc in {self.symbols.get('log_line'), self.symbols.get('horizon_mark_std_stream')}:
            self.ret(0)
        else:
            super().hook(vm, pc, size, user)

    def wide(self, p):
        out = bytearray()
        while self.vm.mem_read(p+len(out), 2) != b'\0\0':
            out.extend(self.vm.mem_read(p+len(out), 2))
            assert len(out) < 8192
        return out.decode('utf-16le')

    def create(self, target):
        self.vm.mem_write(self.data, (target+'\0').encode())
        p = self.call(self.constructor, self.data, self.data+0x400,
                      self.data+0x600, 640)
        assert p
        allocated = dict(self.allocations)[p]
        assert self.uq(p+0x40)  # CWD UNICODE_STRING.Buffer
        length, maximum = struct.unpack('<HH', self.vm.mem_read(p+0x38, 4))
        current, dlls = self.uq(p+0x40), self.uq(p+0x58)
        assert maximum >= 520 and dlls-current == maximum
        assert len(self.wide(current))*2 == length
        assert 'C:\\windows\\system32' in self.wide(dlls)
        image, command, environment = self.uq(p+0x68), self.uq(p+0x78), self.uq(p+0x80)
        assert self.wide(image) == target and self.wide(command) == target
        for pointer in (current, dlls, image, command, environment):
            assert p <= pointer < p+allocated
        for dest, n in self.allocations:
            assert self.vm.mem_read(dest+n, 64) == b'\xa5'*64, 'allocation size did not include reserved capacity'
        return maximum//2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path)
    p.add_argument('--dll', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    capacities = []
    for target in ['C:\\PES13\\pes2013.exe', 'C:\\'+('nested\\'*34)+'pes2013.exe',
                   'C:\\'+('nested\\'*42)+'pes2013.exe']:
        capacity = Model(a.elf).create(target)
        capacities.append(capacity)
        guest = DirectoryModel(a.dll, capacity)
        for directory in ['C:\\PES13\\kitserver13', 'C:\\PES13\\', 'C:\\'+('d'*255)]:
            guest.set_directory(directory)
            assert guest.intact()
    report = {'passed': True, 'hardware_tested': False,
              'native_elf_sha256': hashlib.sha256(a.elf.read_bytes()).hexdigest(),
              'guest_ntdll_sha256': hashlib.sha256(a.dll.read_bytes()).hexdigest(),
              'capacities_chars': capacities,
              'checks': ['Linked ARM64 constructor reserves at least MAX_PATH for CWD',
                         'Allocation includes the full reserved gap; guard bytes remain intact',
                         'DLL path, image, command and environment remain within the allocation',
                         'Initial paths exceeding MAX_PATH retain enough capacity',
                         'Shipped x86 chdir preserves the DLL path using the produced capacities'],
              'limits': 'Kernel/file services modeled; no hardware or full PES execution.'}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
