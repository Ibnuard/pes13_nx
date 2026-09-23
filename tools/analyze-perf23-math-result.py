"""Summarize the retained, successful PERF23 math-control hardware run."""
from pathlib import Path
import hashlib,json,re
p=Path(__file__).resolve().parents[1]; w=p/'local/perf24'
raw=(w/'perf23-math-control-result.log').read_bytes()
log=raw.decode(errors='replace')
assert '[BUILD] pes13-nx-0.2.0-perf23-transitions' in log
assert '[PERF22] enabled=0 active=0' in log
rows=[]
for line in log.splitlines():
    if line.startswith('[PERF8]'):
        rows.append(dict(re.findall(r'(\w+)=(\S+)',line)))
    elif rows and line.startswith('[THREADS]'):
        rows[-1]['cores']=float(re.search(r'use ([\d.]+) cores',line)[1])
        rows[-1]['threads']=line
groups={}
for name,lo,hi in [('early',40,50),('middle',120,150),('late',160,200)]:
    selected=[r for r in rows if lo<=int(r['uptime_s'])<=hi]
    groups[name]={'windows_ending_s':[int(r['uptime_s']) for r in selected],
        'presents_per_s':1000*sum(int(r['presents']) for r in selected)/sum(int(r['interval_ms']) for r in selected),
        'range':[min(float(r['fps']) for r in selected),max(float(r['fps']) for r in selected)]}
report={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'groups':groups,'intervals':rows,
    'guest_exceptions':re.findall(r'^\[EXC\].*$',log,re.M),
    'failed_launch_included':False,'sampling_enabled':False,
    'math':'FASTROUND=1 scoped, X87DOUBLE=1, SAFEFLAGS=2',
    'limitations':['Scenes are not timestamp-marked; the foul cannot be aligned exactly.',
        'Successful present counts are not unique simulation frames or GPU execution times.',
        'No matched scene/clock benchmark against the preceding run.',
        'The overwritten earlier input from this turn was not archived; this file is the later math-control run.']}
(w/'perf23-math-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('bytes','sha256','groups')},indent=2))
