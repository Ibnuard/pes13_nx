"""Compare sampled guest blocks before/after a PES13 camera or replay slowdown."""
from pathlib import Path
from collections import Counter
import argparse
import importlib.util
import json
import re


project = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'cadence', project / 'tools/analyze-perf29-result.py')
cadence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cadence)


def phase(text):
    match = re.fullmatch(r'(\d+):(\d+)', text)
    if not match or int(match[1]) > int(match[2]):
        raise argparse.ArgumentTypeError('expected START:END application seconds')
    return int(match[1]), int(match[2])


def parse(path):
    run = cadence.parse(path)
    rows = {row['uptime_s']: row for row in run['rows']}
    current = None
    for line in path.read_text(errors='replace').splitlines():
        if line.startswith('[PERF8] '):
            current = rows[cadence.numbers(line)['uptime_s']]
            current['jit'] = {}
        elif line.startswith('[JIT37] '):
            match = re.match(r'\[JIT37\] (\d+[ws]) samples=(\d+) '
                             r'word_dropped=(\d+) block_dropped=(\d+)', line)
            if not match or current is None or match[1] in current['jit']:
                raise ValueError('invalid or duplicate JIT histogram header')
            current['jit'][match[1]] = {
                'samples': int(match[2]), 'word_dropped': int(match[3]),
                'block_dropped': int(match[4]), 'words': {}, 'blocks': []}
        elif line.startswith('[JIT37-WORDS] '):
            fields = line.split()
            if current is None or fields[1] not in current['jit']:
                raise ValueError('orphan JIT words')
            words = current['jit'][fields[1]]['words']
            for item in fields[2:]:
                word, count = item.split(':')
                int(word, 16)
                if word in words or int(count) <= 0:
                    raise ValueError('invalid JIT word count')
                words[word] = int(count)
        elif line.startswith('[JIT37-BLOCK] '):
            fields = line.split()
            if current is None or fields[1] not in current['jit']:
                raise ValueError('orphan JIT block')
            data = dict(item.split('=') for item in fields[2:])
            current['jit'][fields[1]]['blocks'].append({
                'guest': int(data['guest'], 16),
                'guest_bytes': int(data['guest_bytes']),
                'arm_bytes': int(data['arm_bytes']),
                'samples': int(data['samples'])})
    for row in run['rows']:
        for record in row.get('jit', {}).values():
            if sum(record['words'].values()) + record['word_dropped'] != record['samples']:
                raise ValueError('truncated JIT word histogram')
            if len(record['blocks']) > 12 or (sum(b['samples'] for b in record['blocks']) +
                                               record['block_dropped'] > record['samples']):
                raise ValueError('invalid JIT top-block list')
    return run


def summarize(rows):
    interval_ms = sum(row['interval_ms'] for row in rows)
    samples = 0
    blocks = Counter()
    threads = Counter()
    quiet_bins = [0] * 10
    quiet_total_us = 0
    for row in rows:
        quiet = row.get('frames', {}).get('gap_quiet')
        if quiet:
            quiet_total_us += quiet['n'] * quiet['avg_us']
            for index, count in enumerate(quiet['bins']):
                quiet_bins[index] += count
        for tid, record in row.get('jit', {}).items():
            samples += record['samples']
            threads[tid] += record['samples']
            for block in record['blocks']:
                blocks[block['guest']] += block['samples']
    quiet_count = sum(quiet_bins)
    return {
        'windows_ending_s': [row['uptime_s'] for row in rows],
        'presents_per_s': (round(1000 * sum(row['presents'] for row in rows) /
                                 interval_ms, 2) if interval_ms else None),
        'quiet_gap': {
            'count': quiet_count,
            'mean_ms': round(quiet_total_us / quiet_count / 1000, 2)
                if quiet_count else None,
            'over_33_334_ms_count': sum(quiet_bins[2:]),
            'over_33_334_ms_percent': round(100 * sum(quiet_bins[2:]) /
                                            quiet_count, 2) if quiet_count else None,
        },
        'jit_wall_samples': samples,
        'sampled_threads': dict(threads.most_common()),
        'top_reported_guest_blocks': [
            {'guest': f'{address:08x}', 'samples': count}
            for address, count in blocks.most_common(15)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--before', type=phase)
    parser.add_argument('--after', type=phase)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if bool(args.before) != bool(args.after):
        parser.error('--before and --after must be provided together')
    run = parse(args.log)
    if not any('perf43-match-probe' in build or 'perf37-jit-probe' in build
               for build in run['build']):
        raise ValueError('log is not a JIT probe build')
    report = {'build': run['build'], 'sha256': run['sha256'],
              'sampler': run['sampler'],
              'limits': [
                  'Present rate is not independent game simulation FPS.',
                  'Profiler samples are wall samples, not CPU cycles.',
                  'Only top guest blocks per thread/interval are reported.',
                  'Sampling changes frame timing; do not benchmark sampled FPS.',
                  'Scene windows rely on the tester-provided approximate uptime.'],
              'all': summarize(run['rows'])}
    if args.before:
        for label, (start, end) in (('before', args.before), ('after', args.after)):
            selected = [row for row in run['rows'] if start <= row['uptime_s'] <= end]
            if not selected:
                raise ValueError(f'{label} window has no PERF8 interval')
            report[label] = summarize(selected)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
