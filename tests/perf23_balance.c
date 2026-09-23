#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "thread_profile.h"
#include "../src/runtime/pes13_perf23_balance.h"

static uint64_t score(const struct nx_balance_thread *t, unsigned n, unsigned cores,
                      int after, unsigned *peak)
{
    unsigned load[NX_BALANCE_MAX_CORES]={0}; uint64_t result=0;
    for (unsigned i=0;i<n;i++) {
        int c=after?t[i].new_core:t[i].core;
        if(c>=0 && (unsigned)c<cores) load[c]+=t[i].load;
    }
    *peak=0;
    for(unsigned c=0;c<cores;c++) {
        result+=(uint64_t)load[c]*load[c];
        if(load[c]>*peak) *peak=load[c];
    }
    return result;
}
static uint32_t rng=0x235eed;
static uint32_t next(void) { rng=rng*1664525u+1013904223u; return rng; }
int main(void)
{
    /* PERF22 late-run-like layout: 124 owns the peak; 184/audio share core3
     * and core2 is empty. Upstream's peak-only admission rejects splitting. */
    struct nx_balance_thread example[]={{500,0,1,0},{846,1,0,1},{381,3,0,3},{220,3,0,3},{60,3,0,3}};
    struct nx_balance_thread tmp[5]; memcpy(tmp,example,sizeof(tmp));
    unsigned before,after; uint64_t gain;
    after=nx_balance_assign(tmp,5,4,&before);
    assert(after+5*NX_BALANCE_SLACK/3>=before);
    assert(pes23_secondary_move(example,5,4,&gain));
    assert(example[0].new_core==0 && example[1].new_core==1);
    assert(example[2].new_core==2 || example[3].new_core==2);
    assert(!pes23_secondary_move(NULL,0,0,&gain));
    assert(!pes23_secondary_move(NULL,0,1,&gain));
    assert(!pes23_secondary_move(NULL,0,NX_BALANCE_MAX_CORES+1,&gain));
    struct nx_balance_thread fixed[]={{800,1,1,1},{300,1,1,1},{200,-1,1,-1}};
    assert(!pes23_secondary_move(fixed,3,4,&gain));
    /* Random layouts: no fixed affinity changes, at most one migration,
     * never a larger measured peak, exact squared-load improvement. */
    for(unsigned trial=0;trial<20000;trial++) {
        struct nx_balance_thread t[32]; unsigned n=1+next()%32, cores=2+next()%7;
        for(unsigned i=0;i<n;i++) {
            t[i].load=next()%1001; t[i].fixed=(next()%5)==0;
            t[i].core=(int)(next()%(cores+1))-1; t[i].new_core=-2;
        }
        uint64_t old=score(t,n,cores,0,&before);
        int moved=pes23_secondary_move(t,n,cores,&gain); unsigned changes=0;
        uint64_t now=score(t,n,cores,1,&after);
        for(unsigned i=0;i<n;i++) if(t[i].core!=t[i].new_core) {
            ++changes; assert(!t[i].fixed && t[i].core>=0 && t[i].load>=100);
            assert(t[i].new_core>=0 && (unsigned)t[i].new_core<cores);
        }
        assert(changes==(unsigned)moved && after<=before);
        assert(moved ? (old>now && old-now==gain) : (old==now && !gain));
    }
    puts("PERF23 secondary-core regression and 20000 affinity/load invariants PASS");
}
