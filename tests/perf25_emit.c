/* Real pinned opcode encoders and branch macros, producing both loop variants. */
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#include <string.h>
static uint32_t words[128];
struct inst { int mark,mark2,mark3,markf,markf2,markseg,marklock,epilog; };
struct dynamic { int native_size; struct inst *insts; };
#define EMIT(A) do { words[dyn->native_size/4]=(uint32_t)(A); dyn->native_size+=4; } while (0)
#include "arm64_emitter.h"
#include "perf25_branches.h"
#include "../src/runtime/pes13_perf25_copy_emit.h"
#include "../src/runtime/pes13_perf25_policy.h"
static int emit(int paircopy)
{
    struct inst inst={0}; struct dynamic context={0,&inst}, *dyn=&context;
    int ninst=0; int64_t j64;
    for (unsigned pass=0; pass<4; ++pass) {
        dyn->native_size=0;
        CBZx_NEXT(xRCX);
        TBNZ_MARK2(xFlags,10);
        if (paircopy) { PES25_COPY_FORWARD(); }
        MARK;
        LDRw_S9_postindex(x1,xRSI,4); STRw_S9_postindex(x1,xRDI,4);
        SUBx_U12(xRCX,xRCX,1); CBNZx_MARK(xRCX);
        B_NEXT_nocond;
        MARK2;
        LDRw_S9_postindex(x1,xRSI,-4); STRw_S9_postindex(x1,xRDI,-4);
        SUBx_U12(xRCX,xRCX,1); CBNZx_MARK2(xRCX);
        inst.epilog=dyn->native_size;
    }
    return dyn->native_size;
}
int main(int argc,char **argv)
{
    assert(argc==3);
    assert(pes25_copy_match(0x93df43,pes25_copy_guest,35,1,1,1));
    assert(!pes25_copy_match(0x93df42,NULL,35,1,1,1));
    assert(!pes25_copy_match(0x93df43,NULL,35,0,1,1));
    assert(!pes25_copy_match(0x93df43,NULL,35,1,0,1));
    assert(!pes25_copy_match(0x93df43,NULL,35,1,1,0));
    unsigned char code[35]; memcpy(code,pes25_copy_guest,35);
    for (unsigned i=0;i<35;++i) { code[i]^=1; assert(!pes25_copy_match(0x93df43,code,35,1,1,1)); code[i]^=1; }
    for (int mode=0;mode<2;++mode) {
        int bytes=emit(mode); FILE *f=fopen(argv[mode+1],"wb"); assert(f);
        assert(fwrite(words,1,bytes,f)==(size_t)bytes); fclose(f);
    }
    puts("PERF25 identity/scope/control/fingerprint guards and pinned encoder fixtures PASS");
}
