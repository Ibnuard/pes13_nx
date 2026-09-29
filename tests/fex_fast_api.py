"""Execute the final ARM64 gateway: live table guards, ABI, fallback and QPC.

Native clock, delay handler and TLS are modeled boundaries; this is neither
Horizon scheduling nor a hardware speedup measurement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unicorn import UcError
from fex_reservations import Model as NativeModel, arm, reg
from fextendo_source_normalization import undo_fast_api

ROOT=Path(__file__).resolve().parents[1]


class Model(NativeModel):
    def __init__(self, elf):
        super().__init__(elf)
        self.steps=0;self.route=[];self.handlers=[];self.traces=0
        self.teb=self.data+0x9000;self.tls=self.data+0x5000
        self.counter=9876543210123;self.delay_status=0x102
        self.table=self.data+0x2000;self.argsizes=self.data+0x4000
        self.custom=self.data+0x800
        self.q(self.table+0x31*8,self.symbols['NtQueryPerformanceCounter'])
        self.q(self.table+0x34*8,self.symbols['NtDelayExecution'])
        self.q(self.table+9*8,self.custom)
        self.vm.mem_write(self.argsizes,bytes(256))
        self.vm.mem_write(self.argsizes+9,bytes([128]))
        self.vm.mem_write(self.argsizes+0x31,bytes([16]))
        self.vm.mem_write(self.argsizes+0x34,bytes([16]))
        for i in range(4):
            self.vm.mem_write(self.symbols['KeServiceDescriptorTable']+i*32,
                              struct.pack('<4Q',self.table,0,256,self.argsizes))
        self.vm.mem_write(self.symbols['wine_nx_fex_polling'],struct.pack('<I',1))

    def hook(self,vm,pc,size,user):
        self.steps+=1;s=self.symbols
        if pc in (s.get('wine_nx_fex_fast_qpc'),s.get('wine_nx_fex_fast_delay'),s.get('wine_nx_do_syscall')):
            self.route.append(next(k for k in ('wine_nx_fex_fast_qpc','wine_nx_fex_fast_delay','wine_nx_do_syscall') if s[k]==pc))
        if pc==s.get('__aarch64_read_tp'):
            self.ret(self.tls);return
        if pc in (s.get('wine_nx_current_teb'),s.get('NtCurrentTeb')):
            self.ret(self.teb);return
        if pc==s.get('horizon_interrupt_time'):
            vm.reg_write(reg(18),0xdead1234) # force native clobber, gateway must restore Wine TEB
            self.ret(self.counter);return
        if pc==s.get('NtDelayExecution'):
            self.handlers.append((vm.reg_read(reg(0)),vm.reg_read(reg(1))))
            vm.reg_write(reg(18),0xdead5678)
            self.ret(self.delay_status);return
        if pc==self.custom:
            args=[vm.reg_read(reg(i)) for i in range(8)]
            sp=vm.reg_read(arm.UC_ARM64_REG_SP)
            args.extend(self.uq(sp+i*8) for i in range(8))
            self.handlers.append(args);self.ret(sum(args));return
        if pc==s.get('snprintf'):
            self.ret(0);return
        if pc==s.get('wine_nx_runtime_trace'):
            self.traces+=1;self.ret();return
        super().hook(vm,pc,size,user)

    def run(self,id,args=(),enabled=1,verbose=0):
        self.returned=False;self.steps=0;self.route=[];self.handlers=[];self.traces=0
        self.vm.mem_write(self.symbols['wine_nx_fex_fast_api'],struct.pack('<I',enabled))
        self.vm.mem_write(self.symbols['wine_nx_runtime_verbose'],struct.pack('<I',verbose))
        self.vm.reg_write(arm.UC_ARM64_REG_SP,self.stack+0xf000)
        for i in range(8):self.vm.reg_write(reg(i),args[i] if i<len(args) else i+1)
        for i in range(8):self.q(self.stack+0xf000+i*8,9+i)
        self.vm.reg_write(reg(8),id);self.vm.reg_write(reg(9),self.stop)
        self.vm.reg_write(reg(18),self.teb)
        for i in range(19,30):self.vm.reg_write(reg(i),0xabcdef00+i)
        self.vm.reg_write(reg(30),self.stop+4) # stub's return must be bypassed, same as original gateway
        self.vm.emu_start(self.symbols['__wine_syscall_dispatcher'],0,count=100000)
        assert self.returned
        assert self.vm.reg_read(arm.UC_ARM64_REG_SP)==self.stack+0xf000
        assert self.vm.reg_read(reg(18))==self.teb
        for i in range(19,30):assert self.vm.reg_read(reg(i))==0xabcdef00+i,(i,self.route)
        return self.vm.reg_read(reg(0))&0xffffffff


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,required=True);ap.add_argument('--source',type=Path,required=True)
    a=ap.parse_args();elf=a.work/'runtime/reference/pes13-fex.elf'
    r=json.loads((a.work/'runtime/runtime-build.json').read_text())
    assert r['fast_api'] and hashlib.sha256(elf.read_bytes()).hexdigest()==r['native_elf_sha256']
    old=json.loads((ROOT/'local/fex3/polling-v1/runtime/wine-patches.json').read_text())
    # Retain the v3.5 API oracle while admitting only the three embedded menu
    # headers changed by this native-only cleanup. The historical archive is
    # pinned; each whole header must match once, and replay must be byte exact.
    import zipfile
    archive=ROOT/'dist/pes13-fextendo-v3.5-polling-v1.zip'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()=='c9b05eba80fb2b9994ab0ebbe9ad77bc91a488bde2811d80fe5f5426bb8739c3'
    scopes={}
    for name in ('dlls/ntdll/unix/signal_arm64.c','wine-nx-probe/source/runtime.c','wine-nx-probe/source/thread_profile.c'):
        text,scope=undo_fast_api((a.source/name).read_text(),ROOT,name)
        if name.endswith('/runtime.c'):
            edits=[]
            original=text
            with zipfile.ZipFile(archive) as z:
                for header in ('presets','ui','launcher'):
                    path='src/runtime/fextendo_'+header+'.h'
                    new=(ROOT/path).read_text()
                    before=z.read('source/'+path).decode()
                    assert r['patch_sources'][path]==hashlib.sha256(new.encode()).hexdigest()
                    assert text.count(new)==1,path
                    text=text.replace(new,before,1)
                    edits.append((new,before))
            replay=text
            for new,before in reversed(edits):
                assert replay.count(before)==1
                replay=replay.replace(before,new,1)
            assert replay==original
            scope['launcher_headers_exact_roundtrip']=True
        assert hashlib.sha256(text.encode()).hexdigest()==old['native-source'][name],name
        scopes[name]=scope
    counts={}
    for enabled in (0,1):
        m=Model(elf);p=m.data+0x100;f=p+16
        for frequency in (f,0,p):
            assert m.run(0x31,(p,frequency),enabled)==0
            assert m.uq(p)==(10000000 if frequency==p else m.counter)
            if frequency:assert m.uq(frequency)==10000000
            assert m.route==['wine_nx_fex_fast_qpc' if enabled else 'wine_nx_do_syscall']
        # Measure warmed counters with identical modeled service boundaries.
        m.run(0x31,(p,f),enabled);counts[str(enabled)]=m.steps
        for alertable,timeout in ((0,p),(0,0),(1,p)):
            assert m.run(0x34,(alertable,timeout),enabled)==m.delay_status
            assert m.handlers==[(alertable,timeout)]
            assert m.route==['wine_nx_fex_fast_delay' if enabled and not alertable else 'wine_nx_do_syscall']
        assert m.run(9,range(1,9),enabled)==136
        assert m.handlers==[list(range(1,17))]
        assert m.run(0x31,(p,f),enabled,verbose=1)==0 and m.traces==2
        assert m.route==['wine_nx_do_syscall']
        assert m.run(0x1031,(p,f),enabled)==0 and m.route==['wine_nx_do_syscall']
        assert m.run(0x300,enabled=enabled)==0xc000001c
        assert m.run(7,enabled=enabled)==0xc000001c
        # Pinning an ID is insufficient: mutated handler must keep full routing.
        m.q(m.table+0x31*8,m.custom);m.vm.mem_write(m.argsizes+0x31,bytes([128]))
        assert m.run(0x31,range(1,9),enabled)==136
        assert m.route==['wine_nx_do_syscall'] and m.handlers==[list(range(1,17))]
        m.q(m.table+0x31*8,0)
        assert m.run(0x31,(p,f),enabled)==0xc000001c
        m.q(m.symbols['KeServiceDescriptorTable']+16,0x31)
        assert m.run(0x31,(p,f),enabled)==0xc000001c
    faults=[]
    for enabled in (0,1):
        m=Model(elf)
        try:m.run(0x31,(0,0),enabled)
        except UcError:
            faults.append(m.vm.reg_read(arm.UC_ARM64_REG_PC))
        else:raise AssertionError('NULL required counter unexpectedly succeeded')
    assert len(faults)==2 and faults[0]==faults[1],faults
    assert counts['1']<counts['0'],counts
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':r['native_elf_sha256'],
            'checks':['Live ID/handler/table-limit guards, null handler, other table and verbose fallback',
                      'Final assembly preserves x18, x19-x29, SP and PE caller LR, including forced native x18 clobber',
                      'Original QPC value/frequency, optional/aliased outputs and identical faulting store',
                      'Delay arguments/status retained; alertable requests use original gateway',
                      'Fallback preserves all 16 arguments; wrong handler never enters fast path'],
            'warm_qpc_modeled_instructions':counts,'scope':scopes,
            'source_hashes':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in
                ('tests/fex_fast_api.py','tests/fex_reservations.py','tests/fextendo_source_normalization.py',
                 'tools/fex_fast_api_patches.py','src/runtime/fex_fast_api.h','src/runtime/fex_polling_counters.h')}}
    (a.work/'fast-api.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
