"""Compare measured cold/warm windows without prorating JIT or adding nested timers."""
import argparse
from collections import defaultdict
import importlib.util
import json
import math
from pathlib import Path
import re

spec = importlib.util.spec_from_file_location('short_trace', Path(__file__).with_name('analyze-fextendo-short-trace.py'))
trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace)


def fields(line):
    return {k: int(v) for k, v in re.findall(r'\b(\w+)=(\d+)\b', line)}


def analyze(path, ranges):
    observed = trace.analyze(path)
    origin = observed['play_origin_tick']
    if origin is None or not observed['short_trace']['time_correlation_available']:
        raise ValueError('A unique, consistent Play clock is required')
    lines = path.read_text(errors='replace').splitlines()
    batches, gaps, names = [], [], {}
    batch = None
    for number, line in enumerate(lines, 1):
        f = fields(line)
        if line.startswith('[PROGRESS] '):
            if batch:
                batches.append(batch)
            batch = {'line': number, 'progress': f, 'warm': {}, 'threads': []}
        if line.startswith('[FEX3-DXVKCORE] tid='):
            name = re.search(r'\bname=(\S+)', line)
            if name:
                names[f['tid']] = name[1]
        if line.startswith('[FEX3-GAP] tick='):
            gaps.append({'line': number, **f,
                         'end_s': (f['tick'] - origin) / 19200000,
                         'start_s': (f['tick'] - origin) / 19200000 - f['end_gap_us'] / 1000000})
        if not batch:
            continue
        if line.startswith('[FEX3-SHORT-STATS] tick='):
            batch['anchor_s'] = (f['tick'] - origin) / 19200000
            batch['anchor_line'] = number
        if line.startswith('[FEX3-WARM] ') and ' n=' in line:
            name = line.split()[1]
            batch['warm'][name] = {'line': number, **f}
        if line.startswith('[THREADS] '):
            batch['thread_line'] = number
            batch['threads'] = [{'tid': int(tid), 'kind': kind, 'core': int(core), 'load': float(load)}
                for tid, kind, core, load in re.findall(r'(\d+)([ws])@(\d+) (\d+\.\d+)%', line)]
        if line.startswith('[FEX3-PACE] entry_gap '):
            bins = [int(v) for v in line.split('bins=')[1].split()[0].split(',')]
            if len(bins) != 9 or sum(bins) != f['n']:
                raise ValueError('Invalid frame histogram on line ' + str(number))
            batch['frame'] = {'line': number, **f, 'bins': bins}
    if batch:
        batches.append(batch)

    intervals = []
    for before, after in zip(batches, batches[1:]):
        if ('anchor_s' not in before or 'anchor_s' not in after or 'frame' not in after
                or after['anchor_s'] <= before['anchor_s']):
            continue
        keys = ('reads', 'read_ms', 'sd_reads', 'sd_ms', 'frames', 'syscalls')
        if any(k not in before['progress'] or k not in after['progress'] for k in keys):
            continue
        delta = {k: after['progress'][k] - before['progress'][k] for k in keys}
        if any(v < 0 for v in delta.values()):
            raise ValueError('Counter reset/wrap: do not interpret this batch as a delta')
        cores = defaultdict(float)
        for thread in after['threads']:
            cores[thread['core']] += thread['load']
        intervals.append({'approx_start_s': before['anchor_s'], 'approx_end_s': after['anchor_s'],
            'progress_lines': [before['line'], after['line']], 'anchor_line': after['anchor_line'],
            'delta': delta, 'frame': after['frame'], 'warm': after['warm'],
            'displayed_thread_core_subtotals': dict(cores), 'threads': after['threads']})

    windows = observed['short_trace']['compile_windows']
    summaries = []
    for start, end in ranges:
        if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end:
            raise ValueError('Ranges must have 0 <= start < end')
        selected = [w for w in windows if w['begin_tplus_ms'] >= start * 1000 and w['end_tplus_ms'] <= end * 1000]
        per_thread = {}
        for w in selected:
            t = per_thread.setdefault(w['tid'], {'name': names.get(w['tid']), 'windows': 0,
                'calls': 0, 'wall_us': 0, 'peak_us': 0, 'lines': []})
            t['windows'] += 1
            t['calls'] += w['calls']
            t['wall_us'] += w['total_us']
            t['peak_us'] = max(t['peak_us'], w['peak_us'])
            t['lines'].append(w['line'])
        chosen = [b for b in intervals if b['approx_start_s'] >= start and b['approx_end_s'] <= end]
        frame_bins = [sum(b['frame']['bins'][i] for b in chosen) for i in range(9)]
        warm = {}
        for name in ('graphics_pipeline', 'compute_pipeline', 'driver_cache_get'):
            stages = [b['warm'][name] for b in chosen if name in b['warm']]
            warm[name] = {'batches': len(stages), 'calls': sum(s['n'] for s in stages),
                          'wall_us': sum(s['total_us'] for s in stages)}
        selected_gaps = [g for g in gaps if g['start_s'] >= start and g['end_s'] <= end]
        summaries.append({'requested_range_s': [start, end],
            'jit_full_windows_only': {'windows': len(selected), 'calls': sum(w['calls'] for w in selected),
                'wall_us': sum(w['total_us'] for w in selected), 'per_thread': per_thread},
            'full_report_batches': chosen, 'warm_stages_separate': warm,
            'frame_histogram': {'observations': sum(frame_bins), 'bins': frame_bins,
                'gt_33334_us': sum(frame_bins[4:]), 'gt_50000_us': sum(frame_bins[5:])},
            'recorded_gaps': {'count': len(selected_gaps), 'max_us': max((g['end_gap_us'] for g in selected_gaps), default=None),
                'largest': sorted(selected_gaps, key=lambda g: g['end_gap_us'], reverse=True)[:5]}})
    return {'sha256': observed['sha256'], 'bytes': observed['bytes'], 'builds': observed['builds'],
        'play_origin_tick': origin, 'timestamp_requested': observed['timestamp_requested'],
        'bounded_trace_summary': observed['summary'], 'ranges': summaries, 'all_report_intervals': intervals,
        'last_trace_stats': observed['short_trace']['last_cumulative_stats'],
        'limits': ['JIT totals include only fully contained completed-call windows; boundary windows and in-flight work are excluded.',
            'JIT/pipeline/cache timers are wall time, can overlap/nest, and are never summed into freeze duration or CPU utilization.',
            'Progress/warm/frame batch anchors use the nearby flusher SHORT-STATS tick; they are approximate, not per-I/O event timestamps.',
            'Frame histograms have different collection boundaries from JIT windows; equal requested ranges do not imply equal scenes.',
            'Individual gap records are bounded; histogram counts and individual end-gap records use different boundaries.',
            'Displayed thread core subtotals omit unlisted threads and OS work and do not measure instantaneous physical-core saturation.',
            'Read counters do not measure SD writes, flush time, or log-mutex waits. No causal conclusion about writes follows from them.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--range', action='append', nargs=2, type=float, dest='ranges', metavar=('START_SECONDS', 'END_SECONDS'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.log.resolve():
        parser.error('Output must not overwrite the capture')
    report = analyze(args.log, args.ranges or [(100, 150), (350, 400)])
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'sha256': report['sha256'], 'output': str(args.output),
        'ranges': [{'seconds': r['requested_range_s'],
                    'jit': {k: v for k, v in r['jit_full_windows_only'].items() if k != 'per_thread'},
                    'frame': r['frame_histogram'], 'warm': r['warm_stages_separate']} for r in report['ranges']]}, indent=2))


if __name__ == '__main__':
    main()
