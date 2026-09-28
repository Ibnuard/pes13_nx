"""Read FEX3 timing histograms; never equate presents with unique/simulation FPS."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def fields(line):
    result = {}
    for key, value in re.findall(r'(\w+)=([0-9]+(?:,[0-9]+)*)(?=\s|$)', line):
        result[key] = list(map(int, value.split(','))) if ',' in value else int(value)
    return result


def analyze(path):
    data = path.read_bytes()
    windows, progress, events, cache, jit = [], [], [], [], []
    for number, line in enumerate(data.decode(errors='replace').splitlines(), 1):
        if line.startswith('[FEX3-PACE] elapsed_ms='):
            windows.append(dict(line=number, **fields(line), stages={}))
        elif line.startswith(('[FEX3-PACE] ', '[FEX3-PIPE] ')) and ' bins=' in line and windows:
            stage = line.split()[1]
            values = dict(line=number, **fields(line))
            if len(values['bins']) != 9 or sum(values['bins']) != values['n']:
                raise ValueError(f'Invalid histogram at line {number}')
            windows[-1]['stages'][stage] = values
        elif line.startswith('[PROGRESS] '):
            progress.append(dict(line=number, elapsed_label=line.split()[1], **fields(line)))
        elif line.startswith('[FEX3-EVENT] '):
            events.append(dict(line=number, **fields(line)))
        elif line.startswith('[FEX3-JIT] phase='):
            jit.append(dict(line=number, phase=line.split()[1].split('=', 1)[1], **fields(line)))
        elif 'Found cache file:' in line or 'Cache: ' in line:
            cache.append(dict(line=number, text=line))
    complete = [w for w in windows if w.get('window_ms') and 'entry_gap' in w['stages']]
    tail = complete[-3:]
    summary = []
    for w in tail:
        gap = w['stages']['entry_gap']
        summary.append({
            'elapsed_ms': w['elapsed_ms'], 'window_ms': w['window_ms'],
            'present_intervals': gap['n'], 'entry_mean_us': gap['avg_us'],
            'gap_over_50000_through_100000_us': gap['bins'][5],
            'gap_over_100000_us': sum(gap['bins'][6:]),
            'native_present_mean_us': w['stages']['native_total']['avg_us'],
            'driver_present_mean_us': w['stages']['driver_call']['avg_us'],
        })
    return {
        'input': str(path.resolve()), 'bytes': len(data),
        'sha256': hashlib.sha256(data).hexdigest(),
        'histogram_upper_inclusive_us': [8334, 16667, 20000, 33334, 50000, 100000, 250000, 500000, None],
        'limits': ['Presents are not unique rendered frames or simulation FPS.',
                   'Peaks are cumulative since launch, not per-window maxima.',
                   'Histograms cannot locate individual pauses or prove periodicity.',
                   'Completed Vulkan CPU call times include scheduling and are not GPU timestamps.',
                   'elapsed_ms, elapsed_s and JIT uptime_ms have different origins; align by line order.',
                   'JIT dispatch_compile includes cache hits; it is not a count of actual translations.',
                   'JIT cumulative completed-call durations overlap across stages and threads.'],
        'last_three_complete_windows': summary, 'windows': windows,
        'progress': progress, 'events': events, 'cache': cache, 'jit': jit,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.log), indent=2))
