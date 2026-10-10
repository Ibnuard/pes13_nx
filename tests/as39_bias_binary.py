"""Execute the linked ARM64 benchmark in Unicorn; timing is NEVER emulated.

Checks copied JIT kernels against a separate reference, high/low 32-bit guest
addresses, full memory results, ABI preservation, pointer boundaries, and
mapping failures. Horizon results are injected, not claimed as device tests.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_PROT_ALL, UC_PROT_NONE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X29, UC_ARM64_REG_X30, UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_Q0

PAGE = 4096
BIAS = 0x5000000000
KINDS = ('chase', 'scalar', 'vector', 'pair', 'atomic')
XREGS = [UC_ARM64_REG_X0+i for i in range(29)] + [UC_ARM64_REG_X29, UC_ARM64_REG_X30]


class Machine:
    def __init__(self, path, failure=None):
        self.vm = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.failure, self.events, self.maps = failure, [], {}
        with path.open('rb') as file:
            elf = ELFFile(file)
            segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
            end = max(s['p_vaddr'] + s['p_memsz'] for s in segments)
            self.vm.mem_map(0, (end + PAGE - 1) & -PAGE)
            for segment in segments: self.vm.mem_write(segment['p_vaddr'], segment.data())
            self.symbols = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
            self.relocations = [r['r_offset'] for section in elf.iter_sections()
                                if section['sh_type'] in ('SHT_REL', 'SHT_RELA') for r in section.iter_relocations()]
        self.stack, self.data, self.stop, self.jit, self.backing = (0x100000000, 0x200000000, 0x300000000, 0x7000000000, 0x4000000000)
        for address in (self.stack, self.data, self.stop, self.jit, self.backing): self.vm.mem_map(address, 0x10000)
        self.names = {self.symbols[n]: n for n in ('record', 'envGetOwnProcessHandle', 'svcQueryMemory',
                     'svcMapProcessCodeMemory', 'svcSetProcessMemoryPermission', 'svcUnmapProcessCodeMemory')}
        self.vm.hook_add(UC_HOOK_CODE, self.hook)

    def reg(self, index): return self.vm.reg_read(XREGS[index])

    def ret(self, value=0):
        self.vm.reg_write(UC_ARM64_REG_X0, value)
        self.vm.reg_write(UC_ARM64_REG_PC, self.vm.reg_read(UC_ARM64_REG_X30))

    def hook(self, vm, pc, _size, _data):
        name = self.names.get(pc)
        if name is None: return
        x = self.reg
        if name == 'record': self.ret(); return
        if name == 'envGetOwnProcessHandle': self.ret(42); return
        if name == 'svcQueryMemory':
            if self.failure == 'query': self.ret(0xd401); return
            kind = 5 if self.failure == 'occupied' else 0
            vm.mem_write(x(0), struct.pack('<QQIIIIII', 0, 1 << 39, kind, 0, 0, 0, 0, 0))
            vm.mem_write(x(1), bytes(4))
            self.ret(); return
        if name == 'svcMapProcessCodeMemory':
            assert x(0) == 42
            dst, src, length = x(1), x(2), x(3)
            self.events.append(('map', dst, src, length))
            if self.failure == 'map': self.ret(0xd401); return
            vm.mem_map(dst, length)
            vm.mem_write(dst, bytes(vm.mem_read(src, length)))
            vm.mem_protect(src, length, UC_PROT_NONE)
            vm.mem_protect(dst, length, UC_PROT_NONE)
            self.maps[dst] = (src, length)
            self.ret(); return
        if name == 'svcSetProcessMemoryPermission':
            assert x(3) == 3  # data remains RW, no RW->RX conversion
            self.events.append(('rw', x(1)))
            if self.failure in ('permission', 'permission-unmap'): self.ret(0xd401); return
            vm.mem_protect(x(1), x(2), UC_PROT_ALL)
            self.ret(); return
        if name == 'svcUnmapProcessCodeMemory':
            dst, src, length = x(1), x(2), x(3)
            self.events.append(('unmap', dst, src, length))
            assert self.maps[dst] == (src, length)
            if self.failure in ('unmap', 'permission-unmap'): self.ret(0xd401); return
            vm.mem_protect(src, length, UC_PROT_ALL)
            vm.mem_protect(dst, length, UC_PROT_ALL)
            vm.mem_write(src, bytes(vm.mem_read(dst, length)))
            vm.mem_unmap(dst, length)
            del self.maps[dst]
            self.ret(); return

    def call(self, address, args, budget=2_000_000):
        if isinstance(address, str): address = self.symbols[address]
        vm = self.vm
        for i in range(31): vm.reg_write(XREGS[i], 0)
        vm.reg_write(UC_ARM64_REG_SP, self.stack + 0xf000)
        vm.reg_write(UC_ARM64_REG_X30, self.stop)
        preserved = {i: 0xaabb00000000 + i for i in range(18, 30)}
        for i, value in preserved.items(): vm.reg_write(XREGS[i], value)
        for i in range(8, 16): vm.reg_write(UC_ARM64_REG_Q0 + i, 0x1234560000 + i)
        for i, value in enumerate(args): vm.reg_write(XREGS[i], value)
        vm.emu_start(address, self.stop, count=budget)
        assert vm.reg_read(UC_ARM64_REG_PC) == self.stop, 'instruction budget exhausted'
        assert vm.reg_read(UC_ARM64_REG_SP) == self.stack + 0xf000, 'stack corrupted'
        for i, value in preserved.items(): assert self.reg(i) == value, f'ABI x{i} corrupted'
        for i in range(8, 16): assert vm.reg_read(UC_ARM64_REG_Q0+i) & ((1<<64)-1) == 0x1234560000+i
        return self.reg(0)

    def copy_kernel(self, name):
        first, last = self.symbols[name], self.symbols[name + '_end']
        assert 0 < last-first < PAGE
        assert not any(first <= offset < last for offset in self.relocations), 'copied kernel needs relocation'
        self.vm.mem_write(self.jit, bytes(self.vm.mem_read(first, last-first)))
        # Unicorn caches translations when the same slot receives different code.
        self.vm.ctl_remove_cache(self.jit, self.jit + PAGE)
        return self.jit


def data_pattern(guest, size):
    words = [(i * 2654435761 + 0x132039) & 0xffffffff for i in range(size // 4)]
    count = size // 32
    for i in range(count): words[((i * 4051) & (count-1))*8] = guest + (((i+1)*4051) & (count-1))*32
    return bytearray(struct.pack('<' + 'I'*len(words), *words))


def reference(kind, data, guest, loops):
    data = bytearray(data)
    count = len(data) // 32
    if kind == 'chase':
        ptr = guest
        for _ in range(loops*8): ptr = struct.unpack_from('<I', data, ptr-guest)[0]
        return ptr, data
    position, checksum, lanes = 0, 0, [0]*4
    for _ in range(loops):
        position = (position + 97) % count
        offset = position * 32
        if kind in ('scalar', 'atomic'):
            value = (struct.unpack_from('<I', data, offset+4)[0] + 1) & 0xffffffff
            struct.pack_into('<I', data, offset+4, value)
            checksum ^= value
        elif kind == 'vector':
            values = [(v+1) & 0xffffffff for v in struct.unpack_from('<4I', data, offset+16)]
            struct.pack_into('<4I', data, offset+16, *values)
            lanes = [a ^ b for a,b in zip(lanes,values)]
        else:
            a,b = struct.unpack_from('<QQ', data, offset+16)
            a,b = (a+1) & ((1<<64)-1), (b+3) & ((1<<64)-1)
            struct.pack_into('<QQ', data, offset+16, a,b)
            checksum ^= a ^ b
    return (sum(lanes) & 0xffffffff if kind == 'vector' else checksum), data


def check_kernels(path, results):
    machine = Machine(path)
    for guest in (0x10000000, 0x90000000, 0xfffff000):
        original = data_pattern(guest, PAGE)
        for kind in KINDS:
            for loops in (0, 1, 17, 1009):
                want, memory = reference(kind, original, guest, loops)
                for variant, bias in (('direct', 0), ('bias', BIAS)):
                    vm = machine.vm
                    vm.mem_map(bias+guest, PAGE)
                    vm.mem_write(bias+guest, bytes(original))
                    code = machine.copy_kernel(f'as39_{kind}_{variant}')
                    actual = machine.call(code, (bias, guest, loops, PAGE//32-1))
                    assert actual == want, (kind, variant, hex(guest), loops, hex(actual), hex(want))
                    assert vm.mem_read(bias+guest, PAGE) == memory, (kind, variant, 'memory differs')
                    vm.mem_unmap(bias+guest, PAGE)
                    results.append(f'{kind}/{variant}/guest-{guest:08x}/loops-{loops}')
    for guest, operand, delta in ((0x400000,0x400000,0x20), (0x10000,0xfffffff0,0x10030),
                                  (0xfffff000,0x20,0xfffff000)):
        vm = machine.vm
        vm.mem_map(BIAS+guest, PAGE)
        vm.mem_write(BIAS+guest+0x20, struct.pack('<I',0xcafe1320))
        code = machine.copy_kernel('as39_wrap_read')
        assert machine.call(code,(BIAS,operand,delta,0)) == 0xcafe1320
        vm.mem_unmap(BIAS+guest,PAGE)
        results.append(f'fixed/wrapped-guest-{guest:08x}')


def check_boundaries(path, results):
    m = Machine(path)
    for bias,guest,size,ok,want in ((BIAS,0x400000,4096,1,BIAS+0x400000),
             (BIAS,0xffffffff,1,1,BIAS+0xffffffff), (BIAS,0xffffffff,2,0,None),
             (BIAS,0,0,1,0), (BIAS,0,1,0,None), ((1<<64)-(1<<32),1,1,0,None)):
        m.vm.mem_write(m.data,struct.pack('<Q',0x1234))
        assert m.call('as39_bench_guest_span',(bias,guest,size,m.data)) == ok
        assert struct.unpack('<Q',m.vm.mem_read(m.data,8))[0] == (want if ok else 0x1234)
        results.append(f'guest-span/{bias:x}/{guest:x}/{size}')
    for ptr,ok,want in ((0,1,0),(BIAS+0x400000,1,0x400000),(BIAS+0xffffffff,1,0xffffffff),
                        (BIAS,0,None),(BIAS-1,0,None),(BIAS+(1<<32),0,None)):
        m.vm.mem_write(m.data,struct.pack('<I',0x1234))
        assert m.call('as39_bench_host_pointer',(BIAS,ptr,m.data)) == ok
        assert struct.unpack('<I',m.vm.mem_read(m.data,4))[0] == (want if ok else 0x1234)
        results.append(f'host-pointer/{ptr:x}')
    assert m.call('as39_bench_guest_span',(BIAS,1,1,0)) == 0
    assert m.call('as39_bench_host_pointer',(BIAS,BIAS+1,0)) == 0
    results.append('null-output-pointers-rejected')


def check_lifecycle(path, results):
    for failure in (None,'query','occupied','map','permission','unmap','permission-unmap'):
        m = Machine(path,failure)
        m.vm.mem_write(m.data,struct.pack('<QQQI4x',m.backing,0,0,0))
        mapped = m.call('as39_bench_map',(m.data,BIAS+0x400000,PAGE))
        assert mapped == int(failure in (None,'unmap'))
        if mapped: assert m.call('as39_bench_unmap',(m.data,)) == int(failure is None)
        retained = failure in ('unmap','permission-unmap')
        assert bool(m.maps) == retained
        assert struct.unpack('<I',m.vm.mem_read(m.symbols['cleanup_failed'],4))[0] == int(retained)
        assert struct.unpack('<I',m.vm.mem_read(m.data+24,4))[0] == int(retained)
        if retained:
            before = list(m.events)
            assert m.call('as39_bench_map',(m.data,BIAS+0x800000,PAGE)) == 0
            assert m.events == before
        results.append('map-lifecycle/' + str(failure))
    for target,size in ((BIAS+1,PAGE),(BIAS,0),(BIAS,PAGE+1),(BIAS,8*1024*1024)):
        m = Machine(path)
        m.vm.mem_write(m.data,struct.pack('<QQQI4x',m.backing,0,0,0))
        assert m.call('as39_bench_map',(m.data,target,size)) == 0 and not m.events
        results.append(f'map-invalid/{target:x}/{size}')


def check_analysis(results):
    tool = Path(__file__).resolve().parents[1] / 'tools/analyze-as39-bias-bench.py'
    spec = importlib.util.spec_from_file_location('bias_analysis',tool)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Synthetic timing fixtures test statistics/rejection only, NOT performance.
    rows = ['[CORRECTNESS] PASS', '[CPU] pin_core=2 rc=00000000 tick_frequency=19200000',
            '[CASE] kernel=scalar footprint=16384 loops=1000 steps=1000 samples=9']
    for i in range(9):
        rows.append(f'[SAMPLE] kernel=scalar bytes=16384 pair={i} order={"BA" if i%2 else "AB"} loops=1000 '
                    f'direct_ticks=1000 bias_ticks={1100+i} checksum=1234 cpu_hz=1020000000,1020000000,1020000000 '
                    'ram_hz=1600000000,1600000000,1600000000 clock=STABLE')
    rows.append('[SUMMARY] BENCH-COMPLETE cleanup_failed=0')
    text = '\n'.join(rows)
    report = mod.analyze(text)
    assert report['complete'] is False  # only one of the required 15 cases
    assert abs(report['cases'][0]['paired_overhead_pct']-10.4) < 1e-7
    assert report['cases'][0]['clock_verified']
    unknown = mod.analyze(text.replace('1020000000,1020000000,1020000000','0,0,0').replace('clock=STABLE','clock=UNKNOWN'))
    assert not unknown['cases'][0]['clock_verified']
    changed = mod.analyze(text.replace('1020000000,1020000000,1020000000','1020000000,1785000000,1785000000').replace('clock=STABLE','clock=CHANGED'))
    assert changed['cases'][0]['usable_pairs'] == 0
    for broken in (text.replace('direct_ticks=1000','direct_ticks=0'),text+'\n'+rows[3]):
        try: mod.analyze(broken)
        except ValueError: pass
        else: raise AssertionError('invalid/duplicate sample accepted')
    results.extend(['analysis/paired-median','analysis/partial-not-complete','analysis/unknown-clocks',
                    'analysis/changed-clocks-excluded','analysis/invalid-and-duplicate-rejected'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--output',type=Path)
    args = p.parse_args()
    results = []
    check_kernels(args.elf,results)
    check_boundaries(args.elf,results)
    check_lifecycle(args.elf,results)
    check_analysis(results)
    report = {'passed':len(results),'elf_sha256':hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              'arm64_execution':'Unicorn, copied kernels above 4 GiB', 'hardware_tested':False,
              'performance_measured':False,'cases':results}
    if args.output: args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'cases'},indent=2))


if __name__ == '__main__': main()
