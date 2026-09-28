"""Match FEXTendo video T+ times to recorded gaps; never infer missing Play clocks."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

TICKS_PER_MS = 19200
V2_BUILD = 'pes13-fextendo-v2-budget'


def parse_time(value):
    """Accept seconds, MM:SS.d or HH:MM:SS.d, with optional T+ prefix."""
    value = value.removeprefix('T+').strip()
    try:
        parts = value.split(':')
        if not 1 <= len(parts) <= 3:
            raise ValueError
        if any(not p.isdigit() for p in parts[:-1]):
            raise ValueError
        numbers = [float(p) for p in parts]
        if any(not math.isfinite(n) or n < 0 for n in numbers):
            raise ValueError
        if len(numbers) > 1 and any(n >= 60 for n in numbers[1:]):
            raise ValueError
        return sum(n * 60 ** i for i, n in enumerate(reversed(numbers))) * 1000
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Use seconds, MM:SS.d, or HH:MM:SS.d (nonnegative).') from exc


def analyze(path, at_ms=None, radius_ms=2000):
    if not math.isfinite(radius_ms) or radius_ms < 0:
        raise ValueError('Window radius must be finite and nonnegative')
    if at_ms is not None and (not math.isfinite(at_ms) or at_ms < 0):
        raise ValueError('Event time must be finite and nonnegative')
    raw = path.read_bytes()
    gaps, queries, origins, budget, builds, snapshots = [], [], [], [], [], []
    notices, malformed, seen, duplicates = [], [], set(), []
    observer = None
    overlay = 'not_reported'
    query_calls = query_dropped = gap_dropped = 0
    query_batches = 0
    for number, line in enumerate(raw.decode(errors='replace').splitlines(), 1):
        fields = {k: int(v) for k, v in re.findall(r'\b(\w+)=(\d+)\b', line)}
        build = re.search(r'\[BUILD\]\s+(\S+)|\[PES13-VK\] build=(\S+)', line)
        if build:
            builds.append(build[1] or build[2])
        if '[FEXTENDO-TIME] origin_tick=' in line:
            if {'origin_tick', 'enabled'} <= fields.keys() and fields['origin_tick'] > 0:
                origins.append({'line': number, **fields})
            else:
                malformed.append(number)
        if '[FEXTENDO-TIME] elapsed_ms=' in line:
            if {'elapsed_ms', 'tick'} <= fields.keys():
                snapshots.append({'line': number, **fields})
            else:
                malformed.append(number)
        if '[FEXTENDO-TIME] overlay ready' in line:
            overlay = 'ready'
        elif '[FEXTENDO-TIME] overlay unavailable' in line or '[FEXTENDO-TIME] overlay worker unavailable' in line:
            overlay = 'unavailable'
        if '[FEX3-MEMBUDGET]' in line and 'client_extension' in fields:
            budget.append(fields['client_extension'])
        if '[FEX3-MEMQUERY] v1' in line:
            observer = fields.get('enabled')
        if '[FEX3-MEMQUERY] calls=' in line:
            if {'calls', 'dropped'} <= fields.keys():
                query_batches += 1
                query_calls += fields['calls']
                query_dropped += fields['dropped']
            else:
                malformed.append(number)
        if '[FEX3-GAP] recorded=' in line:
            if 'dropped' in fields:
                gap_dropped += fields['dropped']
            else:
                malformed.append(number)
        if '[FEX3-GAP] tick=' in line:
            kind, rows = 'gap', gaps
            required = {'tick', 'handle', 'end_gap_us', 'cpu_valid', 'thread_cpu_us'}
        elif '[FEX3-MEMQUERY] begin_tick=' in line:
            kind, rows = 'query', queries
            required = {'begin_tick', 'end_tick', 'handle', 'wall_us', 'cpu_valid', 'thread_cpu_us'}
        else:
            continue
        if not required <= fields.keys() or fields.get('cpu_valid') not in (0, 1):
            malformed.append(number)
            continue
        if kind == 'query' and fields['end_tick'] < fields['begin_tick']:
            malformed.append(number)
            continue
        key = (kind, tuple(sorted(fields.items())))
        if key in seen:
            duplicates.append(number)
            continue
        seen.add(key)
        rows.append({'line': number, **fields})

    origin = origins[0]['origin_tick'] if len(origins) == 1 else None
    if not origins:
        notices.append('No Play origin: T+ cannot be reconstructed from log order, JIT uptime or EVENT elapsed_s.')
    elif len(origins) > 1:
        notices.append('Multiple Play origins: split captures into individual runs before time correlation.')
    if malformed:
        notices.append('Incomplete or invalid diagnostic rows skipped; see malformed_lines.')
    if duplicates:
        notices.append('Duplicate diagnostic samples ignored; batch summaries may also contain repeated data.')
    if len(set(builds)) > 1:
        notices.append('Multiple build markers: this may be a concatenated capture.')
        origin = None
    if len(set(budget)) > 1:
        notices.append('Conflicting budget switches: split captures into individual runs.')
    if origin is not None:
        for snapshot in snapshots:
            actual_ms = (snapshot['tick'] - origin) / TICKS_PER_MS
            if abs(actual_ms - snapshot['elapsed_ms']) > 1:
                notices.append('Timestamp snapshot disagrees with Play origin; T+ correlation disabled.')
                origin = None
                break

    def elapsed(tick):
        return round((tick - origin) / TICKS_PER_MS, 3) if origin is not None else None

    rows = []
    for gap in sorted(gaps, key=lambda r: r['tick']):
        # Integer fifth-ticks avoid cancellation at large system uptimes.
        # The recorded gap is truncated to microseconds: allow <1us tolerance.
        start5 = gap['tick'] * 5 - gap['end_gap_us'] * 96
        contained = [q for q in queries if q['handle'] == gap['handle']
                     and q['begin_tick'] * 5 >= start5 - 96 and q['end_tick'] <= gap['tick']]
        all_cpu_valid = bool(contained) and gap['cpu_valid'] and all(q['cpu_valid'] for q in contained)
        query_cpu = sum(q['thread_cpu_us'] for q in contained) if all_cpu_valid else None
        ratio = query_cpu / gap['thread_cpu_us'] if all_cpu_valid and gap['thread_cpu_us'] else None
        rows.append({**gap, 'start_elapsed_ms': elapsed(start5 / 5), 'end_elapsed_ms': elapsed(gap['tick']),
                     'query_lines': [q['line'] for q in contained],
                     'query_wall_us': sum(q['wall_us'] for q in contained),
                     'query_cpu_us': query_cpu, 'query_to_gap_cpu_ratio': ratio})
    ratios = [r['query_to_gap_cpu_ratio'] for r in rows if r['query_to_gap_cpu_ratio'] is not None]
    summary = {'recorded_gaps_over_50ms': len(gaps), 'recorded_slow_queries': len(queries),
               'matched_gaps': sum(bool(r['query_lines']) for r in rows),
               'median_matched_query_to_gap_cpu_ratio': statistics.median(ratios) if ratios else None,
               'max_recorded_gap_ms': max((r['end_gap_us'] / 1000 for r in gaps), default=None),
               'query_calls_in_flushed_batches': query_calls if query_batches else None,
               'query_batches': query_batches, 'reported_dropped_queries': query_dropped,
               'reported_dropped_gaps': gap_dropped}

    def window(start, end):
        if origin is None:
            return {'available': False, 'reason': 'No unique, consistent Play origin.'}
        return {'available': True, 'start_ms': start, 'end_ms': end,
                'gaps': [r for r in rows if r['end_elapsed_ms'] >= start and r['start_elapsed_ms'] <= end],
                'queries': [{**q, 'start_elapsed_ms': elapsed(q['begin_tick']), 'end_elapsed_ms': elapsed(q['end_tick'])}
                            for q in sorted(queries, key=lambda r: r['begin_tick'])
                            if elapsed(q['end_tick']) >= start and elapsed(q['begin_tick']) <= end]}

    result = {'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
              'builds': sorted(set(builds)), 'is_v2': set(builds) == {V2_BUILD},
              'budget_client_extension': budget[0] if len(set(budget)) == 1 else None,
              'memory_observer_enabled': observer, 'overlay': overlay,
              'timestamp_requested': origins[0]['enabled'] if len(origins) == 1 else None,
              'play_origin_tick': origin, 'summary': summary,
              'first_120_seconds': window(0, 120000),
              'largest_recorded_gaps': sorted(rows, key=lambda r: r['end_gap_us'], reverse=True)[:10],
              'malformed_lines': malformed, 'duplicate_sample_lines': duplicates, 'notices': notices,
              'limits': ['Only bounded gaps >50ms and queries >=1ms have individual records; this is not a complete frame trace.',
                         'Missing records or summaries do not establish zero queries or smooth gameplay.',
                         'Clock matching uses event system ticks, not the order in which queued records are written.',
                         'The first 120 seconds is a search window, not a detected kickoff event.',
                         'Matched CPU ratios describe one presenting thread; they do not prove total core load or causality.',
                         'Baseline/current counts may cover different durations and scenes; no automatic performance verdict.']}
    if at_ms is not None:
        result['selected_event'] = {'at_ms': at_ms, **window(max(0, at_ms - radius_ms), at_ms + radius_ms)}
    return result


def compare(current, baseline):
    return {'same_capture': current['sha256'] == baseline['sha256'],
            'current_is_v2': current['is_v2'], 'baseline_sha256': baseline['sha256'],
            'baseline_builds': baseline['builds'], 'baseline_summary': baseline['summary'],
            'verdict': 'identical_capture' if current['sha256'] == baseline['sha256'] else 'hardware_event_comparison_required'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--at', type=parse_time, help='Video T+ time, e.g. 01:32.4')
    parser.add_argument('--window', type=float, default=2, help='Seconds on each side of --at (default 2)')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.window) or args.window < 0:
        parser.error('--window must be finite and nonnegative')
    if args.output and args.output.resolve() in {p.resolve() for p in (args.log, args.baseline) if p}:
        parser.error('--output must not overwrite an input log')
    result = analyze(args.log, args.at, args.window * 1000)
    if args.baseline:
        result['comparison'] = compare(result, analyze(args.baseline))
    text = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
