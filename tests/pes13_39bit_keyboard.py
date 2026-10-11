"""Run the delivered ARM64 controller shortcut and monitor-owned OSK.

Physical HID, presenter acknowledgement and Wine window services are modeled. This
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
        self.display_fail=False
        self.display_wait=False
        self.display_functions={v for n,v in self.symbols.items() if n.startswith('fx_osk_display_show')}
        self.pads=[(1,1,0,0,0,0,0),(1,1,0,0,0,0,0)]

    def hook(self,vm,pc,size,user):
        names=self.symbols
        if pc in self.display_functions:
            self.displays+=1;assert vm.reg_read(reg(1))==0;self.ret(0 if self.display_fail else 2 if self.display_wait else 1)
        elif pc==names.get('hidGetTouchScreenStates'):self.ret(0)
        elif pc==names.get('fx_osk_display_close'):self.ret()
        else:super().hook(vm,pc,size,user)

    def chord(self,choice,style,connected,buttons,player=0,hold_ms=0):
        self.vm.mem_write(self.symbols['fx_keyboard_options'],struct.pack('<iii',choice,0,hold_ms))
        self.pads[player]=(style,connected,buttons,0,0,0,0)
        self.state(player)
        if hold_ms:
            assert not self.get('fx_keyboard_manual_pending')
            self.counter_ms+=hold_ms-1;self.state(player)
            assert not self.get('fx_keyboard_manual_pending')
            self.counter_ms+=1;self.state(player)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--before',type=Path,help='Reproduce capture after a first-surface failure in the old build')
    a=p.parse_args();cases=[]
    def fail_before_first_frame(path):
        m=Model(path);m.display_fail=True;m.chord(2,1,1,(1<<6)|(1<<7)|(1<<10))
        m.pump();assert m.get('fx_osk_phase')==1 and not m.get('fx_osk_unclaimed')
        m.step();m.pads[0]=(1,1,0,0,0,0,0);m.pads[1]=(1,1,1,0,0,0,0);m.step()
        return m
    if a.before:
        old=fail_before_first_frame(a.before)
        assert old.get('fx_osk_blocking') and old.get('fx_osk_phase')==3
    recovered=fail_before_first_frame(a.elf)
    assert not recovered.get('fx_osk_blocking') and recovered.get('fx_osk_phase')==0
    recovered.pump();assert not recovered.pressed
    pending=Model(a.elf);pending.display_wait=True
    pending.chord(2,1,1,(1<<6)|(1<<7)|(1<<10));pending.step();pending.pump()
    assert pending.get('fx_osk_phase')==1
    pending.pads[0]=(1,1,0,0,0,0,0);pending.step()
    pending.pads[0]=(1,1,1,0,0,0,0);pending.step();pending.pump()
    assert pending.get('fx_osk_phase')==1 and not pending.pressed and pending.field_text()=='Nunu'
    pending.display_fail=True;pending.step()
    pending.pads[0]=(1,1,0,0,0,0,0);pending.step()
    assert not pending.get('fx_osk_blocking') # no Wine pump needed after no-present failure
    for hold in (0,300,600,1000,1500,2000):
      for style,connected in ((1,1),(4,21),(2,21)):
        m=Model(a.elf);m.chord(2,style,connected,(1<<6)|(1<<7)|(1<<10),hold_ms=hold)
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
        cases.append({'style':style,'hold_ms':hold,'native_open':True,'delayed_wine_claim':True,'p2_ignored':True})
    for choice,buttons in ((0,(1<<6)|(1<<7)|(1<<4)),(1,(1<<10)|(1<<11)),
                          (2,(1<<6)|(1<<7)|(1<<10)),(3,(1<<8)|(1<<9)|(1<<11))):
        for hold in (0,300,600,1000,1500,2000):
            m=Model(a.elf);m.chord(choice,1,1,buttons,player=1,hold_ms=hold);m.step()
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
        'first_surface_failure_without_wine_pump':True,'no_keys_before_present_ack':True,
        'before_elf_sha256':hashlib.sha256(a.before.read_bytes()).hexdigest() if a.before else None,
        'p2_all_shortcuts_rejected':True,'unclaimed_close_checked':True,
        'limits':'HID, presentation and OS services modeled; test on Switch still required.'},indent=2)+'\n')
    print('PASS: native P1 instant/all 5 hold presets, full/paired/handheld pads, delayed Wine claim, P2 exclusion and close/drain')


if __name__=='__main__':main()
