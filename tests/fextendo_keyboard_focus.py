"""Replay Plus/Enter through the real linked libnx swkbdShow and TextCheck.

Horizon applet IPC and focus suspension are modeled; libnx's interactive
request/reply, UTF conversion and the native callback execute as ARM64.
The previous ELF must reproduce the wait cycle before the new ELF is accepted.
This is not a Switch/PES hardware test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from fextendo_keyboard_binary import Model as Bridge, reg


class SuspendedCaller(Exception):pass


class Model(Bridge):
    def __init__(self,path):
        super().__init__(path)
        self.storages={};self.replied=False;self.interactive=False
        self.text='Manager Test';self.callback_calls=0;self.real_shows=0;self.focus_error=0

    def hook(self,vm,pc,size,user):
        s=self.symbols
        if pc==s.get('appletSetFocusHandlingMode') and self.focus_error:
            mode=vm.reg_read(reg(0));self.focus_changes.append(mode)
            if mode==0:self.ret(self.focus_error)
            else:self.focus_mode=mode;self.ret()
        elif pc==s.get('swkbdConfigSetTextCheckCallback'):
            self.validation_callback=vm.reg_read(reg(1)) # execute actual setter
        elif pc==s.get('swkbdShow'):
            self.real_shows+=1 # execute actual libnx show function
        elif pc==self.validation_callback and self.validation_callback:
            self.callback_calls+=1 # execute actual UTF validation callback
        elif pc==s.get('__libnx_alloc'):
            assert vm.reg_read(reg(0))<4096;self.ret(self.data+0x6000)
        elif pc==s.get('__libnx_free'):self.ret()
        elif pc==s.get('appletCreateLibraryApplet'):
            # Current software keyboard applet, foreground library mode.
            assert vm.reg_read(reg(1))==0x11 and vm.reg_read(reg(2))==0
            self.ret()
        elif pc in {s.get('libappletArgsPush'),s.get('libappletPushInData'),
                    s.get('appletCreateTransferMemoryStorage'),s.get('appletHolderPushInData'),
                    s.get('appletHolderStart'),s.get('appletHolderClose'),
                    s.get('appletStorageClose'),s.get('appletStorageCloseTmem')}:
            self.ret()
        elif pc==s.get('appletHolderWaitInteractiveOut'):
            if not self.cancel and not self.replied:
                # At +, TextCheck makes the library applet await an interactive
                # reply. AlwaysSuspend makes the caller unable to produce it.
                if self.focus_mode==3:raise SuspendedCaller('TextCheck waits for a suspended caller')
                assert self.focus_mode==0 and not self.interactive
                self.interactive=True;self.ret(1)
            else:self.ret(0)
        elif pc==s.get('appletHolderPopInteractiveOutData'):
            text=self.text.encode('utf-16le')+b'\0\0'
            self.storages[vm.reg_read(reg(1))]=bytearray(struct.pack('<Q',len(text))+text)
            self.ret()
        elif pc==s.get('appletCreateStorage'):
            self.storages[vm.reg_read(reg(0))]=bytearray(vm.reg_read(reg(1)));self.ret()
        elif pc==s.get('appletStorageRead'):
            store,offset,dest,n=[vm.reg_read(reg(i)) for i in range(4)]
            data=self.storages[store][offset:offset+n];vm.mem_write(dest,bytes(data).ljust(n,b'\0'));self.ret()
        elif pc==s.get('appletStorageWrite'):
            store,offset,src,n=[vm.reg_read(reg(i)) for i in range(4)]
            self.storages[store][offset:offset+n]=bytes(vm.mem_read(src,n));self.ret()
        elif pc==s.get('appletHolderPushInteractiveInData'):
            data=self.storages[vm.reg_read(reg(1))]
            assert self.callback_calls==1 and struct.unpack('<I',data[:4])[0]==0
            assert data[4:].decode('utf-16le').split('\0')[0]==self.text
            self.replied=True;self.ret()
        elif pc==s.get('appletHolderJoin'):
            assert self.cancel or self.replied;self.ret()
        elif pc==s.get('appletHolderGetExitReason'):self.ret(0)
        elif pc==s.get('appletHolderPopOutData'):
            self.storages[vm.reg_read(reg(1))]=bytearray(struct.pack('<I',int(self.cancel))+self.text.encode('utf-16le')+b'\0\0')
            self.ret()
        else:super().hook(vm,pc,size,user)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path)
    p.add_argument('--before',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();before=Model(a.before);before.request()
    try:before.step()
    except SuspendedCaller:pass
    else:raise AssertionError('The previous build did not reproduce the focus/TextCheck wait cycle')
    assert before.real_shows==1 and before.callback_calls==0 and before.focus_changes==[]
    after=Model(a.elf);token=after.request();after.step()
    assert after.real_shows==1 and after.replied and after.callback_calls==1
    assert after.focus_changes==[0,3] and after.focus_mode==3 and not after.get('fx_keyboard_applet_active')
    assert after.call('fx_keyboard_take',token,after.data+0x1000)==1
    data=bytes(after.vm.mem_read(after.data+0x1000,520))
    assert struct.unpack('<I',data[:4])[0]==1
    assert data[4:].decode('utf-16le').split('\0')[0]==after.text
    cancel=Model(a.elf);cancel.cancel=True;token=cancel.request();cancel.step()
    assert cancel.real_shows==1 and not cancel.replied and cancel.callback_calls==0
    assert cancel.focus_changes==[0,3] and cancel.focus_mode==3 and not cancel.get('fx_keyboard_applet_active')
    assert cancel.call('fx_keyboard_take',token,cancel.data+0x1000)==1
    assert not struct.unpack('<I',cancel.vm.mem_read(cancel.data+0x1000,4))[0]
    failed=Model(a.elf);failed.focus_error=1;token=failed.request();failed.step()
    assert not failed.real_shows and failed.closes==1 and failed.focus_changes==[0,3]
    assert not failed.get('fx_keyboard_applet_active')
    assert failed.call('fx_keyboard_take',token,failed.data+0x1000)==1
    assert not struct.unpack('<I',failed.vm.mem_read(failed.data+0x1000,4))[0]
    report={'passed':True,'hardware_tested':False,
            'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
            'before_native_elf_sha256':hashlib.sha256(a.before.read_bytes()).hexdigest(),
            'before':'Real swkbdShow reaches TextCheck wait while caller has AlwaysSuspend; cannot reply',
            'after':'Real swkbdShow executes callback and acknowledges Plus, returns text, restores AlwaysSuspend',
            'checks':['Actual libnx ARM64 software keyboard interactive storage round trip',
                      'HOME/sleep suspension retained; previous focus mode restored after confirm and Cancel',
                      'Focus setup failure skips opening, releases input/frame gate and closes config']}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
