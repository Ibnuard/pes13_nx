"""Read aggregate logs without treating JIT/PROGRESS clocks as time since Play."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re


def fields(line):
    return {key: int(value) for key, value in re.findall(r'\b(\w+)=(\d+)\b', line)}


def interval(start, end):
    if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end:
        raise ValueError('Expected finite 0 <= start < end')


def analyze(path, play_range=(110, 140), jit_ranges=((100, 151), (250, 301))):
    interval(*play_range)
    for bounds in jit_ranges:
        interval(*bounds)
    data = path.read_bytes()
    lines = data.decode(errors='replace').splitlines()
    origins = [fields(line) for line in lines if line.startswith('[FEXTENDO-TIME] ')]
    if len(origins) != 1 or 'origin_tick' not in origins[0]:
        raise ValueError('Expected exactly one Play origin; do not merge sessions')
    if any(line.startswith('[FEXTENDO-TIME] ') and
           'units=19200000_ticks_per_second' not in line for line in lines):
        raise ValueError('Unknown Play counter frequency')
    origin = origins[0]['origin_tick']
    batches, jit, gaps, config = [], [], [], {}
    batch = None
    for number, line in enumerate(lines, 1):
        f = fields(line)
        for prefix, key in (('[FEX3-SHORT] ', 'short_trace'), ('[FEX3-HOT] ', 'sampler'),
                            ('[FEX3-FASTAPI] ', 'fast_api')):
            if line.startswith(prefix) and 'enabled' in f:
                config[key] = f['enabled']
        if line.startswith('[FEX3-DISKCACHE] ') and 'requested' in f:
            config['disk_cache_requested'] = f['requested']
        if line.startswith('[FEX3-JIT] phase=compile_code '):
            required = ('uptime_ms', 'calls', 'total_us', 'over20ms', 'over50ms')
            if not all(key in f for key in required):
                raise ValueError(f'Incomplete JIT counter at line {number}')
            if jit and (f['uptime_ms'] <= jit[-1]['uptime_ms'] or
                        any(f[k] < jit[-1][k] for k in required[1:])):
                raise ValueError(f'JIT counter reset or reordered report at line {number}')
            jit.append({'line': number, **f})
        if line.startswith('[PROGRESS] '):
            match = re.match(r'\[PROGRESS\] (\d+)s ', line)
            if not match:
                raise ValueError(f'Invalid PROGRESS time at line {number}')
            batch = {'line': number, 'runtime_elapsed_s': int(match[1]), 'counters': f,
                     'warm': {}, 'gaps': [], 'gap_dropped': None}
            if batches:
                keys = ('reads', 'read_ms', 'sd_reads', 'sd_ms', 'frames')
                if all(k in f and k in batches[-1]['counters'] for k in keys):
                    delta = {k: f[k] - batches[-1]['counters'][k] for k in keys}
                    if min(delta.values()) < 0:
                        raise ValueError(f'PROGRESS counter reset at line {number}')
                    batch['delta'] = delta
            batches.append(batch)
        if line.startswith('[FEX3-GAP] tick='):
            end = (f['tick'] - origin) / 19200000
            row = {'line': number, **f, 'play_end_s': end,
                   'play_start_s': end - f['end_gap_us'] / 1000000}
            gaps.append(row)
            if batch is not None:
                batch['gaps'].append(row)
        if batch is None:
            continue
        if line.startswith('[FEX3-GAP] recorded='):
            batch['gap_dropped'] = f['dropped']
        if line.startswith('[FEX3-PACE] entry_gap '):
            bins = [int(v) for v in line.split('bins=')[1].split()[0].split(',')]
            if len(bins) != 9 or sum(bins) != f['n']:
                raise ValueError(f'Invalid frame histogram at line {number}')
            batch['frame'] = {'line': number, **f, 'bins': bins,
                              'gt33334_us': sum(bins[4:]), 'gt50000_us': sum(bins[5:])}
        if line.startswith('[FEX3-WARM] ') and 'n' in f:
            batch['warm'][line.split()[1]] = {'line': number, **f}

    comparisons = []
    for start, end in jit_ranges:
        selected = [r for r in jit if start * 1000 <= r['uptime_ms'] <= end * 1000]
        comparison = {'requested_jit_uptime_s': [start, end], 'available': len(selected) >= 2}
        if len(selected) >= 2:
            before, after = selected[0], selected[-1]
            comparison.update({'lines': [before['line'], after['line']],
                'actual_jit_uptime_ms': [before['uptime_ms'], after['uptime_ms']],
                'duration_ms': after['uptime_ms'] - before['uptime_ms'],
                'delta': {k: after[k] - before[k] for k in ('calls', 'total_us', 'over20ms', 'over50ms')}})
        comparisons.append(comparison)
    chosen = [g for g in gaps if g['play_end_s'] >= play_range[0] and g['play_start_s'] <= play_range[1]]
    chosen_lines = {g['line'] for g in chosen}
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
        'play_origin_tick': origin, 'config': config, 'requested_play_range_s': list(play_range),
        'recorded_gaps_overlapping_play_range': chosen, 'jit_comparisons': comparisons,
        'batches_containing_selected_gaps': [b for b in batches if any(g['line'] in chosen_lines for g in b['gaps'])],
        'capture_gap_dropped': sum(b['gap_dropped'] or 0 for b in batches),
        'capture_gap_reports_without_drop_counter': sum(b['gap_dropped'] is None for b in batches),
        'last_compile_counter': jit[-1] if jit else None,
        'limits': [
            'GAP timestamps use the Play clock. JIT uptime and PROGRESS elapsed time have separate origins.',
            'Batches contain asynchronous observations; a selected gap does not timestamp every counter in its batch.',
            'JIT deltas count completed calls across threads, including races, not unique blocks or pure CPU time.',
            'Calls completing in a JIT interval can have started earlier; in-flight work is absent. No prorating is used.',
            'CompileCode is nested within dispatch_compile. Do not add the two timers.',
            'Frame histograms measure Present entry gaps; GAP records measure completion gaps. Neither proves simulation progress.',
            'Pipeline/submit measurements include scheduling and waits, not just shader compilation or GPU execution.',
            'SD counters cover reads, not all writes/flushes. A cache request flag is not proof of cache hits.',
            'No observed gap does not prove no stutter: the observer has a threshold, bounded capacity and no simulation marker.'
        ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--play-range', nargs=2, type=float, default=[110, 140])
    parser.add_argument('--jit-range', nargs=2, type=float, action='append')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.log.resolve():
        parser.error('Output must not overwrite the capture')
    result = analyze(args.log, args.play_range, args.jit_range or [(100, 151), (250, 301)])
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: result[k] for k in ('sha256', 'config', 'jit_comparisons')}))


if __name__ == '__main__':
    main()
