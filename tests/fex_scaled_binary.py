"""Run the delivered scaled-submit ARM64 helper and verify its caller checks errors."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import capstone
from elftools.elf.elffile import ELFFile
from unicorn import arm64_const as arm
from fex_reservations import Model as NativeModel, reg


class Model(NativeModel):
    def __init__(self, path):
        super().__init__(path)
        self.fake_submit = self.stop + 0x100
        self.outcome = 0
        self.calls = []
        self.queue, self.device, self.info = self.data, self.data + 0x1000, self.data + 0x4000
        # Pinned compiled struct offsets: host queue 0, device 0x30, dispatch slot 0x1228.
        self.q(self.queue, 42)
        self.q(self.queue + 0x30, self.device)
        self.q(self.device + 0x1228, self.fake_submit)
        self.original = bytes(range(72))
        self.vm.mem_write(self.info, self.original)

    def hook(self, vm, pc, size, user):
        if pc == self.symbols.get('wine_nx_fex_frame_tick'):
            self.ret(123456)
        elif pc == self.fake_submit:
            self.calls.append(('submit', *[vm.reg_read(reg(i)) for i in range(4)]))
            self.ret(self.outcome & 0xffffffff)
        elif pc == self.symbols.get('wine_nx_fex_pipeline_note'):
            self.calls.append(('metric', *[vm.reg_read(reg(i)) for i in range(3)]))
            self.ret()
        else:
            super().hook(vm, pc, size, user)

    def run(self, name, result):
        self.calls, self.outcome, self.returned = [], result, False
        self.vm.reg_write(arm.UC_ARM64_REG_SP, self.stack + 0xf000)
        self.vm.reg_write(reg(30), self.stop)
        self.vm.reg_write(reg(0), self.queue)
        self.vm.reg_write(reg(1), self.info)
        self.vm.emu_start(self.symbols[name], 0, count=1000)
        assert self.returned
        assert self.vm.reg_read(reg(0)) & 0xffffffff == result & 0xffffffff
        assert self.calls == [('submit', 42, 1, self.info, 0), ('metric', 1, 123456, result & 0xffffffff)]
        assert self.vm.mem_read(self.info, 72) == self.original


def main():
    if not __debug__:
        raise RuntimeError('Assertions required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.elf.open('rb') as stream:
        elf = ELFFile(stream)
        symbols = {s.name: s for s in elf.get_section_by_name('.symtab').iter_symbols()}
        names = [n for n in symbols if n.startswith('nx_submit_scaled')]
        assert len(names) == 1, names
        helper = names[0]
        s = symbols['win32u_vkQueuePresentKHR']
        section = elf.get_section(s['st_shndx'])
        offset = s['st_value'] - section['sh_addr']
        instructions = list(capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM).disasm(
            section.data()[offset:offset+s['st_size']], s['st_value']))
        calls = [i for i, ins in enumerate(instructions)
                 if ins.mnemonic == 'bl' and ins.op_str == '#' + hex(symbols[helper]['st_value'])]
        assert len(calls) == 1
        following = instructions[calls[0]+1:calls[0]+5]
        assert any(i.mnemonic == 'cbnz' and i.op_str.startswith('w0,') for i in following), following
    model = Model(args.elf)
    for result in (0, -1, -2, -4):
        model.run(helper, result)
    report = {'passed': True, 'native_elf_sha256': hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              'checks': ['Actual helper submits once, retains command/semaphore pointers, preserves VkResult',
                         'Success/OOM/device-lost paths feed existing metrics',
                         'Linked caller branches on nonzero blit-submit status'],
              'scope': 'Actual ARM64 instructions under Unicorn; GPU calls modeled', 'hardware_tested': False}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS linked scaled submit and caller error check')


if __name__ == '__main__':
    main()
