"""Summarize the sampled PERF25 upload separately from the quiet run."""
from pathlib import Path
from collections import defaultdict
import json,re
p=Path(__file__).resolve().parents[1];w=p/'local/perf26'
parser=p/'tools/analyze-perf24-result.py'
ns={'__file__':str(parser)}
exec(compile(parser.read_text().split('\nruns=')[0],str(parser),'exec'),ns)
runs=[ns['parse'](f) for f in sorted((w/'diagnostic-results').glob('*.log'))]
current=next(r for r in runs if r['file']=='pes13-nx.log')
assert current['build']==['pes13-nx-0.2.0-perf25-paircopy']
old=json.loads((w/'perf25-analysis.json').read_text())
known={r['sha256']:r['file'] for r in old['runs']}
for r in runs:r['same_as_prior_upload']=known.get(r['sha256'])
groups={}
for name,lo,hi in [('early_2d',40,60),('3d_middle',130,160),('slower_interval',170,210),('ending',220,230)]:
    g=ns['group'](current['rows'],lo,hi)
    rows=[r for r in current['rows'] if lo<=int(r['uptime_s'])<=hi]
    for tid,s in g['profiles'].items():
        for cat in ('x86 callers','x86 frames'):
            acc=defaultdict(float)
            for r in rows:
                x=r['profiles'].get(tid)
                if x:
                    for site,pct in x['sites'].get(cat,{}).items():acc[site]+=x['samples']*pct/s['samples']
            s['top_reported_sites'][cat]=dict(sorted(acc.items(),key=lambda kv:-kv[1])[:16])
    g['cpu_percent_range']={tid:[min(r['threads'][tid] for r in rows if tid in r['threads']),max(r['threads'][tid] for r in rows if tid in r['threads'])]
        for tid in sorted({t for r in rows for t in r['threads']})}
    groups[name]=g
raw=(w/'diagnostic-results/pes13-nx.log').read_text()
events=[];end=0
for line in raw.splitlines():
    if line.startswith('[PERF8]'):end=int(re.search(r'uptime_s=(\d+)',line)[1])
    if re.match(r'\[(THREAD|LIFECYCLE|BALANCE23|BALANCE)\]',line):events.append({'after_report_s':end,'text':line})
report={'runs':runs,'groups':groups,'events':events,'cpu_sampler_enabled':True,
    'user_report':'Slow replay, lofted-ball stutter, persistent slowdown after several goal/foul events.',
    'last_reported_clocks_mhz':{'cpu':1728,'gpu':768,'ram':1600},
    'limitations':['Scene and event timestamps were not recorded.','Sampling observes blocked wall time as well as running code.',
        'Present rate is not simulation rate or a unique-frame count.','Host-present duration is not total GPU/driver time.',
        'Historical logs are duplicates; only current is new sampled PERF25.']}
(w/'perf25-diagnostics-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
for r in current['rows']:
    print(r['uptime_s'],r['fps'],r['host_present_ms_per_call'],r['threads'])
print(json.dumps({name:{k:v for k,v in g.items() if k!='profiles'} for name,g in groups.items()},indent=2))
for name,g in groups.items():
    print(name)
    for tid,s in g['profiles'].items():
        print(tid,s['samples'],s['shares'],dict(list(s['top_reported_sites']['x86'].items())[:6]))
