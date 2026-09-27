"""Compile actual generated WOW64 floating-point import/export slices against contract tests."""
from pathlib import Path
import argparse,hashlib,json,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
PRE = r'''
#include <cstdint>
#include <cstring>
#include <cstdio>
#include "horizon_fpu.h"
bool HorizonReducedPrecision=false;
using std::memcpy;
using U128=__uint128_t;
namespace FEXCore { namespace X86State {
enum { X87FLAG_IE_LOC, X87FLAG_C0_LOC, X87FLAG_C1_LOC, X87FLAG_C2_LOC, X87FLAG_C3_LOC, X87FLAG_TOP_LOC };
} namespace FPState {
// Tag conversion does not affect tested registers; no claim to test tags.
uint16_t ConvertFromAbridgedFTW(uint16_t, const uint64_t (&)[8][2], uint8_t) { return 0; }
}}
struct alignas(16) XSAVE_FORMAT {
 uint16_t ControlWord,StatusWord; uint8_t TagWord,Reserved1; uint16_t ErrorOpcode;
 uint32_t ErrorOffset; uint16_t ErrorSelector,Reserved2; uint32_t DataOffset;
 uint16_t DataSelector,Reserved3; uint32_t MxCsr,MxCsr_Mask;
 U128 FloatRegisters[8],XmmRegisters[16]; uint8_t Reserved4[96];
};
static_assert(sizeof(XSAVE_FORMAT)==512);
struct Legacy { uint32_t ControlWord,StatusWord,TagWord,ErrorOffset,ErrorSelector,DataOffset,DataSelector; uint8_t RegisterArea[80]; uint32_t Cr0NpxState; };
struct ContextType { alignas(16) uint8_t ExtendedRegisters[512]; Legacy FloatSave; } context{};
struct StateType { U128 mm[8],xmm[8]; uint16_t FCW; uint8_t flags[64],AbridgedFTW; uint32_t mxcsr; } State{};
struct CtxType {
 void SetXMMRegistersFromState(void*,const U128* p,void*) { memcpy(State.xmm,p,sizeof(State.xmm)); }
 void ReconstructXMMRegisters(void*,U128* p,void*) { memcpy(p,State.xmm,sizeof(State.xmm)); }
} ctx;
auto* CTX=&ctx; void* Thread=nullptr;
void load(ContextType* Context) {
'''
POST = r'''
int failures=0,controls=0;
void check(const char* name,bool ok,bool control=false) {
 printf("%s %s\n",ok?"PASS":"FAIL",name); if(!ok) ++failures; else if(control) ++controls;
}
void reset() { context={}; State={}; HorizonReducedPrecision=false; }
int main() {
 auto* x=reinterpret_cast<XSAVE_FORMAT*>(context.ExtendedRegisters);
 reset(); State.mxcsr=0x5f80; x->MxCsr=0x1f80; save(&context);
 check("MXCSR export 0x5f80",x->MxCsr==0x5f80);
 reset(); x->MxCsr=0x5f80; State.mxcsr=0x1f80; load(&context);
 check("MXCSR import 0x5f80",State.mxcsr==0x5f80);
 reset(); State.flags[FEXCore::X86State::X87FLAG_TOP_LOC]=3;
 for(int i=0;i<8;i++) State.mm[i]=(U128(0x4000+i)<<64) | (0x8000000000000000ULL+i);
 U128 expected=State.mm[3]; save(&context);
 check("x87 export TOP=3 rotation",x->FloatRegisters[0]==expected);
 reset(); x->StatusWord=3<<11;
 for(int i=0;i<8;i++) x->FloatRegisters[i]=(U128(0x4000+i)<<64) | (0x8000000000000000ULL+i);
 expected=x->FloatRegisters[0]; load(&context);
 check("x87 import TOP=3 rotation",State.mm[3]==expected);
 reset(); HorizonReducedPrecision=true; State.mm[0]=0x3ff8000000000000ULL; save(&context);
 U128 ext=(U128(0x3fff)<<64)|0xc000000000000000ULL;
 check("F64 internal 1.5 exports as x87 80-bit",x->FloatRegisters[0]==ext);
 reset(); HorizonReducedPrecision=true; x->FloatRegisters[0]=ext; load(&context);
 check("x87 80-bit 1.5 imports as F64 internal",uint64_t(State.mm[0])==0x3ff8000000000000ULL);
 reset(); State.mm[0]=ext; save(&context);
 check("legacy FloatSave register data populated",memcmp(context.FloatSave.RegisterArea,&ext,10)==0);
 reset(); State.mm[0]=ext; State.FCW=0x37f; State.xmm[0]=12345; save(&context);
 check("control: TOP=0 full80 direct register export",x->FloatRegisters[0]==ext,true);
 check("control: FCW export",x->ControlWord==0x37f,true);
 State={}; load(&context); check("control: XMM roundtrip",State.xmm[0]==12345,true);
 printf("contract_failures=%d controls_passed=%d\n",failures,controls);
 return failures?1:0;
}
'''
def function(data,name):
 a=data.index('void '+name+'('); b=data.index('{',a); depth=1; e=b+1
 while depth:
  depth+=(data[e]=='{')-(data[e]=='}'); e+=1
 return data[b+1:e-1]
def main():
 if not __debug__: raise RuntimeError('Assertions required')
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
 p=args.source/'Source/Windows/WOW64/Module.cpp';data=p.read_text()
 load=function(data,'LoadStateFromWowContext');load=load[load.index('  // Floating-point register state'):]
 store=function(data,'StoreWowContextFromState');store=store[store.index('  // Floating-point register state'):]
 cpp=PRE+load+'\n}\nvoid save(ContextType* Context) {\n'+store+'\n}\n'+POST
 with tempfile.TemporaryDirectory(prefix='fex-fp-context-') as folder:
  file=Path(folder)/'test.cpp';binary=Path(folder)/'test';file.write_text(cpp)
  subprocess.run(['clang++','-std=c++17','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'src/fex'),str(file),str(ROOT/'src/fex/module_fpu.cpp'),'-o',str(binary)],check=True)
  r=subprocess.run([str(binary)],capture_output=True,text=True,check=True,timeout=30)
 report={'passed':True,'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'stdout':r.stdout,'stderr':r.stderr,'scope':'Generated context body, host ASan/UBSan, modeled Wine/FEX structures; not full guest execution'}
 args.output.write_text(json.dumps(report,indent=2)+'\n');print(r.stdout)
if __name__=='__main__':main()
