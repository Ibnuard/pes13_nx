"""Verify the delivered checker cannot reset the shared two-player HID setup."""
import argparse,hashlib,json
from pathlib import Path
from fextendo_gamepad_startup import callers,Model
from pes_low_window_binary import Logging,LOW,END
class Admission(Logging):
    def __init__(self,path):super().__init__(path);self.resets=0
    def hook(self,vm,pc,size,user):
        if pc==self.symbols.get('padConfigureInput'):self.resets+=1;self.ret()
        elif pc==self.symbols.get('consoleInit'):self.ret(0) # unsupported mode returns to its loader
        else:super().hook(vm,pc,size,user)
def main():
    p=argparse.ArgumentParser();p.add_argument('elf',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    calls=callers(a.elf)
    owners=[c['function'] for c in calls if c['target']=='padConfigureInput']
    # The inherited terminal guest-test rejection console also has a one-pad
    # setup. It returns without Wine/UI; it must never execute for admitted
    # layouts. The normal checker and launcher retain the shared owner.
    assert owners==['fx_pads_once','fx_launch_memory_validate'],calls
    assert all(c['function']=='padConfigureInput' for c in calls if c['target'].startswith('hidSetSupportedNpad'))
    m=Model(a.elf);m.call('fx_pads_once');assert m.configuration==[[2,31]] and m.orientation==[1]
    for base,end,alias,ready in ((LOW,1<<32,0,1),(LOW,END,0x1800000000,1),(0x8000000,END,0x1800000000,0)):
        v=Admission(a.elf);v.info.update({12:base,13:end-base,3:alias})
        assert v.call('fx_launch_memory_validate')==ready and not v.resets
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        'configure_players':2,'callers':calls,'checks':['normal startup retains shared HID configuration','startup checker does not configure one player','actual ARM64 enables two players','32/39 admission does not enter the terminal rejection reset']}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print('PASS: startup/admitted paths retain two-player HID; rejection is terminal')
if __name__=='__main__':main()
