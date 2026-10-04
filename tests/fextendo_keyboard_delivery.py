"""Run the linked Wine text pump and real NtUserCallHwndParam dispatch.

Window APIs, keyboard layout and server input are modeled. The server returns
NTSTATUS (zero success); the actual Wine dispatch forwards that status. This
reproduces v2's one-character abort without mocking the misleading BOOL API.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from fextendo_keyboard_binary import Model as Keyboard, reg


class Model(Keyboard):
    def __init__(self,path):
        super().__init__(path)
        self.milliseconds=100
        self.focus=self.foreground=0x10020
        self.caret=0
        self.tls=self.data+0x8000
        self.teb=self.data+0x6000
        self.q(self.teb+72,1)  # TEB.ClientId.UniqueThread, ARM64
        self.pressed=set()
        self.events=[]
        self.units=[]
        self.send_calls=0
        self.fail_at=0

    def hook(self,vm,pc,size,user):
        s=self.symbols
        if pc==s.get('__aarch64_read_tp'):self.ret(self.tls)
        elif pc==s.get('NtCurrentTeb'):self.ret(self.teb)
        elif pc==s.get('NtGetTickCount'):self.ret(self.milliseconds)
        elif pc==s.get('get_focus'):self.ret(self.focus)
        elif pc==s.get('NtUserGetForegroundWindow'):self.ret(self.foreground)
        elif pc==s.get('get_window_thread'):self.ret(1)
        elif pc in {s.get('is_window_visible'),s.get('is_window_enabled')}:self.ret(1)
        elif pc==s.get('NtUserGetAncestor'):
            assert vm.reg_read(reg(1))==2
            self.ret(vm.reg_read(reg(0)))
        elif pc==s.get('NtUserGetClassName'):self.ret(0)  # Custom game field
        elif pc==s.get('NtUserGetGUIThreadInfo'):
            self.q(vm.reg_read(reg(1))+48,self.caret)  # GUITHREADINFO.hwndCaret
            self.ret(1)
        elif pc==s.get('NtUserGetKeyboardLayout'):self.ret(0x409)
        elif pc==s.get('NtUserVkKeyScanEx'):
            c=vm.reg_read(reg(0))
            if 65<=c<=90:self.ret(c|0x100)
            elif 97<=c<=122:self.ret(c-32)
            elif c==33:self.ret(49|0x100)
            elif c==32 or 48<=c<=57:self.ret(c)
            else:self.ret(0xffff)
        elif pc==s.get('NtUserMapVirtualKeyEx'):
            keys=dict(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ',
                          [30,48,46,32,18,33,34,35,23,36,37,38,50,49,24,25,16,19,31,20,22,47,17,45,21,44]))
            scans={ord(k):v for k,v in keys.items()}
            scans.update({16:42,32:57,48:11,**{48+i:1+i for i in range(1,10)}})
            assert vm.reg_read(reg(1))==4
            self.ret(scans[vm.reg_read(reg(0))])
        elif pc==s.get('send_hardware_message'):
            # Keep NtUserCallHwndParam_SendHardwareInput REAL. Model only the
            # server boundary, whose successful reply is STATUS_SUCCESS=0.
            hwnd,flags,ptr,lparam=[vm.reg_read(reg(i)) for i in range(4)]
            assert not flags and not lparam
            assert struct.unpack('<I',vm.mem_read(ptr,4))[0]==1
            vk,scan,flags=struct.unpack('<HHI',vm.mem_read(ptr+8,8))
            assert hwnd==self.focus or (not hwnd and flags&2)
            self.send_calls+=1
            if self.send_calls==self.fail_at:self.ret(0xc0000008);return
            self.events.append((vk,scan,flags))
            if flags&4:
                if not flags&2:self.units.append(scan)
            elif flags&2:
                assert vk in self.pressed,(vk,self.pressed)
                self.pressed.remove(vk)
            else:
                assert vk not in self.pressed,'Repeated letter lacked a key release'
                if 65<=vk<=90:self.units.append(vk if 16 in self.pressed else vk+32)
                elif vk!=16:self.units.append(33 if vk==49 and 16 in self.pressed else vk)
                self.pressed.add(vk)
            self.ret(0)
        else:super().hook(vm,pc,size,user)

    def pump(self):
        self.milliseconds+=50
        self.call('fx_wine_text_pump')

    def start(self,text,signal=0):
        self.text=text
        if signal==3:self.caret=self.focus
        if signal==2:
            self.call('wine_nx_drv_NotifyIMEStatus',self.focus,1)
            self.call('wine_nx_drv_SetIMECompositionRect',self.focus,0,0)
        self.set('fx_keyboard_manual_pending',1)
        self.pump()
        assert self.get('fx_keyboard_phase')==1
        self.step();self.pump()
        assert self.call('fx_keyboard_delivering')

    def drain(self):
        for _ in range(800):
            if not self.call('fx_keyboard_delivering'):break
            self.pump()
        assert not self.call('fx_keyboard_delivering'),'Text delivery never completed'

    def text_received(self):
        return b''.join(struct.pack('<H',c) for c in self.units).decode('utf-16le')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path);p.add_argument('--before',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    before=Model(a.before);before.start('hallo');before.drain()
    assert before.text_received()=='h' and before.pressed=={ord('H')}
    for text in ('hallo','Hallo','HaLLo','Manager Test','AAaa 11!','é😀',''):
        m=Model(a.elf);m.start(text);m.drain()
        assert m.text_received()==text,(text,m.text_received())
        assert not m.pressed and not m.get('fx_keyboard_blocked')
        count=len(m.events);m.pump();assert len(m.events)==count
    for signal in (2,3):
        m=Model(a.elf);m.start('Hallo',signal);m.pump()
        assert m.text_received()=='H'
        if signal==2:m.call('wine_nx_drv_NotifyIMEStatus',m.focus,0)
        else:m.caret=0
        m.drain();assert m.text_received()=='Hallo' and not m.pressed
    # A real focus change cancels and releases both the held key and Shift.
    m=Model(a.elf);m.start('Hallo');m.pump();m.focus=m.foreground=0x10021;m.drain()
    assert m.text_received()=='H' and not m.pressed
    # A nonzero server error really IS a failure; don't continue or retry text.
    m=Model(a.elf);m.start('Hallo');m.fail_at=2;m.drain()
    assert not m.text_received() and not m.pressed and m.send_calls==3
    report={'passed':True,'hardware_tested':False,
            'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
            'before_elf_sha256':hashlib.sha256(a.before.read_bytes()).hexdigest(),
            'test_sources':{str(path.relative_to(Path(__file__).resolve().parents[1])):
                            hashlib.sha256(path.read_bytes()).hexdigest() for path in
                            (Path(__file__).resolve(),Path(__file__).with_name('fextendo_keyboard_binary.py'))},
            'checks':['Real v2 Wine pump truncates hallo to h and leaves H held on STATUS_SUCCESS',
                      'Real new Wine pump and NtUserCallHwndParam deliver full mixed-case/repeated/Unicode text',
                      'Manual caret/IME transition preserves remaining characters; focus change still cancels',
                      'Keys and Shift released at completion/cancellation; real nonzero status aborts',
                      'No implicit Enter, duplicate text, or storage I/O']}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
