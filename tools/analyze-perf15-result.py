"""Archive and summarize the user-confirmed stable PERF15 3D run."""
from pathlib import Path
import hashlib, json, re

p = Path(__file__).resolve().parents[1]
work = p/'local/perf16'
work.mkdir(parents=True, exist_ok=True)
source = Path('C:/Users/Administrator/Documents/PES13LOGS/pes13-nx.log')
raw = source.read_bytes()
log = raw.decode('utf-8', errors='replace')
assert '[BUILD] pes13-nx-0.2.0-perf15-guest-exceptions' in log
(work/'perf15-stable-3d-slow.log').write_bytes(raw)
rows = []
for line in log.splitlines():
    if line.startswith('[PERF8] '):
        values = dict(re.findall(r'(\w+)=([^ ]+)', line))
        rows.append({k: float(values[k]) for k in
            ('uptime_s', 'interval_ms', 'presents', 'fps', 'avg_frame_ms', 'host_present_ms_per_call')})
    elif line.startswith('[THREADS] ') and rows:
        cores = re.search(r'use ([0-9.]+) cores', line)
        rows[-1]['cores'] = float(cores[1]) if cores else None
        rows[-1]['threads'] = {m[0]+m[1]:float(m[3]) for m in
            re.findall(r'(\d+)([ws])@(-?\d+) ([\d.]+)%', line)}

def stats(a, b):
    group = [r for r in rows if a <= r['uptime_s'] <= b]
    assert group
    frames, ms = sum(r['presents'] for r in group), sum(r['interval_ms'] for r in group)
    return {
        'intervals_ending_s': [r['uptime_s'] for r in group],
        'weighted_fps': frames*1000/ms, 'frames':frames, 'wall_ms':ms,
        'fps_min':min(r['fps'] for r in group), 'fps_max':max(r['fps'] for r in group),
        'cores_min':min(r['cores'] for r in group), 'cores_max':max(r['cores'] for r in group),
        'host_present_ms_min':min(r['host_present_ms_per_call'] for r in group),
        'host_present_ms_max':max(r['host_present_ms_per_call'] for r in group),
    }
result = {
    'input_sha256':hashlib.sha256(raw).hexdigest(), 'input_bytes':len(raw),
    'build':'pes13-nx-0.2.0-perf15-guest-exceptions',
    'menu_candidate':stats(40,60), 'late_match_candidate':stats(140,190),
    'scene_assignment':'Inferred from user sequence, not synchronized screenshot timestamps',
    'new_exception_or_exit_lines':[l for l in log.splitlines() if
        l.startswith(('[EXC]', '[EXIT]', '[BOX64] status='))],
    'intervals':rows,
}
(work/'analysis.json').write_text(json.dumps(result, indent=2))
print(json.dumps({k:v for k,v in result.items() if k != 'intervals'}, indent=2))
