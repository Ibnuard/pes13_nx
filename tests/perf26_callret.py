"""Exercise the actual pinned return emitter, retained stack cap and trap routing.

The fixture omits unchanged flag/memory barriers and tests have_purge=0 only.
This is not a whole-emulator or Switch integration test.
"""
from pathlib import Path
import hashlib,json,os,random,struct,subprocess,tempfile
import unicorn as uc
from unicorn import arm64_const as ar
p=Path(__file__).resolve().parents[1];out=p/'local/perf26'
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
source=root/'runtime-perf11-source/wine-nx-probe';arm=source/'vendor/box64/src/dynarec/arm64'
raw=(arm/'dynarec_arm64_helper.c').read_text()
ret=raw[raw.index('void ret_to_next('):raw.index('void iret_to_next(')]
ops=(root/'runtime-perf25-paircopy/wine-nx-box64-core-dynarec_arm64_00.c').read_text()
cap='''ADDx_U12(x3, xSP, 0);
                        SUBx_REG(x3, xSavedSP, x3);
                        LSRx(x3, x3, 16);
                        CBZx(x3, 2*4);
                        SUBx_U12(xSP, xSavedSP, 16);'''
assert ops.count(cap)==3
trapraw=(source/'source/wow64_box64_dynarec.c').read_text()
trap=trapraw[trapraw.index('int wine_nx_box64_callret_trap('):trapraw.index('\n#ifdef JMPTABL_SHIFT4',trapraw.index('int wine_nx_box64_callret_trap('))]
with tempfile.TemporaryDirectory(prefix='perf26-return-',dir=root) as tmp:
    tmp=Path(tmp)
    fixture='''#include <stdint.h>
#include <stdio.h>
#include <assert.h>
static uint32_t words[128];static unsigned used;
#define EMIT(A) do {words[used++]=(uint32_t)(A);} while(0)
#include "arm64_emitter.h"
typedef struct {int dynarec_callret;} env_t;
typedef struct {int have_purge;env_t *env;} dynarec_arm_t;
typedef struct {int is32bits;int w;} rex_t;
#define MAYUSE(A) (void)(A)
#define CHECK_DFNONE(A) ((void)0)
#define SMEND() ((void)0)
#define NOTEST(A) ((void)0)
#define CLEARIP() ((void)0)
#define BOX64DRENV(A) dyn->env->A
static void doLeaveBlock(dynarec_arm_t*d,int n,int a,int b,int c) {assert(!"purge outside fixture scope");}
static int indirect_lookup(dynarec_arm_t *dyn,int n,int bits,int a,int b) {MOVx_REG(x2,7);return x2;}
'''+ret+'''
int main(int argc,char **argv) {
 assert(argc==5);env_t env={0};dynarec_arm_t d={0,&env};rex_t rex={1,0};
 for(int mode=0;mode<4;++mode) {
  used=0;
  if(mode<2) {env.dynarec_callret=mode?2:0;ret_to_next(&d,0,0,rex);}
  else {'''+cap+'''
   if(mode==2){STPx_S7_preindex(x4,x2,xSP,-16);}else{STPx_S7_preindex(x4,xRIP,xSP,-16);}
  }
  FILE*f=fopen(argv[mode+1],"wb");assert(f);assert(fwrite(words,4,used,f)==used);fclose(f);
 }
}
'''
    (tmp/'emit.c').write_text(fixture)
    subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=undefined',
        '-fno-sanitize=shift','-I'+str(arm),str(tmp/'emit.c'),'-o',str(tmp/'emit')],check=True)
    names=['return-baseline','return-guarded','push-direct','push-indirect']
    subprocess.run([str(tmp/'emit')]+[str(out/(name+'.bin')) for name in names],check=True)
    codes=[(out/(name+'.bin')).read_bytes() for name in names]
    X=[getattr(ar,'UC_ARM64_REG_X'+str(i)) for i in range(31)]
    CODE,STACK,NATIVE,FALLBACK=0x100000,0x200000,0x300000,0x301000
    saved=STACK+0x12000;rng=random.Random(26);cases=0
    def machine(code,sp):
        m=uc.Uc(uc.UC_ARCH_ARM64,uc.UC_MODE_ARM)
        m.mem_map(CODE,4096);m.mem_write(CODE,code);m.mem_map(STACK,0x20000);m.mem_map(NATIVE,8192)
        for i,r in enumerate(X):m.reg_write(r,0xa00000+i)
        m.reg_write(ar.UC_ARM64_REG_SP,sp);m.reg_write(X[28],saved)
        m.reg_write(ar.UC_ARM64_REG_NZCV,0xa0000000);m.reg_write(X[7],FALLBACK)
        return m
    for mode in (0,1):
        for match in (False,True):
            for depth in (16,32,128,65520,65536):
                for _ in range(40):
                    sp=saved-depth;target=rng.randrange(0x401000,0x13d1000)
                    m=machine(codes[mode],sp);m.reg_write(X[27],target)
                    m.mem_write(sp,struct.pack('<QQ',NATIVE,target if match else target+1))
                    dest=NATIVE if mode and match else FALLBACK
                    m.emu_start(CODE,dest,count=100)
                    assert m.reg_read(ar.UC_ARM64_REG_PC)==dest
                    assert m.reg_read(ar.UC_ARM64_REG_SP)==(sp if not mode else sp+16 if match else saved-16)
                    for i in (*range(10,28),28):
                        assert m.reg_read(X[i])==(target if i==27 else saved if i==28 else 0xa00000+i)
                    assert m.reg_read(ar.UC_ARM64_REG_NZCV)==0xa0000000
                    cases+=1
    for mode in (2,3):
        for depth in (0,16,32,65504,65520,65536,65552,70000):
            m=machine(codes[mode],saved-depth);m.reg_write(X[4],NATIVE)
            m.reg_write(X[2],0x123456);m.reg_write(X[27],0xabcdef)
            m.emu_start(CODE,CODE+len(codes[mode]),count=100)
            sp=saved-32 if depth>=65536 else saved-depth-16
            assert m.reg_read(ar.UC_ARM64_REG_SP)==sp
            assert bytes(m.mem_read(sp,16))==struct.pack('<QQ',NATIVE,0x123456 if mode==2 else 0xabcdef)
            assert m.reg_read(ar.UC_ARM64_REG_NZCV)==0xa0000000
            cases+=1
    harness='''#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <stdio.h>
typedef struct {unsigned offs;int type;} callret_t;
typedef struct {void *block,*x64_addr,*jmpnext;size_t size,x64_size;int callret_size,gone,always_test;unsigned hash;callret_t *callrets;} dynablock_t;
struct nx_arena {unsigned char *rw;size_t used;};
static uint32_t code[4];static callret_t sites[2]={{0,0},{8,0}};static dynablock_t db;
static struct nx_arena arena={(void*)code,sizeof(code)};
static int present=1,readable=1,protects,flushes,left;static unsigned current_hash=123;
unsigned int wine_nx_box64_callret_clean,wine_nx_box64_callret_dirty;
#define ARCH_NOP 0xd503201fU
#define ARCH_UDF 0xcafeU
static struct nx_arena *find_arena(void*p,size_t*o) {*o=(uintptr_t)p-(uintptr_t)code;return present && *o<sizeof(code)?&arena:NULL;}
static dynablock_t *block_at(struct nx_arena*a,size_t o){(void)a;(void)o;return &db;}
static int guest_code_readable(void*a,uintptr_t n){(void)a;(void)n;return readable;}
static unsigned X31_hash_code(void*a,int n){(void)a;(void)n;return current_hash;}
static void protectDB(uintptr_t a,int n){(void)a;(void)n;protects++;}
static void *DynarecMapWritableAddress(void*p){return p;}
static void DynarecMapClearCache(void*a,size_t n){(void)a;(void)n;flushes++;}
static void protectDBJumpTable(uintptr_t a,size_t n,void*b,void*c){(void)a;(void)n;(void)b;(void)c;protects++;}
static void dynablock_leave_runtime(dynablock_t*d){(void)d;left++;}
static void arm64_epilog(void){}
'''+trap+'''
int main(void){
 db=(dynablock_t){.block=code,.x64_addr=code,.size=16,.x64_size=16,.callret_size=2,.hash=123,.callrets=sites};
 uintptr_t pc;
 code[0]=code[2]=ARCH_UDF;pc=(uintptr_t)code;
 assert(wine_nx_box64_callret_trap(&pc)==1 && pc==(uintptr_t)code+4);
 assert(code[0]==ARCH_NOP && code[2]==ARCH_NOP && flushes==1 && protects==1 && !left);
 assert(wine_nx_box64_callret_clean==1);
 for(int mode=0;mode<3;++mode){
  code[0]=code[2]=ARCH_UDF;pc=(uintptr_t)code;db.gone=mode==0;readable=mode!=1;current_hash=mode==2?124:123;
  assert(wine_nx_box64_callret_trap(&pc)==1 && pc==(uintptr_t)arm64_epilog);
  assert(code[0]==ARCH_UDF && code[2]==ARCH_UDF && left==mode+1);
 }
 assert(wine_nx_box64_callret_dirty==3);db.gone=0;readable=1;current_hash=123;
 db.always_test=1;pc=(uintptr_t)code;
 assert(wine_nx_box64_callret_trap(&pc)==1 && pc==(uintptr_t)code+4);
 assert(code[0]==ARCH_UDF && code[2]==ARCH_UDF && flushes==1 && protects==2);
 db.always_test=0;
 for(int mode=0;mode<4;++mode){
  present=mode!=0;code[0]=mode==1?ARCH_NOP:ARCH_UDF;sites[0].type=mode==2;db.callret_size=mode==3?0:2;pc=(uintptr_t)code;
  assert(wine_nx_box64_callret_trap(&pc)==0 && pc==(uintptr_t)code);
 }
 puts("PERF26 actual trap body: clean, dirty, unreadable, gone, always-test and non-return rejection PASS");
}
'''
    (tmp/'trap.c').write_text(harness)
    subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(tmp/'trap.c'),'-o',str(tmp/'trap')],check=True)
    subprocess.run([str(tmp/'trap')],check=True)
    report={'emitted_return_and_stack_cap_cases':cases,'trap_routing_cases':9,
        'actual_pinned_return_body':True,'all_three_existing_stack_caps_identical':True,'guarded_mode':2,
        'source_sha256':{'return_body':hashlib.sha256(ret.encode()).hexdigest(),'trap_body':hashlib.sha256(trap.encode()).hexdigest()},
        'limits':['Return emitter fixture uses have_purge=0, unchanged memory/flag barriers omitted.',
                 'Trap harness stubs memory mapping/cache/hash APIs; no concurrent self-modifying-code test.',
                 'These tests do not establish whole-game correctness or speed on Switch.'],'hardware_tested':False}
    (out/'callret-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
