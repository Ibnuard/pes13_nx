"""Run the linked ARM64 Kitserver enumeration policy with SD access forbidden."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from fextendo_silent import Model as BaseModel, reg


class Model(BaseModel):
    def __init__(self,path):
        super().__init__(path)
        self.allow_fallback=False
        self.path_calls=0
        self.forbidden.update(self.symbols[n] for n in ('fsFsGetFileTimeStampRaw','fsFsOpenFile',
                              'fsFileGetSize','fsDirRead','timeToPosixTimeWithMyRule') if n in self.symbols)

    def hook(self,vm,pc,size,user):
        if pc==self.symbols.get('fsdevTranslatePath'):
            assert self.allow_fallback, 'Asset filename scan issued an SD path lookup'
            self.path_calls+=1;self.ret(-1)
        else:super().hook(vm,pc,size,user)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();m=Model(a.elf)
    for value in (0,1):assert m.config('kitserver_fast_scan',value,1-value)==value
    m.call('horizon_dir_set_asset_scan',1)
    hint,out=m.data+0x500,m.data+0x600
    snapshot=struct.pack('<IIQ',0,1,0x112233445566)
    m.vm.mem_write(hint,snapshot)
    names=('sdmc:/switch/pes13-fex/drive_c/PES13/kitserver13/PATCH/img/dt00_e.img/unnamed_1941.bin',
           'sdmc:/KITServer13/Selector/IMG/DT01.IMG/unnamed_1.adx')
    for name in names:
        m.vm.mem_write(m.data,name.encode()+b'\0')
        m.vm.mem_write(out-16,b'X'*16+b'Y'*256+b'Z'*16)
        assert m.call('horizon_dir_entry_stat',m.data,hint,out,0)==2
        assert bytes(m.vm.mem_read(out-16,16))==b'X'*16
        assert bytes(m.vm.mem_read(out+256,16))==b'Z'*16
        assert struct.pack('<Q',0x112233445566) in bytes(m.vm.mem_read(out,256))
        assert bytes(m.vm.mem_read(hint,16))==snapshot
    assert not m.path_calls
    # Disabling the policy restores the ordinary path. Translation failure
    # explicitly selects the existing lstat fallback instead of inventing data.
    m.allow_fallback=True;m.call('horizon_dir_set_asset_scan',0)
    assert m.call('horizon_dir_entry_stat',m.data,hint,out,0)==0 and m.path_calls==1
    m.call('horizon_dir_set_asset_scan',1)
    for name in ('sdmc:/game/img/dt01.img/file.bin','sdmc:/kitserver13/GDB/config.txt',
                 'sdmc:/kitserver13/../img/dt01.img/file.bin'):
        m.vm.mem_write(m.data,name.encode()+b'\0')
        assert m.call('horizon_dir_entry_stat',m.data,hint,out,0)==0
    assert m.path_calls==4
    assert not m.call('horizon_dir_diag_begin',0x1c34)
    m.call('horizon_dir_diag_tick')
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
            'checks':['Linked ARM64 asset listings issue no timestamp, directory or file-open IPC',
                      'Enumerated 64-bit size retained; caller boundaries and input hint preserved',
                      'INI override restores ordinary lookup; non-asset and parent-escape paths fall back',
                      'Quiet observer returns without diagnostic IO'],
            'sources':{'tests/fextendo_asset_scan_binary.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
