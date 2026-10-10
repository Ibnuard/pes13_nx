"""Execute the Kitserver serial handoff against old and new linked ARM64 code."""
import argparse,hashlib,json
from pathlib import Path
from fextendo_anon_pipe_binary import Model,reg

class WriteBlocked(Exception):pass
class QuotaModel(Model):
    def __init__(self,path):
        self.copied_payload=0
        super().__init__(path)
    def hook(self,vm,pc,size,user):
        if pc==self.symbols.get('pthread_cond_wait'):raise WriteBlocked()
        if pc==self.symbols.get('memcpy'):
            source=vm.reg_read(reg(1))
            if 0x54000000<=source<0x54220000:self.copied_payload+=vm.reg_read(reg(2))
        super().hook(vm,pc,size,user)

def run(elf,old):
    m=QuotaModel(elf);quota=2101740;length=1050870
    status,_,reader,created=m.create(capacity=quota);assert not status and created
    status,_,writer,_=m.connect();assert not status and writer
    assert not m.call('NtQueryInformationFile',reader,m.data+0x700,m.data+0x800,40,24)
    capacity=m.u32(m.data+0x810);assert capacity==(1048576 if old else quota)
    payload=bytes((i*17+i//67)&255 for i in range(length));buffer=0x54000000
    m.vm.mem_map(buffer,0x220000);m.vm.mem_write(buffer,payload)
    try:status=m.call('NtWriteFile',writer,0,0,0,m.data+0x700,buffer,length,0,0)
    except WriteBlocked:
        assert old and m.copied_payload==1048576
        return {'baseline':True,'passed':True,'capacity':capacity,'copied_bytes':m.copied_payload,
            'remaining_bytes':length-m.copied_payload,'result':'Actual Kit12 NtWriteFile enters wait before reader can be published'}
    assert not old and not status and m.uq(m.data+0x708)==length
    # The same thread can now hand off and read; no concurrent reader was modeled.
    m.vm.mem_write(buffer,bytes(length))
    assert not m.call('NtReadFile',reader,0,0,0,m.data+0x700,buffer,length,0,0)
    assert m.uq(m.data+0x708)==length and bytes(m.vm.mem_read(buffer,length))==payload
    m.close(writer);m.close(reader)
    assert not m.allocations and not m.uq(m.symbols['horizon_server_handles'])
    return {'baseline':False,'passed':True,'capacity':capacity,'transferred_bytes':length,
        'result':'Actual candidate NtWriteFile finishes before first NtReadFile; byte-exact payload and final handle cleanup pass'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf',type=Path);parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    checks=[run(args.before,True),run(args.elf,False)]
    names=('src/runtime/horizon_anon_pipe.h','src/runtime/horizon_anon_pipe_server.h',
        'tests/fextendo_anon_pipe_binary.py','tests/fextendo_pipe_quota_binary.py')
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':sha(args.elf),
        'baseline_elf_sha256':sha(args.before),'checks':checks,
        'sources':{n:sha(Path(n)) for n in names},
        'limit':'Real linked ARM64 pipe and NT wrapper code; OS locking/allocation, buffers and completion transport modeled.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
