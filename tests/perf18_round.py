"""Execute ARM64 emitted by the real Box64 macros; compare both paths in Unicorn."""
from pathlib import Path
import json
import random
import struct
import subprocess
import sys
import capstone
import unicorn as uc
from unicorn import arm64_const as reg

p = Path(__file__).resolve().parents[1]
work = p / 'local/perf18'
work.mkdir(parents=True, exist_ok=True)
arm_linux = '/home/blekjek/pes13-build/runtime-perf11-source/wine-nx-probe/vendor/box64/src/dynarec/arm64'
arm = Path('//wsl.localhost/Ubuntu' + arm_linux) if sys.platform == 'win32' else Path(arm_linux)


def function(source, name):
    start = source.index(name + '(')
    start = source.rfind('\n', 0, start) + 1
    end = source.index('\n}', start) + 2
    return source[start:end]


source = (arm / 'dynarec_arm64_helper.c').read_text()
baseline = '\n'.join(function(source, name) for name in ('x87_setround', 'x87_restoreround'))
fixture = r'''
#include <stdio.h>
#include <stdint.h>
#include <stddef.h>
#define STEP 3
#define MAYUSE(x) ((void)(x))
typedef struct { char padding[0x31c]; uint32_t cw; } x64emu_t;
typedef struct { struct { uintptr_t addr; } x64; } ins_t;
typedef struct { ins_t *insts; } dynarec_arm_t;
static uint32_t code[256]; static unsigned int used;
#define EMIT(x) do { code[used++] = (uint32_t)(x); } while (0)
#include "arm64_emitter.h"
BASELINE
static int enabled;
int wine_nx_perf18_round_site(uintptr_t addr, int pass) {
    return enabled && addr == 0x112fb90 && pass == 3;
}
#include "ROUND_HEADER"
int main(void) {
    ins_t inst = {{0x112fb90}}; dynarec_arm_t dyn = {&inst};
    for (int variant=0; variant<4; ++variant) {
        enabled = variant != 2;
        inst.x64.addr = variant == 3 ? 0x70000000 : 0x112fb90;
        for (int op=0; op<3; ++op) {
            used=0;
            int token = variant ? pes18_setround(&dyn, 0, x1, x2, x4)
                                : x87_setround(&dyn, 0, x1, x2, x4);
            if (op == 0) { FMULD(8, 8, 9); }
            if (op == 1) { FADDD(8, 8, 9); }
            if (op == 2) { FCVT_S_D(8, 8); }
            if (variant) pes18_restoreround(&dyn, 0, token);
            else x87_restoreround(&dyn, 0, token);
            printf("%d %d ", variant, op);
            for (unsigned int i=0;i<used;++i)
                for (unsigned int b=0;b<4;++b) printf("%02x", (code[i]>>(b*8))&255);
            puts("");
        }
    }
}
'''.replace('BASELINE', baseline)
linux_project = '/mnt/' + p.drive[0].lower() + str(p)[2:].replace('\\', '/') if sys.platform == 'win32' else str(p)
fixture = fixture.replace('ROUND_HEADER', linux_project + '/src/runtime/pes13_perf18_round.h')
(work / 'round-emitter.c').write_text(fixture)
prefix = ['wsl', '-d', 'Ubuntu', '-u', 'root', '--'] if sys.platform == 'win32' else []
subprocess.run(prefix + ['cc', '-O2', '-std=gnu11', '-I' + arm_linux,
                        linux_project + '/local/perf18/round-emitter.c',
                        '-o', '/tmp/pes13-perf18-round-emitter'], check=True)
result = subprocess.run(prefix + ['/tmp/pes13-perf18-round-emitter'], check=True, capture_output=True, text=True)
streams = {(int(v), int(o)): bytes.fromhex(h) for v, o, h in (line.split() for line in result.stdout.splitlines())}
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
engines = {}
for key, code in streams.items():
    (work / f'round-{key[0]}-{key[1]}.bin').write_bytes(code)
    (work / f'round-{key[0]}-{key[1]}.txt').write_text('\n'.join(f'{i.address:x} {i.mnemonic} {i.op_str}' for i in md.disasm(code, 0x10000)))
    m = uc.Uc(uc.UC_ARCH_ARM64, uc.UC_MODE_ARM)
    m.mem_map(0x10000, 0x1000); m.mem_write(0x10000, code)
    m.mem_map(0x20000, 0x1000)
    writes = []
    msr = {i.address for i in md.disasm(code, 0x10000) if i.mnemonic == 'msr' and i.op_str.startswith('fpcr')}
    m.hook_add(uc.UC_HOOK_CODE, lambda em, pc, size, data: data[0].append(pc) if pc in data[1] else None, (writes, msr))
    engines[key] = (m, code, writes)


def run(key, fpcr, cw, a, b):
    m, code, writes = engines[key]
    writes.clear()
    for r in range(8): m.reg_write(getattr(reg, 'UC_ARM64_REG_X' + str(r)), 0x5a0000 + r)
    m.reg_write(reg.UC_ARM64_REG_X0, 0x20000)
    m.mem_write(0x2031c, struct.pack('<I', cw))
    m.reg_write(reg.UC_ARM64_REG_Q8, a); m.reg_write(reg.UC_ARM64_REG_Q9, b)
    m.reg_write(reg.UC_ARM64_REG_FPCR, fpcr)
    actual_fpcr = m.reg_read(reg.UC_ARM64_REG_FPCR)
    m.reg_write(reg.UC_ARM64_REG_FPSR, 0)
    m.reg_write(reg.UC_ARM64_REG_NZCV, 0xa0000000)
    m.emu_start(0x10000, 0x10000 + len(code), count=100)
    state = tuple(m.reg_read(r) for r in (reg.UC_ARM64_REG_Q8, reg.UC_ARM64_REG_Q9,
                  reg.UC_ARM64_REG_FPCR, reg.UC_ARM64_REG_FPSR, reg.UC_ARM64_REG_NZCV,
                  reg.UC_ARM64_REG_X0, reg.UC_ARM64_REG_X4))
    assert state[2] == actual_fpcr and state[4] == 0xa0000000
    return state, len(writes)


rng = random.Random(18)
values = [0, 1<<63, 1, 0xfffffffffffff, 0x10000000000000, 0x3ff0000000000000,
          0x3ff0000010000000, 0x3fefffffffffffff, 0xbff0000000000000,
          0x7fefffffffffffff, 0x7ff0000000000000, 0xfff0000000000000,
          0x7ff8000000000001, 0x7ff0000000000001] + [rng.getrandbits(64) for _ in range(32)]
cases = equal_cases = 0
for host_mode in range(4):
    for guest_mode in range(4):
        for other in (0, 1<<24, 1<<25, (1<<24)|(1<<25)):
            fpcr = other | host_mode<<22
            cw = 0x37f | guest_mode<<10
            for op in range(3):
                for idx, a in enumerate(values):
                    b = values[(idx*7+5) % len(values)]
                    baseline_state, baseline_writes = run((0, op), fpcr, cw, a, b)
                    fast_state, fast_writes = run((1, op), fpcr, cw, a, b)
                    assert fast_state == baseline_state, (host_mode, guest_mode, other, op, hex(a), hex(b), baseline_state, fast_state)
                    assert baseline_writes == 2
                    equal = host_mode == ((guest_mode & 1)<<1 | guest_mode>>1)
                    assert fast_writes == (0 if equal else 2)
                    cases += 1; equal_cases += equal
for op in range(3):
    assert streams[2, op] == streams[0, op] == streams[3, op], 'off/outside must emit identical baseline'
summary = {'cases': cases, 'equal_mode_cases': equal_cases, 'all_bit_identical': True,
           'equal_mode_fpcr_writes': 0, 'different_mode_fpcr_writes': 2,
           'scope_disabled_and_outside_byte_identical': True,
           'tested': ['4x4 rounding modes', 'FZ/DN', 'NaNs/infinities/subnormals', 'mul/add/f64-to-f32', 'FPSR/NZCV/FPCR restoration'],
           'limitations': 'Unicorn semantic checks, not Switch performance or OS signal handling'}
(work / 'round-tests.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
