"""Decode sampled ARM words and guest blocks; never call sample shares cycles."""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import importlib.util
import json
import re
import struct
import capstone

p=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cadence',p/'tools/analyze-perf29-result.py')
cadence=importlib.util.module_from_spec(spec); spec.loader.exec_module(cadence)
decoder=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM)

def decode(word):
    ins=list(decoder.disasm(struct.pack('<I',word),0))
    if not ins: return 'undecoded','undecoded'
    m=ins[0].mnemonic
    if m in ('dmb','dsb','isb','yield','wfe','wfi'): category='barrier_or_wait'
    elif m.startswith(('ldxr','ldaxr','stxr','stlxr','cas','swp','ldadd')): category='atomic'
    elif m in ('mrs','msr'): category='system_register'
    elif m.startswith(('fcvt','scvt','ucvt')): category='float_conversion'
    elif m.startswith('f'): category='float_other'
    elif m in ('b','bl','br','blr','ret','cbz','cbnz','tbz','tbnz') or m.startswith('b.'): category='branch'
    elif m.startswith(('ldr','ldur','ldp','str','stur','stp','ldar','stlr')): category='load_store'
    else: category='other'
    return m,category

def parse(path):
    run=cadence.parse(path)
    rows={r['uptime_s']:r for r in run['rows']}; current=None
    for line in path.read_text(errors='replace').splitlines():
        if line.startswith('[PERF8]'):
            current=rows[cadence.numbers(line)['uptime_s']]; current['jit']={}
        elif line.startswith('[JIT37] '):
            m=re.match(r'\[JIT37\] (\d+[ws]) samples=(\d+) word_dropped=(\d+) block_dropped=(\d+)',line)
            if not m or current is None: raise ValueError('JIT37 header outside cadence interval')
            if m[1] in current['jit']: raise ValueError('Duplicate JIT37 thread interval')
            current['jit'][m[1]]=dict(samples=int(m[2]),word_dropped=int(m[3]),block_dropped=int(m[4]),words={},blocks=[])
        elif line.startswith('[JIT37-WORDS] '):
            fields=line.split(); tid=fields[1]
            if current is None or tid not in current['jit']: raise ValueError('Orphan JIT37 words')
            record=current['jit'][tid]
            for item in fields[2:]:
                word,count=item.split(':'); int(word,16)
                if word in record['words'] or int(count)<=0: raise ValueError('Duplicate/invalid opcode count')
                record['words'][word]=int(count)
        elif line.startswith('[JIT37-BLOCK] '):
            fields=line.split(); tid=fields[1]
            if current is None or tid not in current['jit']: raise ValueError('Orphan JIT37 block')
            values=dict(item.split('=') for item in fields[2:])
            record=current['jit'][tid]
            record['blocks'].append(dict(guest=int(values['guest'],16),guest_bytes=int(values['guest_bytes']),
                arm_bytes=int(values['arm_bytes']),samples=int(values['samples'])))
    intervals=0
    for row in run['rows']:
        for tid,record in row.get('jit',{}).items():
            intervals+=1
            if sum(record['words'].values())+record['word_dropped']!=record['samples']:
                raise ValueError('Truncated opcode histogram')
            if len(record['blocks'])>12 or sum(b['samples'] for b in record['blocks'])+record['block_dropped']>record['samples']:
                raise ValueError('Invalid top-block counts')
            mnemonic=Counter(); category=Counter()
            for word,count in record['words'].items():
                m,c=decode(int(word,16)); mnemonic[m]+=count; category[c]+=count
            record['mnemonics']=dict(mnemonic.most_common())
            record['categories']=dict(category.most_common())
    run['jit_thread_intervals']=intervals
    run['limits']=['Samples include blocked time and are not CPU-cycle shares.',
        'Native instruction category alone does not identify simulation or rendering.',
        'Top guest blocks are reported, not complete call stacks or all executed blocks.',
        'No scene timestamps: use the supplied test sequence to interpret intervals.',
        'Probe timing includes sampling overhead; compare quiet gaps separately.',
        'Float operations can come from x87 or SSE; guest code inspection must distinguish them.']
    return run

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('log',type=Path)
    ap.add_argument('--output',type=Path); args=ap.parse_args()
    report=parse(args.log)
    target=args.output or p/'local/perf37/results'/report['sha256'][:12]/'analysis.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists(): assert json.loads(target.read_text())==report, 'Refusing to replace different analysis'
    else: target.write_text(json.dumps(report,indent=2)+'\n')
    print('jit_thread_intervals',report['jit_thread_intervals'],'output',target)
    for r in report['rows']:
        if r.get('jit'):
            print(r['uptime_s'],round(1000*r['presents']/r['interval_ms'],2),
                  {tid:v['categories'] for tid,v in r['jit'].items()})

if __name__=='__main__': main()
