"""Execute the linked ARM64 routing function; kernel signaling is modeled."""
from pathlib import Path
import argparse, hashlib, json, struct
import capstone
from elftools.elf.elffile import ELFFile
from fex_reservations import Model as NativeModel, arm, reg

class Model(NativeModel):
    def __init__(self,path):
        super().__init__(path); self.signals=[]; self.broadcasts=[]
    def w(self,a,v): self.vm.mem_write(a,struct.pack('<I',v & 0xffffffff))
    def u64(self,a): return struct.unpack('<Q',self.vm.mem_read(a,8))[0]
    def hook(self,vm,pc,size,user):
        if pc==self.symbols.get('pthread_cond_signal'):
            self.signals.append(vm.reg_read(reg(0))); self.ret()
        elif pc==self.symbols.get('pthread_cond_broadcast'):
            self.broadcasts.append(vm.reg_read(reg(0))); self.ret()
        else: super().hook(vm,pc,size,user)
    def run(self,mode=1,change=0,alias=False,closed=False,unknown=False,shared=1,broad=False):
        self.signals=[];self.broadcasts=[];self.returned=False
        objects=[self.data+0x200,self.data+0x400]
        conditions=[self.data+0x600,self.data+0x620]
        interests=[self.data+0x800,self.data+0xa00]
        waiters=[self.data+0xc00,self.data+0xc40]
        entries=[self.data+0xd00,self.data+0xd40]
        for i in range(2):
            # Pinned Horizon enum: RESERVE=1, REG_KEY=2, EVENT=3.
            self.vm.mem_write(objects[i],bytes(256));self.w(objects[i]+4,3 if i==0 or not unknown else 99)
            self.vm.mem_write(interests[i],bytes(272));self.w(interests[i],0x100+i*4);self.w(interests[i]+256,1)
            self.q(waiters[i],waiters[i+1] if i==0 else 0);self.q(waiters[i]+8,interests[i]);self.q(waiters[i]+16,conditions[i])
            self.vm.mem_write(entries[i],bytes(40));self.w(entries[i],0x100+i*4)
            self.q(entries[i]+8,objects[0] if alias else objects[i])
            self.q(self.symbols['horizon_server_handle_hash']+(64+i)*8,0 if closed and i==1 else entries[i])
        if broad:self.w(interests[1]+260,1)
        router=self.symbols['fex_sync_router'];self.vm.mem_write(router,bytes(56));self.q(router,waiters[0])
        self.w(self.symbols['wine_nx_fex_targeted_wake'],mode)
        self.w(self.symbols['horizon_server_sleepers'],shared)
        self.vm.reg_write(arm.UC_ARM64_REG_SP,self.stack+0xf000);self.vm.reg_write(reg(30),self.stop)
        self.vm.reg_write(reg(0),0 if change is None else objects[change])
        self.vm.emu_start(self.symbols['fex_sync_signal_object_locked'],0,count=100000)
        assert self.returned
        assert self.broadcasts==([self.symbols['horizon_server_objects_cond']] if shared else [])
        return [conditions.index(c) for c in self.signals],tuple(self.u64(router+i) for i in (24,32,40))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path)
    p.add_argument('--output',required=True,type=Path);a=p.parse_args();m=Model(a.elf)
    assert m.run()==([0],(2,1,1))
    assert m.run(shared=0)==([0],(2,1,1))
    for kw in ({'alias':True},{'closed':True},{'unknown':True},{'broad':True},{'change':None}):
        assert m.run(**kw)==([0,1],(2,2,0)),kw
    assert m.run(mode=0)==([],(0,0,0))
    bindings=[]
    with a.elf.open('rb') as f:
        e=ELFFile(f);sy={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()}
        d=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM)
        for name,target,n in [('horizon_server_signal_object_locked','fex_sync_signal_object_locked',3),
            ('horizon_server_handle_event_op','fex_sync_signal_object_locked',1),
            ('horizon_server_handle_release_mutex','fex_sync_signal_object_locked',1),
            ('horizon_server_handle_release_semaphore','fex_sync_signal_object_locked',1),
            ('NtDelayExecution','wine_nx_fex_delay_note',1),
            ('log_flusher','wine_nx_fex_sync_snapshot',1)]:
            s=sy[name];sec=e.get_section(s['st_shndx']);start=s['st_value']-sec['sh_addr']
            ins=list(d.disasm(sec.data()[start:start+s['st_size']],s['st_value']))
            hits=[i for i in ins if i.mnemonic in ('b','bl') and i.op_str==f'#{hex(sy[target]["st_value"])}']
            assert len(hits)==n,(name,len(hits),n);bindings.append((name,target,n))
    report={'passed':True,'hardware_tested':False,'scenarios':8,'bindings':bindings,
            'scope':__doc__,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
            'source_sha256':{'tests/fex_sync_binary.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
