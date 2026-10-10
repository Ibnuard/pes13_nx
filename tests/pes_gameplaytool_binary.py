"""Run LW4's ARM64 helper and Wine DLL-policy parser from the delivered ELF.

Environment, allocations and registry access are modeled. Wine's override
parsing, case/path matching and precedence execute unchanged; no PES gameplay
or Switch performance is simulated by this check.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from fextendo_silent import Model as Quiet
from fex_reservations import reg
from pes_low_window_binary import Buffered


class Policy(Quiet):
    def __init__(self, elf):
        super().__init__(elf)
        self.env = {}
        self.writes = []
        self.allocations = {}
        self.pool = 0x53000000
        self.vm.mem_map(self.pool, 0x100000)
        self.next = self.pool
        self.fail_setenv = False

    def alloc(self, data):
        addr = self.next
        self.next += (max(1, len(data)) + 15) & -16
        assert self.next < self.pool + 0x100000
        self.vm.mem_write(addr, data)
        self.allocations[addr] = len(data)
        return addr

    def hook(self, vm, pc, size, user):
        s = self.symbols
        x = lambda i: vm.reg_read(reg(i))
        if pc == s.get('getenv'):
            value = self.env.get(self.string(x(0)))
            self.ret(self.alloc(value.encode() + b'\0') if value is not None else 0)
        elif pc == s.get('setenv'):
            key, value, replace = self.string(x(0)), self.string(x(1)), x(2)
            if self.fail_setenv:
                self.ret(-1)
            else:
                self.writes.append((key, value, replace))
                if replace or key not in self.env: self.env[key] = value
                self.ret(0)
        elif pc in {s.get('open_hkcu_key'), s.get('NtQueryInformationToken')}:
            # open_hkcu_key may be inlined; fail its first OS query as well.
            self.ret(0xc0000034)  # No registry override in this fixture.
        elif pc == s.get('ntdll_umbstowcs'):
            raw = bytes(vm.mem_read(x(0), x(1)))
            wide = raw.decode('ascii').encode('utf-16le')
            assert len(wide) <= x(3) * 2
            vm.mem_write(x(2), wide)
            self.ret(len(raw))
        elif pc == s.get('malloc'):
            self.ret(self.alloc(bytes(x(0))))
        elif pc == s.get('realloc'):
            old, size = x(0), x(1)
            raw = bytes(vm.mem_read(old, min(self.allocations[old], size))) if old else b''
            self.ret(self.alloc(raw.ljust(size, b'\0')))
        else:
            super().hook(vm, pc, size, user)

    def order(self, name):
        raw = name.encode('utf-16le')
        ptr = self.alloc(raw + b'\0\0')
        us = self.alloc(struct.pack('<HH4xQ', len(raw), len(raw) + 2, ptr))
        return self.call('get_load_order', us)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    data = a.elf.read_bytes()
    elf = Buffered(data)
    m = Policy(elf)
    for enabled in (0, 1):
        assert m.config('kitserver_gameplaytool', enabled, 1-enabled) == enabled
    rule = 'gameplaytool,*gameplaytool='
    for before, expected in ((None, rule), ('', rule),
                             ('d3d9=n,b;dxgi=n', 'd3d9=n,b;dxgi=n;' + rule)):
        m.env = {} if before is None else {'WINEDLLOVERRIDES': before}
        m.writes.clear()
        assert m.call('pes_gameplaytool_control', 0, 0) == 1
        assert m.env['WINEDLLOVERRIDES'] == expected
        assert m.writes == [('WINEDLLOVERRIDES', expected, 1)]
    for guest, enabled in ((1, 0), (0, 1), (1, 1)):
        m.env = {'WINEDLLOVERRIDES': 'dxgi=n'}
        m.writes.clear()
        assert m.call('pes_gameplaytool_control', guest, enabled) == 1
        assert m.env == {'WINEDLLOVERRIDES': 'dxgi=n'} and not m.writes
    for value in ('x' * 4096, 'x' * 4080):
        m.env = {'WINEDLLOVERRIDES': value}
        m.writes.clear()
        assert m.call('pes_gameplaytool_control', 0, 0) == 0
        assert m.env['WINEDLLOVERRIDES'] == value and not m.writes
    m.env = {}
    m.fail_setenv = True
    assert m.call('pes_gameplaytool_control', 0, 0) == 0
    assert not m.env
    m.fail_setenv = False

    # Real Wine parser: late override replaces old basename and wildcard rules.
    m.env = {'WINEDLLOVERRIDES': 'd3d9=n,b;dxgi=n;gameplaytool=n;*gameplaytool=n'}
    assert m.call('pes_gameplaytool_control', 0, 0) == 1
    cases = ['Gameplaytool.dll', 'GAMEPLAYTOOL.DLL',
             r'\??\C:\PES13\kitserver13\Gameplaytool.dll',
             r'C:\PES13\kitserver13\gameplaytool.dll']
    results = {name: m.order(name) for name in cases}
    assert set(results.values()) == {1}, results  # LO_DISABLED
    assert m.order('d3d9.dll') == 4  # LO_NATIVE_BUILTIN
    assert m.order('dxgi.dll') == 2  # LO_NATIVE
    for name in ('kload.dll', 'kserv.dll', 'fserv.dll', 'afs2fs.dll',
                 'zlib1.dll', 'ballserv.dll', 'gameplayload.dll'):
        assert m.order(name) != 1, name

    # Restore / guest checks run in a fresh process, as documented to users.
    n = Policy(elf)
    assert n.call('pes_gameplaytool_control', 0, 1) == 1
    assert n.order('Gameplaytool.dll') != 1 and not n.writes
    report = dict(passed=True, hardware_tested=False,
                  elf_sha256=hashlib.sha256(data).hexdigest(),
                  modeled=['environment', 'heap', 'registry absent', 'ASCII to UTF16 conversion'],
                  checks=['real runtime config accepts kitserver_gameplaytool 0 and 1',
                          'real ARM64 helper preserves prior unrelated overrides',
                          'guest-test / explicit restore skip policy mutation',
                          'oversized environment and setenv failure stop safely',
                          'real Wine parser disables parent by name, case and explicit path',
                          'later disable rules replace prior basename/wildcard native rules',
                          'real Wine parser preserves other Kitserver/rendering module policies',
                          'helper/policy lookup perform no storage I/O'],
                  policy_results=results)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
