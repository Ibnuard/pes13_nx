"""Execute actual pinned SSE emission fragments under both environment lookups.

This checks the generated ARM arithmetic and scope fallback. FASTNAN relaxes
NaN sign/payload and exception details; this does not assert x86 equivalence
for NaNs or establish whole-game correctness/performance.
"""
from pathlib import Path
import hashlib
import json
import os
import random
import struct
import subprocess
import capstone
import unicorn as uc
from unicorn import arm64_const as reg

p = Path(__file__).resolve().parents[1]
root = Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build'))
vendor = root / 'runtime-perf11-source/wine-nx-probe/vendor/box64/src'
arm = vendor / 'dynarec/arm64'
w = p / 'local/perf36/fastnan-test'
w.mkdir(parents=True, exist_ok=True)
source = (arm / 'dynarec_arm64_f30f.c').read_text()
names = ['SQRTSS', 'ADDSS', 'MULSS', 'SUBSS', 'DIVSS']
fragments = []
for name in names:
    start = source.index('INST_NAME("' + name + ' Gx, Ex")')
    start = source.index('if(!BOX64ENV(dynarec_fastnan))', start)
    end = source.index('            break;', start)
    fragments.append(source[start:end])

fixture = r'''
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#include "env.h"
box64env_t box64env;
static uint32_t code[256]; static unsigned used;
#define EMIT(x) do { assert(used<256); code[used++]=(uint32_t)(x); } while(0)
#include "arm64_emitter.h"
typedef struct { box64env_t *env; } dynarec_arm_t;
/* The fragments only request 0x00400000. This is the same single MOVZ
 * selected by pinned arm64_move32's immediate fast path for that value. */
static void arm64_move32(dynarec_arm_t *d, int n, int r, uint32_t v) {
    (void)d;(void)n;assert(v==0x00400000);MOVZw_LSL(r,0x40,16);
}
static unsigned scratch;
static int fpu_get_scratch(dynarec_arm_t *d, int n) { (void)d;(void)n;return scratch++; }
int main(void) {
    for (int mode=0;mode<5;++mode) for (int op=0;op<5;++op) {
        box64env_t scoped={0}; dynarec_arm_t state={&scoped}, *dyn=&state;
        box64env.dynarec_fastnan=(mode==4);
        scoped.dynarec_fastnan=(mode!=4);
        scoped.is_dynarec_fastnan_overridden=(mode!=2);
        if (mode==3) dyn->env=NULL;
        int ninst=0,d0=9,d1=8,v0=0,v1=10,v2=0,q0=8;
        if(op==0) d1=10; /* SQRTSS uses a scratch result before lane insertion. */
        (void)dyn;(void)ninst;(void)v0;(void)v1;(void)v2;(void)q0;
        used=0;scratch=11;
        if (mode==0) { ORIGINAL } else { PATCHED }
        printf("%d %d ",mode,op);
        for(unsigned i=0;i<used;++i) for(unsigned b=0;b<4;++b) printf("%02x",(code[i]>>(8*b))&255);
        puts("");
    }
}
'''
body = '\n'.join(f'if(op=={i}) {{ {fragment} }}' for i, fragment in enumerate(fragments))
fixture = fixture.replace('ORIGINAL', body).replace(
    'PATCHED', body.replace('BOX64ENV(dynarec_fastnan)', 'BOX64DRENV(dynarec_fastnan)'))
(w / 'fixture.c').write_text(fixture)
exe = root / 'perf36-fastnan-fixture'
subprocess.run(['cc', '-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                '-I' + str(arm), '-I' + str(vendor / 'include'),
                str(w / 'fixture.c'), '-o', str(exe)], check=True)
lines = subprocess.check_output([str(exe)], text=True).splitlines()
streams = {(int(m), int(o)): bytes.fromhex(b) for m, o, b in (l.split() for l in lines)}
for op in range(len(names)):
    assert streams[0, op] == streams[2, op] == streams[3, op] == streams[4, op]
    assert len(streams[1, op]) < len(streams[0, op])
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
machines = {}
for key, code in streams.items():
    m = uc.Uc(uc.UC_ARCH_ARM64, uc.UC_MODE_ARM)
    m.mem_map(0x10000, 4096); m.mem_write(0x10000, code)
    machines[key] = m
    (w / f'{key[0]}-{names[key[1]]}.asm').write_text('\n'.join(
        f'{ins.mnemonic} {ins.op_str}' for ins in md.disasm(code, 0x10000)))

def run(key, a, b, fpcr):
    m = machines[key]; code = streams[key]
    # Dirty scratch registers deliberately: the emitted path must define them.
    for i in range(8, 16): m.reg_write(getattr(reg, 'UC_ARM64_REG_Q' + str(i)), (1 << 128)-1)
    upper = 0x112233445566778899aabbcc << 32
    m.reg_write(reg.UC_ARM64_REG_Q8, upper | a)
    m.reg_write(reg.UC_ARM64_REG_Q9, upper | b)
    m.reg_write(reg.UC_ARM64_REG_FPCR, fpcr)
    m.reg_write(reg.UC_ARM64_REG_FPSR, 0)
    m.reg_write(reg.UC_ARM64_REG_NZCV, 0xa0000000)
    m.emu_start(0x10000, 0x10000 + len(code), count=200)
    result = m.reg_read(reg.UC_ARM64_REG_Q8)
    assert result >> 32 == upper >> 32
    assert m.reg_read(reg.UC_ARM64_REG_Q9) == upper | b
    assert m.reg_read(reg.UC_ARM64_REG_FPCR) == fpcr
    assert m.reg_read(reg.UC_ARM64_REG_NZCV) == 0xa0000000
    return result & 0xffffffff

def nan(n): return n & 0x7f800000 == 0x7f800000 and n & 0x7fffff != 0

rng = random.Random(36)
values = [0,0x80000000,1,0x80000001,0x007fffff,0x00800000,
          0x3f800000,0xbf800000,0x3f000000,0x7f7fffff,
          0x7f800000,0xff800000,0x7fc00001,0x7f800001,0xffc01234]
pairs = [(a,b) for a in values for b in values] + [(rng.getrandbits(32),rng.getrandbits(32)) for _ in range(250)]
cases = nan_cases = 0
for rounding in range(4):
    for fz in (0,1):
        fpcr = (rounding << 22) | (fz << 24)
        for op in range(len(names)):
            for a,b in pairs:
                old = run((0,op),a,b,fpcr); new = run((1,op),a,b,fpcr)
                if nan(old):
                    assert nan(new), (names[op],hex(a),hex(b),old,new)
                    nan_cases += 1
                else:
                    assert old == new, (names[op],hex(a),hex(b),old,new)
                cases += 1
report = dict(cases=cases, nan_classification_cases=nan_cases,
    fallback_byte_identical=True, finite_results_identical=True,
    upper_lanes_fpcr_nzcv_preserved=True,
    arm_instructions={name:dict(baseline=len(streams[0,i])//4,scoped=len(streams[1,i])//4) for i,name in enumerate(names)},
    fragment_sha256=[hashlib.sha256(f.encode()).hexdigest() for f in fragments],
    limits=['Register arithmetic fragments, not complete opcode decode or whole guest blocks.',
            'NaN payload/sign and FPSR equivalence are intentionally not claimed.',
            'Unicorn results do not measure Switch FPS.'])
(w / 'results.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
