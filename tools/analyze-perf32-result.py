"""Archive PERF32 input and report cadence without guessing the corner timestamp."""
from pathlib import Path
import hashlib, importlib.util, json, re, zipfile

p=Path(__file__).resolve().parents[1]
w=p/'local/perf32/corner-result'
w.mkdir(parents=True,exist_ok=True)
source=p/'dist/pes13-perf32-game-blocks/switch/pes13-nx.log'
raw=source.read_bytes();target=w/'pes13-nx.log'
if target.exists():assert target.read_bytes()==raw,'Refusing to replace archived evidence'
else:target.write_bytes(raw)
spec=importlib.util.spec_from_file_location('parser',p/'tools/analyze-perf29-result.py')
parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
run=parser.parse(target)
assert run['build']==['pes13-nx-0.2.0-perf32-game-blocks']
assert run['sampler']==['off']
row=None;by_time={x['uptime_s']:x for x in run['rows']}
for line in raw.decode().splitlines():
    if line.startswith('[PERF8]'):
        row=by_time[parser.numbers(line)['uptime_s']]
    elif row is not None and line.startswith('[PERF32]'):
        row['policy32']=parser.numbers(line)
    elif row is not None and line.startswith('[AFF23]'):
        row['affinity_line']=line
    elif row is not None and line.startswith('[SERVER]'):
        row['server_line']=line
groups={label:parser.summarize(run['rows'],lo,hi) for label,lo,hi in (
    ('early_130_170',130,170),('transition_180',180,180),
    ('sustained_190_270',190,270),('transition_280_290',280,290),('last_300',300,300))}
for g in groups.values():
    hist=g['frames'].get('gap_quiet',{})
    if hist:
        g['gap_quiet_over_100ms']=sum(hist['bins'][5:])
        g['gap_quiet_over_200ms']=sum(hist['bins'][6:])
report=dict(run=run,groups=groups,source=str(source),
    user_corner_time_approx_s=300,last_log_report_s=run['rows'][-1]['uptime_s'],
    limits=['User time is approximate; the log does not label corners or gameplay scenes.',
            'Log ends at the reported event time, with no later report of persistent slowdown.',
            'Present count does not establish simulation speed or count unique displayed images.',
            'Host present duration is not total renderer work or GPU execution time.',
            'Server wait totals overlap among threads and are not CPU time.',
            'Newly compiled blocks and bytes are not executed instruction counts.',
            'No sampled PCs in this run; old samples cannot identify this corner failure.'])
(w/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
for label,g in groups.items():
    print(label,'presents/s',round(g['presents_per_s'],3),'mean_gap_us',g['frames']['gap_quiet']['avg_us'],
          'host_present_us',g['frames']['host_present']['avg_us'],
          'over100ms',g['gap_quiet_over_100ms'],'/',g['frames']['gap_quiet']['n'])
print('log sha256',run['sha256'],'last policy',run['rows'][-1]['policy32'])
print('faults',run['faults'])
for row in run['rows']:
    if row['uptime_s']>=130:
        print(row['uptime_s'],round(row['presents']*1000/row['interval_ms'],2),
              'top',sorted(row['threads'].items(),key=lambda x:-x[1])[:3])

# Verify the already-built diagnostic package is the exact same runtime.
records=json.loads((p/'local/perf32/packages.json').read_text())
payloads={}
for name in ('game-blocks','diagnostics'):
    record=next(r for r in records if r['variant']==name)
    file=p/'dist'/f'pes13-perf32-{name}.zip'
    data=file.read_bytes();assert hashlib.sha256(data).hexdigest()==record['sha256']
    with zipfile.ZipFile(file) as z:
        assert z.testzip() is None
        manifest=json.loads(z.read('PERF32-manifest.json'))
        assert all(hashlib.sha256(z.read(n)).hexdigest()==digest for n,digest in manifest['files'].items())
        payloads[name]={n:z.read(n) for n in z.namelist() if n.startswith('switch/')}
prefix='switch/pes13-nx/'
assert set(payloads['game-blocks'])==set(payloads['diagnostics'])
assert {n for n in payloads['game-blocks'] if payloads['game-blocks'][n]!=payloads['diagnostics'][n]}=={
    prefix+'profile.txt',prefix+'drive_c/PES13/pes2013.wine-nx.txt'}
assert sum(n.endswith('.nro') for n in payloads['diagnostics'])==1
print('Existing full PERF32 diagnostics: same NRO, only two sampler settings differ, ZIP and manifest PASS')
