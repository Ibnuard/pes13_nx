"""Exercise the exact new C pass with captured blocks and branching paths."""
from pathlib import Path
import json
p=Path(__file__).resolve().parents[1]
w=p/'local/perf38';w.mkdir(parents=True,exist_ok=True)
path=p/'tests/perf20_replay.py'
text=path.read_text().replace("work = p/'local/perf20'", "work = p/'local/perf38'")
text=text.replace('perf20-fuse.so','perf38-fuse.so').replace('tests/perf20_fuse.c','tests/perf38_fuse.c')
text=text.replace('-DPERF20_SHARED','-DPERF38_SHARED').replace('perf20_test_fuse','perf38_test_fuse')
text=text.replace('perf20_test_gap','perf38_test_gap')
text=text.replace("work/'captures/slot-2-arm64.bin'","p/'local/perf20/captures/slot-2-arm64.bin'")
text=text.replace('src/runtime/pes13_perf20_fuse.h','src/runtime/pes13_perf38_fuse.h')
ns={'__file__':str(path),'__name__':'perf38_shared_tests'}
exec(compile(text,str(path),'exec'),ns)
# Reuse only the emulator harness; production fusion remains the compiled C.
globals().update({k:v for k,v in ns.items() if not k.startswith('__')})
lib.perf38_test_old.argtypes=lib.perf38_test_fuse.argtypes
lib.perf38_test_old.restype=Result
report['branch_cases']=0
report['widen_cases']=0
report['loop_cases']=0
# CBZ precedes two separate safe runs; exercise taken and fallthrough paths.
# A backward BNE loop has its target at the first guard. Neither optimizer
# may share FPCR state across either control-flow edge.
g=[0xb9431c01,0x330a2c21,0x53010425,0x331f0025,0xd53b4401,
   0xaa0103e4,0xb36a04a1,0xd51b4401,0x1e690908,0xd51b4404]
for variant in (2,5):
    for count in (2,5):
        words=[]
        for j in range(count):
            seq=g.copy()
            if variant==2:seq[2],seq[3],seq[6]=0x53010422,0x331f0022,0xb36a0441
            # Alternate ten/eleven-word forms, preserving the widening
            # result and its FPSR exception effects for every input class.
            if j%2==0:seq.insert(8,0x1e22c138)  # FCVT D24,S9
            words+=seq+[0xd503201f]
        original=struct.pack('<'+'I'*len(words),*words)
        patched,info=fuse(original);assert info['merged']==count-1,info
        machines=[machine(original),machine(patched)]
        for host in range(4):
            for guest in range(4):
                for other in (0,1<<24,1<<25,(1<<24)|(1<<25)):
                    for pattern in range(8):
                        args=(len(original),other|host<<22,0x37f|guest<<10,vectors[pattern],'synthetic',0)
                        a=replay(machines[0],*args,random.Random(pattern))
                        b=replay(machines[1],*args,random.Random(pattern))
                        assert a==b,(variant,count,host,guest,other,pattern)
                        report['widen_cases']+=1
for op in (0x3400000a,0xb400000a,0x3600000a,0x54000000):
    words=[op|(22<<5)]+g*2+[0x14000016]+g*2+[0xd503201f]
    original=struct.pack('<'+'I'*len(words),*words)
    patched,info=fuse(original); assert info['merged']>=1 and not info['flow_rejected'],info
    machines=[machine(original),machine(patched)]
    for host in range(4):
        for guest in range(4):
            for other in (0,1<<24,1<<25,(1<<24)|(1<<25)):
                for branch in (0,1):
                    results=[]
                    for m in machines:
                        # replay initializes the machine; custom register/
                        # flags hook chooses both sides of the first branch.
                        def choose(em,pc,size,_):
                            if pc==CODE:
                                em.reg_write(reg.UC_ARM64_REG_X10,branch)
                                em.reg_write(reg.UC_ARM64_REG_NZCV,branch<<30)
                        h=m.hook_add(uc.UC_HOOK_CODE,choose)
                        result=replay(m,len(original),other|host<<22,0x37f|guest<<10,
                                      vectors[branch],'synthetic',0,random.Random(3))
                        m.hook_del(h);results.append(result)
                    assert results[0]==results[1],(hex(op),host,guest,other,branch)
                    report['branch_cases']+=1
# Exercise a real backward edge, with the first guard as a loop entry.
words=g*3+[0x7100054a,0x54000001|(((-31)&0x7ffff)<<5)]
original=struct.pack('<'+'I'*len(words),*words)
patched,info=fuse(original);assert info['merged']==1,info
machines=[machine(original),machine(patched)]
for host in range(4):
    for guest in range(4):
        for other in (0,1<<24,1<<25,(1<<24)|(1<<25)):
            results=[]
            for m in machines:
                started=[False]
                def choose(em,pc,size,_):
                    if not started[0]:
                        em.reg_write(reg.UC_ARM64_REG_X10,3);started[0]=True
                h=m.hook_add(uc.UC_HOOK_CODE,choose)
                results.append(replay(m,len(original),other|host<<22,0x37f|guest<<10,
                                      vectors[0],'synthetic',0,random.Random(4)))
                m.hook_del(h)
            assert results[0]==results[1],('backedge',host,guest,other)
            report['loop_cases']+=1
# Decode randomized branch immediates independently with Capstone, including
# negative displacements and B.cond, CBZ/CBNZ, TBZ/TBNZ register/width bits.
lib.perf38_test_target.argtypes=[ct.c_uint32,ct.c_size_t,ct.POINTER(ct.c_int64)]
lib.perf38_test_target.restype=ct.c_int
md.detail=True;report['decoded_branches']=0
for base,bits,shift in ((0x14000000,26,0),(0x54000000,19,5),
        (0x34000000,19,5),(0xb5000000,19,5),(0x36000000,14,5),(0xb7000000,14,5)):
    for _ in range(1000):
        imm=rng.getrandbits(bits);word=base|(imm<<shift)
        if shift: word|=rng.randrange(14 if base==0x54000000 else 32)
        decoded=list(md.disasm(struct.pack('<I',word),CODE))
        assert len(decoded)==1
        target=ct.c_int64()
        assert lib.perf38_test_target(word,0,ct.byref(target))==1
        assert (CODE+target.value*4)&((1<<64)-1)==decoded[0].operands[-1].imm&((1<<64)-1)
        report['decoded_branches']+=1
# Audit stored native captures; no assertion that every historic capture is
# within the new runtime scope, or that a static merge is a speedup.
seen=set(); captures=[]
for f in sorted((p/'local').rglob('*arm64.bin')):
    if 'captures' not in f.parts: continue
    b=f.read_bytes();digest=hashlib.sha256(b).hexdigest()
    if digest in seen:continue
    seen.add(digest)
    new,info=fuse(b)
    oldbuf=ct.create_string_buffer(b);old=lib.perf38_test_old(oldbuf,len(b))
    if info['merged']>old.merged:
        captures.append(dict(path=str(f.relative_to(p)),sha256=digest,
                             old_merged=old.merged,new_merged=info['merged']))
report['stored_captures_with_extra_static_merges']=captures
report['source_sha256']={str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest()
    for f in (p/'src/runtime/pes13_perf38_fuse.h',p/'src/runtime/pes13_perf20_fuse.h',
              p/'tests/perf38_fuse.c',p/'tests/perf38_replay.py')}
(work/'fusion-tests.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF38 complete',report['cases'],'straight-line cases,',report['branch_cases'],
      'branch-path cases,',report['widen_cases'],'widen cases,',
      report['loop_cases'],'loop cases,',report['decoded_branches'],'decoded branches,',
      len(captures),'stored blocks with additional static merges')
