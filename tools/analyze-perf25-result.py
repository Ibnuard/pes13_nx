"""Reproduce the five supplied PERF25/older-run results without pooling builds."""
from pathlib import Path
import hashlib,json,re
p=Path(__file__).resolve().parents[1];w=p/'local/perf26'
# Reuse the exact parser, without executing the previous report's output code.
previous=p/'tools/analyze-perf24-result.py'
ns={'__file__':str(previous),'__name__':'perf24_parser_only'}
text=previous.read_text();assert text.count('\nruns=')==1
exec(compile(text.split('\nruns=')[0],str(previous),'exec'),ns)
runs=[ns['parse'](f) for f in sorted((w/'results').glob('*.log'))]
current=next(r for r in runs if r['file']=='pes13-nx.log')
assert current['build']==['pes13-nx-0.2.0-perf25-paircopy']
assert not current['faults'] and not current['exits']
raw=(w/'results/pes13-nx.log').read_text()
assert '[INIT] profiler off (profile.txt)' in raw and '[PROF]' not in raw
assert '[PERF25] paircopy=1 compile_checks=4 accepted=4' in raw
groups={name:ns['group'](current['rows'],lo,hi) for name,lo,hi in (
    ('early',40,60),('middle',130,200),('worker_transition',210,220),('late',230,300))}
for name,g in groups.items():
    chosen=[r for r in current['rows'] if int(r['uptime_s']) in g['windows_ending_s']]
    tids={tid for r in chosen for tid in r['threads']}
    g['reported_thread_cpu_range']={tid:[min(r['threads'][tid] for r in chosen if tid in r['threads']),
                                         max(r['threads'][tid] for r in chosen if tid in r['threads'])] for tid in sorted(tids)}
old=json.loads((p/'local/perf25/perf24-analysis.json').read_text())
known={r['sha256']:r['file'] for r in old['runs']}
for run in runs:run['same_as_previous_upload']=known.get(run['sha256'])
# Verify the runtime snapshot contains exactly the tested emitted loop.
capture=(w/'captures/slot-1-arm64.bin').read_bytes()
expected=(p/'local/perf25/copy-pair.bin').read_bytes()
assert capture[36:36+len(expected)]==expected
assert (w/'captures/slot-1-x86.bin').read_bytes()==(p/'local/perf25/captures/slot-1-x86.bin').read_bytes()
events=re.findall(r'^\[(?:THREAD|LIFECYCLE|BALANCE23|BALANCE)\].+$',raw,re.M)
report={'runs':runs,'groups':groups,'events_without_timestamps':events,
    'user_reported_replay_slowdown':'Returns to pre-replay performance afterward',
    'copy_loop_matches_tested_emitter':True,'cpu_sampler_enabled':False,
    'last_reported_clocks_mhz':{'cpu':1728,'gpu':768,'ram':1600},
    'limitations':['Only current log is PERF25; previous files repeat older supplied runs.',
        'No synchronized scene/replay labels; event association is not established.',
        'Thread CPU use is available; this run has no PC samples.',
        'Present cadence is not a unique simulation-frame counter or total GPU execution time.',
        'No same-scene, same-sampler A/B test; no isolated percentage speedup claim.']}
(w/'perf25-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
summary={'runs':[{k:r[k] for k in ('file','sha256','build','same_as_previous_upload')} for r in runs],
         'groups':{name:{k:g[k] for k in ('presents_per_s','fps_range','frames')} for name,g in groups.items()},
         'copy_loop_matches_tested_emitter':True}
print(json.dumps(summary,indent=2))
