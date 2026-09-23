"""Execute the real emitted loops and compare x86 REP MOVSD, including faults.

WSL, with local/perf20/linux-libs on PYTHONPATH. No hardware FPS claim.
"""
from pathlib import Path
import ctypes as ct
import hashlib,json,os,random,struct,subprocess,sys,tempfile
import capstone
import unicorn as uc
from unicorn import arm64_const as ar, x86_const as xr
p=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(p/'tools'))
from perf15_patches import source_changes
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
source=root/'runtime-perf11-source'
arm=source/'wine-nx-probe/vendor/box64/src/dynarec/arm64'
out=p/'local/perf25'; out.mkdir(parents=True,exist_ok=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
helper=(arm/'dynarec_arm64_helper.h').read_text()
branches=helper[helper.index('#define MARK        '):helper.index('// Test bit N of A and branch to next instruction if not set')]
engine=source_changes(source,p/'patches/perf15')[source/'wine-nx-probe/source/wow64_box64_engine.c']
adjust=engine[engine.index('static void adjust_partial_instruction('):engine.index('static void recover_translated_state(')]
with tempfile.TemporaryDirectory(prefix='perf25-copy-',dir=root) as tmp:
    tmp=Path(tmp)
    (tmp/'perf25_branches.h').write_text(branches)
    exe=tmp/'emit'
    # Pinned upstream encoders construct signed-int bit patterns with shifts
    # into bit 31. Keep their exact bytes; disable only shift instrumentation.
    subprocess.run(['cc','-O2','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=undefined',
        '-fno-sanitize=shift','-fno-sanitize-recover=all',
        '-I'+str(arm),'-I'+str(tmp),str(p/'tests/perf25_emit.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe),str(out/'copy-baseline.bin'),str(out/'copy-pair.bin')],check=True)
    # Test the actual retained fault helper, not a reimplementation of it.
    (tmp/'adjust.c').write_text('''#include <stdint.h>
#include <assert.h>
#include <sys/mman.h>
typedef uintptr_t ULONG_PTR;
typedef union { uint64_t q[1]; uint32_t dword[2]; } test_reg;
typedef struct { test_reg regs[8],ip; } x64emu_t;
enum { _SP=4, _SI=6 };
'''+adjust+'''
uint32_t undo(uint32_t esi,uint32_t instruction) {
    static unsigned char *code;
    if (!code) { code=mmap(0,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_32BIT,-1,0);
        assert(code!=MAP_FAILED && (uintptr_t)code<=UINT32_MAX); code[0]=0xf3; code[1]=0xa5; }
    x64emu_t e={0}; e.ip.q[0]=(uintptr_t)code; e.regs[_SI].dword[0]=esi;
    adjust_partial_instruction(&e,(uintptr_t)&instruction); return e.regs[_SI].dword[0];
}
''')
    libfile=tmp/'adjust.so'
    subprocess.run(['cc','-O2','-fPIC','-shared','-Wall','-Wextra','-Werror','-fsanitize=undefined',str(tmp/'adjust.c'),'-o',str(libfile)],check=True)
    lib=ct.CDLL(str(libfile)); lib.undo.argtypes=[ct.c_uint32,ct.c_uint32];lib.undo.restype=ct.c_uint32
    baseline=(out/'copy-baseline.bin').read_bytes(); pair=(out/'copy-pair.bin').read_bytes()
    captured=(out/'captures/slot-1-arm64.bin').read_bytes()
    assert baseline==captured[36:80], 'Fixture must match the actual captured native loop'
    md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM)
    for name,code in [('baseline',baseline),('pair',pair)]:
        (out/f'copy-{name}.txt').write_text('\n'.join(f'{i.address:04x} {i.mnemonic} {i.op_str}' for i in md.disasm(code,0))+'\n')
    CODE,DATA,SIZE=0x100000,0x200000,0x4000
    X=[getattr(ar,'UC_ARM64_REG_X'+str(i)) for i in range(31)]
    Q=[getattr(ar,'UC_ARM64_REG_Q'+str(i)) for i in range(32)]
    rng=random.Random(25); initial=bytes(rng.getrandbits(8) for _ in range(SIZE))
    def run(code,count,src,dst,df,protect=None,x86=False):
        m=uc.Uc(uc.UC_ARCH_X86,uc.UC_MODE_32) if x86 else uc.Uc(uc.UC_ARCH_ARM64,uc.UC_MODE_ARM)
        m.mem_map(CODE,4096);m.mem_write(CODE,code);m.mem_map(DATA,SIZE);m.mem_write(DATA,initial)
        if protect: m.mem_protect(DATA+protect[0],4096,protect[1])
        flags=0x202|(df<<10); steps=[0]; failure=[]
        def invalid(machine,access,address,size,value,user):
            failure.append((access,address));return False
        m.hook_add(uc.UC_HOOK_MEM_INVALID,invalid)
        m.hook_add(uc.UC_HOOK_CODE,lambda *a:steps.__setitem__(0,steps[0]+1))
        if x86:
            for r,v in [(xr.UC_X86_REG_ECX,count),(xr.UC_X86_REG_ESI,src),(xr.UC_X86_REG_EDI,dst),(xr.UC_X86_REG_EFLAGS,flags)]:m.reg_write(r,v)
        else:
            for i,r in enumerate(X):m.reg_write(r,0xaaa000+i)
            for i,r in enumerate(Q):m.reg_write(r,0x112233445566778899aabbccdd000000+i)
            for r,v in [(ar.UC_ARM64_REG_X11,count),(ar.UC_ARM64_REG_X16,src),(ar.UC_ARM64_REG_X17,dst),(ar.UC_ARM64_REG_X26,flags),
                        (ar.UC_ARM64_REG_NZCV,0xa0000000),(ar.UC_ARM64_REG_FPCR,0x400000),(ar.UC_ARM64_REG_FPSR,0x10)]:m.reg_write(r,v)
        try:m.emu_start(CODE,CODE+len(code),count=10000)
        except uc.UcError:
            assert failure
        if x86:
            state=tuple(m.reg_read(r) for r in [xr.UC_X86_REG_ECX,xr.UC_X86_REG_ESI,xr.UC_X86_REG_EDI,xr.UC_X86_REG_EFLAGS])
        else:
            pc=m.reg_read(ar.UC_ARM64_REG_PC)
            if failure:
                word=struct.unpack_from('<I',code,pc-CODE)[0]
                m.reg_write(ar.UC_ARM64_REG_X16,lib.undo(m.reg_read(ar.UC_ARM64_REG_X16),word))
            else:assert pc==CODE+len(code)
            state=tuple(m.reg_read(X[i]) for i in (11,16,17,26))
            for i,r in enumerate(X):
                if i not in (1,11,16,17,26):assert m.reg_read(r)==0xaaa000+i
            assert all(m.reg_read(r)==0x112233445566778899aabbccdd000000+i for i,r in enumerate(Q))
            assert tuple(m.reg_read(r) for r in [ar.UC_ARM64_REG_NZCV,ar.UC_ARM64_REG_FPCR,ar.UC_ARM64_REG_FPSR])==(0xa0000000,0x400000,0x10)
        return (state,bytes(m.mem_read(DATA,SIZE)),failure),steps[0]
    cases=0;faults=0
    def check(n,s,d,df,protection=None,reference=True):
        global cases,faults
        before,steps0=run(baseline,n,s,d,df,protection)
        after,steps1=run(pair,n,s,d,df,protection)
        assert before==after,(n,s,d,df,protection,before[0],after[0],before[2],after[2])
        if reference:
            x86,_=run(b'\xf3\xa5',n,s,d,df,protection,x86=True)
            assert after==x86,(n,s,d,df,protection,after[0],x86[0],after[2],x86[2])
        cases+=1;faults+=bool(after[2]);return steps0,steps1
    for df in (0,1):
        for n in (0,1,2,3,4,7,16,237,238,239,512):
            for a in range(8):
                for delta in (-64,-16,-8,-4,-1,0,1,4,8,16,64,0x1000):
                    check(n,DATA+0x1000+a,DATA+0x1000+a+delta,df)
    for df in (0,1):
        for n in (2,8,238):
            for offset in (0,4,8,12,16):
                # Protection boundaries: aligned pairs never straddle a page.
                boundary=DATA+0x2000
                for read in (False,True):
                    s,d=(boundary-offset,DATA+0x800) if read else (DATA+0x800,boundary-offset)
                    check(n,s,d,df,(0x2000,uc.UC_PROT_NONE if read else uc.UC_PROT_READ))
    count0,count1=check(238,DATA+0x800,DATA+0x2000,0)
    report={'cases':cases,'page_fault_cases':faults,'x86_state_memory_identical':True,
        'unchanged_guest_flags_simd_and_other_gprs':True,'actual_perf15_fault_helper':True,
        'baseline_matches_hardware_capture':True,'instructions_238_aligned':{'baseline':count0,'pair':count1},
        'source_sha256':{str(f.relative_to(p)):sha(f.read_bytes()) for f in [p/'src/runtime/pes13_perf25_copy_emit.h',p/'src/runtime/pes13_perf25_policy.h',p/'tests/perf25_emit.c']},
        'baseline_sha256':sha(baseline),'pair_sha256':sha(pair),'hardware_tested':False}
    (out/'copy-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
