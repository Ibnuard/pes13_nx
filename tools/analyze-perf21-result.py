"""Summarize the measured PERF21 run and compare matching captured blocks."""
from pathlib import Path
import hashlib, json, re
import capstone

p=Path(__file__).resolve().parents[1]; w=p/'local/perf22'
raw=(w/'perf21-result.log').read_bytes(); log=raw.decode(errors='replace')
rows=[dict(re.findall(r'(\w+)=(\S+)',line)) for line in log.splitlines() if line.startswith('[PERF8]')]
groups={}
for name,lo,hi in [('early_2d_candidate',40,50),('middle_3d_candidate',110,160),('late_mixed_candidate',170,240)]:
    selected=[r for r in rows if lo<=int(r['uptime_s'])<=hi]
    groups[name]={'ends_s':[int(r['uptime_s']) for r in selected],
        'fps_weighted':1000*sum(int(r['presents']) for r in selected)/sum(int(r['interval_ms']) for r in selected),
        'fps_range':[min(float(r['fps']) for r in selected),max(float(r['fps']) for r in selected)]}
md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM); md.skipdata=True
old={b['slot']:b for b in json.loads((p/'local/perf21/captures/manifest.json').read_text())['blocks']}
captures=[]
for b in json.loads((w/'captures/manifest.json').read_text())['blocks']:
    listing=list(md.disasm((w/f"captures/slot-{b['slot']}-arm64.bin").read_bytes(),b['native']))
    prev=old[b['slot']]
    assert b['guest']==prev['guest'] and b['x86_sha256']==prev['x86_sha256']
    captures.append({'slot':b['slot'],'guest':hex(b['guest']),
        'same_guest_bytes_as_perf20':True,'perf20_native_bytes':prev['native_size'],
        'perf21_native_bytes':b['native_size'],'capture_complete':b['native_size']==b['arm_bytes'],
        'fpcr_accesses':sum(i.mnemonic in ('mrs','msr') and 'fpcr' in i.op_str for i in listing),
        'float_double_conversions':sum(i.mnemonic=='fcvt' for i in listing),
        'dmb_barriers':sum(i.mnemonic=='dmb' for i in listing)})
report={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
    'profiler_off':'[INIT] profiler off (profile.txt)' in log,
    'groups':groups,'captures':captures,
    'last_perf21':re.findall(r'^\[PERF21\].*$',log,re.M)[-1],
    'limitations':'Presents, not unique simulated frames. Scene labels inferred. Different runs are not a controlled benchmark. Native byte counts and static instruction counts are not execution time.'}
(w/'perf21-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
