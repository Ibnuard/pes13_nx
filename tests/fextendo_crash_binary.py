"""Run fatal writer and termination wrappers in the actual delivered ARM64 ELF.

Only native FS, thread identity and termination are modeled. Unknown heap,
stdio or lock calls fail. Not a console crash/power-loss durability test.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from fextendo_silent import Model as Base,arm,reg

class Model(Base):
    def __init__(self,path):
        super().__init__(path);self.writes=[];self.termination=[];self.io_error=0
        self.forbidden.update(self.symbols[n] for n in ('malloc','calloc','realloc','memalign','aligned_alloc',
              'pthread_mutex_lock','mutexLock','snprintf','printf','__wrap_malloc') if n in self.symbols)
    def hook(self,vm,pc,size,user):
        s=self.symbols;ins=struct.unpack('<I',vm.mem_read(pc,4))[0]
        if ins&~31 in (0xd53be020,0xd53be000):
            vm.reg_write(reg(ins&31),38400000 if ins&~31==0xd53be020 else 19200000)
            vm.reg_write(arm.UC_ARM64_REG_PC,pc+4);return
        if pc==s.get('threadGetCurHandle'):self.ret(0x1234)
        elif pc==s.get('svcQueryMemory'):
            info,page,address=[vm.reg_read(reg(i)) for i in range(3)]
            if address==s['fx_crash_bootstrap']:base,length,perm=self.data,0x1000,5
            elif self.stack<=address<self.stack+0x10000:base,length,perm=self.stack,0x10000,3
            elif self.data+0x8000<=address<self.data+0x9000:base,length,perm=self.data+0x8000,0x1000,3
            else:base,length,perm=address&-4096,4096,0
            vm.mem_write(info,struct.pack('<QQIIIIII',base,length,3,0,perm,0,0,0))
            vm.mem_write(page,struct.pack('<I',0));self.ret(0)
        elif pc==s.get('fsFileWrite'):
            f,off,data,n,flags=[vm.reg_read(reg(i)) for i in range(5)]
            assert f==s['fx_crash_file'] and n==2048 and off+n<=18432
            self.writes.append((off,bytes(vm.mem_read(data,n)),flags));self.ret(self.io_error)
        elif pc==s.get('fsdevGetDeviceFileSystem'):
            assert self.string(vm.reg_read(reg(0)))=='sdmc';self.ret(self.data+0x6000)
        elif pc==s.get('fsFsGetEntryType'):self.ret(1) # fresh run: no files yet
        elif pc in {s.get('fsFsCreateFile'),s.get('fsFsOpenFile'),s.get('fsFileClose')}:self.ret(0)
        elif pc==s.get('svcBreak'):
            self.termination.append(('svcBreak',tuple(vm.reg_read(reg(i)) for i in range(3))))
            self.ret(0x6789)
        elif pc in {s.get('abort'),s.get('diagAbortWithResult')}:
            self.termination.append(('abort' if pc==s['abort'] else 'diagAbortWithResult',vm.reg_read(reg(0))))
            self.returned=True;vm.emu_stop()
        else:super().hook(vm,pc,size,user)
    def set32(self,name,value):self.vm.mem_write(self.symbols[name],struct.pack('<I',value))
    def u32(self,name):return struct.unpack('<I',self.vm.mem_read(self.symbols[name],4))[0]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path)
    p.add_argument('--nro',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    m=Model(a.elf)
    m.call('wine_nx_runtime_trace',1);m.call('wine_nx_crash_exception',1,1);assert not m.writes
    if 'fx_launch_debug_begin' in m.symbols:
        # Production keeps fatal capture disarmed until Debug launch is selected.
        m.call('fx_crash_bootstrap');m.call('fx_crash_init',1);assert not m.writes
        m.forbidden.discard(m.symbols.get('snprintf')) # RAM line prefixes only
        m.call('fx_launch_debug_begin',1)
    nro=a.nro.read_bytes();m.vm.mem_write(m.data,nro[:128]);m.call('fx_crash_bootstrap')
    assert len(m.writes)==10 and m.u32('fx_crash_ready')==1 and m.writes[-1][2]==1
    assert (b'nro_build_id='+nro[0x40:0x60].hex().encode()) in m.writes[-1][1]
    assert m.uq(m.symbols['fx_crash_nro_base'])==m.data
    m.call('wine_nx_crash_fex_image',0xff540000,0x410000)
    m.vm.mem_write(m.data,b'[FEX2-HEAP] STOP compiler scratch failed\nforged\0')
    m.call('wine_nx_runtime_trace',m.data)
    assert len(m.writes)==11 and m.writes[-1][0]==2048 and m.writes[-1][2]==1
    assert b'RECORD=FEX_STOP' in m.writes[-1][1] and b'failed?forged' in m.writes[-1][1]
    m.vm.mem_write(m.data,b'[FEX3-NHEAP-FAIL] bytes=10485760 align=16 pages_stage=6 rc=0 reserve_free=0\0')
    m.call('wine_nx_runtime_trace',m.data)
    assert b'RECORD=FEX_HEAP_FAILED' in m.writes[-1][1] and b'pages_stage=6' in m.writes[-1][1]
    # No transition worker, printf, heap allocation or stack unwinding needed.
    dump=bytearray(0x340);struct.pack_into('<I',dump,0,0x104)
    for i in range(29):struct.pack_into('<Q',dump,16+8*i,0x1000+i)
    struct.pack_into('<4Q',dump,0xf8,0x111,0x222,0x333,0xff68bb88)
    struct.pack_into('<IQ',dump,0x32c,0xf0000000,0x7654)
    m.vm.mem_write(m.data+0x2000,bytes(dump));m.call('wine_nx_crash_exception',m.data+0x2000,0x80000003)
    record=m.writes[-1][1]
    for line in (b'pc=0x00000000ff68bb88',b'far=0x0000000000007654',b'x28=0x000000000000101c',
                 b'fex_base=0x00000000ff540000',b'END_RECORD'):
        assert line in record,line
    count=len(m.writes);m.set32('fx_crash_lock',1)
    m.call('wine_nx_crash_exception',1,1);assert len(m.writes)==count
    m.set32('fx_crash_lock',0)
    m.call('__wrap_abort');assert m.termination[-1][0]=='abort' and any(b'NATIVE_ABORT' in w[1] for w in m.writes)
    m.call('__wrap_diagAbortWithResult',0xdead);assert m.termination[-1]==('diagAbortWithResult',0xdead)
    assert m.call('__wrap_svcBreak',3,0x123,0x456)==0x6789
    assert m.termination[-1]==('svcBreak',(3,0x123,0x456)) and any(b'SVC_BREAK' in w[1] for w in m.writes)
    count=len(m.writes);m.call('__wrap_svcBreak',0x80000000,7,8);m.call('wine_nx_crash_exit',0)
    assert len(m.writes)==count
    m.set32('fx_crash_records',0)
    m.io_error=0x777;m.call('wine_nx_crash_exit',1);assert m.u32('fx_crash_last_result')==0x777
    m.io_error=0;m.call('wine_nx_crash_exit',2)
    while m.u32('fx_crash_records')<8:m.call('wine_nx_crash_exit',3)
    count=len(m.writes);m.call('wine_nx_crash_exception',1,1);assert len(m.writes)==count
    if 'fx_launch_debug_begin' in m.symbols:
        m.set32('fx_crash_records',0)
        m.call('wine_nx_crash_rust_allocation',3,131077,64,65536,0x12345)
        assert b'RECORD=RUST_ALLOCATION_FAILED' in m.writes[-1][1]
        m.call('fx_launch_debug_begin',0);count=len(m.writes)
        m.call('wine_nx_crash_exception',1,1);m.call('wine_nx_crash_exit',1)
        m.vm.mem_write(m.data,b'[FEX3-NHEAP-FAIL] bytes=10485760 pages_stage=6\0')
        m.call('wine_nx_runtime_trace',m.data)
        assert len(m.writes)==count # switching to normal cannot write to an old armed file
    if 'fx_crash_native_detail' in m.symbols:
        m.set32('fx_crash_length',0);m.set32('fx_tr_enabled',1)
        tail=b'memory allocation of 131077 bytes failed\n';m.vm.mem_write(m.data,tail)
        m.call('wine_nx_runtime_std_write',2,m.data,len(tail))
        m.call('wine_nx_transition_alloc_site',1,131077,64,0x12345,12)
        fp=m.data+0x8000
        m.vm.mem_write(fp,struct.pack('<4Q',fp+16,0x87c8c,fp+16,0x885f8))
        m.call('fx_crash_native_detail',fp)
        text=bytes(m.vm.mem_read(m.symbols['fx_crash_buffer'],m.u32('fx_crash_length')))
        for line in (b'bt00=0x0000000000087c8c',b'bt01=0x00000000000885f8',b'alloc_size=0x0000000000020005',b'native_text_tail=memory allocation'):
            assert line in text,line
        assert b'bt02=' not in text
        m.set32('fx_crash_length',0);m.set32('fx_tr_lock',1)
        m.call('fx_crash_native_detail',1)
        text=bytes(m.vm.mem_read(m.symbols['fx_crash_buffer'],m.u32('fx_crash_length')))
        assert b'bt00=' not in text and b'trace_busy=' in text
        m.set32('fx_tr_lock',0);m.set32('fx_crash_records',0)
        m.call('wine_nx_crash_rust_allocation',3,131077,64,65536,0x12345)
        assert b'RECORD=RUST_ALLOCATION_FAILED' in m.writes[-1][1] and b'old_size=0x0000000000010000' in m.writes[-1][1]
    r={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
       'nro_sha256':hashlib.sha256(nro).hexdigest(),'checks':[
       'ARM64 bootstrap preallocates bounded file, flushes session header and reads actual NRO build ID',
       'Real FEX STOP callback flushes record without worker, stdio, heap or locks',
       'Native exception writer reads real dump offsets and persists registers and module metadata',
       'Reentry and record limit return without dereferencing exception input',
       'abort/diagAbortWithResult/svcBreak still reach original termination with unchanged arguments',
       'When enabled, native context retains buffered text, allocation site and checked frame chain; cycles and unreadable frames stop safely',
       'Debug breaks and zero exit cause no writes; FS write failure releases local guard'],
       'sources':{n:hashlib.sha256((Path(__file__).resolve().parents[1]/n).read_bytes()).hexdigest()
                  for n in ['src/runtime/fextendo_crash.h','tests/fextendo_crash_binary.py']}}
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
