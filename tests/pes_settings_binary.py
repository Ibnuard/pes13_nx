"""Execute the delivered ARM64 Wine name resolver and NtCreateFile routing.

Allocation, character conversion, filesystem metadata/open and NT transport
are modeled. Alias matching and Wine disposition/error handling run from the
real ELF. This is not a full PES/Kitserver or Switch gameplay test.
"""
import argparse, hashlib, json, struct
from pathlib import Path
from fextendo_silent import Model as Quiet, reg
from pes_low_window_binary import Buffered

CANONICAL = r'\??\C:\KONAMI\Pro Evolution Soccer 2013\settings.dat'
PATCH = r'\??\C:\KONAMI\FIFA World Cup 2026 Patch\settings.dat'
ROOT = 'sdmc:/switch/pes13-fex/drive_c'
TARGET = ROOT + '/KONAMI/Pro Evolution Soccer 2013/settings.dat'


class Model(Quiet):
    def __init__(self, elf):
        super().__init__(elf)
        self.pool, self.next = 0x53000000, 0x53000000
        self.vm.mem_map(self.pool, 0x100000)
        self.allocations = {}; self.failed_alloc = False; self.paths = []; self.messages = []; self.opens = []
        self.exists = {TARGET}; self.debug = False
        self.q(self.symbols['config_dir'], self.alloc((ROOT.removesuffix('/drive_c')+'\0').encode()))

    def alloc(self, data):
        address = self.next; self.next += (max(1, len(data)) + 15) & -16
        assert self.next < self.pool + 0x100000
        self.vm.mem_write(address, data); self.allocations[address] = len(data)
        return address

    def wide(self, pointer, length):
        return bytes(self.vm.mem_read(pointer, length*2)).decode('utf-16le')

    def unicode(self, pointer):
        length, _, data = struct.unpack('<HH4xQ', self.vm.mem_read(pointer, 16))
        return self.wide(data, length // 2)

    def hook(self, vm, pc, size, user):
        s = self.symbols; x = lambda i: vm.reg_read(reg(i))
        if pc == s.get('malloc'):
            self.ret(0 if self.failed_alloc else self.alloc(bytes(x(0))))
        elif pc == s.get('calloc'):
            self.ret(0 if self.failed_alloc else self.alloc(bytes(x(0)*x(1))))
        elif pc == s.get('free'):
            if x(0): assert self.allocations.pop(x(0), None) is not None, 'Invalid/double free'
            self.ret()
        elif pc == s.get('realloc'):
            if self.failed_alloc: self.ret(0)
            else:
                raw = bytes(vm.mem_read(x(0), min(self.allocations[x(0)], x(1)))) if x(0) else b''
                if x(0): del self.allocations[x(0)]
                self.ret(self.alloc(raw.ljust(x(1), b'\0')))
        elif pc == s.get('ntdll_wcstoumbs'):
            raw = self.wide(x(0), x(1)).encode('utf-8')
            assert len(raw) <= x(3); vm.mem_write(x(2), raw); self.ret(len(raw))
        elif pc == s.get('fstatat'):
            path = self.string(x(1)); self.paths.append(path)
            if path in self.exists: self.ret(0)
            else:
                vm.mem_write(self.data + 0x1000, struct.pack('<I', 2)); self.ret(-1)
        elif pc == s.get('find_file_in_dir'):
            prefix = self.string(x(1))[:x(2)]
            path = prefix + '/' + self.wide(x(3), x(4))
            self.paths.append(path)
            if path in self.exists or any(p.startswith(path + '/') for p in self.exists):
                vm.mem_write(x(1), path.encode() + b'\0'); self.ret(0)
            else: self.ret(0xc0000034)
        elif pc == s.get('wine_nx_launch_debug_active'): self.ret(int(self.debug))
        elif pc == s.get('wine_nx_runtime_trace'):
            assert self.debug; self.messages.append(self.string(x(0))); self.ret()
        elif pc == s.get('__wine_dbg_get_channel_flags'): self.ret(0)
        elif pc == s.get('is_hidden_file.part.0'): self.ret(0)  # No hidden-file registry policy in this fixture.
        elif pc == s.get('wine_server_call'):
            # Real open_unix_file (possibly inlined) builds the server wire
            # request. Only transport/handle creation is modeled here.
            request = x(0)
            fields = struct.unpack('<8I', vm.mem_read(request, 32))
            assert fields[0] == 44 and struct.unpack('<I', vm.mem_read(request+64, 4))[0] == 2
            obj, obj_size, filename, filename_size = struct.unpack('<QI4xQI4x', vm.mem_read(request+80, 32))
            root, attributes, security_length, name_length = struct.unpack('<4I', vm.mem_read(obj, 16))
            assert root == 0 and attributes == 0x40 and security_length == 0
            assert 16 + name_length <= obj_size
            path = bytes(vm.mem_read(filename, filename_size)).decode()
            self.opens.append((path, self.wide(obj+16, name_length//2), fields[5]))
            vm.mem_write(request, struct.pack('<4I', 0, 0, 0x444, 0)); self.ret(0)
        else: super().hook(vm, pc, size, user)

    def args(self, name):
        raw = name.encode('utf-16le')
        text = self.alloc(raw + b'\0\0')
        us = self.alloc(struct.pack('<HH4xQ', len(raw), len(raw)+2, text))
        attr = self.alloc(struct.pack('<I4xQQI4xQQ', 48, 0, us, 0x40, 0, 0))
        return attr

    def resolve(self, name, disposition=1):
        attr = self.args(name); owned = self.alloc(bytes(16)); unix = self.alloc(bytes(8))
        start = set(self.allocations)
        rc = self.call('get_nt_and_unix_names', attr, owned, unix, disposition, 0) & 0xffffffff
        name_out = self.unicode(self.uq(attr+16))
        path_out = self.string(self.uq(unix)) if self.uq(unix) else None
        for address in (self.uq(owned+8), self.uq(unix)):
            if address: assert self.allocations.pop(address, None) is not None
        assert self.allocations.keys() == start, 'Resolver leaked an allocation'
        return rc, name_out, path_out


def main():
    global ROOT, TARGET
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('elf', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--edition', choices=('experimental', 'patch'), default='experimental')
    p.add_argument('--baseline', action='store_true', help='Reproduce the missing-directory failure on LW5')
    a = p.parse_args()
    if a.edition == 'patch':
        ROOT = 'sdmc:/switch/pes13-patch-fex/drive_c'
        TARGET = ROOT + '/KONAMI/Pro Evolution Soccer 2013/settings.dat'
    binary = a.elf.read_bytes(); m = Model(Buffered(binary))
    if a.baseline:
        result = m.resolve(PATCH)
        assert result == (0xc000003a, PATCH, None), result
        assert m.paths[0].endswith('/FIFA World Cup 2026 Patch/settings.dat')
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(dict(passed=True, regression_reproduced=True, hardware_tested=False,
            elf_sha256=hashlib.sha256(binary).hexdigest(), status='c000003a',
            description='LW5 reproduces the logged missing patch directory even when canonical preset exists.',
            limitations=__doc__), indent=2)+'\n')
        print('PASS control: LW5 reproduces c000003a for renamed settings with canonical preset available')
        return
    for name in (PATCH, PATCH.upper(), PATCH.replace('\\??\\', '\\DosDevices\\'),
                 PATCH.replace('C:\\', 'C:\\PES13\\'),
                 PATCH.replace('C:\\', 'C:\\users\\steamuser\\Documents\\')):
        before = len(m.paths)
        assert m.resolve(name) == (0, CANONICAL, TARGET), name
        assert m.paths[before:] == [TARGET], 'Must not scan a missing patch directory'
    assert not m.messages
    m.debug = True
    assert m.resolve(PATCH) == (0, CANONICAL, TARGET)
    assert len(m.messages) == 1 and '[LW6-SETTINGS]' in m.messages[0] and 'FIFA World Cup' in m.messages[0]
    # Existing canonical file retains ordinary FILE_CREATE collision behavior.
    assert m.resolve(PATCH, 2) == (0xc0000035, CANONICAL, None)
    for filename in ('OPTION.bin', 'EDIT.bin', 'settings.dat.old'):
        name = PATCH.replace('settings.dat', filename)
        path = ROOT + '/KONAMI/FIFA World Cup 2026 Patch/' + filename
        m.exists.add(path)
        assert m.resolve(name) == (0, name, path)
    # Original settings and other game/drive files also keep their own location.
    for name, path in ((CANONICAL, TARGET),
                       (r'\??\C:\PES13\settings.dat', ROOT+'/PES13/settings.dat'),
                       (r'\??\C:\OtherGame\KONAMI\Patch\settings.dat', ROOT+'/OtherGame/KONAMI/Patch/settings.dat')):
        m.exists.add(path); assert m.resolve(name) == (0, name, path)
    m.failed_alloc = True
    before = len(m.paths)
    assert m.resolve(PATCH) == (0xc0000017, PATCH, None)
    assert len(m.paths) == before
    m.failed_alloc = False
    # No invented success when the canonical file or directory is unavailable.
    m.exists = {ROOT + '/KONAMI/Pro Evolution Soccer 2013/other.dat'}
    assert m.resolve(PATCH) == (0xc0000034, CANONICAL, None)
    assert m.resolve(PATCH, 3) == (0xc000000f, CANONICAL, TARGET)  # FILE_OPEN_IF -> create permitted
    m.exists = set()
    assert m.resolve(PATCH) == (0xc000003a, CANONICAL, None)
    m.exists = {TARGET}
    # Execute the real public read-open/write-open API, with only the final OS
    # handle creation modeled. Both share the preset NT name and Unix file.
    for access in (0x80000000, 0x40000000):
        attr = m.args(PATCH); handle = m.alloc(bytes(8)); io = m.alloc(bytes(16))
        assert m.call('NtOpenFile', handle, access, attr, io, 3, 0) == 0
        assert m.uq(handle) == 0x444 and m.opens[-1] == (TARGET, CANONICAL, 1)
    report = dict(passed=True, hardware_tested=False, edition=a.edition, root=ROOT,
        elf_sha256=hashlib.sha256(binary).hexdigest(),
        checks=['Real Wine resolver redirects renamed KONAMI settings before failed directory lookup',
                'Case/DOS/game-local/Documents aliases return the canonical NT and Unix path',
                'Save files, original settings and unrelated game files keep their paths',
                'Allocation failure, missing file/directory and create collision retain NT errors',
                'Actual public read/write opens share the real canonical file; normal routing emits no debug log'],
        limitations=__doc__)
    a.output.parent.mkdir(parents=True, exist_ok=True); a.output.write_text(json.dumps(report, indent=2)+'\n')
    print('PASS ARM64 Wine settings path resolution, read/write opens, save isolation and NT error handling')


if __name__ == '__main__': main()
