"""Reproduce the PERF38 event/worker cadence finding from one archived run."""
from pathlib import Path
import importlib.util, json, re

project=Path(__file__).resolve().parents[1]
source=project/'local/perf38/results/5438c8383572/pes13-nx.log'
spec=importlib.util.spec_from_file_location('cadence',project/'tools/analyze-perf29-result.py')
cadence=importlib.util.module_from_spec(spec);spec.loader.exec_module(cadence)
run=cadence.parse(source)
assert run['sha256']=='5438c83835726f0ab228d4435a1102edf898b7bc9e64bb27a0575f6ef129d6f5'
assert run['build']==['pes13-nx-0.2.0-perf38-region-fusion']
assert run['sampler']==['off']
raw=source.read_text(errors='replace').splitlines()
perf38=[]
for line in raw:
    if line.startswith('[PERF38]'):
        d=cadence.numbers(line)
        if d.get('region_fusion')==1:perf38.append(d)
assert perf38 and perf38[-1]['merged']>=178
windows={label:cadence.summarize(run['rows'],lo,hi) for label,lo,hi in (
    ('early_90_100',90,100),('busy_140_220',140,220),
    ('worker_turnover_230_240',230,240),('replacement_250',250,250))}
timeline=[]
for row in run['rows']:
    if row['uptime_s']<80:continue
    timeline.append(dict(end_s=row['uptime_s'],
        presents_per_s=round(1000*row['presents']/row['interval_ms'],2),
        cores=row.get('cores'),
        threads={tid:row['threads'].get(tid) for tid in ('4w','124w','176w','188w','200w')
                 if tid in row['threads']},
        host_present_ms=round(row['frames']['host_present']['avg_us']/1000,3),
        quiet_gap_ms=round(row['frames']['gap_quiet']['avg_us']/1000,3)))
transitions=[]
for item in run['lifecycle']:
    m=re.search(r'(?:tid=|exit tid=)(176|188|200)\b',item['text'])
    if m:transitions.append(item)
result=dict(source_sha256=run['sha256'],build=run['build'],
    perf38=dict(enabled=perf38[-1]['region_fusion'],blocks=perf38[-1]['blocks'],
        guards=perf38[-1]['guards'],merged=perf38[-1]['merged'],
        flow_rejected=perf38[-1]['flow_rejected']),
    windows=windows,timeline=timeline,transitions=transitions,
    faults=run['faults'],progress=run['progress'],
    limits=['Thread CPU percent is per logical core, not a frame-stage timer.',
            'The log has no synchronized game scene/event timestamps.',
            'Worker entry 0x4da0e3 is generic and does not identify its work.',
            'Host-present time does not cover all CPU rendering, GPU work or waits.',
            'PERF38 merged counts are block-compilation counts, not executions.',
            'The RUN23 log is a single run and ends near 250 s.'])
target=source.parent/'analysis.json'
if target.exists():assert json.loads(target.read_text())==result
else:target.write_text(json.dumps(result,indent=2)+'\n')
print('Archived',run['sha256'],'rows',len(run['rows']),'faults',len(run['faults']))
for r in timeline:
    print(r['end_s'],r['presents_per_s'],r['cores'],r['threads'],r['host_present_ms'])
