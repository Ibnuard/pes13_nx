"""Exercise the shipped ARM64 VM fault path and debug-only permission report.

Horizon protection/query calls and the Wine TEB are modeled. Wine's actual
page table, fault classification, write-watch clearing and return codes run
from each ELF. This is not a device test or a claimed Kitserver crash fix.
"""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import struct

from fextendo_silent import Model as Base, reg, arm


class Model(Base):
    def __init__(self, path):
        super().__init__(path)
        self.debug = False
        self.query_status = 0
        self.protections, self.queries, self.reports = [], [], []
        self.protect_reports = []
        self.vm.mem_map(0x55000000, 0x100000)
        self.q(self.symbols['pages_vprot'], self.data + 0x2000)
        self.q(self.data + 0x2000, 0x55000000)
        self.q(self.symbols['pages_vprot_size'], 1)
        self.q(self.symbols['host_page_size'], 4096)
        self.q(self.symbols['host_page_mask'], 4095)

    def hook(self, vm, pc, size, user):
        x = lambda i: vm.reg_read(reg(i))
        names = self.symbols
        if pc in {names.get('pthread_mutex_lock'), names.get('pthread_mutex_unlock')}:
            self.ret(0)
        elif pc == names.get('NtCurrentTeb'):
            self.ret(self.data + 0x4000)
        elif pc == names.get('horizon_mprotect'):
            self.protections.append([x(i) for i in range(3)])
            self.ret(0)
        elif pc == names.get('wine_nx_launch_debug_active'):
            self.ret(int(self.debug))
        elif pc == names.get('svcQueryMemory'):
            self.queries.append(x(2))
            if not self.query_status:
                vm.mem_write(x(0), struct.pack('<QQ6I', x(2) & -4096, 4096, 4, 0, 1, 0, 0, 0))
                vm.mem_write(x(1), bytes(4))
            self.ret(self.query_status)
        elif pc == names.get('horizon_trace'):
            fmt = self.string(x(0))
            assert fmt.startswith(('[VM-FAULT] v2 ', '[VM-PROTECT] v1 ')), fmt
            tail = list(struct.unpack('<3Q', vm.mem_read(vm.reg_read(arm.UC_ARM64_REG_SP), 24)))
            (self.protect_reports if fmt.startswith('[VM-PROTECT]') else self.reports).append(
                [x(i) for i in range(1, 8)] + tail)
            self.ret()
        else:
            super().hook(vm, pc, size, user)

    def fault(self, vprot, kind=1, write_exceptions=False, address=0x60000042, pc=0x12345678):
        page_entry = 0x55000000 + (address >> 12)
        self.vm.mem_write(page_entry, bytes([vprot]))
        self.vm.mem_write(self.symbols['enable_write_exceptions'], struct.pack('<I', int(write_exceptions)))
        # ARM64 EXCEPTION_RECORD: kind and fault address follow NumberParameters.
        self.vm.mem_write(self.data, struct.pack('<IIQQIIQQQ',
                          0xc0000005, 0, 0, pc, 2, 0, kind, address, 0))
        self.protections.clear()
        result = self.call('virtual_handle_fault', self.data, 0x71000000) & 0xffffffff
        assert struct.unpack('<I', self.vm.mem_read(self.data, 4))[0] == result
        return result, self.vm.mem_read(page_entry, 1)[0], list(self.protections)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path)
    p.add_argument('--before', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    baseline = None
    for path in (a.before, a.elf):
        m = Model(path)
        results = []
        # Legitimate write-watch writes recover. Readonly/unmapped pages and
        # unexplained faults remain access violations; guard semantics survive.
        cases = [(0x6d, 1, False, 0), (0x6f, 1, False, 0),
                 (0x25, 1, False, 0xc0000005), (0, 1, False, 0xc0000005),
                 (0x2d, 1, False, 0xc0000005), (0x6d, 1, True, 0xc0000006),
                 (0x37, 1, False, 0x80000001), (0x25, 0, False, 0xc0000005)]
        for vprot, kind, enabled, expected in cases:
            result = m.fault(vprot, kind, enabled)
            assert result[0] == expected, (hex(vprot), result, hex(expected))
            results.append(result)
        assert not m.queries and not m.reports, 'Normal launch queried/logged diagnostics'
        if path == a.before:
            baseline = results
        else:
            assert results == baseline, 'Observer changed VM results or protections'
            m.debug = True
            m.fault(0x6d)
            assert not m.queries and not m.reports, 'Handled write fault was logged'
            m.fault(0x25)
            assert m.queries == [0x60000042]
            # PC, address, access kind, status, Wine permissions, query rc,
            # native base, size, type and permissions.
            assert m.reports == [[0x12345678, 0x60000042, 1, 0xc0000005, 0x25, 0,
                                  0x60000000, 4096, 4, 1]], m.reports
            for i in range(100):
                assert m.fault(0x25, address=0x60000080, pc=0x33330000 + 4*i)[0] == 0xc0000005
            assert len(m.queries) == len(m.reports) == 1, 'Repeated page faults consumed the budget'
            m.fault(0x2d, address=0x01c80042, pc=0xf1e411ff)
            assert m.reports[-1][:5] == [0xf1e411ff, 0x01c80042, 1, 0xc0000005, 0x2d]
            # A changed logical protection on the same page gets a fresh report.
            m.fault(0x25, address=0x01c80042)
            assert len(m.queries) == 3
            m.query_status = 0xdead
            m.fault(0, address=0x02000042)
            assert m.reports[-1][5:] == [0xdead, 0, 0, 0, 0], m.reports[-1]
            m.query_status = 0
            for i in range(64):
                assert m.fault(0, address=0x03000042 + i*4096)[0] == 0xc0000005
            assert len(m.queries) == len(m.reports) == 32, 'Unique fault reports are unbounded'
            if 'horizon_debug_vm_protect' in m.symbols:
                m.queries.clear()
                m.debug = False
                m.call('horizon_debug_vm_protect', 0x01c80000, 4096, 0x40, 0x20, 0, 0xff543210)
                assert not m.queries and not m.protect_reports, 'Quiet protection trace performed I/O'
                m.debug = True
                m.call('horizon_debug_vm_protect', 0x01c80000, 4096, 0x40, 0x20, 0, 0xff543210)
                assert m.protect_reports == [[0x01c80000, 4096, 0x40, 0x20, 0, 0xff543210,
                                              0, 0x01c80000, 4096, 1]], m.protect_reports
                m.query_status = 0xbeef
                m.call('horizon_debug_vm_protect', 0x01c80000, 4096, 0x20, 0x40, 0xc0000045, 0xffb90100)
                assert m.protect_reports[-1] == [0x01c80000, 4096, 0x20, 0x40, 0xc0000045,
                                                0xffb90100, 0xbeef, 0, 0, 0]
                for i in range(80):
                    m.call('horizon_debug_vm_protect', 0x01c80000, 4096, 0x40, 0x20, 0, 0xff543210)
                assert len(m.queries) == len(m.protect_reports) == 64, 'Protection history is unbounded'
        del m
        gc.collect()
    report = {'passed': True, 'hardware_tested': False,
              'native_elf_sha256': hashlib.sha256(a.elf.read_bytes()).hexdigest(),
              'baseline_elf_sha256': hashlib.sha256(a.before.read_bytes()).hexdigest(),
              'checks': ['Eight VM fault scenarios preserve prior statuses and protection calls',
                         'Normal launch performs no diagnostic query or logging',
                         'Handled write-watch faults remain silent',
                         'Debug report records PC plus Wine and Horizon page metadata; failed queries preserve zero metadata',
                         '100 repeated faults with different PCs cannot hide the next distinct page fault',
                         'Changed logical protection on one page is recorded separately',
                         'Reports stop at 32 distinct events; faults are never suppressed',
                         'Protection observer, when present, preserves caller/status/permissions and caps debug queries at 64; quiet mode has no queries'],
              'test_sources': {str(Path(__file__).relative_to(Path(__file__).parents[1])).replace('\\', '/'):
                               hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
