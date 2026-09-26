"""Summarize physical present timings without treating them as simulation FPS."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/kickoff-pacing'
log = (WORK / 'before/fex-runtime.log').read_bytes()
windows = []
for line in log.decode(errors='replace').splitlines():
    if line.startswith('[FEX3-PACE] elapsed_ms='):
        row = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)}
        row['host_presents_per_second'] = round(row['ok'] * 1000 / row['window_ms'], 2) if row['window_ms'] else None
        row['stages'] = {}
        windows.append(row)
    elif line.startswith('[FEX3-PACE] ') and 'bins=' in line:
        name = line.split()[1]
        row = {k: int(v) for k, v in re.findall(r'(n|avg_us|peak_since_launch_us)=(\d+)', line)}
        row['bins'] = list(map(int, line.split('bins=')[1].split(',')))
        windows[-1]['stages'][name] = row
assert len(windows) > 10 and all(len(w['stages']) == 4 for w in windows)
report = {
    'input_sha256': hashlib.sha256(log).hexdigest(), 'input_bytes': len(log),
    'build': 'pes13-fex3-frame-pacing',
    'user_report': {'kickoff': 'after about two minutes', 'oc_to_stock': 'around five minutes',
                    'symptom': 'pauses followed by apparent double-speed/catch-up, especially kick-off'},
    'windows': windows,
    'limitations': [
        'elapsed_ms starts at the first flusher report, roughly ten seconds after flusher start.',
        'The supplied present series ends at elapsed_ms=241044; no logged clock-change marker isolates the approximate five-minute OC change.',
        'Presents are native API calls, not unique displayed images or game simulation ticks.',
        'Driver-present CPU wall time does not measure GPU execution or prior acquire/fence waits.',
        'Peaks are cumulative since launch; scene labels and clock changes are approximate.',
    ],
    'next_change': 'DXVK maxFrameLatency=1; passive native acquire/submit/fence/semaphore and shared-clock-gap observers',
    'hardware_fix_verified': False,
}
(WORK / 'analysis.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'windows'}, indent=2))
print('elapsed_ms  presents/s  gap_us  native_us  driver_us')
for w in windows:
    if w['window_ms']:
        print(w['elapsed_ms'], w['host_presents_per_second'],
              *[w['stages'][k]['avg_us'] for k in ('entry_gap', 'native_total', 'driver_call')])
