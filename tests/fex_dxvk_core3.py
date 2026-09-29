"""Exercise role offload in production C and linked ARM64 with modeled SVC grants."""
from pathlib import Path
import argparse,hashlib,json,struct,subprocess,tempfile,re
from fex_worker_cores import Model as WorkerModel,reg
from unicorn import arm64_const as arm
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class Model(WorkerModel):
    def __init__(self,p):
        super().__init__(p);self.priorities={21:59};self.permitted_priorities=(1<<64)-1;self.priority_failure=0;self.queries_fail=0;self.query_pid=10;self.query_tid=24
        self.masks[21]=2;self.q(self.teb+0x40,10)
        self.vm.mem_write(self.symbols['registry'],struct.pack('<IIc3xii4xQQQ',21,24,b'w',1,0,self.teb,0,0))
    def string(self,p):
        b=bytearray()
        while (c:=bytes(self.vm.mem_read(p+len(b),1)))!=b'\0':b+=c
        return bytes(b)
    def hook(self,vm,pc,size,user):
        s=self.symbols
        if pc==s.get('svcGetInfo') and vm.reg_read(reg(1))==1:
            self.q(vm.reg_read(reg(0)),self.permitted_priorities);self.ret(self.info_error)
        elif pc==s.get('svcGetThreadPriority'):
            out,h=[vm.reg_read(reg(i)) for i in range(2)];self.u32(out,self.priorities[h]);self.ret()
        elif pc==s.get('svcSetThreadPriority'):
            h,p=[vm.reg_read(reg(i)) for i in range(2)]
            if not self.priority_failure:self.priorities[h]=p
            self.ret(self.priority_failure)
        elif pc==s.get('snprintf'):
            dst,n,fmt=[vm.reg_read(reg(i)) for i in range(3)];text=self.string(vm.reg_read(reg(3))) if self.string(fmt)==b'%s' else b'log'
            text=text[:n-1];vm.mem_write(dst,text+b'\0');self.ret(len(text))
        elif pc==s.get('NtQueryInformationThread'):
            out=vm.reg_read(reg(2));self.q(out+16,self.query_pid);self.q(out+24,self.query_tid);self.ret(self.queries_fail)
        elif pc==s.get('pthread_getspecific'):self.ret(self.teb)
        elif pc==s.get('GetCurrentProcessId'):self.ret(10)
        else:super().hook(vm,pc,size,user)
    def name(self,value,native=False):
        p=self.data+0x6000
        if native:
            v=value.encode('utf-16-le');self.vm.mem_write(p,v+b'\0\0');self.vm.mem_write(p+0x500,struct.pack('<HH4xQ',len(v),len(v)+2,p));self.call('set_native_thread_name',0xffffffffffffffff,p+0x500)
        else:self.vm.mem_write(p,value.encode()+b'\0');self.call('wine_nx_fex_dxvk_name',24,p)
    def active(self):return self.read32(self.symbols['fex_dxvk_slots']+64)

def main():
    p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--source',type=Path,required=True);a=p.parse_args();w=a.work.resolve();elf=w/'runtime/reference/pes13-fex.elf';checks=[]
    with tempfile.TemporaryDirectory() as d:
        exe=Path(d)/'native'
        subprocess.run(['clang','-std=c11','-O1','-g','-Wall','-Wextra','-pthread','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(ROOT/'tests/fex_dxvk_core3.c'),'-o',str(exe)],check=True)
        r=subprocess.run([str(exe)],check=True,text=True,capture_output=True);checks.append(r.stdout.strip())
    m=Model(elf)
    for requested,auto,grant,priority in [(0,0,15,(1<<64)-1),(1,1,15,(1<<64)-1),(1,0,7,(1<<64)-1),(1,0,15,1<<59)]:
        m.grant=grant;m.permitted_priorities=priority;m.call('wine_nx_fex_dxvk_configure',requested,auto);m.name('dxvk-cs',True);assert m.masks[21]==2 and not m.active() and not m.sets
    m.grant=15;m.permitted_priorities=(1<<64)-1;m.call('wine_nx_fex_dxvk_configure',1,0)
    for name in ('dxvk-submit','dxvk-queue','game','dxvk-cs-extra','DXVK-CS','dxvk-csé'):
        m.name(name,True);assert m.masks[21]==2 and not m.active()
    m.query_pid=99;m.name('dxvk-cs',True);assert not m.active();m.query_pid=10
    m.queries_fail=0xc0000008;m.name('dxvk-cs',True);assert not m.active();m.queries_fail=0
    m.u32(m.symbols['registry']+16,1);m.name('dxvk-cs',True);assert not m.active();m.u32(m.symbols['registry']+16,0)
    m.name('dxvk-cs',True);assert m.active() and m.masks[21]==8 and m.priorities[21]==63
    calls=len(m.sets);m.name('dxvk-cs',True);assert len(m.sets)==calls
    m.name('game',True);assert not m.active() and m.masks[21]==2 and m.priorities[21]==59
    m.name('dxvk-cs',True);assert m.call('wine_nx_fex_dxvk_affinity',24,4)==1
    assert not m.active() and m.masks[21]==4 and m.priorities[21]==59 and m.read32(m.pipe+96)==4
    checks.append('Linked ARM64: UTF-16 name bridge, exact role, foreign/failed query, explicit affinity, grants/OFF, priority 63, rename restore and real server-mask publication.')
    # Include one heavily loaded helper beside ordinary workers: balancing must
    # not repatriate it to cores 0-2 or move its server connection to core 3.
    m=Model(elf);m.call('wine_nx_fex_dxvk_configure',1,0);m.name('dxvk-cs',True)
    m.balance([(21,8,850,0),(22,1,900,0),(23,2,100,0),(24,4,100,0)])
    assert m.masks[21]==8 and not any(h==21 and mask!=8 for h,core,mask in m.sets)
    checks.append('Linked ARM64: stable balancer excludes active helper, leaves application policy intact.')
    # Candidate role stays at normal priority, remains visible to the real
    # stable balancer and carries its server connection to the quieter core.
    m=Model(elf);m.call('wine_nx_fex_dxvk_configure',0,0);m.name('dxvk-cs',True)
    m.balance([(21,1,300,0),(22,1,800,0),(23,2,350,0),(24,4,900,0)])
    assert m.masks[21]==2 and m.priorities[21]==59 and not m.active()
    assert m.sets==[(21,1,2)] and m.read32(m.pipe+96)==2
    runtime=(a.source/'wine-nx-probe/source/runtime.c').read_text()
    assert '"/fex_dxvk_balance", 1)' in runtime
    assert 'wine_nx_fex_dxvk_configure(!guest_tests && !fex_dxvk_balance && fex_dxvk_legacy, wine_nx_fex_auto_core3);' in runtime
    checks.append('Candidate default overrides legacy core3 request; normal-priority dxvk-cs participates in linked one-move balancing with server-mask follow.')
    thread=(a.source/'dlls/ntdll/unix/thread.c').read_text();profile=(a.source/'wine-nx-probe/source/thread_profile.c').read_text()
    assert 'if (!status && !fex_dxvk_explicit_affinity(handle,req_aff) && is_current_thread_handle( handle ))' in thread
    assert 'memset(&fex_dxvk_slots[slot],0,sizeof(fex_dxvk_slots[slot]));' in profile
    dis=subprocess.check_output(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump','-d','--disassemble=NtSetInformationThread',str(elf)],text=True)
    assert re.search(r'\bbl\s+[0-9a-f]+ <wine_nx_fex_dxvk_affinity>',dis)
    checks.append('Final NtSetInformationThread routes accepted affinity to helper restore; reused registry slots clear role metadata.')
    sources=['src/runtime/fex_dxvk_core3.h','tools/fex_dxvk_core3_patches.py','tests/fex_dxvk_core3.c','tests/fex_dxvk_core3.py']
    result={'passed':True,'hardware_tested':False,'native_elf_sha256':sha(elf),'checks':checks,'source_hashes':{s:sha(ROOT/s) for s in sources}}
    (w/'dxvk-core3.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
