"""Exercise the compiled probe's mapping lifecycle with modeled Horizon SVCs.

Unicorn executes the actual ARM64 probe and its generated return-42 code.
Address-space restrictions are injected, not claimed as hardware measurements.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_PROT_ALL, UC_PROT_NONE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X30, UC_ARM64_REG_PC, UC_ARM64_REG_SP

ROOT = Path(__file__).resolve().parents[1]
PAGE = 4096


class Model:
    def __init__(self, path, failure=None):
        self.vm = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.failure = failure
        self.events, self.allocations, self.maps, self.reservations = [], {}, {}, {}
        self.map_states = {}
        with path.open('rb') as file:
            elf = ELFFile(file)
            segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
            end = max(s['p_vaddr'] + s['p_memsz'] for s in segments)
            self.vm.mem_map(0, (end + PAGE - 1) & -PAGE)
            for segment in segments:
                self.vm.mem_write(segment['p_vaddr'], segment.data())
            self.symbols = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        self.names = {value: key for key, value in self.symbols.items() if value}
        self.stack = 0x200000000
        self.data = 0x300000000
        self.stop = 0x100000000
        self.backing = 0x800000000  # exercise 64-bit native backing pointers
        for address in (self.stack, self.data, self.stop): self.vm.mem_map(address, 0x20000)
        self.vm.mem_write(self.data, b'test\0')
        self.vm.hook_add(UC_HOOK_CODE, self.hook)

    def reg(self, index):
        return self.vm.reg_read(UC_ARM64_REG_X0 + index)

    def ret(self, value=0):
        self.vm.reg_write(UC_ARM64_REG_X0, value)
        self.vm.reg_write(UC_ARM64_REG_PC, self.vm.reg_read(UC_ARM64_REG_X30))

    def hook(self, vm, pc, size, _):
        name = self.names.get(pc)
        x = self.reg
        if name in ('record', 'virtmemLock', 'virtmemUnlock', 'armDCacheFlush', 'armICacheInvalidate'):
            self.ret()
        elif name == 'aligned_alloc':
            if self.failure == 'backing': self.ret(0); return
            assert x(0) == PAGE and x(1) % PAGE == 0
            self.allocations[self.backing] = x(1)
            vm.mem_map(self.backing, x(1))
            self.ret(self.backing)
        elif name == 'free':
            address = x(0)
            assert not any(src == address for src, _ in self.maps.values()), 'live backing freed'
            vm.mem_unmap(address, self.allocations.pop(address))
            self.ret()
        elif name == 'svcQueryMemory':
            if self.failure == 'query': self.ret(0xd401); return
            memory_type = 5 if self.failure == 'occupied' else 0
            vm.mem_write(x(0), struct.pack('<QQIIIIII', 0, 1 << 39, memory_type, 0, 0, 0, 0, 0))
            vm.mem_write(x(1), bytes(4))
            self.ret()
        elif name == 'virtmemFindCodeMemory': self.ret(0x400000000)
        elif name == 'virtmemAddReservation':
            if self.failure == 'reservation': self.ret(0); return
            token = self.data + 0x1000
            self.reservations[token] = (x(0), x(1))
            self.ret(token)
        elif name == 'virtmemRemoveReservation':
            assert not self.maps, 'reservation released before unmap'
            self.reservations.pop(x(0))
            self.ret()
        elif name == 'envGetOwnProcessHandle': self.ret(42)
        elif name == 'svcMapProcessCodeMemory':
            assert x(0) == 42
            dst, src, length = x(1), x(2), x(3)
            self.events.append(('map', dst, src, length))
            if self.failure == 'map' or self.failure == 'floor' and dst < 0x08000000:
                self.ret(0xd401); return  # observed device result for below-floor destination
            assert self.allocations[src] == length
            vm.mem_map(dst, length)
            vm.mem_write(dst, bytes(vm.mem_read(src, length)))
            vm.mem_protect(src, length, UC_PROT_NONE)
            vm.mem_protect(dst, length, UC_PROT_NONE)
            self.maps[dst] = (src, length)
            self.map_states[dst] = 'AliasCode'
            self.ret()
        elif name == 'svcSetProcessMemoryPermission':
            address, length, perm = x(1), x(2), x(3)
            self.events.append(('permission', perm))
            if self.failure == 'rw' and perm == 3 or self.failure == 'rx' and perm == 5:
                self.ret(0xd401); return
            if self.map_states[address] != 'AliasCode':
                self.ret(0xd401); return
            if perm == 3: self.map_states[address] = 'AliasCodeData'
            vm.mem_protect(address, length, perm)
            self.ret()
        elif name == 'svcUnmapProcessCodeMemory':
            dst, src, length = x(1), x(2), x(3)
            assert self.maps[dst] == (src, length)
            self.events.append(('unmap', dst))
            if self.failure == 'unmap': self.ret(0xd401); return
            vm.mem_protect(src, length, UC_PROT_ALL)
            vm.mem_write(src, bytes(vm.mem_read(dst, length)))
            vm.mem_unmap(dst, length)
            del self.maps[dst]
            del self.map_states[dst]
            self.ret()

    def call(self, target=0x400000, size=PAGE, execute=0):
        self.vm.reg_write(UC_ARM64_REG_SP, self.stack + 0x1f000)
        self.vm.reg_write(UC_ARM64_REG_X30, self.stop)
        for index, value in enumerate((self.data, target, size, execute)):
            self.vm.reg_write(UC_ARM64_REG_X0 + index, value)
        self.vm.emu_start(self.symbols['test_mapping'], self.stop, count=4_000_000)
        assert self.vm.reg_read(UC_ARM64_REG_PC) == self.stop
        result = self.reg(0) & 0xffffffff
        return result if result < 0x80000000 else result - (1 << 32)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--before', type=Path, help='Optional original v1 ELF to reproduce its invalid RW-to-RX test')
    args = parser.parse_args()
    results = []
    cases = [(None, 0x400000, PAGE, 0, 1), (None, 0x400000, 0x189a000, 0, 1),
             (None, 0, PAGE, 1, 1), ('floor', 0x400000, PAGE, 0, 0),
             ('floor', 0x10000000, 0x189a000, 0, 1)]
    cases += [(failure, 0x400000, PAGE, 0 if failure == 'rw' else 1, 0 if failure == 'map' else -1)
              for failure in ('backing', 'query', 'occupied', 'reservation', 'map', 'rw', 'rx', 'unmap')]
    for failure, target, size, execute, expected in cases:
        model = Model(args.elf, failure)
        actual = model.call(target, size, execute)
        assert actual == expected, (failure, actual, expected)
        retained = failure == 'unmap'
        assert bool(model.allocations) == retained and bool(model.maps) == retained
        assert bool(model.reservations) == retained
        results.append({'failure': failure, 'target': hex(target), 'bytes': size, 'result': actual,
                        'retained_on_failed_unmap': retained})
    if args.before:
        original = Model(args.before)
        assert original.call(0, PAGE, 1) == -1
        assert ('permission', 3) in original.events and ('permission', 5) in original.events
        assert not original.allocations and not original.maps and not original.reservations
    sys.path.insert(0, str(ROOT / 'tools'))
    spec = importlib.util.spec_from_file_location('builder', ROOT / 'tools/build-as39-probe.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    npdm_checks = []
    for mode in (32, 39):
        data = (args.work / f'forwarder-{mode}/exefs/main.npdm').read_bytes()
        builder.check_npdm(data, mode, builder.title_id(mode))
        corrupt = bytearray(data)
        corrupt[12] ^= 2  # reject the wrong address-space setting
        try: builder.check_npdm(corrupt, mode, builder.title_id(mode))
        except AssertionError: pass
        else: raise AssertionError('Corrupted NPDM accepted')
        npdm_checks.append(mode)
    report = {'passed': True, 'hardware_tested': False,
              'elf_sha256': hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              'actual_arm64_lifecycle_cases': results, 'npdm_modes_checked': npdm_checks,
              'original_rw_to_rx_failure_reproduced': bool(args.before),
              'baseline_elf_sha256': hashlib.sha256(args.before.read_bytes()).hexdigest() if args.before else None,
              'limitations': 'Horizon services and region restrictions modeled; no Wine/PES execution.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
