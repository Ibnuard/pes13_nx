"""Preserve and summarize the two supplied PERF16 renderer/profile logs."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('C:/Users/Administrator/Documents/PES13LOGS')
OUT = ROOT / 'local/perf16/results'
OUT.mkdir(parents=True, exist_ok=True)


def read_run(filename):
    raw = (SOURCE / filename).read_bytes()
    log = raw.decode('utf-8', errors='replace')
    assert '[BUILD] pes13-nx-0.2.0-perf15-guest-exceptions' in log
    archived = OUT / filename
    if archived.exists() and archived.read_bytes() != raw:
        raise ValueError(f'Refusing to replace a different archived log: {archived}')
    archived.write_bytes(raw)
    rows = []
    for line in log.splitlines():
        if line.startswith('[PERF8] '):
            values = dict(re.findall(r'(\w+)=([^ ]+)', line))
            rows.append({k: float(values[k]) for k in
                         ('uptime_s', 'interval_ms', 'presents', 'fps')})
            rows[-1]['samples'] = {}
        elif line.startswith('[THREADS] ') and rows:
            rows[-1]['cores'] = float(re.search(r'use ([\d.]+) cores', line)[1])
            rows[-1]['cpu_percent_per_thread'] = {
                tid: float(pct) for tid, pct in
                re.findall(r'(\d+[ws])@-?\d+ ([\d.]+)%', line)}
        elif line.startswith('[PROF] ') and rows:
            match = re.match(r'\[PROF\] (\d+[ws]) samples=(\d+) missed=(\d+) '
                             r'x86=([\d.]+)% pe=([\d.]+)% native=([\d.]+)% '
                             r'svc=([\d.]+)%', line)
            if match:
                tid, n, missed, *percentages = match.groups()
                rows[-1]['samples'][tid] = {
                    'count': int(n), 'missed': int(missed),
                    **dict(zip(('x86', 'pe', 'native', 'svc'), map(float, percentages))),
                }
            else:
                match = re.match(r'\[PROF\] (\d+[ws]) x86 by module: (.+)', line)
                if match and match[1] in rows[-1]['samples']:
                    rows[-1]['samples'][match[1]]['x86_modules_percent'] = {
                        name: float(pct) for name, pct in
                        re.findall(r'(\S+) ([\d.]+)%', match[2])}
    return {
        'input': filename, 'sha256': hashlib.sha256(raw).hexdigest(),
        'bytes': len(raw), 'intervals': rows,
        'renderer_evidence': [line for line in log.splitlines() if
                              'Direct3D 9 ' in line or 'DXVK: v' in line or
                              'Setting multithreaded command stream' in line],
        'gl_progress': [line for line in log.splitlines() if
                        line.startswith('[PROGRESS]') and 'gl_frames=' in line],
        'critical_section_timeouts': [line for line in log.splitlines() if
                                      'RtlpWaitForCriticalSection' in line],
    }


dxvk = read_run('pes13-nx-test-1.log')
wine = read_run('pes13-nx-test-wined3d.log')
early = [row for row in dxvk['intervals'] if 100 <= row['uptime_s'] <= 120]
late = [row for row in wine['intervals'] if 120 <= row['uptime_s'] <= 170]
assert len(early) == 3 and len(late) == 6
assert all('4w' in row['samples'] for row in early)
summary = {
    'dxvk_intervals_ending_100_120_main_x86_percent':
        [row['samples']['4w']['x86'] for row in early],
    'dxvk_intervals_ending_100_120_main_core_percent':
        [row['cpu_percent_per_thread']['4w'] for row in early],
    'dxvk_last_interval': dxvk['intervals'][-1],
    'wined3d_intervals_ending_120_170_cores': [row['cores'] for row in late],
    'wined3d_fps': None,
    'limitations': [
        'Scene times are inferred from the reported sequence, not synchronized markers.',
        'The DXVK sampler alters timing; sampled FPS is not a production benchmark.',
        'Samples include blocked time, and select only four previously busy threads.',
        'Dropped address buckets undercount per-module samples, not the x86 category.',
        'WineD3D PERF8 presents are Vulkan-only; zero does not mean zero OpenGL FPS.',
        'The WineD3D GL aggregate does not isolate a match interval.',
    ],
}
(OUT / 'analysis.json').write_text(
    json.dumps({'summary': summary, 'dxvk': dxvk, 'wined3d': wine}, indent=2) + '\n',
    encoding='utf-8')
print(json.dumps({
    'sources': [{key: run[key] for key in ('input', 'bytes', 'sha256')}
                for run in (dxvk, wine)],
    'summary': summary,
}, indent=2))
