"""Read-only summaries from the five retained PERF24/23 runs."""
from pathlib import Path
from collections import defaultdict
import hashlib,json,re
p=Path(__file__).resolve().parents[1]; w=p/'local/perf25'

def parse(path):
    raw=path.read_bytes(); text=raw.decode(errors='replace'); rows=[]
    for line in text.splitlines():
        if line.startswith('[PERF8]'):
            r=dict(re.findall(r'(\w+)=(\S+)',line))
            r.update({'profiles':{},'frames':{},'threads':{}}); rows.append(r)
        elif not rows: continue
        elif line.startswith('[THREADS]'):
            r['cores']=float(re.search(r'use ([\d.]+) cores',line)[1])
            r['threads']={tid:float(pct) for tid,pct in re.findall(r'(\d+[ws])@-?\d+ ([\d.]+)%',line)}
        elif line.startswith('[FRAME24]'):
            m=re.match(r'\[FRAME24\] (\w+) n=(\d+) avg_us=(\d+) max_since_launch_us=(\d+) bins=(.+)',line)
            if m: r['frames'][m[1]]={'n':int(m[2]),'avg_us':int(m[3]),'max_since_launch_us':int(m[4]),'bins':list(map(int,m[5].split(',')))}
        elif line.startswith('[SAMPLE24]'):
            r['sampler']=dict(re.findall(r'(\w+)=(\d+)',line))
        elif line.startswith('[PROF]'):
            m=re.match(r'\[PROF\] (\d+[ws]) samples=(\d+) missed=(\d+) (.*)',line)
            if m: r['profiles'][m[1]]={'samples':int(m[2]),'missed':int(m[3]),'shares':{k:float(v) for k,v in re.findall(r'(\w+)=([\d.]+)%',m[4])},'sites':{}}
            else:
                m=re.match(r'\[PROF\] (\d+[ws]) ([\w ]+): (.*)',line)
                if m and m[1] in r['profiles']:
                    r['profiles'][m[1]]['sites'][m[2]]={k:float(v) for k,v in re.findall(r'(\S+) ([\d.]+)%',m[3])}
    return {'file':path.name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
        'build':re.findall(r'^\[BUILD\] (.+)$',text,re.M), 'rows':rows,
        'faults':re.findall(r'^\[BOX64 FAULT\].+$',text,re.M),
        'exits':re.findall(r'^\[EXIT\].+$',text,re.M)}

def group(rows,lo,hi):
    rows=[r for r in rows if lo<=int(r['uptime_s'])<=hi]
    out={'windows_ending_s':[int(r['uptime_s']) for r in rows],
         'presents_per_s':sum(int(r['presents']) for r in rows)*1000/sum(int(r['interval_ms']) for r in rows),
         'fps_range':[min(float(r['fps']) for r in rows),max(float(r['fps']) for r in rows)],'frames':{},'profiles':{}}
    for phase in ('gap_quiet','gap_sampled','host_present'):
        frame=[r['frames'][phase] for r in rows if phase in r['frames']]
        n=sum(r['n'] for r in frame); bins=[sum(r['bins'][i] for r in frame) for i in range(10)]
        out['frames'][phase]={'n':n,'bins':bins,'avg_us':sum(r['n']*r['avg_us'] for r in frame)/n if n else None,
            'over_100ms':sum(bins[5:]),'over_200ms':sum(bins[6:])}
    tids={t for r in rows for t in r['profiles']}
    for tid in sorted(tids):
        samples=[r['profiles'][tid] for r in rows if tid in r['profiles']]
        n=sum(s['samples'] for s in samples)
        shares={k:sum(s['samples']*s['shares'].get(k,0) for s in samples)/n for k in ('x86','pe','native','svc')}
        sites={}
        for category in ('x86 by module','x86','svc','native','callers'):
            acc=defaultdict(float)
            for s in samples:
                for site,pct in s['sites'].get(category,{}).items(): acc[site]+=s['samples']*pct/n
            sites[category]=dict(sorted(acc.items(),key=lambda kv:-kv[1])[:15])
        out['profiles'][tid]={'samples':n,'shares':shares,'top_reported_sites':sites}
    return out

runs=[parse(path) for path in sorted((w/'results').glob('*.log'))]
current=next(r for r in runs if r['file']=='pes13-nx.log')
groups={name:group(current['rows'],lo,hi) for name,lo,hi in [('early',40,50),('middle',120,170),('late',220,300)]}
report={'runs':runs,'groups':groups,'user_reported_clocks_mhz':{'cpu':1728,'gpu':768,'ram':1600},'limitations':[
    'No synchronized scene/event labels or GPU execution timing.',
    'Sampling includes blocked time; rounded per-site top lists are incomplete.',
    'The frame histograms omit gaps crossing sampling phase changes.',
    'User reports unchanged clocks; scenes are not matched with earlier experiments.']}
(w/'perf24-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
addresses=set()
for r in current['rows']:
    for s in r['profiles'].values():
        for c in ('native','svc','callers'):
            for site in s['sites'].get(c,{}): addresses.update(re.findall(r'\+(0x[0-9a-f]+)',site))
(w/'native-addresses.txt').write_text('\n'.join(sorted(addresses,key=lambda a:int(a,16)))+'\n')
print(json.dumps({'runs':[{k:r[k] for k in ('file','bytes','build','faults','exits')} for r in runs],
    'groups':{name:{k:v for k,v in g.items() if k!='profiles'} for name,g in groups.items()},
    'late_samples':{t:{k:v for k,v in s.items() if k!='top_reported_sites'} for t,s in groups['late']['profiles'].items()}},indent=2))
