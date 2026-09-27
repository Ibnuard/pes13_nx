"""Exercise actual ARM64 PE lookup/unwind instructions used by FEX exceptions.

Runs under Unicorn, with NT services modeled. This is not a Horizon guest PASS.
The bootstrap's native module index is represented by real LDR entries; the PE
lookup, .pdata/.xdata decoding and FEX capture wrapper execute unmodified.
"""
from pathlib import Path
import argparse
import hashlib
import json
import random
import struct

import pefile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm64_const as arm
from fex_alloc import coff_symbols, reg

TEB, PEB, STACK, DATA, STUB = 0x20000000, 0x20100000, 0x21000000, 0x22000000, 0x23000000


class Model:
    def __init__(self, ntdll, fex, wow64, elf=None):
        self.vm = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.modules = {}
        for name, path, base in (('ntdll', ntdll, 0x18000000),
                                 ('fex', fex, 0x10000000), ('wow64', wow64, 0x19000000)):
            data = path.read_bytes()
            pe = pefile.PE(data=data)
            old = pe.OPTIONAL_HEADER.ImageBase
            symbols = {n: a-old+base for n, a in coff_symbols(data, pe).items()}
            pe.relocate_image(base)
            self.vm.mem_map(base, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
            self.vm.mem_write(base, bytes(pe.get_memory_mapped_image()))
            self.modules[name] = (pe, symbols, base)
        self.nt = self.modules['ntdll'][1]
        self.fex = self.modules['fex'][1]
        self.wow = self.modules['wow64'][1]
        for base, size in ((TEB, 0x10000), (PEB, 0x10000), (STACK, 0x80000),
                           (DATA, 0x10000), (STUB, 0x10000)):
            self.vm.mem_map(base, size)
        self.q(TEB+0x60, PEB)
        self.q(TEB+0x08, STACK+0x80000)
        self.q(TEB+0x10, STACK)
        self.q(TEB, 0xffffffffffffffff)
        self.q(TEB+0x48, 8)
        self.vm.reg_write(reg(18), TEB)
        self.imports = {}
        for name, (pe, _, _) in self.modules.items():
            for dll in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
                for item in dll.imports:
                    symbol = item.name.decode() if item.name else str(item.ordinal)
                    address = self.nt.get(symbol)
                    if not address:
                        address = STUB+0x100+4*len(self.imports)
                        self.imports[address] = dll.dll.decode()+':'+symbol
                    self.q(item.address, address)
        for name, address in self.nt.items():
            if name.startswith('__wine_dbch_'):
                self.vm.mem_write(address, b'\0')
        self.q(self.wow['pBTCpuSimulate'], self.fex['BTCpuSimulate'])
        self.state = {}
        self.native = {}
        if elf:
            base = 0x1000000
            with elf.open('rb') as stream:
                binary = ELFFile(stream)
                self.native = {s.name: base+s['st_value'] for s in binary.get_section_by_name('.symtab').iter_symbols()}
                for segment in binary.iter_segments():
                    if segment['p_type'] != 'PT_LOAD':
                        continue
                    va, size = segment['p_vaddr'], segment['p_memsz']
                    low, high = va & ~4095, (va+size+4095) & ~4095
                    self.vm.mem_map(base+low, high-low)
                    self.vm.mem_write(base+va, segment.data())
                for relocation in binary.get_section_by_name('.relr.dyn').iter_relocations():
                    address = base+relocation['r_offset']
                    self.q(address, base+self.readq(address))
                for name, address in self.native.items():
                    if name.startswith('__wine_dbch_'):
                        self.vm.mem_write(address, b'\0')
        self.omit_export = None
        self.deliver_guest = False
        self.guest_context = bytearray(0x2cc)
        self.vm.hook_add(UC_HOOK_CODE, self.hook)

    def q(self, address, value):
        self.vm.mem_write(address, struct.pack('<Q', value))

    def readq(self, address):
        return struct.unpack('<Q', self.vm.mem_read(address, 8))[0]

    def ret(self, value=0):
        self.vm.reg_write(reg(0), value)
        self.vm.reg_write(arm.UC_ARM64_REG_PC, self.vm.reg_read(reg(30)))

    def string(self, address):
        data = bytearray()
        while self.vm.mem_read(address+len(data), 1) != b'\0':
            data.extend(self.vm.mem_read(address+len(data), 1))
            assert len(data) < 512
        return data.decode()

    def hook(self, vm, pc, size, user):
        if pc in self.imports:
            raise AssertionError('Unexpected import: '+self.imports[pc])
        if pc == self.native.get('RtlFindExportedRoutineByName'):
            base, name = vm.reg_read(reg(0)), self.string(vm.reg_read(reg(1)))
            module = next(pe for pe, _, b in self.modules.values() if b == base)
            result = next((base+s.address for s in module.DIRECTORY_ENTRY_EXPORT.symbols
                           if s.name and s.name.decode() == name and name != self.omit_export), 0)
            self.ret(result)
        elif pc == self.native.get('NtCurrentTeb'):
            self.ret(TEB)
        elif pc == self.native.get('wine_nx_runtime_trace'):
            self.state.setdefault('logs', []).append(self.string(vm.reg_read(reg(0))))
            self.ret()
        elif pc == STUB:
            self.state['returned'] = True
            vm.emu_stop()
        elif pc == self.fex['BTCpuSimulateImpl']:
            self.state['captured'] = vm.reg_read(reg(0))
            vm.emu_stop()
        elif pc == self.wow['Wow64PassExceptionToGuest']:
            self.state['guest_handler'] = vm.reg_read(reg(0))
            if not self.deliver_guest:
                vm.emu_stop()
        elif self.deliver_guest and pc == self.fex['BTCpuResetToConsistentState']:
            # This second prepare callback sees native EntryContext, outside
            # JIT; the hardware trace confirms FEX returns STATUS_SUCCESS.
            self.state['native_prepare'] = True
            self.ret()
        elif self.deliver_guest and pc == self.nt['RtlWow64GetThreadContext']:
            vm.mem_write(vm.reg_read(reg(1)), bytes(self.guest_context))
            self.ret()
        elif self.deliver_guest and pc == self.nt['RtlWow64SetThreadContext']:
            source = vm.reg_read(reg(1))
            requested = bytes(vm.mem_read(source, 0x2cc))
            assert struct.unpack_from('<I', requested)[0] == 0x10001
            self.guest_context[0xb4:0xcc] = requested[0xb4:0xcc]
            self.state['guest_context_set'] = True
            self.ret()
        elif self.deliver_guest and pc == self.nt['NtContinue']:
            context = bytes(vm.mem_read(vm.reg_read(reg(0)), 0x390))
            self.state['continued'] = context
            for i in range(31):
                vm.reg_write(reg(i), struct.unpack_from('<Q', context, 8+8*i)[0])
            sp, resume = struct.unpack_from('<2Q', context, 0x100)
            vm.reg_write(arm.UC_ARM64_REG_SP, sp)
            vm.reg_write(arm.UC_ARM64_REG_PC, resume)
        elif pc == self.nt.get('__wine_dbg_get_channel_flags'):
            self.ret(0)
        elif pc == self.nt.get('RtlFreeHeap'):
            assert vm.reg_read(reg(2)) == 0
            self.ret(1)
        elif pc == self.nt.get('NtRaiseException'):
            self.state['raised'] = vm.reg_read(reg(0))
            vm.emu_stop()
        elif pc == self.nt.get('RtlRaiseStatus'):
            self.state['raise_status'] = vm.reg_read(reg(0)) & 0xffffffff
            vm.emu_stop()
        elif pc == self.nt.get('virtual_unwind'):
            context = vm.reg_read(reg(2))
            frame = struct.unpack('<3Q', vm.mem_read(context+0xf8, 24))
            seen = self.state.setdefault('unwind_frames', [])
            seen.append(frame)
            if len(seen) > 12:
                self.state['unwind_loop'] = True
                vm.emu_stop()

    def call(self, name, *args, symbols=None, count=100000):
        self.state.clear()
        for i in range(8):
            self.vm.reg_write(reg(i), args[i] if i < len(args) else 0)
        # Keep the captured CPU simulation frames at the upper end intact.
        self.vm.reg_write(arm.UC_ARM64_REG_SP, STACK+0x60000)
        self.vm.reg_write(reg(18), TEB)
        self.vm.reg_write(reg(30), STUB)
        self.vm.emu_start((symbols or self.nt)[name], 0, count=count)
        assert any(n in self.state for n in ('returned', 'captured', 'guest_handler', 'raised', 'raise_status', 'unwind_loop')), f'No bounded completion for {name}, pc={self.vm.reg_read(arm.UC_ARM64_REG_PC):x}'
        return self.vm.reg_read(reg(0))

    def capture(self):
        self.state.clear()
        self.vm.reg_write(arm.UC_ARM64_REG_SP, STACK+0x7f000)
        self.vm.reg_write(reg(18), TEB)
        self.vm.reg_write(reg(29), STACK+0x7f100)
        self.vm.reg_write(reg(30), STUB)
        self.vm.emu_start(self.wow['cpu_simulate'], 0, count=5000)
        assert 'captured' in self.state
        return bytes(self.vm.mem_read(self.state['captured'], 0x390))

    def module_tree(self):
        # Native bootstrap already owns these LDR entries. Build a balanced
        # three-node tree, including the module containing the unwinder itself.
        entries = {}
        for index, name in enumerate(('fex', 'ntdll', 'wow64')):
            pe, _, base = self.modules[name]
            entry = DATA+0x4000+index*0x200
            entries[name] = entry
            self.q(entry+0x30, base)
            self.vm.mem_write(entry+0x40, struct.pack('<I', pe.OPTIONAL_HEADER.SizeOfImage))
        middle = entries['ntdll']+0xc8
        left, right = entries['fex']+0xc8, entries['wow64']+0xc8
        self.q(middle, left)
        self.q(middle+8, right)
        self.q(left+16, middle)
        self.q(right+16, middle)
        self.q(DATA+0x5000, middle)
        self.q(DATA+0x5008, left)
        return entries

    def bind_tree(self):
        shared = self.nt.get('wine_nx_pe_module_index')
        if shared and self.native:
            assert self.call('pes13_fex_install_dispatcher', self.modules['ntdll'][2], DATA+0x5000,
                             self.modules['fex'][2], self.modules['wow64'][2], symbols=self.native) == 0
            assert any('[FEX3-UNWIND] PASS' in line for line in self.state['logs'])
            assert self.readq(shared) == DATA+0x5000
        elif shared:
            self.q(shared, DATA+0x5000)
        else:
            # Diagnostic repair of the old binary only, never a shipped patch.
            self.vm.mem_write(self.nt['base_address_index_tree'],
                              bytes(self.vm.mem_read(DATA+0x5000, 16)))

    def check_tree_mutations(self):
        """Bootstrap insertions and subsequent PE unloads share RB invariants."""
        tree = DATA+0x6000
        rng = random.Random(0x46455833)
        operations = 0
        for trial in range(6):
            self.vm.mem_write(tree, bytes(16))
            keys = list(range(48))
            if trial % 3 == 1:
                keys.reverse()
            elif trial % 3 == 2:
                rng.shuffle(keys)
            addresses = {DATA+0x8000+key*32: key for key in keys}
            live = set()

            def validate():
                root = self.readq(tree)
                visited = set()

                def walk(node, parent, lo, hi):
                    if not node:
                        return 1
                    assert node not in visited and node in addresses
                    visited.add(node)
                    key = addresses[node]
                    left, right, pv = struct.unpack('<3Q', self.vm.mem_read(node, 24))
                    assert lo < key < hi and (pv & ~3) == parent
                    red = pv & 1
                    if red:
                        assert not left or not (self.readq(left+16) & 1)
                        assert not right or not (self.readq(right+16) & 1)
                    lh, rh = walk(left, node, lo, key), walk(right, node, key, hi)
                    assert lh == rh, 'Native/PE tree black height differs'
                    return lh + (not red)

                walk(root, 0, -1, 49)
                assert {addresses[n] for n in visited} == live
                if root:
                    assert not (self.readq(root+16) & 1)
                    assert addresses[self.readq(tree+8)] == min(live)
                else:
                    assert not live and self.readq(tree+8) == 0

            for i, key in enumerate(keys):
                parent, node, right = 0, self.readq(tree), 0
                while node:
                    parent = node
                    right = int(key > addresses[node])
                    node = self.readq(node+8*right)
                symbols = self.native if trial < 3 or i % 2 else self.nt
                self.call('RtlRbInsertNodeEx', tree, parent, right, DATA+0x8000+key*32, symbols=symbols)
                live.add(key)
                validate()
                operations += 1
            rng.shuffle(keys)
            for i, key in enumerate(keys):
                symbols = self.nt if i % 2 else self.native
                self.call('RtlRbRemoveNode', tree, DATA+0x8000+key*32, symbols=symbols)
                live.remove(key)
                validate()
                operations += 1
        return operations

    def check_guest_delivery(self):
        """Real PE dispatcher -> WOW64 frame -> RtlUnwind -> CPU simulation.

        Only NT guest Get/SetContext and final native NtContinue are modeled;
        neither the PE unwinder nor the x86 exception-frame builder is skipped.
        Actual execution of the x86 VEH remains the hardware stress test.
        """
        context = self.capture()
        for name in ('GetContext', 'SetContext', 'ResetToConsistentState'):
            self.q(self.wow['pBTCpu'+name], self.fex['BTCpu'+name])
        self.q(self.nt['pWow64PrepareForException'], self.wow['Wow64PrepareForException'])
        self.vm.mem_write(self.wow['current_machine'], struct.pack('<H', 0x14c))
        self.vm.mem_write(self.wow['native_machine'], struct.pack('<H', 0xaa64))
        self.vm.mem_write(self.wow['ss32_sel'], struct.pack('<H', 0x2b))
        self.q(self.wow['pLdrSystemDllInitBlock'], DATA+0x7000)
        self.q(DATA+0x7020, 0x70000100)
        self.vm.mem_map(0x30000000, 0x10000)
        struct.pack_into('<I', self.guest_context, 0, 0x1003f)
        struct.pack_into('<6I', self.guest_context, 0xb4, 0x3000f080, 0x02640040, 0x23, 0x202, 0x3000f000, 0x2b)
        original_guest = bytes(self.guest_context)
        sp = struct.unpack_from('<Q', context, 0x100)[0]
        frame = sp-0x470
        record = struct.pack('<IIQQIIQQ', 0xc0000005, 0, 0, 0x02640040, 2, 0, 0, 0x02650000)
        self.vm.mem_write(frame, context)
        self.vm.mem_write(frame+0x390, struct.pack('<iIiIiI', -0x390, 0x460, -0x390, 0x390, 0xd0, 0))
        self.vm.mem_write(frame+0x3b0, record+bytes(0x98-len(record)))
        self.vm.mem_write(frame+0x448, struct.pack('<3Q', 0, sp, struct.unpack_from('<Q', context, 0x108)[0]))
        self.state.clear()
        self.deliver_guest = True
        self.vm.reg_write(reg(18), TEB)
        self.vm.reg_write(arm.UC_ARM64_REG_SP, frame)
        self.vm.emu_start(self.nt['KiUserExceptionDispatcher'], 0, count=250000)
        assert self.state.get('native_prepare') and self.state.get('guest_context_set'), self.state
        assert 'continued' in self.state and 'captured' in self.state, self.state
        eip, esp = struct.unpack_from('<I', self.guest_context, 0xb8)[0], struct.unpack_from('<I', self.guest_context, 0xc4)[0]
        assert eip == 0x70000100 and 0x30000000 <= esp < 0x3000f000
        assert struct.unpack('<2I', self.vm.mem_read(esp, 8)) == (esp+8, esp+0x58)
        assert struct.unpack('<7I', self.vm.mem_read(esp+8, 28)) == (0xc0000005, 0, 0, 0x02640040, 2, 0, 0x02650000)
        assert bytes(self.vm.mem_read(esp+0x58, 0x2cc)) == original_guest
        restored_sp = struct.unpack_from('<Q', self.state['continued'], 0x100)[0]
        assert restored_sp == STACK+0x7f000-16, 'RtlUnwind must resume original cpu_simulate frame'
        self.deliver_guest = False


def main():
    if not __debug__:
        raise RuntimeError('Unwind validation requires Python assertions; disable -O/-OO and PYTHONOPTIMIZE')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ntdll', type=Path)
    parser.add_argument('fex', type=Path)
    parser.add_argument('wow64', type=Path)
    parser.add_argument('--elf', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    m = Model(args.ntdll, args.fex, args.wow64, args.elf)
    context = m.capture()
    pc = struct.unpack_from('<Q', context, 0x108)[0]
    m.module_tree()
    missing = m.call('RtlLookupFunctionEntry', pc, DATA+0x800, 0)
    print('Before native index handoff: function entry =', hex(missing))
    assert missing == 0, 'Fresh PE tree should not know native bootstrap modules'
    m.vm.mem_write(DATA, context)
    m.vm.mem_write(DATA+0x1000, struct.pack('<IIQQIIQQ', 0xc0000005, 0, 0, 0x2640040, 2, 0, 0, 0x2650000))
    m.call('dispatch_exception', DATA+0x1000, DATA)
    print('Before handoff: dispatcher state =', m.state)
    assert m.state.get('raise_status') == 0xc0000026 or m.state.get('unwind_loop'), m.state
    m.bind_tree()
    found = m.call('RtlLookupFunctionEntry', pc, DATA+0x800, 0)
    print('After native index handoff: function entry =', hex(found))
    assert found and m.readq(DATA+0x800) == m.modules['fex'][2]
    m.vm.mem_write(DATA, context)
    m.call('dispatch_exception', DATA+0x1000, DATA)
    print('After handoff: dispatcher state =', m.state)
    assert 'guest_handler' in m.state, m.state
    ptrs = m.state['guest_handler']
    assert m.readq(ptrs) == DATA+0x1000 and m.readq(ptrs+8) == DATA
    m.check_guest_delivery()
    tree_operations = m.check_tree_mutations() if args.elf else 0
    if args.elf:
        m.omit_export = 'wine_nx_pe_module_index'
        result = m.call('pes13_fex_install_dispatcher', m.modules['ntdll'][2], DATA+0x5000,
                        m.modules['fex'][2], m.modules['wow64'][2], symbols=m.native)
        assert result & 0xffffffff == 0xc0000059, 'Missing matching PE DLL must refuse startup'
        m.omit_export = None
    report = {'passed': True, 'ntdll_sha256': hashlib.sha256(args.ntdll.read_bytes()).hexdigest(),
              'fex_sha256': hashlib.sha256(args.fex.read_bytes()).hexdigest(),
              'wow64_sha256': hashlib.sha256(args.wow64.read_bytes()).hexdigest(),
              'shared_index_export': 'wine_nx_pe_module_index' in m.nt,
              'native_elf_sha256': hashlib.sha256(args.elf.read_bytes()).hexdigest() if args.elf else None,
              'tree_operations': tree_operations,
              'checks': ['Unshared bootstrap index reproduces a non-progressing exception unwind',
                         'Actual FEX capture and Wine .pdata/.xdata unwind reach WOW64 guest handler',
                         'PE dispatcher builds the correct x86 fault frame, unwinds and reenters CPU simulation',
                         'Shared tree root remains balanced through native/PE insertion and removal' if args.elf else 'Native ELF not supplied'],
              'hardware_guest_tested': False}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
