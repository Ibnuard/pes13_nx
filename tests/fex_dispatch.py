"""Check the linked FEX3 native exception dispatcher and PE callback ABI.

NT memory allocation and continuation are modeled; this is not a Switch or
guest SEH execution test. The separate fex-stress.exe provides that device test.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm64_const as arm


def reg(index):
    return getattr(arm, f'UC_ARM64_REG_X{index}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    vm = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    base, stack, param, frame, stubs = 0x1000000, 0x31000000, 0x32000000, 0x33000000, 0x34000000
    teb, dispatcher = param+0x8000, stubs+0x100
    with args.elf.open('rb') as stream:
        elf = ELFFile(stream)
        symbols = {s.name: base+s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        for segment in elf.iter_segments():
            if segment['p_type'] != 'PT_LOAD':
                continue
            va, size = segment['p_vaddr'], segment['p_memsz']
            low, high = va & ~4095, (va+size+4095) & ~4095
            vm.mem_map(base+low, high-low)
            vm.mem_write(base+va, segment.data())
        for relocation in elf.get_section_by_name('.relr.dyn').iter_relocations():
            address = base+relocation['r_offset']
            old, = struct.unpack('<Q', vm.mem_read(address, 8))
            vm.mem_write(address, struct.pack('<Q', base+old))
    for address in (stack, param, frame, stubs):
        vm.mem_map(address, 0x10000)
    state = {}

    def string(address):
        data = bytearray()
        while vm.mem_read(address+len(data), 1) != b'\0':
            data.extend(vm.mem_read(address+len(data), 1))
        return data.decode()

    def return_to_caller(result=None):
        if result is not None:
            vm.reg_write(reg(0), result)
        vm.reg_write(arm.UC_ARM64_REG_PC, vm.reg_read(reg(30)))

    def hook(machine, pc, size, user):
        if pc == stubs:
            state['returned'] = True
            machine.emu_stop()
        elif pc in {symbols['memcpy'], symbols['memmove']}:
            dest, source, count = [machine.reg_read(reg(i)) for i in range(3)]
            assert count <= 4096
            machine.mem_write(dest, bytes(machine.mem_read(source, count)))
            return_to_caller(dest)
        elif pc == symbols['virtual_setup_exception']:
            state['allocation'] = [machine.reg_read(reg(i)) for i in range(3)]
            return_to_caller(0 if state.get('fail_allocation') else frame)
        elif pc == symbols['NtCurrentTeb']:
            return_to_caller(teb)
        elif pc == symbols['horizon_trace']:
            machine.reg_write(reg(18), 0xbad)  # Native printf may clobber x18.
            return_to_caller()
        elif pc == symbols['pes13_fex_trace_guest_dispatch']:
            # Model only diagnostic I/O, preserving the real dispatcher path.
            ticket, label, rec, ctx = [machine.reg_read(reg(i)) for i in range(4)]
            text = bytearray()
            while machine.mem_read(label+len(text), 1) != b'\0':
                text.extend(machine.mem_read(label+len(text), 1))
            state.setdefault('trace', []).append((ticket, text.decode(), rec, ctx))
            machine.reg_write(reg(18), 0xbad)
            return_to_caller()
        elif pc == symbols['snprintf']:
            dest, capacity, fmt = [machine.reg_read(reg(i)) for i in range(3)]
            fmt = string(fmt).replace('%llu', '%d').replace('%llx', '%x')
            values = tuple(machine.reg_read(reg(i)) for i in range(3, 3+fmt.count('%')))
            output = (fmt % values).encode()
            assert len(output)+1 <= capacity
            machine.mem_write(dest, output+b'\0')
            return_to_caller(len(output))
        elif pc == symbols['wine_nx_runtime_trace']:
            state.setdefault('fault_logs', []).append(string(machine.reg_read(reg(0))))
            machine.reg_write(reg(18), 0xbad)
            return_to_caller()
        elif pc == symbols['horizon_continue_context']:
            state['continued'] = bytes(machine.mem_read(machine.reg_read(reg(0)), 0x390))
            machine.emu_stop()
        elif pc == stubs+0x200:
            assert machine.reg_read(reg(18)) == teb, 'PE callback received native scratch x18'
            assert machine.reg_read(arm.UC_ARM64_REG_SP) % 16 == 0
            pointers = machine.reg_read(reg(0))
            assert struct.unpack('<2Q', machine.mem_read(pointers, 16)) == (param, param+0x1000)
            assert machine.reg_read(reg(1)) == 0
            state['pe_called'] = True
            return_to_caller(state['handled'])
    vm.hook_add(UC_HOOK_CODE, hook)

    def call(name, *values):
        vm.reg_write(arm.UC_ARM64_REG_SP, stack+0xf000)
        vm.reg_write(reg(30), stubs)
        vm.reg_write(reg(18), 0xfeed1234)
        for i, value in enumerate(values):
            vm.reg_write(reg(i), value)
        vm.emu_start(symbols[name], 0, count=20000)
        assert state.get('returned') or 'continued' in state, 'No bounded completion'
        return vm.reg_read(reg(0)) & 0xffffffff

    context = bytearray((i*37+11) & 255 for i in range(0x390))
    struct.pack_into('<II', context, 0, 0x400007, 0xa0000000)
    struct.pack_into('<2Q', context, 256, param+0xf008, 0x777000)
    record = bytes((i*19+3) & 255 for i in range(0x98))
    vm.mem_write(param, record)
    vm.mem_write(param+0x1000, bytes(context))
    vm.mem_write(symbols['pKiUserExceptionDispatcher'], struct.pack('<Q', dispatcher))
    call('call_user_exception_dispatcher', param, param+0x1000)
    assert [entry[1] for entry in state['trace']] == ['enter', 'stack-ready', 'continue-dispatcher']
    assert state['allocation'] == [param+0xf000, 0x470, param]
    assert bytes(vm.mem_read(frame, 0x390)) == context
    assert bytes(vm.mem_read(frame+0x3b0, 0x98)) == record
    assert struct.unpack('<iIiIiI', vm.mem_read(frame+0x390, 24)) == (-0x390, 0x460, -0x390, 0x390, 0xd0, 0)
    assert bytes(vm.mem_read(frame+0x3a8, 8)) == bytes(8)
    assert struct.unpack('<3Q', vm.mem_read(frame+0x448, 24)) == (0, param+0xf008, 0x777000)
    expected = bytearray(context)
    struct.pack_into('<I', expected, 0, 0x400017)
    struct.pack_into('<Q', expected, 8+18*8, teb)
    struct.pack_into('<2Q', expected, 256, frame, dispatcher)
    assert state['continued'] == expected, 'Dispatcher corrupts incoming guest host registers'
    assert bytes(vm.mem_read(param+0x1000, 0x390)) == context
    assert bytes(vm.mem_read(param, 0x98)) == record
    checks = ['Wine ARM64 0x470 exception frame, CONTEXT_EX and full continuation context match ABI']
    state.clear()
    state['fail_allocation'] = True
    assert call('call_user_exception_dispatcher', param, param+0x1000) == 0xc00000fd
    assert 'continued' not in state
    for bad in ('record', 'context', 'dispatcher', 'sp'):
        state.clear()
        vm.mem_write(symbols['pKiUserExceptionDispatcher'], struct.pack('<Q', 0 if bad == 'dispatcher' else dispatcher))
        vm.mem_write(param+0x1100, struct.pack('<Q', 0 if bad == 'sp' else param+0xf008))
        assert call('call_user_exception_dispatcher', 0 if bad == 'record' else param,
                    0 if bad == 'context' else param+0x1000) == 0xc000000d
        assert 'continued' not in state and 'allocation' not in state
    checks.append('Missing record/context/dispatcher/stack and allocation failure return errors without continuing')
    for handled in (0, 1):
        state.clear()
        state['handled'] = handled
        vm.mem_write(symbols['handle_exception'], struct.pack('<Q', stubs+0x200))
        assert call('pes13_fex_dispatch_exception', param, param+0x1000) == handled
        assert state['pe_called'] and vm.reg_read(reg(18)) == 0xfeed1234
        assert vm.reg_read(arm.UC_ARM64_REG_SP) == stack+0xf000
    state.clear()
    vm.mem_write(symbols['handle_exception'], bytes(8))
    assert call('pes13_fex_dispatch_exception', param, param+0x1000) == 0 and 'pe_called' not in state
    checks.append('Native exception callback installs current TEB, preserves native x18/stack, propagates handled/not-handled')
    # Native snapshots retain a stalled fault even if early page faults have
    # consumed the printed trace allowance. Only diagnostic I/O is modeled.
    rows = symbols['fault_stages']
    vm.mem_write(rows, bytes(32*40))
    for i in range(32):
        vm.mem_write(teb+0x48, struct.pack('<Q', 4+i*4))
        for stage in (1, 2, 3):
            state.clear()
            call('pes13_fex_fault_stage', stage, 0x4000+i, 0x7000+i, 0xc0000005)
        assert struct.unpack('<QIII4xQQ', vm.mem_read(rows+i*40, 40)) == (
            4+i*4, 6, 3, 0xc0000005, 0x4000+i, 0x7000+i)
    before = bytes(vm.mem_read(rows, 32*40))
    vm.mem_write(teb+0x48, struct.pack('<Q', 0x1000))
    state.clear()
    call('pes13_fex_fault_stage', 1, 1, 2, 3)
    assert vm.mem_read(rows, 32*40) == before
    # An odd publication sequence is reported as busy, never as a stable row.
    vm.mem_write(rows+8, struct.pack('<I', 7))
    state.clear()
    call('pes13_fex_dump_fault_stages')
    assert len(state['fault_logs']) == 32
    assert state['fault_logs'][0] == '[FEX3-LAST] tid=4 snapshot=busy'
    assert state['fault_logs'][-1] == '[FEX3-LAST] tid=128 stage=3 pc=401f address=701f status=c0000005'
    checks.append('32 per-thread snapshots retain latest fault, bound capacity, detect busy publication and dump only on request')
    report = {'passed': True, 'native_elf_sha256': hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              'scope': 'Linked ARM64 native code with modeled NT allocation/continue and PE handler', 'checks': checks}
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
