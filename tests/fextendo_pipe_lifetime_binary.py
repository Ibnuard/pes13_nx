"""Replay reader-close/writer-retention using the actual old/new ARM64 handlers."""
import argparse,hashlib,json
from pathlib import Path
from fextendo_anon_pipe_binary import Model,reg

class LifetimeModel(Model):
    def __init__(self,elf):
        super().__init__(elf)
        self.vm.mem_map(0x53400000,0x400000)
        self.spans=[(0x53000000,0x800000)];self.sizes={};self.peak=0;self.deny_large=False
    def hook(self,vm,pc,size,user):
        s=self.symbols;p=vm.reg_read(reg(0))
        if pc in {s.get('malloc'),s.get('calloc')}:
            n=p*vm.reg_read(reg(1)) if pc==s.get('calloc') else p
            if self.deny_large and n>=2101740:self.ret();return
            n=max(16,(n+15)&-16)
            for i,(start,available) in enumerate(self.spans):
                if available<n:continue
                self.spans.pop(i)
                if available>n:self.spans.insert(i,(start+n,available-n))
                self.allocations.add(start);self.sizes[start]=n
                self.peak=max(self.peak,sum(self.sizes.values()))
                # Poison malloc data; only calloc supplies zeroed storage.
                vm.mem_write(start,bytes([0 if pc==s.get('calloc') else 0xa5])*n)
                self.ret(start);return
            self.ret();return
        if pc==s.get('free'):
            if p:
                assert p in self.allocations;self.allocations.remove(p)
                self.spans.append((p,self.sizes.pop(p)));self.spans.sort()
                combined=[]
                for start,n in self.spans:
                    if combined and combined[-1][0]+combined[-1][1]==start:
                        combined[-1]=(combined[-1][0],combined[-1][1]+n)
                    else:combined.append((start,n))
                self.spans=combined
            self.ret();return
        super().hook(vm,pc,size,user)

def run(elf,baseline):
    m=LifetimeModel(elf);writers=[];quota=2101740;length=1050870;buffer=0x54000000
    m.vm.mem_map(buffer,0x220000)
    payload=bytes((i*17+i//67)&255 for i in range(length))
    for i in range(36):
        status,_,reader,_=m.create(capacity=quota)
        if status:
            assert baseline and status==0xc0000017 and i==3;break
        status,_,writer,_=m.connect();assert not status
        writers.append(writer)
        m.vm.mem_write(buffer,payload)
        assert not m.call('NtWriteFile',writer,0,0,0,m.data+0x700,buffer,length,0,0)
        assert m.uq(m.data+0x708)==length
        if i%3==2:
            duplicate=m.duplicate(reader);m.close(reader);reader=duplicate
            assert any(n>=quota for n in m.sizes.values())
            m.vm.mem_write(buffer,bytes(length))
            assert not m.call('NtReadFile',reader,0,0,0,m.data+0x700,buffer,length,0,0)
            assert m.uq(m.data+0x708)==length and bytes(m.vm.mem_read(buffer,length))==payload
        m.close(reader)
        assert m.call('NtWriteFile',writer,0,0,0,m.data+0x700,buffer,1,0,0)==0xc000014b
        assert not m.uq(m.data+0x708)
        if not baseline:assert not any(n>=quota for n in m.sizes.values())
    retained=sum(m.sizes.values());peak=m.peak
    assert len(writers)==(3 if baseline else 36)
    if baseline:assert retained>6*1024*1024
    else:assert retained<128*1024 and peak<3*1024*1024
    for writer in writers:m.close(writer)
    assert not m.allocations and not m.uq(m.symbols['horizon_server_handles'])
    if not baseline:
        m.deny_large=True
        assert m.create(capacity=quota)[0]==0xc0000017
        assert not m.allocations and not m.uq(m.symbols['horizon_server_handles'])
    return {'passed':True,'baseline':baseline,'leftover_writers':len(writers),
        'retained_bytes':retained,'peak_bytes':peak,'fully_released_at_end':True,
        'result':'Kit13 retains closed-reader quotas and hits allocation failure' if baseline else
                 'Kit14 releases quotas on last reader close; duplicate, buffered data, broken writer, rollback and final cleanup pass'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path)
    p.add_argument('--before',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    checks=[run(a.before,True),run(a.elf,False)]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    names=('src/runtime/horizon_anon_pipe.h','src/runtime/horizon_anon_pipe_server.h',
           'tests/fextendo_anon_pipe_binary.py','tests/fextendo_pipe_lifetime_binary.py')
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':sha(a.elf),
        'baseline_elf_sha256':sha(a.before),'checks':checks,
        'sources':{n:sha(Path(n)) for n in names},
        'limit':'Actual ARM64 handlers, duplicate/close and NT I/O; 8-MiB allocator, OS locks and completion transport modeled.'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
