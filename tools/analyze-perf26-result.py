"""Archive-backed PERF26 analysis; no runtime/package changes."""
from pathlib import Path
import json,re,hashlib
p=Path(__file__).resolve().parents[1];w=p/'local/perf27'
parser=p/'tools/analyze-perf24-result.py';ns={'__file__':str(parser)}
exec(compile(parser.read_text().split('\nruns=')[0],str(parser),'exec'),ns)
runs=[ns['parse'](f) for f in sorted((w/'results').glob('*.log'))]
known={r['sha256']:r['file'] for r in json.loads((p/'local/perf26/perf25-diagnostics-analysis.json').read_text())['runs']}
for r in runs:r['same_as_prior_upload']=known.get(r['sha256'])
current=next(r for r in runs if r['file']=='pes13-nx.log')
raw=(w/'results/pes13-nx.log').read_text()
assert current['build']==['pes13-nx-0.2.0-perf26-callret']
assert '[INIT] profiler off (profile.txt)' in raw and '[PROF]' not in raw
assert re.search(r'^\[PERF21\].*active=1.*SAFEFLAGS=2.*X87DOUBLE=1.*CALLRET=2$',raw,re.M)
assert not current['faults'] and not current['exits']
groups={}
for name,lo,hi in [('early_menu_candidate',40,50),('long_match_candidate',130,290),('before_transition',250,290),('after_transition',300,330)]:
    g=ns['group'](current['rows'],lo,hi)
    rows=[r for r in current['rows'] if lo<=int(r['uptime_s'])<=hi]
    g['cpu_percent_range']={tid:[min(r['threads'][tid] for r in rows if tid in r['threads']),max(r['threads'][tid] for r in rows if tid in r['threads'])]
        for tid in sorted({t for r in rows for t in r['threads']})}
    groups[name]=g
events=[];end=0
for line in raw.splitlines():
    if line.startswith('[PERF8]'):end=int(re.search(r'uptime_s=(\d+)',line)[1])
    if re.match(r'\[(THREAD|LIFECYCLE|BALANCE23|PROGRESS)\]',line):events.append({'after_perf8_report_s':end,'line':line})
# Confirm that the actual console translation includes matched-return + fallback.
native=(w/'captures/slot-2-arm64.bin').read_bytes()
ret=bytes.fromhex('fe1bc1a8c6001bcb460000b5c0035fd69f4300d1')
assert native.count(ret)==1
report={'runs':runs,'groups':groups,'events':events,'callret_active_and_captured':True,'cpu_sampler_enabled':False,
    'user_report':'Below 30 FPS initially and persistent slow motion after fouls or similar events.',
    'limits':['Scene labels are inferred, with no synchronized event markers.',
        'Present counts do not measure unique rendered frames or simulation updates.',
        'Host-present time includes blocking/descheduling; it is not GPU execution time.',
        'Current run has no CPU PC samples; previous PERF25 samples are context only.',
        'Server durations include overlapping waits and cannot be summed as CPU busy time.',
        'No matched Linux/Android build, preset and scene trace is available.']}
(w/'perf26-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'runs':[{k:r[k] for k in ('file','sha256','build','same_as_prior_upload')} for r in runs],
    'groups':{n:{'presents_per_s':g['presents_per_s'],'fps_range':g['fps_range'],
        'gap':g['frames']['gap_quiet'],'present':g['frames']['host_present'],'cpu':g['cpu_percent_range']} for n,g in groups.items()},
    'callret_active_and_captured':True},indent=2))
