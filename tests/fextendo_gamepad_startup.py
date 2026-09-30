"""Catch the linked startup HID reset missed by isolated XInput tests.

Audits all direct ARM64 callers and executes the old reset's argument setup
and the new shared HID initializer. Models SDK calls, not an entire Wine boot.
"""
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import struct
from elftools.elf.elffile import ELFFile
from fextendo_silent import Model as Base, reg, arm

def callers(path):
    with path.open('rb') as f:
        elf=ELFFile(f);symbols=list(elf.get_section_by_name('.symtab').iter_symbols())
        targets={s['st_value']:s.name for s in symbols if s.name in
                 ('padConfigureInput','hidSetSupportedNpadIdType','hidSetSupportedNpadStyleSet')}
        functions=sorted((s['st_value'],s.name) for s in symbols if s['st_info']['type']=='STT_FUNC')
        addresses=[a for a,_ in functions];text=elf.get_section_by_name('.text');found=[]
        for i,(op,) in enumerate(struct.iter_unpack('<I',text.data())):
            if op&0x7c000000!=0x14000000:continue
            imm=op&0x3ffffff
            if imm&(1<<25):imm-=1<<26
            pc=text['sh_addr']+i*4;target=pc+4*imm
            if target in targets:
                found.append({'function':functions[bisect.bisect_right(addresses,pc)-1][1],
                              'pc':pc,'target':targets[target]})
        return found

class Model(Base):
    def __init__(self,path):
        super().__init__(path);self.configuration=[];self.orientation=[];self.capture_only=False

    def hook(self,vm,pc,size,user):
        s=self.symbols
        if pc==self.stop:
            self.returned=True;vm.emu_stop()
        elif pc==s.get('padConfigureInput'):
            self.configuration.append([vm.reg_read(reg(0)),vm.reg_read(reg(1))])
            if self.capture_only:self.returned=True;vm.emu_stop()
            else:self.ret()
        elif pc==s.get('hidSetNpadJoyHoldType'):
            self.orientation.append(vm.reg_read(reg(0)));self.ret()
        elif pc==s.get('memset'):
            dest,value,n=[vm.reg_read(reg(i)) for i in range(3)]
            vm.mem_write(dest,bytes([value&255])*n);self.ret(dest)
        elif pc in {s.get('fopen'),s.get('write'),s.get('fprintf')}:
            raise AssertionError('Controller initializer must not load the obsolete players.txt setting')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path)
    p.add_argument('--before',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();old=callers(a.before);new=callers(a.elf)
    reset=[c for c in old if c['function']=='main' and c['target']=='padConfigureInput'];assert len(reset)==1
    m=Model(a.before);m.capture_only=True
    # Two MOV instructions directly before the v1 reset: w1=style, w0=1.
    m.vm.emu_start(0x1000000+reset[0]['pc']-8,0,count=4)
    assert m.configuration==[[1,31]],m.configuration
    assert [c['function'] for c in new if c['target']=='padConfigureInput']==['fx_pads_once'],new
    assert all(c['function']=='padConfigureInput' for c in new if c['target'].startswith('hidSetSupportedNpad'))
    m=Model(a.elf);m.call('fx_pads_once')
    assert m.configuration==[[2,31]] and m.orientation==[1]
    pads=m.symbols['fx_native_pads']
    assert bytes(m.vm.mem_read(pads,4))==b'\x01\0\x01\0' # No1 + handheld
    assert bytes(m.vm.mem_read(pads+56,4))==b'\x02\0\0\0' # No2 only
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
            'before_native_elf_sha256':hashlib.sha256(a.before.read_bytes()).hexdigest(),
            'before_reset_players':1,'after_configure_players':2,'after_callers':new,
            'checks':['v1 main really passes max_players=1 after launcher',
                      'v2 has exactly one HID configuration owner; no Wine startup reset remains',
                      'Real ARM64 initializer enables two controllers, horizontal grip and stable No1/No2 masks']}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
