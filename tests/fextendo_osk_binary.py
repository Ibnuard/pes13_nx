"""Run the delivered ARM64 overlay queue and Wine key pump.

VI readiness is modeled; controller routing/render bounds are covered by the
host test. No key enqueue/dequeue, scan-code creation or Wine dispatch is
substituted. This is not a Switch or PES13 compatibility/performance test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from fextendo_keyboard_delivery import Model as Delivery, reg

class Model(Delivery):
    def __init__(self,path):
        super().__init__(path)
        self.field=list('Nunu');self.cursor=4;self.enters=0;self.times=[]
        self.cells=[]
        for i in range(59):
            self.cells.append(struct.unpack('<QHHBB2x',self.vm.mem_read(self.symbols['fx_osk_cells']+i*16,16)))

    def hook(self,vm,pc,size,user):
        if pc==self.symbols.get('NtUserMapVirtualKeyEx'):
            extras={8:14,13:28,0x25:0xe04b,0x27:0xe04d,0x26:0xe048,0x28:0xe050,
                    0x2e:0xe053,0x24:0xe047,0x23:0xe04f}
            if vm.reg_read(reg(0)) in extras:
                assert vm.reg_read(reg(1))==4;self.ret(extras[vm.reg_read(reg(0))]);return
        if pc==self.symbols.get('send_hardware_message'):
            old=len(self.events);super().hook(vm,pc,size,user)
            if len(self.events)==old:return
            vk,scan,flags=self.events[-1];self.times.append(self.milliseconds)
            if flags&2:return
            if vk==8 and self.cursor:self.cursor-=1;self.field.pop(self.cursor)
            elif vk==0x2e and self.cursor<len(self.field):self.field.pop(self.cursor)
            elif vk==0x25:self.cursor=max(0,self.cursor-1)
            elif vk==0x27:self.cursor=min(len(self.field),self.cursor+1)
            elif vk==0x24:self.cursor=0
            elif vk==0x23:self.cursor=len(self.field)
            elif vk==13:self.enters+=1
            elif 65<=vk<=90 or vk==32:
                self.field.insert(self.cursor,chr(vk if vk==32 or 16 in self.pressed else vk+32));self.cursor+=1
            return
        super().hook(vm,pc,size,user)

    def begin(self,player=0):
        self.set('fx_keyboard_manual_player',player);self.set('fx_keyboard_manual_pending',1);self.pump()
        assert self.get('fx_osk_phase')==1 and self.get('fx_osk_player')==player
        assert self.get('fx_keyboard_phase')==0 # custom field did not request native applet
        self.token=self.uq(self.symbols['fx_osk_serial'])
        assert self.call('fx_osk_valid',self.token)
        self.set('fx_osk_phase',2) # model successful VI creation/first presentation

    def activate(self,index):self.call('fx_osk_activate.constprop.0',index)

    def key(self,character=None,vk=None,action=None):
        if character and character.isupper():self.key(action=1);character=character.lower()
        matches=[i for i,(_,ch,key,act,_) in enumerate(self.cells)
                 if (character is not None and ch==ord(character)) or
                    (vk is not None and key==vk) or (action is not None and act==action)]
        assert len(matches)==1,(character,vk,action,matches)
        self.activate(matches[0])

    def close(self):
        self.key(action=3)
        for _ in range(400):
            if self.get('fx_osk_phase')==4:break
            self.pump()
        assert self.get('fx_osk_phase')==4 and not self.pressed
        assert self.get('fx_osk_blocking')==1 # actual monitor owns neutral drain

    def field_text(self):return ''.join(self.field)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path);p.add_argument('--before',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    old=Delivery(a.before);old.start('hallo');old.drain()
    assert old.text_received()=='h' and old.pressed=={ord('H')}
    m=Model(a.elf);before=m.state(0);m.begin(1)
    for slot in (0,1):
        m.pads[slot]=(4,21,1,20000,0,0,0)
        state=m.state(slot);assert state[1]==1 and state[3:]==(0,)*7
    assert m.state(0)[2]!=before[2]
    for _ in range(4):m.key(vk=8)
    for c in 'Bejo':m.key(character=c)
    m.close();assert m.field_text()=='Bejo' and not m.enters
    assert all(b-a>=50 for a,b in zip(m.times,m.times[1:])),m.times
    # No repeated text or Enter on a closed keyboard.
    count=len(m.events);m.pump();assert len(m.events)==count
    # Simulate completion of the monitor's neutral drain, then reopen same
    # custom window. The game field, not a remembered string, is the source.
    m.set('fx_osk_blocking',0);m.set('fx_osk_phase',0);m.begin()
    m.key(vk=0x25);m.key(vk=0x25);m.key(vk=0x2e);m.key(character='J');m.key(vk=13);m.close()
    assert m.field_text()=='BeJo' and m.enters==1
    assert any(vk==0x25 and scan==0x4b and flags&1 for vk,scan,flags in m.events)
    for reason in ('focus','destroy','disconnect','native-focus'):
        m=Model(a.elf);m.begin();m.key(character='H');m.key(character='i');m.pump();m.pump()
        assert m.pressed=={16,ord('H')}
        if reason=='focus':m.focus=m.foreground=0x10021
        elif reason=='destroy':m.call('wine_nx_drv_DestroyWindow',m.focus)
        elif reason=='disconnect':m.set('fx_game_paused',1);m.call('fx_keyboard_cancel_all')
        else:m.call('fx_osk_abort',0)
        m.pump();assert not m.pressed and m.field_text()=='NunuH' and m.get('fx_osk_phase')==4
    m=Model(a.elf);m.begin();m.key(character='H');m.fail_at=2;m.pump();m.pump()
    assert m.field_text()=='Nunu' and not m.pressed and m.send_calls==3 and m.get('fx_osk_phase')==4
    # A queued transaction cannot take over the native applet; stale overlay
    # tokens cannot close a later keyboard instance.
    m=Model(a.elf);m.request();assert not m.call('fx_osk_open',0)
    m=Model(a.elf);m.begin();old_token=m.token;m.close()
    m.set('fx_osk_blocking',0);m.set('fx_osk_phase',0);m.begin()
    m.call('fx_osk_abort',old_token);m.call('fx_osk_finished',old_token)
    assert m.call('fx_osk_valid',m.token)
    paths=[Path(__file__).resolve(),*(Path(__file__).with_name(n) for n in
           ('fextendo_keyboard_delivery.py','fextendo_keyboard_binary.py','fextendo_gamepad_binary.py','fextendo_silent.py','fex_reservations.py'))]
    root=Path(__file__).resolve().parents[1]
    report={'passed':True,'hardware_tested':False,
            'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
            'before_elf_sha256':hashlib.sha256(a.before.read_bytes()).hexdigest(),
            'test_sources':{str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
            'checks':['Real v2 status-handling regression reproduced; v4 live input uses NTSTATUS correctly',
                      'ARM64 overlay queue -> Wine dispatch edits Nunu to Bejo, reopens and edits middle to BeJo',
                      'Timed Shift/key press and release; real extended scan codes; explicit Enter only',
                      'Close drains queued edits before finish; no duplicate input; both XInput slots stay connected',
                      'Focus/destruction/reconnect/server error cancel queued edits and release Shift/keys',
                      'Native applet exclusion and stale token rejection; no key-pump file/log writes'],
            'limits':['VI presentation/neutral-drain completion modeled; no PES13 or hardware execution']}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
