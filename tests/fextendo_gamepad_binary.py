"""Execute delivered ARM64 XInput, slot polling and pause gate; model libnx HID.

This is not a hardware/app/input-latency test. No normalization/XInput function
is mocked. Only physical pad snapshots and native synchronization are modeled.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from fextendo_silent import Model as Base, arm, reg

class Model(Base):
    def __init__(self,path):
        super().__init__(path)
        self.pads=[(8,1,1<<15,0,-20000,0,0),(16,1,1<<2,0,0,0,20000)]
        self.calls=[];self.waits=0;self.locks=0
        self.counter_ms=1000
        self.vm.mem_write(self.symbols['fx_players'],struct.pack('<I',2))

    def hook(self,vm,pc,size,user):
        s=self.symbols
        # Physical counter reads are inlined by libnx. Model only the timer,
        # leaving the linked shortcut/XInput arithmetic and state untouched.
        instruction=struct.unpack('<I',vm.mem_read(pc,4))[0]
        if instruction&~31 in (0xd53be020,0xd53be000): # CNTPCT_EL0 / CNTFRQ_EL0
            vm.reg_write(reg(instruction&31),self.counter_ms*19200 if instruction&~31==0xd53be020 else 19200000)
            vm.reg_write(arm.UC_ARM64_REG_PC,pc+4);return
        if pc==self.stop:
            self.returned=True;vm.emu_stop()
        elif pc==s.get('pthread_once'):
            self.ret() # initialized shared controller service; no SD setting read
        elif pc==s.get('appletGetFocusState'):self.ret(1)
        elif pc==s.get('pthread_mutex_lock'):
            self.locks+=1;assert self.locks==1;self.ret()
        elif pc==s.get('pthread_mutex_unlock'):
            self.locks-=1;assert self.locks==0;self.ret()
        elif pc==s.get('pthread_cond_wait'):
            assert self.locks==1
            assert struct.unpack('<I',vm.mem_read(s['fx_game_paused'],4))[0]==1
            self.waits+=1
            # Model the monitor's explicit A+neutral-release completion, never an auto Start.
            self.pads[0]=(8,1,0,0,0,0,0)
            if not self.pads[1][1]:self.pads[1]=(16,1,0,0,0,0,0)
            vm.mem_write(s['fx_recovery'],struct.pack('<II',0,3))
            vm.mem_write(s['fx_game_paused'],b'\0'*4);self.ret()
        elif pc==s.get('padUpdate'):
            ptr=vm.reg_read(reg(0));index=(ptr-s['fx_native_pads'])//56
            assert index in (0,1);self.calls.append(index)
            style,connected,buttons,lx,ly,rx,ry=self.pads[index]
            vm.mem_write(ptr,struct.pack('<4BII4xQQ4iII',1<<index,(1<<index) if connected else 0,0,0,
                style if connected else 0,connected,buttons if connected else 0,0,lx,ly,rx,ry,0,0))
            self.ret()
        elif pc==s.get('memset'):
            dest,value,n=[vm.reg_read(reg(i)) for i in range(3)]
            vm.mem_write(dest,bytes([value&255])*n);self.ret(dest)
        elif pc==s.get('memcpy'):
            dest,src,n=[vm.reg_read(reg(i)) for i in range(3)]
            vm.mem_write(dest,bytes(vm.mem_read(src,n)));self.ret(dest)
        elif pc in {s.get('fopen'),s.get('fprintf'),s.get('fwrite'),s.get('write')}:
            raise AssertionError('XInput attempted file I/O')

    def state(self,index):
        self.vm.mem_write(self.data,struct.pack('<I',index)+b'\xaa'*20)
        assert self.call('nx_xinput_get_state_unix',self.data)==0
        assert self.locks==0
        return struct.unpack('<IIIHBB4h',self.vm.mem_read(self.data,24))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();m=Model(a.elf)
    one,two=m.state(0),m.state(1)
    assert one[1:]==(1,1,0x2000,0,0,20000,0,0,0),one
    assert two[1:]==(1,1,0x2000,0,0,20000,0,0,0),two
    m.pads[1]=(16,1,1,0,0,20000,0)
    changed=m.state(1);assert changed[2]==2 and changed[3]==0x1000 and changed[6:]==(0,-20000,0,0)
    assert m.state(0)==one
    m.pads[0]=(4,21,(1<<8)|(1<<9),1200,-3400,5600,-7800) # complete Joy-Con pair
    full=m.state(0);assert full[1]==1 and full[4:]==(255,255,1200,-3400,5600,-7800)
    m.pads[0]=(4,5,0,0,0,0,0) # right half absent, libnx IsConnected still set
    assert m.state(0)[1:]==(0,)*9
    m.pads[0]=(8,0,0,0,0,0,0)
    assert m.state(0)[1:]==(0,)*9
    assert m.state(1)==changed # P2 remains P2 while P1 is absent.
    assert m.state(2)[1:]==(0,)*9 and m.state(3)[1:]==(0,)*9
    # The old manual player-count setting cannot hide a physically present P2.
    m.vm.mem_write(m.symbols['fx_players'],struct.pack('<I',1))
    assert m.state(1)==changed
    m.pads[0]=(8,1,0,0,0,0,0)
    assert m.call('fx_pads_capture_session')==1
    m.pads[0]=(8,0,0,0,0,0,0)
    m.vm.mem_write(m.symbols['fx_game_active'],struct.pack('<I',1))
    m.vm.mem_write(m.symbols['fx_recovery'],struct.pack('<II',0,3))
    restored=m.state(0);assert m.waits==1 and restored[1]==1 and restored[3]==0
    # Pre-game auto detection, frozen two-player session, and late P2 join.
    m.vm.mem_write(m.symbols['fx_game_active'],b'\0'*4)
    m.vm.mem_write(m.symbols['fx_pad_session_captured'],b'\0'*4)
    m.pads[1]=(16,0,0,0,0,0,0)
    assert m.call('fx_pads_capture_session')==1
    assert struct.unpack('<I',m.vm.mem_read(m.symbols['fx_players'],4))[0]==1
    m.vm.mem_write(m.symbols['fx_game_active'],struct.pack('<I',1))
    assert m.state(1)[1:]==(0,)*9 and m.waits==1
    m.pads[1]=(16,1,0,0,0,0,0);assert m.state(1)[1]==1
    assert struct.unpack('<II',m.vm.mem_read(m.symbols['fx_recovery'],8))==(0,3)
    m.pads[1]=(16,0,0,0,0,0,0);m.state(0);assert m.waits==2
    assert {0,1}==set(m.calls)
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        'checks':['Real ARM64 HID normalization -> P1/P2 XInput response and independent packet counters',
                  'P2 is not promoted when P1 disconnects; absent/out-of-range slots are disconnected',
                  'Session auto-detection, stable required slots, and late P2 join/recovery',
                  'Disconnect blocks the requesting game thread until the monitor releases its pause gate',
                  'No file/log I/O from controller polling']}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
