"""Join old pipeline and new native timings without treating them as GPU time."""
from pathlib import Path
import importlib.util,json
p=Path(__file__).resolve().parents[1];w=p/'local/perf31'
def module(name,file):
    s=importlib.util.spec_from_file_location(name,p/'tools'/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
old=module('old','analyze-perf29-result.py');native=module('native','analyze-perf30.py')
runs=[]
for path in sorted((w/'results').glob('*.log')):
    r=old.parse(path);stages=native.parse_log(path.read_text())
    by_time={x['uptime_s']:x for x in stages['windows']}
    for row in r['rows']:row['native30']=by_time[row['uptime_s']]
    runs.append(r)
report={'runs':runs,'user_event_time_approx_seconds':270,
    'user_audio':'Audio remained smooth despite frame slowdown.',
    'limits':['Present count does not establish simulation speed or unique rendered frames.',
    'Sampling run and diagnostic run are not matched A/B scenes.',
    'Native stage times nest; host wait time is not GPU time.',
    'An instrumented archive member does not prove that member was selected by the linker.']}
(w/'joined-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
for r in runs[:3]:
    print(r['file'],r['build'],r['sampler'])
    for row in r['rows']:
        if row['uptime_s']<110:continue
        pipe=row['pipe'].get('submit_host',{});nv=row['native30']['stages'].get('queue_driver',{})
        print(row['uptime_s'],round(row['presents']*1000/row['interval_ms'],2),
              'submit_ms',round(pipe.get('total_us',0)/1000,1),'NVK_ms',round(nv.get('total_us',0)/1000,1),
              'cores',row.get('cores'),'top',sorted(row['threads'].items(),key=lambda x:-x[1])[:3])
