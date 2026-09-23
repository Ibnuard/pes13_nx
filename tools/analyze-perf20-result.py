"""Summarize PERF20's non-sampled console run and captured remaining work."""
from pathlib import Path
import hashlib,json,re
import capstone

p=Path(__file__).resolve().parents[1]; w=p/'local/perf21'
raw=(w/'perf20-result.log').read_bytes(); log=raw.decode(errors='replace')
rows=[dict(re.findall(r'(\w+)=([^ ]+)',l)) for l in log.splitlines() if l.startswith('[PERF8]')]
groups={}
for name,lo,hi in [('selection_candidate',70,80),('late_match_candidate',130,190)]:
    chosen=[r for r in rows if lo<=int(r['uptime_s'])<=hi]
    groups[name]={'ends_s':[int(r['uptime_s']) for r in chosen],
                  'fps_weighted':1000*sum(int(r['presents']) for r in chosen)/sum(int(r['interval_ms']) for r in chosen),
                  'fps_range':[min(float(r['fps']) for r in chosen),max(float(r['fps']) for r in chosen)]}
manifest=json.loads((w/'captures/manifest.json').read_text())
md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM); md.skipdata=True
captures=[]
for b in manifest['blocks']:
    blob=(w/f"captures/slot-{b['slot']}-arm64.bin").read_bytes()
    listing=list(md.disasm(blob,0))
    captures.append({'guest':hex(b['guest']),'guest_size':b['guest_size'],
                     'native_size':b['native_size'],'captured_bytes':len(blob),
                     'complete':b['native_size']==len(blob),
                     'fpcr_reads_in_capture':sum(i.mnemonic=='mrs' and 'fpcr' in i.op_str for i in listing),
                     'fpcr_writes_in_capture':sum(i.mnemonic=='msr' and 'fpcr' in i.op_str for i in listing),
                     'memory_barriers_in_capture':sum(i.mnemonic=='dmb' for i in listing)})
report={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
        'profiler_off': '[INIT] profiler off (profile.txt)' in log,
        'groups':groups,'last_perf20':re.findall(r'^\[PERF20\].*$',log,re.M)[-1],
        'rld_attach':re.findall(r'^.*attach name=rld.dll.*$',log,re.M),
        'captures':captures,
        'limits':'Scene labels inferred, no synchronized old/new comparison; PERF19 had sampling enabled, PERF20 does not. Compilation counters are not execution counts.'}
(w/'perf20-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
