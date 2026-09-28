"""Check the linked FEX DLL's Horizon counter accesses and CRT constructors.

The instruction runner models CNTPCT/CNTFRQ, traps CNTVCT/CNTVCTSS like the
reported device, and uses bounded NT/CRT API mocks. It is not a Switch emulator.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

import pefile
from unicorn import arm64_const as arm
from fex_alloc import Model, reg, PEB, PARAM


CNTFRQ, CNTPCT, CNTVCT, CNTVCTSS = 0xd53be000, 0xd53be020, 0xd53be040, 0xd53be0c0


class CounterTrap(Exception):
    pass


class CounterModel(Model):
    def __init__(self, path, **kwargs):
        self.ticks, self.tick_step, self.frequency = 1000000, 37, 19200000
        self.reads = []
        self.heap_next = 0x30000000
        super().__init__(path, **kwargs)
        # Minimal real-layout process parameters with an empty environment.
        self.writeq(PEB + 0x20, PARAM+0x1000)
        self.writeq(PARAM+0x1080, PARAM+0x2000)
        self.writeq(PEB + 0x30, 0x1234)

    def wide_string(self, pointer):
        result = bytearray()
        while len(result) < 4096:
            data = self.vm.mem_read(pointer + len(result), 2)
            if data == b'\0\0':
                return result.decode('utf-16-le')
            result.extend(data)
        raise AssertionError('Unterminated Unicode string')

    def hook(self, vm, pc, size, user):
        word = int.from_bytes(vm.mem_read(pc, 4), 'little')
        register = word & ~31
        if register in (CNTVCT, CNTVCTSS):
            raise CounterTrap(f'Forbidden virtual counter at RVA {pc-self.base:#x}')
        if register in (CNTPCT, CNTFRQ):
            self.reads.append(register)
            value = self.frequency if register == CNTFRQ else self.ticks
            if register == CNTPCT:
                self.ticks += self.tick_step
            if word & 31 != 31:
                vm.reg_write(reg(word & 31), value)
            vm.reg_write(arm.UC_ARM64_REG_PC, pc+4)
            return
        name = self.hooks.get(pc)
        a = [vm.reg_read(reg(i)) for i in range(8)] if name else []
        result = 0
        if name == 'isspace':
            result = int(a[0] in (9, 10, 11, 12, 13, 32))
        elif name == 'RtlUnicodeToMultiByteSize':
            encoded = bytes(vm.mem_read(a[1], a[2])).decode('utf-16-le').encode()
            vm.mem_write(a[0], struct.pack('<I', len(encoded)))
        elif name == 'RtlUnicodeToMultiByteN':
            encoded = bytes(vm.mem_read(a[3], a[4])).decode('utf-16-le').encode()[:a[1]]
            vm.mem_write(a[0], encoded)
            if a[2]:
                vm.mem_write(a[2], struct.pack('<I', len(encoded)))
        elif name == 'RtlAllocateHeap':
            assert a[0] == 0x1234
            count = (a[2]+4095) & ~4095
            result = self.heap_next
            self.heap_next += count
            vm.mem_map(result, count)
        elif name == 'RtlInitUnicodeString':
            count = len(self.wide_string(a[1]).encode('utf-16-le')) if a[1] else 0
            vm.mem_write(a[0], struct.pack('<HHIQ', count, count+2 if a[1] else 0, 0, a[1]))
        elif name == 'RtlInitAnsiString':
            count = len(self.string(a[1]).encode()) if a[1] else 0
            vm.mem_write(a[0], struct.pack('<HHIQ', count, count+1 if a[1] else 0, 0, a[1]))
        elif name == 'LdrGetDllHandle':
            # Optional CRT helper DLL is also absent in the device log.
            self.writeq(a[3], 0)
            result = 0xc0000135
        elif name == 'LdrGetProcedureAddress':
            assert not a[0]  # The optional helper DLL was not loaded.
            self.writeq(a[3], 0)
            result = 0xc0000135
        elif name == 'RtlNtStatusToDosError' and (a[0] & 0xffffffff) == 0xc0000135:
            result = 126
        else:
            return super().hook(vm, pc, size, user)
        self.calls.append((name, a))
        vm.reg_write(reg(0), result)
        vm.reg_write(arm.UC_ARM64_REG_PC, vm.reg_read(reg(30)))


def scan_counters(path):
    pe = pefile.PE(data=path.read_bytes())
    found = {value: [] for value in (CNTPCT, CNTFRQ, CNTVCT, CNTVCTSS)}
    for section in pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        data = section.get_data()
        for i in range(0, len(data)-3, 4):
            value = int.from_bytes(data[i:i+4], 'little') & ~31
            if value in found:
                found[value].append(section.VirtualAddress+i)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--before', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    checks = []
    if args.before:
        old = CounterModel(args.before)
        try:
            old.call('_ZN3FEX7Windows14InitCRTProcessEv')
        except CounterTrap:
            assert old.vm.reg_read(arm.UC_ARM64_REG_PC) - old.base == 0xc3d80
        else:
            raise AssertionError('Old counter fault was not reproduced')
        checks.append('old DLL traps on CNTVCT at exact hardware RVA 0xc3d80')
    scan = scan_counters(args.dll)
    assert scan[CNTPCT] and scan[CNTFRQ]
    assert not scan[CNTVCT] and not scan[CNTVCTSS], scan
    checks.append('executable sections contain physical/frequency reads and no virtual-counter reads')

    model = CounterModel(args.dll)
    model.call('PES13FexCounterPreflight')
    assert not model.trapped and '[FEX2-TIMER] PASS' in model.logs[-1]
    assert f'{model.frequency:016x}' in model.logs[-1]
    model.call('_GLOBAL__sub_I_JIT.cpp')
    assert not model.trapped
    seed = next(address for name, address in model.symbols.items() if 'RNGState' in name)
    assert model.readq(seed) == model.ticks-model.tick_step
    checks.append('physical-counter preflight passes and JIT seed stores the returned tick')

    # Exercise the real linked IR lowering method, including destination
    # register selection and ISB emission, rather than a separate test emitter.
    # These minimal object offsets are for the pinned FEX revision's layouts:
    # Buffer.CurrentOffset +0x48, GPR map +0x60, OrderedNode.PhysicalRegister
    # +0x10, and IROp_CycleCounter.SelfSynchronizingLoads +4.
    method = next(name for name in model.symbols if '15Op_CycleCounter' in name)
    emitter, mapping, node, ir, buffer = (PARAM+offset for offset in (0x3000, 0x3400, 0x3600, 0x3800, 0x4000))
    for synchronized in (0, 1):
        for destination in (9, 17, 28):
            model.writeq(emitter+0x48, buffer)
            model.writeq(emitter+0x60+model.emitter_view_offset, mapping)
            model.vm.mem_write(mapping+3*4, struct.pack('<I', destination))
            model.vm.mem_write(node+0x10, b'\x43')  # GPR class, physical slot 3.
            model.vm.mem_write(ir+4, bytes([synchronized]))
            model.call(method, emitter, ir, node)
            assert not model.trapped
            end = model.readq(emitter+0x48)
            expected = ([0xd5033fdf] if synchronized else []) + [CNTPCT | destination]
            assert bytes(model.vm.mem_read(buffer, end-buffer)) == struct.pack('<'+'I'*len(expected), *expected)
            model.vm.mem_write(end, struct.pack('<I', 0xd65f03c0))  # RET
            model.symbols['emitted_counter'] = buffer
            tick = model.ticks
            model.call('emitted_counter')
            assert model.vm.reg_read(reg(destination)) == tick
    checks.append('actual JIT counter lowering emits/executes CNTPCT for three registers, with ISB only when requested')
    for mode in ('stopped', 'backwards', 'zero-frequency'):
        bad = CounterModel(args.dll)
        if mode == 'stopped': bad.tick_step = 0
        if mode == 'backwards': bad.tick_step = -1
        if mode == 'zero-frequency': bad.frequency = 0
        bad.call('PES13FexCounterPreflight')
        assert bad.trapped and 'STOP' in bad.logs[-1]
    checks.append('stopped/backwards clocks and zero frequency stop with a diagnostic')
    crt = CounterModel(args.dll)
    crt.call('_ZN3FEX7Windows14InitCRTProcessEv')
    assert not crt.trapped
    checks.append('full linked InitCRTProcess completes with bounded NT API mocks')

    report = {'passed': True, 'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'checks': checks, 'native_counter_reads': {hex(k): len(v) for k,v in scan.items()},
              'scope': 'DLL instructions with modeled Horizon counter access and NT APIs; hardware retest required'}
    if args.before: report['before_sha256'] = hashlib.sha256(args.before.read_bytes()).hexdigest()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n')
    for check in checks: print('PASS:', check)
    print(report['scope'])


if __name__ == '__main__':
    main()
