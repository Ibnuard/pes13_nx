"""Run the delivered ARM64 pipe snapshot and real pipe I/O/handle lifecycle.

OS allocation, locking and reply/completion transport are modeled. This test
does not execute PES or reproduce a Switch crash.
"""
import argparse, hashlib, json
from pathlib import Path
from fextendo_anon_pipe_binary import Model as Pipe, reg

class Model(Pipe):
    def __init__(self, path):
        super().__init__(path)
        self.snapshots=[]; self.attempts=[]; self.busy_address=None

    def hook(self, vm, pc, size, user):
        s=self.symbols
        if pc==s.get('pthread_mutex_trylock'):
            addr=vm.reg_read(reg(0));self.attempts.append(addr)
            if addr==self.busy_address or addr in self.locks:self.ret(1)
            else:self.locks.append(addr);self.ret(0)
        elif pc==s.get('horizon_trace'):
            message=self.string(vm.reg_read(reg(0)))
            if message.startswith('[ASSET-'):
                assert not self.locks, 'Snapshot logging holds a pipe/registry lock'
                args=[vm.reg_read(reg(i)) for i in range(1,8)]
                self.snapshots.append((message,args))
            self.ret()
        else:super().hook(vm,pc,size,user)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();m=Model(args.elf)
    status,_,reader,_=m.create();assert not status
    status,_,writer,_=m.connect();assert not status
    assert m.io('NtWriteFile',writer,b'pipe bytes')[:2]==(0,10)
    allocated=set(m.allocations)
    m.call('wine_nx_asset_pipe_report');assert not m.attempts and not m.snapshots
    m.call('fx_launch_debug_begin',1);m.call('wine_nx_asset_pipe_report')
    summary,rows=m.snapshots[0],m.snapshots[1:]
    assert summary[1][:5]==[2,2,0,0,0],summary
    assert len(rows)==2 and {row[1][0] for row in rows}=={reader,writer}
    assert all(row[1][2:7]==[64,10,1,1,0] for row in rows),rows
    assert m.allocations==allocated
    pipe_lock=m.attempts[-1];m.busy_address=pipe_lock;m.snapshots=[]
    m.call('wine_nx_asset_pipe_report')
    assert len(m.snapshots)==1 and m.snapshots[0][1][:5]==[2,0,2,0,0]
    m.busy_address=m.symbols['horizon_server_objects_mutex'];m.snapshots=[]
    m.call('wine_nx_asset_pipe_report')
    assert len(m.snapshots)==1 and 'registry busy' in m.snapshots[0][0]
    m.busy_address=None
    status,count,payload=m.io('NtReadFile',reader,32)
    assert (status,count,payload[:count])==(0,10,b'pipe bytes')
    m.close(reader);m.close(writer);assert not m.allocations
    report=dict(passed=True,hardware_tested=False,
        elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        checks=['Normal launch performs no snapshot locks or diagnostic output',
                'Real ARM64 snapshot preserves queued bytes, handles and allocations',
                'Busy registry/pipe returns promptly without modifying ownership',
                'Logging occurs after snapshot locks are released; subsequent real read and close succeed'],
        limitations=__doc__,sources={n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in
            ('src/runtime/horizon_asset_probe.h','tests/pes_asset_probe_binary.py')})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS ARM64 quiet/ready/busy snapshots; pipe read and final close remain intact')

if __name__=='__main__':main()
