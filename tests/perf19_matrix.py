"""Replay the entire captured matrix block, not individual arithmetic ops."""
from pathlib import Path
import hashlib
import json
import random
import struct
import sys
import capstone
import unicorn as uc
from unicorn import arm64_const as reg

p = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(p/'tools'))
from perf19_plan import plan
work = p/'local/perf19'
original = (p/'local/perf18/captures/slot-0-arm64.bin').read_bytes()
patched, info = plan(original)
CODE, DATA, SIZE = 0x100000, 0x200000, 0x10000
EMU, STACK, A, B, C = DATA, DATA+0x4000, DATA+0x6000, DATA+0x7000, DATA+0x8000
stop = CODE + info['stop_before_return_lookup']
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
machines = []
for code in (original, patched):
    m = uc.Uc(uc.UC_ARCH_ARM64, uc.UC_MODE_ARM)
    m.mem_map(CODE, 0x4000); m.mem_write(CODE, code); m.mem_map(DATA, SIZE)
    counts = {'instructions': 0, 'fpcr_reads': 0, 'fpcr_writes': 0}
    kinds = {i.address: ('fpcr_reads' if i.mnemonic=='mrs' else 'fpcr_writes')
             for i in md.disasm(code, CODE) if i.mnemonic in ('mrs','msr') and 'fpcr' in i.op_str}
    def tick(em, pc, size, data):
        counts, kinds = data
        counts['instructions'] += 1
        if pc in kinds: counts[kinds[pc]] += 1
    handle = m.hook_add(uc.UC_HOOK_CODE, tick, (counts, kinds))
    machines.append((m, counts, handle))


def run(m, fpcr, cw, values, alias):
    blob = bytearray(SIZE)
    struct.pack_into('<I', blob, 0x31c, cw)
    blob[A-DATA:A-DATA+64] = struct.pack('<16I', *values[:16])
    blob[B-DATA:B-DATA+64] = struct.pack('<16I', *values[16:])
    out = (C, A, B, A+4, B+4)[alias]
    struct.pack_into('<4I', blob, STACK-DATA, 0x12340000, out, A, B)
    m.mem_write(DATA, bytes(blob))
    for i in range(31): m.reg_write(getattr(reg, 'UC_ARM64_REG_X'+str(i)), 0xaaa000+i)
    for i in range(32): m.reg_write(getattr(reg, 'UC_ARM64_REG_Q'+str(i)), 0)
    m.reg_write(reg.UC_ARM64_REG_X0, EMU)
    m.reg_write(reg.UC_ARM64_REG_X14, STACK)
    m.reg_write(reg.UC_ARM64_REG_FPCR, fpcr)
    m.reg_write(reg.UC_ARM64_REG_FPSR, 0)
    m.reg_write(reg.UC_ARM64_REG_NZCV, 0xa0000000)
    m.emu_start(CODE, stop, count=10000)
    assert m.reg_read(reg.UC_ARM64_REG_PC)==stop
    # Return lookup overwrites x2/x3; other scratch values have no guest meaning.
    # Compare full guest memory, guest GPRs, FP cache, flags, rounding and status.
    state = (bytes(m.mem_read(DATA,SIZE)),
             tuple(m.reg_read(getattr(reg,'UC_ARM64_REG_X'+str(i))) for i in range(10,28)),
             tuple(m.reg_read(getattr(reg,'UC_ARM64_REG_Q'+str(i))) for i in range(32)),
             *(m.reg_read(r) for r in (reg.UC_ARM64_REG_FPCR,reg.UC_ARM64_REG_FPSR,reg.UC_ARM64_REG_NZCV)))
    return state


rng = random.Random(19)
finite = [struct.unpack('<I', struct.pack('<f', rng.uniform(-100,100)))[0] for _ in range(32)]
for m, counts, _ in machines: run(m,0,0x37f,finite,0)
instruction_counts = [counts.copy() for _,counts,_ in machines]
for m,_,handle in machines: m.hook_del(handle)
special = [0,0x80000000,1,0x7fffff,0x800000,0x3f800000,0xbf800000,0x7f7fffff,
           0x7f800000,0xff800000,0x7fc00001,0x7f800001]
vectors = [finite, [0]*32, [0x3f800000]*32]
vectors += [[special[(i+shift)%len(special)] for i in range(32)] for shift in range(12)]
vectors += [[rng.getrandbits(32) for _ in range(32)] for _ in range(12)]
cases=0
for host in range(4):
    for guest in range(4):
        for other in (0,1<<24,1<<25,(1<<24)|(1<<25)):
            for index, values in enumerate(vectors):
                alias = index%5
                args=(other | host<<22, 0x37f | guest<<10, values, alias)
                old=run(machines[0][0],*args); new=run(machines[1][0],*args)
                if old != new:
                    detail={'host':host,'guest':guest,'other':other,'vector':index,'alias':alias,
                            'differing_state_fields':[i for i,(a,b) in enumerate(zip(old,new)) if a!=b]}
                    (work/'matrix-failure.json').write_text(json.dumps(detail,indent=2)+'\n')
                    raise AssertionError(detail)
                cases+=1
summary={'cases':cases,'whole_block_bit_identical':True,'executed_instruction_counts':instruction_counts,
         'tested':['all 16 rounding combinations','FZ/DN','random and special float values','output aliasing A/B and offset aliases','full memory, guest GPRs, FP cache, FPCR, FPSR, NZCV'],
         'limits':'Unicorn semantics, no Switch time or OS signal test',
         'original_sha256':hashlib.sha256(original).hexdigest(),'patched_sha256':hashlib.sha256(patched).hexdigest()}
(work/'matrix-tests.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
