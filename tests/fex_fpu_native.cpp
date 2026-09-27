// SPDX-License-Identifier: MIT
// Numerical oracles and physical/logical register serialization contracts.
#include "../src/fex/horizon_fpu.h"
#include <cassert>
#include <cstdio>
#include <cfloat>
#include <cfenv>
#pragma STDC FENV_ACCESS ON
using namespace pes13_fex_fp;
static uint64_t random_bits() {
    static uint64_t state=0x14368face1789ULL;
    state^=state<<13; state^=state>>7; state^=state<<17; return state;
}
int main() {
    assert(expand(0x3ff8000000000000ULL).significand==0xc000000000000000ULL);
    assert(expand(0x3ff8000000000000ULL).exponent==0x3fff);
    assert(expand(1).exponent==15309 && expand(1).significand==(1ULL<<63));
    assert(expand(0x8000000000000000ULL).exponent==0x8000);
    const uint64_t edges[]={0,1,0xfffffffffffffULL,0x10000000000000ULL,
        0x7fefffffffffffffULL,0x7ff0000000000000ULL,0x7ff0000000000001ULL,
        0x7ff8000000000000ULL,0x8000000000000000ULL,0xfff123456789abcdULL};
    for(auto bits:edges) for(unsigned mode=0;mode<4;mode++)
        assert(narrow(expand(bits),0x37f|(mode<<10))==bits);
    for(unsigned i=0;i<100000;i++) {
        uint64_t bits=random_bits();
        assert(narrow(expand(bits),0x37f)==bits); // includes NaNs without quieting
    }
    uint64_t raw[8][2], output[8][2], restored[8][2];
    for(unsigned top=0;top<8;top++) for(unsigned reduced=0;reduced<2;reduced++) {
        for(unsigned i=0;i<8;i++) { raw[i][0]=edges[i]; raw[i][1]=0x3fff+i; }
        PES13FexExportX87(output,raw,top<<11,reduced);
        for(unsigned i=0;i<8;i++) {
            auto expected=reduced?expand(raw[(top+i)&7][0]):Extended{raw[(top+i)&7][0],raw[(top+i)&7][1]};
            assert(output[i][0]==expected.significand && output[i][1]==expected.exponent);
        }
        PES13FexImportX87(restored,output,top<<11,0x37f,reduced);
        for(unsigned i=0;i<8;i++) {
            assert(restored[i][0]==raw[i][0]);
            assert(restored[i][1]==(reduced?0:raw[i][1]));
        }
    }
    // Ties at 1.0, directed underflow and signed overflow.
    Extended halfway{0x8000000000000400ULL,0x3fff};
    assert(narrow(halfway,0x37f)==0x3ff0000000000000ULL);
    assert(narrow(halfway,0xb7f)==0x3ff0000000000001ULL);
    assert(narrow({1,0},0xb7f)==1);
    assert(narrow({1,0x8000},0x77f)==0x8000000000000001ULL);
    assert(narrow({1ULL<<63,0x7ffe},0xf7f)==0x7fefffffffffffffULL);
    unsigned oracle=0;
#if defined(__x86_64__) && LDBL_MANT_DIG == 64
    const int modes[]={FE_TONEAREST,FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO};
    for(unsigned mode=0;mode<4;mode++) {
        assert(fesetround(modes[mode])==0);
        for(unsigned i=0;i<20000;i++) {
            Extended value{random_bits()|(1ULL<<63),(random_bits()%0x7ffe)+1};
            if(i&1) value.exponent|=0x8000;
            long double storage=0;
            memcpy(&storage,&value,10);
            volatile long double input=storage;
            volatile double converted=static_cast<double>(input);
            double result=converted; uint64_t bits; memcpy(&bits,&result,8);
            if(bits!=narrow(value,0x37f|(mode<<10))) {
                fprintf(stderr,"oracle mismatch %llx/%llx mode %u expected %llx actual %llx\n",
                    (unsigned long long)value.significand,(unsigned long long)value.exponent,mode,
                    (unsigned long long)bits,(unsigned long long)narrow(value,0x37f|(mode<<10)));
                return 1;
            }
            ++oracle;
        }
    }
#endif
    printf("PASS FPU: 100000 bit roundtrips, all TOP/profile combinations, edges/rounding; x87 oracle=%u\n",oracle);
}
