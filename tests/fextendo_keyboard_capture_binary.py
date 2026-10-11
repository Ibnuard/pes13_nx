"""Execute Capture registration, actual callback and monitor in the native ELF.

OS message delivery, HID, VI and synchronization services are modeled. This
checks the compiled integration, not hardware Capture availability/visibility.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from pes13_39bit_keyboard import Model as Keyboard, reg


class Model(Keyboard):
    def __init__(self,path):
        super().__init__(path)
        self.cookie=0;self.callback=0;self.redirects=[];self.registrations=0
        self.enable_failure=0;self.unregistrations=0

    def hook(self,vm,pc,size,user):
        s=self.symbols
        if pc==s.get('appletHook'):
            assert not self.callback and not vm.reg_read(reg(2))
            self.cookie=vm.reg_read(reg(0));self.callback=vm.reg_read(reg(1));self.registrations+=1
            self.symbols['capture_callback_for_test']=self.callback;self.ret()
        elif pc==s.get('appletUnhook'):
            assert self.callback and vm.reg_read(reg(0))==self.cookie
            self.callback=0;self.cookie=0;self.unregistrations+=1;self.ret()
        elif pc==s.get('appletSetRequiresCaptureButtonShortPressedMessage'):
            enabled=vm.reg_read(reg(0));assert enabled in (0,1)
            self.redirects.append(enabled);self.ret(self.enable_failure if enabled else 0)
        elif pc==s.get('pthread_self'):self.ret(1)
        elif pc==s.get('pthread_join'):self.ret()
        else:super().hook(vm,pc,size,user)

    def choice(self,value):
        # Keep a saved 2s combo delay: Capture must not inherit it.
        self.vm.mem_write(self.symbols['fx_keyboard_options'],struct.pack('<iii',value,0,2000))

    def event(self,kind=5):
        assert self.callback;self.call('capture_callback_for_test',kind,0)

    def shutdown(self):
        self.set('fx_pad_thread_created',1);self.call('fx_pads_shutdown')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();m=Model(a.elf)
    for shortcut in range(5):
        m.choice(shortcut);m.step();assert not m.registrations and not m.redirects
    m.choice(5);m.step();m.step()
    assert m.registrations==1 and m.redirects==[1] and not m.displays
    m.event(0);m.step();assert not m.displays
    # The OS event contains no slot; P2 activity cannot acquire ownership or
    # prevent P1 from opening/arming/closing this keyboard.
    m.pads[1]=(4,21,1,20000,0,0,0)
    m.event();m.event();m.step()
    assert m.displays==1 and m.get('fx_osk_phase')==2 and m.get('fx_osk_player')==0
    assert not m.get('fx_keyboard_manual_pending')
    token=m.uq(m.symbols['fx_osk_serial'])
    m.event();m.step();assert m.uq(m.symbols['fx_osk_serial'])==token
    core=bytes(m.vm.mem_read(m.symbols['fx_osk_state'],180))
    assert struct.unpack_from('<i',core,156)[0]==1
    m.pump();m.key(character='a');m.close();m.step()
    assert m.field_text()=='Nunua' and not m.get('fx_osk_blocking')
    m.event();m.shutdown()
    assert m.redirects==[1,0] and m.unregistrations==1 and not m.callback
    assert not m.get('fx_keyboard_capture_pending') and not m.get('fx_pad_thread_created')
    m.call('fx_pads_shutdown');assert m.redirects==[1,0]
    failed=Model(a.elf);failed.choice(5);failed.enable_failure=0x1272;failed.step()
    assert failed.registrations==failed.unregistrations==1 and not failed.callback
    assert not failed.get('fx_keyboard_capture_enabled') and not failed.get('fx_osk_blocking')
    assert failed.redirects==[1]
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps({'passed':True,'hardware_tested':False,
        'elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        'checks':['compiled monitor opts in only for Capture',
                  'registered ARM64 callback ignores unrelated messages',
                  'short press opens immediately despite saved 2s hold; P1 ownership',
                  'held P2 cannot navigate or delay keyboard; Wine receives text',
                  'duplicate events do not reopen; compiled shutdown restores screenshots',
                  'OS registration failure leaves no hook or captured gamepad'],
        'limits':'OS Capture messages, VI and HID modeled; Switch visibility/availability still need device test.'},indent=2)+'\n')
    print('PASS: ARM64 Capture callback -> monitor -> P1 keyboard -> Wine; opt-in and screenshot restoration')


if __name__=='__main__':main()
