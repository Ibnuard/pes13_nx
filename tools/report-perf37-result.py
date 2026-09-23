"""Reproduce the PERF37 timeline and sampled-word totals used by PERF38."""
from pathlib import Path
from collections import Counter
import json
p=Path(__file__).resolve().parents[1]
w=p/'local/perf37/results/a03c22c64e05'
run=json.loads((w/'analysis.json').read_text())
groups={'main':['4w'],'worker124':['124w'],
        'changing_workers':['176w','192w','204w','220w','232w']}
result={'source_sha256':run['sha256'],'from_uptime_s':100,
        'event_time_user':'approximately after 5 minutes; exact scenes not timestamped',
        'timeline':[],'groups':{},'faults':run['faults']}
for r in run['rows']:
    if r['uptime_s']>=301:
        result['timeline'].append(dict(uptime_s=r['uptime_s'],
            presents_per_second=round(1000*r['presents']/r['interval_ms'],3),
            quiet_gap_us=r['frames']['gap_quiet']['avg_us'],
            host_present_us=r['frames']['host_present']['avg_us'],core_equivalents=r['cores']))
for name,tids in groups.items():
    words=Counter();blocks=Counter();categories=Counter();samples=0
    for r in run['rows']:
        if r['uptime_s']<100:continue
        for tid in tids:
            a=r.get('jit',{}).get(tid)
            if not a:continue
            assert not a['word_dropped'] and not a['block_dropped']
            samples+=a['samples'];words.update(a['words']);categories.update(a['categories'])
            for b in a['blocks']:
                blocks[(hex(b['guest']),b['guest_bytes'],b['arm_bytes'])]+=b['samples']
    fpcr=sum(count for word,count in words.items()
             if int(word,16)&0xffffffe0 in (0xd53b4400,0xd51b4400))
    result['groups'][name]=dict(tids=tids,jit_wall_samples=samples,
        fpcr_read_write_samples=fpcr,categories=dict(categories),top_words=words.most_common(12),
        top_blocks=[dict(guest=k[0],guest_bytes=k[1],arm_bytes=k[2],samples=v)
                    for k,v in blocks.most_common(8)])
result['limits']=run['limits']
target=w/'evidence.json'
target.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
