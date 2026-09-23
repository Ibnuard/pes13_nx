"""PERF27 upload: startup exceptions, filtered wakeups and pipeline durations."""
from pathlib import Path
import json,re
p=Path(__file__).resolve().parents[1];w=p/'local/perf28'
parser=p/'tools/analyze-perf24-result.py';ns={'__file__':str(parser)}
exec(compile(parser.read_text().split('\nruns=')[0],str(parser),'exec'),ns)
runs=[]
for f in sorted((w/'results').glob('*.log')):
    run=ns['parse'](f); index=-1
    for line in f.read_text().splitlines():
        if line.startswith('[PERF8]'):
            index+=1;row=run['rows'][index];row['pipe']={};row['sync']={}
        elif index>=0 and line.startswith('[PIPE27]'):
            row['pipe'][line.split()[1]]={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)}
        elif index>=0 and line.startswith('[SYNC27]'):
            row['sync']={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)}
    runs.append(run)
current=next(r for r in runs if r['file']=='pes13-nx.log')
groups={}
for label,lo,hi in [('menu_candidate',40,50),('selection_candidate',60,110),
                    ('match_candidate',120,170),('transition_candidate',180,210),
                    ('match_candidate_2',220,280),('late_match_candidate',300,360)]:
    g=ns['group'](current['rows'],lo,hi); rows=[r for r in current['rows'] if lo<=int(r['uptime_s'])<=hi]
    g['pipe']={}
    for stage in sorted({s for r in rows for s in r['pipe']}):
        values=[r['pipe'][stage] for r in rows if stage in r['pipe']];n=sum(v['n'] for v in values)
        g['pipe'][stage]={'n':n,'avg_us':sum(v['total_us'] for v in values)/n if n else None,
            'gt16ms':sum(v['gt16ms'] for v in values)}
    g['sync']={key:sum(r['sync'].get(key,0) for r in rows) for key in ('notices','broad','candidates','notified','filtered','sleeps')}
    g['sync']['filtered_fraction']=g['sync']['filtered']/g['sync']['candidates'] if g['sync']['candidates'] else 0
    g['cpu_percent_range']={tid:[min(r['threads'][tid] for r in rows if tid in r['threads']),
        max(r['threads'][tid] for r in rows if tid in r['threads'])] for tid in sorted({t for r in rows for t in r['threads']})}
    groups[label]=g
report={'runs':runs,'groups':groups,'user_reports_recovery_after_replay_foul':True,
 'screenshot_cpu_mhz':1787.3,'previous_reported_cpu_mhz':1728,
 'limits':['Scene/event labels are inferred; no synchronized timestamps.',
 'CPU sampler is off. PIPE27 measures wall duration, not GPU execution.',
 'Nested and concurrent spans cannot be added to derive total frame time.',
 'No matched PERF27 control run. Screenshot clock differs from previously reported CPU 1728.',
 'Notification attempts filtered are not a measured number of kernel wakeups saved.',
 'Screenshots and user 70% description do not establish a 70% FPS improvement.']}
(w/'perf27-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'runs':[{k:r[k] for k in ('file','bytes','build','faults','exits')} for r in runs],
 'groups':{label:{k:v for k,v in g.items() if k not in ('profiles','frames','cpu_percent_range')} for label,g in groups.items()}},indent=2))
