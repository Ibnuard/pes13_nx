"""Run actual ARM64 pipe handlers, handle ownership and Wine I/O wrappers.

Only OS locks, allocation, validation and reply/completion transport are modeled.
Blocking/concurrent behavior is exercised by the companion real pthread test.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from fextendo_silent import Model as Base,reg,arm

class Model(Base):
    def __init__(self,path):
        super().__init__(path)
        self.heap_next=0x53000000;self.vm.mem_map(self.heap_next,0x400000)
        self.allocations=set();self.locks=[];self.reply=b'';self.fail_alloc=False;self.completions=[]
        self.u32(self.data+0x304,77) # Server reply transport only; never a storage FD.
    def u32(self,p,n=None):
        if n is None:return struct.unpack('<I',self.vm.mem_read(p,4))[0]
        self.vm.mem_write(p,struct.pack('<I',n&0xffffffff))
    def hook(self,vm,pc,size,user):
        s=self.symbols;a=[vm.reg_read(reg(i)) for i in range(8)]
        if pc in {s.get('malloc'),s.get('calloc')}:
            if self.fail_alloc:self.ret();return
            n=a[0]*a[1] if pc==s.get('calloc') else a[0]
            p=self.heap_next;self.heap_next+=(n+15)&-16
            assert self.heap_next<0x53400000
            self.allocations.add(p);vm.mem_write(p,bytes(n));self.ret(p)
        elif pc==s.get('free'):
            if a[0]:assert a[0] in self.allocations,hex(a[0]);self.allocations.remove(a[0])
            self.ret()
        elif pc==s.get('memcpy'):
            vm.mem_write(a[0],bytes(vm.mem_read(a[1],a[2])));self.ret(a[0])
        elif pc==s.get('pthread_mutex_lock'):
            assert a[0] not in self.locks,'Recursive pipe/object lock'
            self.locks.append(a[0]);self.ret()
        elif pc==s.get('pthread_mutex_unlock'):
            assert self.locks.pop()==a[0];self.ret()
        elif pc in {s.get(n) for n in ('pthread_mutex_init','pthread_mutex_destroy',
            'pthread_cond_init','pthread_cond_destroy','pthread_cond_broadcast','pthread_cond_signal')}:
            self.ret()
        elif pc==s.get('pthread_cond_wait'):
            raise AssertionError('Unexpected blocking in ready/closed ARM64 pipe test')
        elif pc==s.get('horizon_server_write_reply'):
            assert not a[4];self.reply=bytes(vm.mem_read(a[1],a[2]));self.ret()
        elif pc==s.get('write'):
            # Optimized handlers inline the fixed-size reply helper.
            assert a[0]==77 and a[2]==64,(a[:3],hex(vm.reg_read(reg(30))))
            self.reply=bytes(vm.mem_read(a[1],16));self.ret(a[2])
        elif pc==s.get('server_get_unix_fd'):
            if a[3]:self.u32(a[3],0)
            self.ret(0xc00000cb) # Actual get-handle-FD handler checked separately.
        elif pc in {s.get('virtual_check_buffer_for_write'),s.get('virtual_check_buffer_for_read')}:
            self.ret(1)
        elif pc==s.get('file_complete_async'):
            vm.mem_write(a[5],struct.pack('<QQ',a[6],a[7]));self.completions.append((a[6],a[7]));self.ret()
        elif pc in {s.get('horizon_trace'),s.get('wine_nx_runtime_trace')}:
            self.ret()
        else:super().hook(vm,pc,size,user)
    def call(self,name,*args):
        self.returned=False;sp=self.stack+0xe000
        self.vm.reg_write(arm.UC_ARM64_REG_SP,sp);self.vm.reg_write(reg(30),self.stop)
        for i,value in enumerate(args[:8]):self.vm.reg_write(reg(i),value&0xffffffffffffffff)
        for i,value in enumerate(args[8:]):self.q(sp+i*8,value)
        self.vm.emu_start(self.symbols[name],0,count=400000)
        assert self.returned,'Unbounded call '+name
        assert not self.locks,self.locks
        return self.vm.reg_read(reg(0))&0xffffffff
    def create(self,name='\\??\\pipe\\Win32.Pipes.00000032.00000001',flags=0,capacity=64):
        b=name.encode('utf-16-le');payload=struct.pack('<4I',0,0x40,0,len(b))+b
        r=struct.pack('<10Iq2I',142,len(payload),0,0x80100100,0x20,2,3,1,capacity,capacity,0,flags,0)
        assert len(r)==56
        self.vm.mem_write(self.data,r);self.vm.mem_write(self.data+0x100,payload)
        self.call('horizon_server_handle_create_anon_pipe',self.data+0x300,self.data,self.data+0x100,len(payload))
        return struct.unpack('<4I',self.reply)
    def connect(self):
        name='\\Device\\NamedPipe\\win32.pipes.00000032.00000001'.encode('utf-16-le')
        self.vm.mem_write(self.data,struct.pack('<8I',45,len(name),0,0x40100080,0x40,0,0,0x60))
        self.vm.mem_write(self.data+0x100,name)
        self.call('horizon_server_handle_open_file_object',self.data+0x300,self.data,self.data+0x100,len(name))
        return struct.unpack('<4I',self.reply)
    def io(self,name,h,data_or_size):
        p=self.data+0x800;io=self.data+0x700
        size=data_or_size if isinstance(data_or_size,int) else len(data_or_size)
        if not isinstance(data_or_size,int):self.vm.mem_write(p,data_or_size)
        result=self.call(name,h,0,0,0,io,p,size,0,0)
        return result,self.uq(io+8),bytes(self.vm.mem_read(p,size))
    def close(self,h):
        self.vm.mem_write(self.data,struct.pack('<4I',21,0,0,h))
        self.call('horizon_server_handle_close_handle',self.data+0x300,self.data)
        assert struct.unpack_from('<I',self.reply)[0]==0
    def duplicate(self,h):
        self.vm.mem_write(self.data,struct.pack('<10I',23,0,0,0xffffffff,h,0xffffffff,0,0,2,0))
        self.call('horizon_server_handle_dup_handle',self.data+0x300,self.data)
        status,_,duplicate,_=struct.unpack('<4I',self.reply)
        assert not status and duplicate
        return duplicate

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();m=Model(a.elf)
    status,_,read,created=m.create();assert not status and read and created
    status,_,write,_=m.connect();assert not status and write
    m.vm.mem_write(m.data,struct.pack('<4I',48,0,0,read))
    m.call('horizon_server_handle_get_handle_fd',m.data+0x300,m.data)
    assert struct.unpack_from('<I',m.reply)[0]==0xc00000cb
    assert m.io('NtWriteFile',write,b'pipe bytes')[0:2]==(0,10)
    for cls,size in ((5,24),(8,4),(16,4),(23,8),(24,40)):
        assert m.call('NtQueryInformationFile',read,m.data+0x700,m.data+0x800,size,cls)==0
        assert m.uq(m.data+0x708)==size
        if cls==8:assert m.u32(m.data+0x800)&1 and not m.u32(m.data+0x800)&2
        if cls==16:assert m.u32(m.data+0x800)==0x20
        if cls==24:assert m.u32(m.data+0x81c)==54 # 64-byte quota minus 10 bytes
        assert m.call('NtQueryInformationFile',read,m.data+0x700,m.data+0x800,size-1,cls)==0xc0000004
        assert m.uq(m.data+0x708)==0
    # Actual peek/file-info wrappers must identify a pipe rather than SD directory.
    m.call('NtFsControlFile',read,0,0,0,m.data+0x700,0x11400c,0,0,m.data+0x800,32)
    assert m.uq(m.data+0x708)==26 and bytes(m.vm.mem_read(m.data+0x810,10))==b'pipe bytes'
    assert m.call('NtQueryVolumeInformationFile',read,m.data+0x700,m.data+0x800,8,4)==0
    assert m.u32(m.data+0x800)==0x11 # FILE_DEVICE_NAMED_PIPE
    status,count,data=m.io('NtReadFile',read,32)
    assert (status,count,data[:count])==(0,10,b'pipe bytes')
    assert m.io('NtReadFile',write,1)[0]==0xc0000022
    # Execute actual duplicate/ref-count/hash unlink and final endpoint disposal.
    duplicate=m.duplicate(write);m.close(write)
    assert m.io('NtWriteFile',duplicate,b'x')[0:2]==(0,1);m.close(duplicate)
    assert m.io('NtReadFile',read,32)[0:2]==(0,1)
    assert m.io('NtReadFile',read,32)[0:2]==(0xc000014b,0)
    m.close(read);assert not m.allocations,m.allocations
    assert not m.uq(m.symbols['horizon_server_handles'])
    assert m.create(flags=1)[0]==0xc00000bb # Unsupported message pipe must not fake success.
    m.fail_alloc=True;assert m.create()[0]==0xc0000017;m.fail_alloc=False
    assert not m.allocations and not m.uq(m.symbols['horizon_server_handles'])
    names=['tests/fextendo_anon_pipe_binary.py','src/runtime/horizon_anon_pipe.h',
        'src/runtime/horizon_anon_pipe_api.h','src/runtime/horizon_anon_pipe_server.h',
        'tools/fextendo_anon_pipe_patches.py']
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        'checks':['Actual ARM64 create/open namespace and wire replies; no dummy handles',
            'Real NtReadFile/NtWriteFile partial byte transfer; PeekNamedPipe and GetFileType paths',
            'Actual pipe/local/standard/access/mode info queries and undersized-buffer rejection',
            'Real duplicate/close retains data, reports broken pipe and frees all owners',
            'Unsupported message mode and allocation failure return errors without leaked handles'],
        'sources':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in names},
        'limit':'OS locking, allocation, reply transport and guest-buffer validation modeled; no Switch game execution.'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
