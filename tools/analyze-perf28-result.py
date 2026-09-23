"""Reproducible read-only summary of archived PERF28 runs and sampled workers."""
from pathlib import Path
import json,re
p=Path(__file__).resolve().parents[1];w=p/'local/perf29'
parser=p/'tools/analyze-perf24-result.py';ns={'__file__':str(parser)}
exec(compile(parser.read_text().split('\nruns=')[0],str(parser),'exec'),ns)
runs=[]
for path in sorted((w/'results').glob('*.log')):
    run=ns['parse'](path);index=-1;run['fault28']=[]
    for line in path.read_text().splitlines():
        if line.startswith('[FAULT28]') and any(x in line for x in ('begin read-only',' eip=',' inferred table=',' end scanned=')):
            run['fault28'].append(line)
        if line.startswith('[PERF8]'):
            index+=1;row=run['rows'][index];row['pipe']={}
        elif index>=0 and line.startswith('[PIPE27]'):
            row['pipe'][line.split()[1]]={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)}
    assert run['build']==['pes13-nx-0.2.0-perf28-diagnostics'],run['file']
    runs.append(run)
assert len(runs)==5
current=next(r for r in runs if r['file']=='pes13-nx.log');groups={}
for label,lo,hi in [('menu_candidate',40,50),('selection_candidate',60,90),
                    ('early_match',110,150),('later_match',170,330)]:
    g=ns['group'](current['rows'],lo,hi)
    rows=[r for r in current['rows'] if lo<=int(r['uptime_s'])<=hi]
    g['cpu_percent_range']={tid:[min(r['threads'][tid] for r in rows if tid in r['threads']),
        max(r['threads'][tid] for r in rows if tid in r['threads'])] for tid in sorted({t for r in rows for t in r['threads']})}
    g['pipe']={}
    for stage in sorted({s for r in rows for s in r['pipe']}):
        values=[r['pipe'][stage] for r in rows if stage in r['pipe']];n=sum(v['n'] for v in values)
        g['pipe'][stage]={'n':n,'avg_us':sum(v['total_us'] for v in values)/n if n else None,
            'gt16ms':sum(v['gt16ms'] for v in values)}
    groups[label]=g
report={'runs':runs,'groups':groups,'scene_confirmation':'User was playing match at approximately 2–3 minutes after launch.',
    'limits':['Present rate is not simulation speed; only the 2–3 minute scene was explicitly confirmed.',
    'CPU samples include blocked wall time; rounded top-site lists are incomplete.',
    'PIPE27 host spans are neither GPU time nor additive frame costs.',
    'No matched control run or independent clock verification in this upload.',
    'FAULT28 inferred table capture is bounded and may race concurrent game writes.']}
(w/'perf28-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'runs':[{k:r[k] for k in ('file','bytes','sha256','fault28')} for r in runs],
    'groups':{label:{k:v for k,v in g.items() if k not in ('profiles','cpu_percent_range')} for label,g in groups.items()}},indent=2))
