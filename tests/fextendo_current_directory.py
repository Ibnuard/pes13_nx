"""Execute the shipped x86 Wine SetCurrentDirectory implementation in Unicorn.

Filesystem syscalls and PEB locks are modeled. The directory write, restore,
Unicode string lengths and adjacent DLL-path bytes execute from ntdll.dll.
No PES or Kitserver executable code is executed.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn import x86_const as x86


class DirectoryModel:
    def __init__(self, dll, capacity):
        self.vm = Uc(UC_ARCH_X86, UC_MODE_32)
        pe = pefile.PE(str(dll))
        self.base = pe.OPTIONAL_HEADER.ImageBase
        self.vm.mem_map(self.base, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
        image = pe.get_memory_mapped_image()
        self.vm.mem_write(self.base, image)
        # Channel defaults are normally initialized by Wine startup. Disable
        # file TRACE here so diagnostics do not call uninitialized host thunks.
        channel = b'\xfffile' + b'\0'*11
        assert image.count(channel) == 1
        self.vm.mem_write(self.base+image.index(channel), b'\0')
        self.symbols = {s.name.decode(): self.base + s.address
                        for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name}
        pe.close()
        self.vm.mem_map(0, 0x1000)  # FS base is zero in this 32-bit CPU model.
        self.data = 0x10000000
        self.vm.mem_map(self.data, 0x20000)
        self.teb, self.peb, self.params = self.data, self.data+0x1000, self.data+0x2000
        self.current = self.data+0x3000
        self.dll_path = self.current+capacity*2
        self.stack, self.stop = self.data+0x10000, self.data+0x1f000
        self.dword(0x18, self.teb)
        self.dword(0x30, self.peb)
        self.dword(self.teb+0x18, self.teb)
        self.dword(self.teb+0x30, self.peb)
        self.dword(self.peb+0x10, self.params)
        cwd = 'C:\\PES13\\'
        self.vm.mem_write(self.current, (cwd+'\0').encode('utf-16le'))
        self.vm.mem_write(self.params+0x24, struct.pack('<HHI', len(cwd)*2, capacity*2, self.current))
        self.expected = ('C:\\PES13;C:\\dxvk;C:\\windows\\system32;C:\\windows;C:\\\0').encode('utf-16le')
        self.vm.mem_write(self.dll_path, self.expected)
        self.vm.mem_write(self.params+0x30, struct.pack('<HHI', len(self.expected)-2, len(self.expected), self.dll_path))
        self.vm.hook_add(UC_HOOK_CODE, self.hook)
        self.returned = False

    def dword(self, address, value):
        self.vm.mem_write(address, struct.pack('<I', value))

    def uint(self, address):
        return struct.unpack('<I', self.vm.mem_read(address, 4))[0]

    def wide(self, address):
        out = bytearray()
        while self.vm.mem_read(address+len(out), 2) != b'\0\0':
            out.extend(self.vm.mem_read(address+len(out), 2))
            assert len(out) < 8192
        return out.decode('utf-16le')

    def ret(self, value, args=0):
        sp = self.vm.reg_read(x86.UC_X86_REG_ESP)
        pc = self.uint(sp)
        self.vm.reg_write(x86.UC_X86_REG_EAX, value)
        self.vm.reg_write(x86.UC_X86_REG_ESP, sp+4+args*4)
        self.vm.reg_write(x86.UC_X86_REG_EIP, pc)

    def hook(self, vm, pc, size, _):
        sp = vm.reg_read(x86.UC_X86_REG_ESP)
        arg = lambda n: self.uint(sp+4+n*4)
        if pc == self.stop:
            self.returned = True
            vm.emu_stop()
        elif pc in (self.symbols['RtlAcquirePebLock'], self.symbols['RtlReleasePebLock']):
            self.ret(0)
        elif pc in (self.symbols['RtlDosPathNameToNtPathName_U'],
                    self.symbols['RtlDosPathNameToNtPathName_U_WithStatus']):
            path = '\\??\\'+self.wide(arg(0))
            buf = self.data+0x8000
            vm.mem_write(buf, (path+'\0\0').encode('utf-16le'))
            vm.mem_write(arg(1), struct.pack('<HHI', len(path)*2, (len(path)+2)*2, buf))
            self.ret(1 if pc == self.symbols['RtlDosPathNameToNtPathName_U'] else 0, 4)
        elif pc == self.symbols['NtOpenFile']:
            self.dword(arg(0), 0x444)
            self.ret(0, 6)
        elif pc == self.symbols['NtQueryVolumeInformationFile']:
            vm.mem_write(arg(2), struct.pack('<II', 7, 1))  # removable disk
            self.ret(0, 5)
        elif pc in (self.symbols['NtClose'], self.symbols['RtlFreeUnicodeString']):
            self.ret(0, 1)
        elif pc == self.symbols['RtlFreeHeap']:
            self.ret(1, 3)  # RtlFreeUnicodeString may be inlined by the PE compiler.
        elif pc in (self.symbols.get('__wine_dbg_get_channel_flags'), self.symbols.get('__wine_dbg_header')):
            self.ret(0)  # cdecl, TRACE disabled

    def set_directory(self, path):
        arg, buf = self.data+0x7000, self.data+0x7100
        self.vm.mem_write(buf, (path+'\0').encode('utf-16le'))
        self.vm.mem_write(arg, struct.pack('<HHI', len(path)*2, (len(path)+1)*2, buf))
        self.vm.mem_write(self.stack, struct.pack('<II', self.stop, arg))
        self.vm.reg_write(x86.UC_X86_REG_ESP, self.stack)
        self.returned = False
        self.vm.emu_start(self.symbols['RtlSetCurrentDirectory_U'], 0, count=100000)
        assert self.returned
        assert self.vm.reg_read(x86.UC_X86_REG_EAX) == 0
        assert self.wide(self.current) == path.rstrip('\\')+'\\'

    def intact(self):
        return bytes(self.vm.mem_read(self.dll_path, len(self.expected))) == self.expected


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('dll', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    old = DirectoryModel(a.dll, len('C:\\PES13\\')+1)
    old.set_directory('C:\\PES13\\kitserver13')
    assert not old.intact(), 'Baseline must reproduce adjacent DLL-path corruption'
    corrupted = old.wide(old.dll_path)
    old.set_directory('C:\\PES13\\')
    assert not old.intact(), 'Restoring CWD does not restore DLL-path bytes'
    paths = ['C:\\PES13\\kitserver13', 'C:\\PES13\\', 'C:\\',
             'C:\\PES13\\kitserver13\\GDB\\uni\\Club\\Premier League',
             'C:\\'+'d'*255]  # 259 characters after the trailing separator
    new = DirectoryModel(a.dll, 260)
    for path in paths*3:
        new.set_directory(path)
        assert new.intact(), path
    report = {'passed': True, 'hardware_tested': False,
              'guest_ntdll_sha256': hashlib.sha256(a.dll.read_bytes()).hexdigest(),
              'baseline_dll_path_after_kitserver_chdir': corrupted,
              'fixed_capacity_chars': 260, 'directory_changes': len(paths)*3,
              'checks': ['Shipped x86 RtlSetCurrentDirectory_U overwrites the short baseline CWD into DllPath',
                         'Restoring the original CWD leaves DllPath corrupted',
                         'MAX_PATH reservation preserves DLL path through Kitserver, root, deep and boundary paths'],
              'limits': 'PE CPU execution with filesystem and lock syscalls modeled; not a Switch game test.'}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
