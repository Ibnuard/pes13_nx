"""Summarize PERF22 and retain the evidence for persistent post-transition lag."""
from pathlib import Path
import hashlib,json,re
import capstone
p=Path(__file__).resolve().parents[1]; w=p/'local/perf23'
raw=(w/'perf22-result.log').read_bytes(); log=raw.decode(errors='replace')
rows=[dict(re.findall(r'(\w+)=(\S+)',l)) for l in log.splitlines() if l.startswith('[PERF8]')]
groups={}
for label,lo,hi in [('early',40,50),('before_worker_exit',120,190),('after_worker_exit',210,260)]:
    selected=[r for r in rows if lo<=int(r['uptime_s'])<=hi]
    groups[label]={'windows_ending_s':[int(r['uptime_s']) for r in selected],
        'fps':1000*sum(int(r['presents']) for r in selected)/sum(int(r['interval_ms']) for r in selected),
        'range':[min(float(r['fps']) for r in selected),max(float(r['fps']) for r in selected)]}
previous={b['slot']:b for b in json.loads((p/'local/perf22/captures/manifest.json').read_text())['blocks']}
md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM); md.skipdata=True
blocks=[]
for b in json.loads((w/'captures/manifest.json').read_text())['blocks']:
    old=previous[b['slot']]; assert old['x86_sha256']==b['x86_sha256']
    ins=list(md.disasm((w/f"captures/slot-{b['slot']}-arm64.bin").read_bytes(),b['native']))
    blocks.append({'guest':hex(b['guest']),'slot':b['slot'],'same_guest':True,
        'perf21_bytes':old['native_size'],'perf22_bytes':b['native_size'],
        'conversions':sum(i.mnemonic=='fcvt' for i in ins)})
report={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'groups':groups,'blocks':blocks,
        'captured_stalled_launch':False,'last_perf22':re.findall(r'^\[PERF22\].*$',log,re.M)[-1],
        'last_balance':re.findall(r'^\[BALANCE\].*$',log,re.M)[-1],
        'worker_replacement':'tid176 exits between 190/200-second reports; tid184 enters and stays on preferred core3 in subsequent reports',
        'limitations':'Thread reports show preferred core, not complete affinity/fixed state. No simultaneous scene marker or failed-launch log. CPU demand is measured delivered time, not runnable demand.'}
(w/'perf22-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
