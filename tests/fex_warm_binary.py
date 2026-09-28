"""Check linked warm observers and execute the ARM64 cache wrapper with modeled I/O."""
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
    def hook(self, vm, pc, size, user):
        if pc == self.symbols.get('disk_cache_get'):
            self.calls += 1
            assert [vm.reg_read(reg(i)) for i in range(3)] == [self.data, self.data+0x100, self.data+0x200]
            self.q(self.data+0x200, 123 if self.hit else 0)
            self.ret(self.data+0x300 if self.hit else 0)
        elif pc in {self.symbols.get('armGetSystemTick'), self.symbols.get('wine_nx_fex_frame_tick')}:
            self.ret(19200000)
        else:
            super().hook(vm, pc, size, user)

    def run(self, hit):
        self.hit, self.calls, self.returned = hit, 0, False
        self.vm.mem_write(self.data+0x100, bytes(range(32)))
        self.vm.reg_write(arm.UC_ARM64_REG_SP, self.stack+0xf000)
        self.vm.reg_write(reg(30), self.stop)
        for i, value in enumerate((self.data, self.data+0x100, self.data+0x200)):
            self.vm.reg_write(reg(i), value)
        self.vm.emu_start(self.symbols['__wrap_disk_cache_get'], 0, count=20000)
        assert self.returned and self.calls == 1
        assert self.vm.reg_read(reg(0)) == (self.data+0x300 if hit else 0)
        assert self.uq(self.data+0x200) == (123 if hit else 0)
        assert self.vm.mem_read(self.data+0x100,32) == bytes(range(32))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with args.elf.open('rb') as stream:
        elf=ELFFile(stream)
        symbols={s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
        def calls(name,target):
            s=symbols[name]; section=elf.get_section(s['st_shndx'])
            offset=s['st_value']-section['sh_addr']
            ins=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM).disasm(
                section.data()[offset:offset+s['st_size']],s['st_value'])
            return [i.address for i in ins if i.mnemonic in ('b','bl') and
                    i.op_str=='#'+hex(symbols[target]['st_value'])]
        bindings=[]
        for bits in (32,64):
            for kind in ('Graphics','Compute'):
                name=f'thunk{bits}_vkCreate{kind}Pipelines'
                if bits==64 and name not in symbols: continue
                assert len(calls(name,'wine_nx_fex_compile_note'))==1,name
                assert len(calls(name,'wine_nx_fex_frame_tick'))==1,name
                bindings.append(name)
        assert len(calls('__wrap_disk_cache_get','disk_cache_get'))==1
        # Verify at least the Vulkan runtime's real disk-cache consumer uses
        # the wrapper; having an unused wrapper symbol alone is insufficient.
        consumers=[name for name,s in symbols.items() if s['st_size'] and
                   'pipeline_cache' in name and calls(name,'__wrap_disk_cache_get')]
        assert consumers, 'Vulkan pipeline cache does not call the wrapper'
    model=Model(args.elf)
    for hit in (False,True): model.run(hit)
    assert model.uq(model.symbols['fex_warm_hits'])==1
    assert model.uq(model.symbols['fex_warm_misses'])==1
    report={'passed':True, 'hardware_tested':False,
            'native_elf_sha256':hashlib.sha256(args.elf.read_bytes()).hexdigest(),
            'pipeline_bindings':bindings, 'cache_consumers':consumers,
            'cache_wrapper_hit_miss_pointer_size_passthrough':True,
            'scope':'Linked ARM64 code; disk I/O modeled, no Switch timing claim'}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
