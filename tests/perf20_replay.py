"""Replay the actual C fusion pass, captured blocks and randomized guard runs.

Run in WSL with Unicorn 2.1.4 and Capstone 5.0.7 on PYTHONPATH (the local
Linux wheels are in local/perf20/linux-libs). It compiles the production
pure-C pass; there is no separate Python implementation of the optimization.
"""
from pathlib import Path
import ctypes as ct
import hashlib
import json
import random
import struct
import subprocess
import capstone
import unicorn as uc
from unicorn import arm64_const as reg

p = Path(__file__).resolve().parents[1]
work = p/'local/perf20'
libpath = Path('/home/blekjek/pes13-build/perf20-fuse.so')
subprocess.run(['cc','-O2','-std=c11','-Wall','-Wextra','-Werror','-DPERF20_SHARED',
                '-fPIC','-shared',str(p/'tests/perf20_fuse.c'),'-o',str(libpath)],check=True)
class Result(ct.Structure):
    _fields_ = [(k,ct.c_uint) for k in ('guards','merged','runs','flow_rejected')]
lib = ct.CDLL(str(libpath))
lib.perf20_test_fuse.argtypes = [ct.c_void_p,ct.c_size_t]
lib.perf20_test_fuse.restype = Result
lib.perf20_test_gap.argtypes = [ct.c_uint32]
lib.perf20_test_gap.restype = ct.c_int

def fuse(blob):
    out=ct.create_string_buffer(blob)
    result=lib.perf20_test_fuse(out,len(blob))
    return out.raw[:len(blob)], {k:getattr(result,k) for k,_ in Result._fields_}

md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM)
rng=random.Random(20)
# Independently decode randomized whitelist encodings. Mask bugs must not
# broaden the pass to a different instruction or clobber a scratch GPR.
prefixes=[0xbd000000,0xbd400000,0xfd000000,0xfd400000,0x3d800000,0x3dc00000,
          0xb9000000,0xb9400000,0xf9000000,0xf9400000,
          0xbc000000,0xbc400000,0xfc000000,0xfc400000,0x3c800000,0x3cc00000,
          0xb8000000,0xb8400000,0xf8000000,0xf8400000]
decoded=0
for base in prefixes:
    unscaled=(base & 0x01000000)==0
    for rn in range(32):
        for rd in range(32):
            imm=rng.randrange(512 if unscaled else 4096)
            word=base | imm<<(12 if unscaled else 10) | rn<<5 | rd
            if not lib.perf20_test_gap(word): continue
            ins=list(md.disasm(struct.pack('<I',word),0))
            assert len(ins)==1 and ins[0].mnemonic in ('ldr','str','ldur','stur'),ins
            assert 10<=rn<=27
            is_fp=bool(base & 0x04000000)
            assert is_fp or 10<=rd<=27
            decoded+=1

CODE,DATA,SIZE=0x100000,0x200000,0x10000
STACK,A,B,C,CTX=DATA+0x4000,DATA+0x6000,DATA+0x7000,DATA+0x8000,DATA+0x9000
XREG=[getattr(reg,'UC_ARM64_REG_X'+str(i)) for i in range(31)]
QREG=[getattr(reg,'UC_ARM64_REG_Q'+str(i)) for i in range(32)]
FLAGS=[reg.UC_ARM64_REG_FPCR,reg.UC_ARM64_REG_FPSR,reg.UC_ARM64_REG_NZCV]

def machine(code):
    m=uc.Uc(uc.UC_ARCH_ARM64,uc.UC_MODE_ARM)
    m.mem_map(CODE,0x10000);m.mem_write(CODE,code);m.mem_map(DATA,SIZE)
    return m

def replay(m,stop,fpcr,cw,values,kind,alias,seed):
    blob=bytearray(SIZE)
    struct.pack_into('<I',blob,0x31c,cw)
    blob[A-DATA:A-DATA+64]=struct.pack('<16I',*values[:16])
    blob[B-DATA:B-DATA+64]=struct.pack('<16I',*values[16:])
    if kind=='matrix':
        out=(C,A,B,A+4,B+4)[alias%5]
        struct.pack_into('<4I',blob,STACK-DATA,0x12340000,out,A,B)
    elif kind=='worker':
        out=(C,STACK,STACK-20)[alias%3]
        struct.pack_into('<I',blob,CTX-DATA+24,out)
        struct.pack_into('<7I',blob,STACK-DATA,0x12340000,*values[:6])
    m.mem_write(DATA,bytes(blob))
    for i,r in enumerate(XREG):m.reg_write(r,A if 10<=i<=27 else 0xaaa000+i)
    for i,r in enumerate(QREG):m.reg_write(r,seed.getrandbits(128))
    m.reg_write(reg.UC_ARM64_REG_X0,DATA)
    if kind=='worker':m.reg_write(reg.UC_ARM64_REG_X11,CTX)
    m.reg_write(reg.UC_ARM64_REG_X14,STACK)
    m.reg_write(reg.UC_ARM64_REG_FPCR,fpcr)
    m.reg_write(reg.UC_ARM64_REG_FPSR,0x08000000)
    m.reg_write(reg.UC_ARM64_REG_NZCV,0xa0000000)
    m.emu_start(CODE,CODE+stop,count=15000)
    assert m.reg_read(reg.UC_ARM64_REG_PC)==CODE+stop
    return (bytes(m.mem_read(DATA,SIZE)),tuple(m.reg_read(r) for r in XREG),
            tuple(m.reg_read(r) for r in QREG),tuple(m.reg_read(r) for r in FLAGS))

special=[0,0x80000000,1,0x7fffff,0x800000,0x3f800000,0xbf800000,0x7f7fffff,
         0x7f800000,0xff800000,0x7fc00001,0x7f800001]
vectors=[[struct.unpack('<I',struct.pack('<f',rng.uniform(-100,100)))[0] for _ in range(32)],
         [0]*32,[0x3f800000]*32]
vectors += [[special[(i+j)%len(special)] for i in range(32)] for j in range(12)]
vectors += [[rng.getrandbits(32) for _ in range(32)] for _ in range(12)]
report={'cases':0,'whole_block_bit_identical':True,'whitelist_decodes':decoded,'blocks':[]}
fixtures=[('matrix',p/'local/perf18/captures/slot-0-arm64.bin'),
          ('worker',work/'captures/slot-2-arm64.bin')]
for kind,path in fixtures:
    original=path.read_bytes();patched,info=fuse(original)
    assert info['merged']>0 and not info['flow_rejected'],info
    (work/(kind+'-fused.bin')).write_bytes(patched)
    stop=next(i.address for i in md.disasm(original,0) if i.mnemonic=='ldr' and i.op_str.startswith('x3, #'))
    machines=[machine(original),machine(patched)]
    counts=[]
    for m,code in zip(machines,(original,patched)):
        kinds={i.address:i.mnemonic for i in md.disasm(code,CODE) if 'fpcr' in i.op_str}
        counter={'instructions':0,'fpcr_reads':0,'fpcr_writes':0}
        def tick(em,pc,size,counter):
            counter['instructions']+=1
            if pc in kinds:counter['fpcr_reads' if kinds[pc]=='mrs' else 'fpcr_writes']+=1
        h=m.hook_add(uc.UC_HOOK_CODE,tick,counter)
        replay(m,stop,0,0x37f,vectors[0],kind,0,random.Random(0));m.hook_del(h)
        counts.append(counter)
    cases=0
    for host in range(4):
        for guest in range(4):
            for other in (0,1<<24,1<<25,(1<<24)|(1<<25)):
                for index,values in enumerate(vectors):
                    args=(stop,other|host<<22,0x37f|guest<<10,values,kind,index)
                    old=replay(machines[0],*args,random.Random(index))
                    new=replay(machines[1],*args,random.Random(index))
                    assert old==new,(kind,host,guest,other,index,[i for i,(a,b) in enumerate(zip(old,new)) if a!=b])
                    cases+=1
    report['cases']+=cases
    report['blocks'].append({'kind':kind,'cases':cases,**info,'counts':counts,
                            'sha256':hashlib.sha256(patched).hexdigest()})
    print(kind,report['blocks'][-1],flush=True)

# Vary all supported arithmetic encodings, scratch variants, guard registers,
# exact FP widening, guest-memory gaps, input NaNs and host/guest rounding.
arithmetic=[0x1e200800,0x1e600800,0x1e201800,0x1e601800,0x1e202800,0x1e602800,
            0x1e203800,0x1e603800,0x1e624000,0x1e21c000,0x1e61c000]
guard=[0xb9431c01,0x330a2c21,0x53010425,0x331f0025,
       0xd53b4401,0xaa0103e4,0xb36a04a1,0xd51b4401,0,0xd51b4404]
for variant in (2,5):
    for op in arithmetic:
        words=[]
        for j in range(6):
            g=guard.copy()
            if variant==2:g[2],g[3],g[6]=0x53010422,0x331f0022,0xb36a0441
            g[8]=op | ((j+12)<<5) | (j+8)
            if op in arithmetic[:8]:g[8]|=(j+16)<<16
            words+=g
            # STR/LDR S through a guest GPR and exact single->double widening.
            words += [0xbd000148+j,0xbd400158+j,0x1e22c300+j]
        original=struct.pack('<'+'I'*len(words),*words)
        patched,info=fuse(original);assert info['merged']==5,info
        machines=[machine(original),machine(patched)]
        for host in range(4):
            for guest in range(4):
                for other in (0,1<<24,1<<25,(1<<24)|(1<<25)):
                    for pattern in (0,1,2):
                        seed=host*100+guest*10+pattern
                        args=(len(original),other|host<<22,0x37f|guest<<10,vectors[pattern],'synthetic',0)
                        old=replay(machines[0],*args,random.Random(seed))
                        new=replay(machines[1],*args,random.Random(seed))
                        assert old==new,(variant,hex(op),host,guest,other,pattern)
                        report['cases']+=1
report['source_sha256']=hashlib.sha256((p/'src/runtime/pes13_perf20_fuse.h').read_bytes()).hexdigest()
report['limits']='Unicorn checks arithmetic/register/memory equivalence, not Switch cycle timing or asynchronous OS faults.'
(work/'fusion-tests.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
