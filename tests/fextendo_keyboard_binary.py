"""Execute the linked ARM64 text bridge and applet monitor with modeled libnx.

The keyboard UI, OS focus, HID and mutex services are modeled. This does not
certify PES text acceptance; request, codec, drain, packet and result logic run
from the delivered ELF. Any attempted storage write fails the check.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from fextendo_gamepad_binary import Model as Pads, reg


class Model(Pads):
    def __init__(self,path):
        super().__init__(path)
        self.pads=[(4,21,0,0,0,0,0),(4,21,0,0,0,0,0)]
        self.opens=0;self.closes=0;self.initial=[];self.cancel=False;self.hold=False;self.monitor=False
        self.validation_callback=0
        self.text='Test é 😀'
        self.focus_mode=3;self.focus_changes=[];self.lock_stack=[];self.keyboard_waits=0
        self.set('fx_keyboard_ready',1)
        self.set('fx_game_active',1)
        self.set('fx_pad_session_captured',1)
        self.vm.mem_write(self.symbols['fx_recovery'],struct.pack('<II',0,3))

    def set(self,name,value):self.vm.mem_write(self.symbols[name],struct.pack('<I',value))
    def get(self,name):return struct.unpack('<I',self.vm.mem_read(self.symbols[name],4))[0]

    def hook(self,vm,pc,size,user):
        s=self.symbols
        if pc==s.get('pthread_mutex_lock'):
            address=vm.reg_read(reg(0));assert address not in self.lock_stack
            if self.lock_stack:assert self.lock_stack==[s['fx_pad_applet_lock']] and address==s['fx_pad_lock']
            self.lock_stack.append(address);self.locks+=1;self.ret()
        elif pc==s.get('pthread_mutex_unlock'):
            assert self.lock_stack.pop()==vm.reg_read(reg(0));self.locks-=1;self.ret()
        elif pc==s.get('pthread_cond_broadcast'):self.ret()
        elif pc==s.get('pthread_cond_wait') and self.get('fx_keyboard_applet_active'):
            assert self.lock_stack==[s['fx_pad_lock']] and not self.get('fx_game_paused')
            self.keyboard_waits+=1
            # The applet worker completed its interactive reply/close, then
            # cleared the frame/input gate and broadcast the condition.
            self.set('fx_keyboard_applet_active',0);self.ret()
        elif pc==s.get('appletSetFocusHandlingMode'):
            assert self.get('fx_keyboard_applet_active')==1
            self.focus_mode=vm.reg_read(reg(0));self.focus_changes.append(self.focus_mode);self.ret()
        elif pc==s.get('appletMainLoop') or pc==s.get('appletGetFocusState'):self.ret(1)
        elif self.monitor and pc==s.get('svcSleepThread'):
            self.returned=True;vm.emu_stop()
        elif pc==s.get('swkbdCreate'):
            self.opens+=1
            # Config is stack memory; modeled setters below do not allocate a
            # real transfer-memory buffer or invoke the OS applet.
            # sizeof(SwkbdConfig) from the pinned libnx 4.12 swkbdCreate memset.
            assert bytes(vm.mem_read(s['swkbdCreate']+8,4))==bytes.fromhex('029e80d2')
            vm.mem_write(vm.reg_read(reg(0)),b'\0'*1264);self.ret()
        elif pc in {s.get('swkbdConfigSetInitialText'),s.get('swkbdConfigSetHeaderText'),
                    s.get('swkbdConfigSetGuideText')}:
            if pc==s.get('swkbdConfigSetInitialText'):self.initial.append(self.string(vm.reg_read(reg(1))))
            self.ret()
        elif pc==s.get('swkbdConfigSetTextCheckCallback'):
            self.validation_callback=vm.reg_read(reg(1));self.ret()
        elif pc==s.get('swkbdShow'):
            assert self.focus_mode==0 and self.get('fx_keyboard_applet_active')==1
            assert self.locks==1 # shared applet serialization held; no pad mutex
            assert vm.reg_read(reg(2))==1025
            vm.mem_write(vm.reg_read(reg(1)),self.text.encode()+b'\0')
            if self.hold:self.pads[1]=(4,21,1,0,0,0,0)
            self.ret(int(self.cancel))
        elif pc==s.get('swkbdClose'):self.closes+=1;self.ret()
        elif pc==s.get('snprintf'):
            dest,size,fmt=[vm.reg_read(reg(i)) for i in range(3)]
            text=self.string(fmt).encode();assert b'%' not in text and size
            vm.mem_write(dest,text[:size-1]+b'\0');self.ret(len(text))
        elif pc in self.forbidden:raise AssertionError('Keyboard attempted storage I/O: '+hex(pc))
        else:super().hook(vm,pc,size,user)

    def request(self):
        initial=('Old Save'.encode('utf-16le')+b'\0\0').ljust(514,b'\0')
        self.vm.mem_write(self.data,struct.pack('<QII',0x10020,1,32)+initial+b'\0'*6)
        return self.call('fx_keyboard_request',self.data)

    def step(self):
        self.monitor=True;self.call('fx_pads_monitor',0);self.monitor=False
        assert self.locks==0


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    m=Model(a.elf);token=m.request();assert token and not m.request()
    m.hold=True;m.step();assert m.opens==m.closes==1 and m.initial==['Old Save']
    assert m.focus_changes==[0,3] and not m.get('fx_keyboard_applet_active')
    assert m.get('fx_keyboard_phase')==3 and m.get('fx_keyboard_blocked')==1
    assert not m.call('fx_keyboard_take',token,m.data+0x1000)
    m.hold=False;m.pads[1]=(4,21,0,0,0,0,0);m.step()
    assert m.get('fx_keyboard_phase')==4
    assert m.call('fx_keyboard_take',token,m.data+0x1000)==1
    result=bytes(m.vm.mem_read(m.data+0x1000,520))
    assert struct.unpack('<I',result[:4])[0]==1
    assert result[4:].decode('utf-16le').split('\0')[0]=='Test é 😀'
    assert m.call('fx_keyboard_delivering')==1 and not m.request()
    m.call('fx_keyboard_delivery_done');assert m.call('fx_keyboard_delivering')==0
    token=m.request();m.cancel=True;m.step()
    assert m.call('fx_keyboard_take',token,m.data+0x1000)==1
    assert bytes(m.vm.mem_read(m.data+0x1000,520))==b'\0'*520
    assert not m.call('fx_keyboard_delivering')
    # Cancel before opening, e.g. focus loss/destruction; a new owner can submit.
    token=m.request();m.call('fx_keyboard_cancel',token);assert m.get('fx_keyboard_phase')==0
    token=m.request();m.call('fx_keyboard_cancel_all');m.call('fx_keyboard_cancel_all')
    assert m.call('fx_keyboard_take',token,m.data+0x1000)==1
    assert not struct.unpack('<I',m.vm.mem_read(m.data+0x1000,4))[0]
    # Suppression/restoration changes the XInput packet even without a physical
    # state change, preventing a cached held button from surviving the applet.
    m.pads[0]=(4,21,1,1000,0,0,0);before=m.state(0)
    m.set('fx_keyboard_delivery',1);blocked=m.state(0)
    assert blocked[1]==1 and blocked[2]!=before[2] and blocked[3:]==(0,)*7
    m.call('fx_keyboard_delivery_done');after=m.state(0)
    assert after[2]!=blocked[2] and after[3:]==before[3:]
    m.set('fx_keyboard_applet_active',1);assert m.state(0)[1]==1
    assert m.keyboard_waits==1 and not m.get('fx_keyboard_applet_active')
    # HID temporarily hidden from the background app is not a physical loss.
    m.set('fx_keyboard_applet_active',1)
    m.pads=[(4,0,0,0,0,0,0),(4,0,0,0,0,0,0)]
    # The public snapshot wrapper is inlined in this build; execute its actual
    # shared polling implementation under the modeled input mutex.
    m.call('pthread_mutex_lock',m.symbols['fx_pad_lock'])
    m.call('fx_pads_poll_locked')
    m.call('pthread_mutex_unlock',m.symbols['fx_pad_lock'])
    assert not m.get('fx_game_paused')
    m.set('fx_keyboard_applet_active',0)
    waits=m.waits;m.state(0);assert m.waits==waits+1 # a real post-applet loss still pauses
    # Execute the actual ARM64 applet validation callback.
    m.vm.mem_write(m.data,b'\xf4\x90\x80\x80\0')
    assert m.call('fx_keyboard_validate',m.data,1025)==1
    m.vm.mem_write(m.data,'é😀'.encode()+b'\0')
    assert m.call('fx_keyboard_validate',m.data,1025)==0
    # Run physical libnx -> normalization -> timed shortcut on each player.
    # A request cannot suppress gameplay until Wine actually opens a keyboard.
    for player in (0,1):
        for style,connected,shoulders,stick in (
            (1,1,(1<<6)|(1<<7),1<<4),
            (4,21,(1<<6)|(1<<7),1<<4),
            (8,1,(1<<24)|(1<<25),1<<4),
            (16,1,(1<<26)|(1<<27),1<<5)):
            pad=Model(a.elf)
            pad.pads[player]=(style,connected,shoulders,0,0,0,0)
            pad.state(player);assert not pad.call('fx_keyboard_manual')
            pad.pads[player]=(style,connected,shoulders|stick,0,0,0,0)
            sample=pad.state(player)
            assert sample[1]==1 and sample[3]!=0 and not pad.call('fx_keyboard_manual')
            pad.counter_ms+=599;pad.state(player);assert not pad.call('fx_keyboard_manual')
            pad.counter_ms+=1;sample=pad.state(player)
            assert sample[3]!=0 and pad.call('fx_keyboard_manual')==1
            assert pad.call('fx_keyboard_manual_owner')==player
            assert pad.state(player)[3]!=0
            pad.state(player);assert not pad.call('fx_keyboard_manual')
            pad.pads[player]=(style,connected,shoulders,0,0,0,0)
            pad.state(player);assert not pad.call('fx_keyboard_manual')
            pad.pads[player]=(style,connected,shoulders|stick,0,0,0,0)
            pad.state(player);pad.counter_ms+=600;pad.state(player)
            assert pad.call('fx_keyboard_manual')==1
            pad.pads[player]=(style,connected,shoulders,20000,0,0,0)
            pad.state(player)
            pad.pads[player]=(style,connected,shoulders|stick,20000,0,0,0)
            pad.state(player);pad.counter_ms+=600;pad.state(player)
            pad.counter_ms+=1001;assert not pad.call('fx_keyboard_manual')
            assert pad.state(player)[3]!=0
    report={'passed':True,'hardware_tested':False,
            'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
            'checks':['ARM64 request queue and single applet serialization',
                      'Native applet result UTF-8 to UTF-16 including surrogate pair',
                      'P2 button drain, Cancel, repeated reconnect cancellation and stale tokens',
                      'Keyboard delivery suppresses P1/P2 without disconnecting XInput; packets change',
                      'Native applet gates XInput; background HID absence does not trigger reconnect',
                      '600ms shortcut on P1/P2 full, paired and horizontal L/R Joy-Con; no repeat',
                      'Pending/stale shortcut never latches XInput; analog motion does not prevent rearming',
                      'Native validation rejects malformed Unicode without storage writes']}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
