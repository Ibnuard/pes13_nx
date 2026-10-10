"""Run actual ARM64 section create/map/unmap across modeled VA holes.

Allocator, OS mappings and address selection are modeled. Wine's section
metadata, anchor splitting, error conversion, aliases and teardown execute
from the shipped ELF. Real shared-byte semantics are tested by the host suite.
"""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import struct
from fextendo_page_store_binary import Model as Base, reg

SIZE = 0x4580000


class Model(Base):
    def __init__(self, path):
        super().__init__(path, limit=SIZE*2)
        self.holes = [(0x30000000+i*0x4000000, 0x32000000+i*0x4000000) for i in range(8)]
        self.searches = []
        self.aliases = {}
        self.serial = 0
        self.fail_alias = 0
        self.alias_calls = 0
        self.fail_reservation = False

    def hook(self, vm, pc, size, user):
        x = lambda i: vm.reg_read(reg(i))
        name = self.names.get(pc, '')
        if name == 'virtmemFindCodeMemory':
            n, guard = x(0), x(1)
            self.searches.append(n)
            for lo, hi in self.holes:
                at = lo+guard
                for a, length in sorted(self.reservations.values()):
                    if a+length+guard <= at: continue
                    if at+n+guard <= a: break
                    at = max(at, a+length+guard)
                if at+n+guard <= hi:
                    self.ret(at)
                    return
            self.ret(0)
        elif name == 'virtmemAddReservation':
            if self.fail_reservation:
                self.ret(0)
            else:
                self.serial += 1
                token = self.data+0x6000+self.serial*32
                assert token < self.data+0xf000
                self.reservations[token] = (x(0), x(1))
                self.ret(token)
        elif name == 'svcMapProcessMemory':
            dst, src, n = x(0), x(2), x(3)
            self.alias_calls += 1
            if self.alias_calls == self.fail_alias:
                self.ret(0xd401)
            else:
                assert x(1) == 42
                assert any(a <= src and src+n <= a+length for a, (_, length) in self.maps.items())
                assert not any(dst < a+length and a < dst+n for a, (_, length) in self.aliases.items())
                self.aliases[dst] = (src, n)
                self.ret()
        elif name == 'svcUnmapProcessMemory':
            dst, src, n = x(0), x(2), x(3)
            assert x(1) == 42 and self.aliases.pop(dst) == (src, n)
            self.ret()
        elif name in ('snprintf', 'wine_nx_transition_event'):
            self.ret()  # Diagnostics do not affect allocation/ownership.
        else:
            super().hook(vm, pc, size, user)

    def create(self):
        self.vm.mem_write(self.data+0x1000, struct.pack('<3I3IQII',
                         0, 0, 16, 0x1f000f, 0x08000000, 0, SIZE, 0, 0))
        self.vm.mem_write(self.data+0x1100, struct.pack('<3I', 32, 33, 34))
        self.call('horizon_server_handle_create_mapping', self.data+0x1100, self.data+0x1000, 0, 0)
        assert len(self.reply) == 64 and struct.unpack_from('<I', self.reply)[0] == 0
        self.section_pointer = self.uq(self.desc_data)
        assert self.section_pointer
        assert SIZE in self.allocations.values()

    def map(self, address=0x60000000):
        return self.call('horizon_mmap', address, SIZE, 3, 1, 15, 0)

    def dispose(self):
        self.call('horizon_memfile_unref', self.section_pointer)
        assert not self.maps and not self.aliases and not self.reservations
        # The native mapping object pool retains its small reusable arena.
        assert not any(n >= SIZE for n in self.allocations.values())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path)
    p.add_argument('--before', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    results = []
    for path in (a.before, a.elf):
        old = path == a.before
        m = Model(path);m.create()
        result = m.map()
        assert (result == 0xffffffffffffffff) == old, hex(result)
        if old:
            assert m.searches == [SIZE] and not m.maps and not m.aliases
        else:
            assert result == 0x60000000 and len(m.maps) > 1
            assert sum(n for _, n in m.maps.values()) == SIZE
            assert sum(n for _, n in m.aliases.values()) == SIZE
            maps = len(m.maps)
            assert m.map(0x68000000) == 0x68000000 and len(m.maps) == maps
            assert m.call('horizon_munmap', 0x60000000, SIZE) == 0 and m.maps
            assert m.call('horizon_munmap', 0x68000000, SIZE) == 0
        m.dispose()
        results.append({'baseline': old, 'mapped': not old, 'anchor_requests': m.searches})
        del m;gc.collect()
    # No VA at all: bounded split attempts, standard ENOMEM, complete cleanup.
    m = Model(a.elf);m.create();m.holes = []
    assert m.map() == 0xffffffffffffffff and len(m.searches) < 32
    assert struct.unpack('<I', m.vm.mem_read(m.data+0x100, 4))[0] == 12
    m.dispose();del m;gc.collect()
    # A kernel error after partial progress is terminal and unwinds aliases.
    m = Model(a.elf);m.create();m.fail_alias = 2
    assert m.map() == 0xffffffffffffffff and m.alias_calls == 2
    assert not m.maps and not m.aliases and not m.reservations
    m.fail_alias = 0
    assert m.map() == 0x60000000
    assert m.call('horizon_munmap', 0x60000000, SIZE) == 0
    m.dispose()
    report = {'passed': True, 'hardware_tested': False,
              'native_elf_sha256': hashlib.sha256(a.elf.read_bytes()).hexdigest(),
              'baseline_elf_sha256': hashlib.sha256(a.before.read_bytes()).hexdigest(),
              'checks': results+['No free VA terminates with ENOMEM and no leaked mappings',
                                'Kernel alias failure rolls back; retry and final unmap release storage'],
              'limitations': 'OS services and free-hole layout modeled; no Switch/PES execution.'}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
