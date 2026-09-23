"""Summarize the archived PERF19 console run without assuming scene parity."""
from pathlib import Path
import hashlib
import json
import re

p = Path(__file__).resolve().parents[1]
work = p/'local/perf20'
raw = (work/'perf19-result.log').read_bytes()
log = raw.decode(errors='replace')
rows = []
for line in log.splitlines():
    if line.startswith('[PERF8] '):
        rows.append(dict(re.findall(r'(\w+)=([^ ]+)', line)))
        rows[-1]['threads'] = {}
    elif line.startswith('[THREADS] ') and rows:
        rows[-1]['cores'] = float(re.search(r'use ([\d.]+) cores', line)[1])
        rows[-1]['threads'] = {tid: float(pct) for tid, pct in re.findall(r'(\d+[ws])@-?\d+ ([\d.]+)%', line)}
groups = {}
for name, lo, hi in [('selection_candidate', 70, 90), ('late_match_candidate', 160, 230)]:
    selected = [r for r in rows if lo <= int(r['uptime_s']) <= hi]
    groups[name] = {
        'intervals_ending_s': [int(r['uptime_s']) for r in selected],
        'fps_weighted': sum(int(r['presents']) for r in selected)*1000/sum(int(r['interval_ms']) for r in selected),
        'fps_range': [min(float(r['fps']) for r in selected), max(float(r['fps']) for r in selected)],
        'cores_range': [min(r['cores'] for r in selected), max(r['cores'] for r in selected)],
        'last_threads': selected[-1]['threads'],
    }
matrix = (work/'captures/slot-0-arm64.bin').read_bytes()
assert hashlib.sha256(matrix).hexdigest() == '810578ecc3cd0cb781f679ad8f3b231bdd61aabe12acb4629f7865d616773ada'
report = {
    'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
    'last_policy': re.findall(r'^\[PERF19\].*$', log, re.M)[-1],
    'actual_matrix_matches_tested_patch': True, 'groups': groups,
    'limitations': 'Scene boundaries inferred. 10 ms sampler active, no controlled old/new scene or clock comparison. Native present time is not GPU time.',
}
(work/'perf19-analysis.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
