"""Run the delivered ARM64 controller shortcut and monitor-owned OSK.

Physical HID, VI surface creation and Wine window services are modeled. This
checks the actual native state machine and key pump, not Switch gameplay.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from fextendo_osk_binary import Model as Overlay, reg


class Model(Overlay):
    def __init__(self,path):
        super().__init__(path)
        self.displays=0
        self.display_functions={v for n,v in self.symbols.items() if n.startswith('fx_osk_display_show')}
        self.pads=[(1,1,0,0,0,0,0),(1,1,0,0,0,0,0)]

    def hook(self,vm,pc,size,user):
        names=self.symbols
        if pc in self.display_functions:
            self.displays+=1;assert vm.reg_read(reg(1))==0;self.ret(1)
        elif pc==names.get('hidGetTouchScreenStates'):self.ret(0)
        elif pc==names.get('fx_osk_display_close'):self.ret()
        else:super().hook(vm,pc,size,user)

    def chord(self,choice,style,connected,buttons,player=0):
        self.vm.mem_write(self.symbols['fx_keyboard_options'],struct.pack('<ii',choice,0))
        self.pads[player]=(style,connected,buttons,0,0,0,0)
        self.state(player);self.counter_ms+=599;self.state(player)
        assert not self.get('fx_keyboard_manual_pending')
        self.counter_ms+=1;self.state(player)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();cases=[]
    for style,connected in ((1,1),(4,21),(2,21)):
        m=Model(a.elf);m.chord(2,style,connected,(1<<6)|(1<<7)|(1<<10))
        assert m.get('fx_keyboard_manual_pending')==1
        m.step() # Wine has not pumped or supplied a focused window yet.
        assert m.displays==1 and m.get('fx_osk_phase')==2 and m.get('fx_osk_unclaimed')==1
        # A delayed Wine pump no longer expires the display request.
        m.counter_ms+=2200;m.pads[0]=(style,connected,0,0,0,0,0)
        m.pads[1]=(1,1,1,20000,0,0,0);m.step()
        core=bytes(m.vm.mem_read(m.symbols['fx_osk_state'],180))
        assert struct.unpack_from('<i',core,156)[0]==1 # armed, despite P2 holding input
        m.pump();assert m.get('fx_osk_unclaimed')==0
        m.key(character='a');m.close();assert m.field_text()=='Nunua'
        m.step();assert not m.get('fx_osk_blocking') # P2 cannot delay the drain
        cases.append({'style':style,'native_open':True,'delayed_wine_claim':True,'p2_ignored':True})
    for choice,buttons in ((0,(1<<6)|(1<<7)|(1<<4)),(1,(1<<10)|(1<<11)),
                          (2,(1<<6)|(1<<7)|(1<<10)),(3,(1<<8)|(1<<9)|(1<<11))):
        m=Model(a.elf);m.chord(choice,1,1,buttons,player=1);m.step()
        assert not m.displays and not m.get('fx_osk_blocking')
    m=Model(a.elf);m.chord(2,1,1,(1<<6)|(1<<7)|(1<<10));m.step()
    # Can dismiss without waiting for Wine to claim/send any keys.
    m.pads[0]=(1,1,0,0,0,0,0);m.step()
    m.pads[0]=(1,1,1<<11,0,0,0,0);m.step()
    m.pads[0]=(1,1,0,0,0,0,0);m.step()
    assert not m.get('fx_osk_blocking') and not m.get('fx_osk_unclaimed')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps({'passed':True,'hardware_tested':False,
        'elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),'cases':cases,
        'p2_all_shortcuts_rejected':True,'unclaimed_close_checked':True,
        'limits':'HID, VI and OS services modeled; test on Switch still required.'},indent=2)+'\n')
    print('PASS: native P1 L+R+Plus display, delayed Wine claim, P2 exclusion and close/drain')


if __name__=='__main__':main()
