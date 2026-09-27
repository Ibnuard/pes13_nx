"""Report present timing and preset evidence without equating presents to game speed."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def analyze(data):
    text = data.decode(errors='replace')
    windows = []
    present_observations = []
    progress_seconds = None
    threads = None
    threads_source_line = threads_progress_seconds = None
    current = None
    for source_line, line in enumerate(text.splitlines(), 1):
        present = re.match(
            r'\[NXVK\] present (\d+): result (-?\d+), swapchain (\d+)x(\d+), '
            r'hwnd (0x[0-9a-fA-F]+) client \((-?\d+),(-?\d+)\)-\((-?\d+),(-?\d+)\)', line)
        if present:
            present_observations.append({
                'source_line': source_line, 'present': int(present[1]),
                'result': int(present[2]), 'swapchain': [int(present[3]), int(present[4])],
                'hwnd': present[5], 'client_rect': [int(present[i]) for i in range(6, 10)],
            })
        if match := re.match(r'\[PROGRESS\] (\d+)s ', line):
            progress_seconds = int(match[1])
        if line.startswith('[THREADS] '):
            threads = line
            threads_source_line = source_line
            threads_progress_seconds = progress_seconds
        if line.startswith('[FEX3-PACE] elapsed_ms='):
            row: dict[str, Any] = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)}
            row['host_presents_per_second'] = (
                round(row['ok'] * 1000 / row['window_ms'], 3) if row['window_ms'] else None)
            row['source_line'] = source_line
            row['progress_seconds'] = progress_seconds
            row['threads'] = threads
            row['threads_source_line'] = threads_source_line
            row['threads_progress_seconds'] = threads_progress_seconds
            row['stages'] = {}
            row['delays'] = []
            windows.append(row)
            current = row
        elif current is not None:
            if match := re.match(r'\[FEX3-(?:PACE|PIPE)\] (\w+) n=', line):
                stage: dict[str, Any] = {
                    k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)
                    if k != 'bins'
                }
                stage['source_line'] = source_line
                bins = re.search(r'\bbins=([0-9,]+)', line)
                if bins:
                    stage['bins'] = [int(v) for v in bins[1].split(',')]
                current['stages'][match[1]] = stage
            elif line.startswith('[FEX3-DELAY] tid='):
                current['delays'].append({k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)})
    last = [row for row in windows
            if row['window_ms'] and row['elapsed_ms'] > windows[-1]['elapsed_ms'] - 60000]
    return {
        'input_sha256': hashlib.sha256(data).hexdigest(),
        'input_bytes': len(data),
        'build': re.findall(r'^\[BUILD\] (.+)$', text, re.M),
        'presets': re.findall(r'^\[FEX3-PRESET\] (.+)$', text, re.M),
        'dxvk_max_frame_rate': re.findall(r'd3d9.maxFrameRate = (-?\d+)', text),
        'dxvk_max_frame_latency': re.findall(r'd3d9.maxFrameLatency = (\d+)', text),
        'exception_lines': [s for s in text.splitlines() if s.startswith('[EXC]')],
        'exit_lines': [s for s in text.splitlines() if s.startswith('[EXIT]')],
        'last_60s': {
            'windows': len(last),
            'window_ms': sum(row['window_ms'] for row in last),
            'presents': sum(row['ok'] for row in last),
            'weighted_presents_per_second': round(sum(row['ok'] for row in last) * 1000 /
                sum(row['window_ms'] for row in last), 3) if last else None,
        },
        'windows': windows,
        'present_observations': present_observations,
        'limitations': [
            'Presents are host API calls, not unique displayed frames or simulation ticks.',
            'There is no in-game scoreboard measurement or OC-change marker in this log.',
            'elapsed_ms is relative to the first diagnostic report, not application launch.',
            'A preset comparison alone cannot locate the instruction or race causing accelerated simulation.',
            'Native timing is CPU wall time, not GPU execution time; parallel stages are not additive.',
            'Lower presentation throughput alone is not evidence that game timing was fixed.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.log.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'windows'}, indent=2))
    print('elapsed_ms, host_presents_per_second')
    for row in report['windows']:
        if row['window_ms']:
            print(row['elapsed_ms'], row['host_presents_per_second'])


if __name__ == '__main__':
    main()
