"""Extract PERF30 interval evidence without inferring GPU time or event causes."""
import argparse, hashlib, json, re
from pathlib import Path

def parse_log(text):
    windows = []
    current = None
    for line in text.splitlines():
        frame = re.search(r'\[PERF8\] uptime_s=(\d+) interval_ms=(\d+) presents=(\d+) fps=([\d.]+)', line)
        if frame:
            current = dict(uptime_s=int(frame[1]), interval_ms=int(frame[2]),
                           presents=int(frame[3]), reported_presents_per_s=float(frame[4]),
                           stages={}, active=[], slow=[], values={})
            windows.append(current)
        if current is None:
            continue
        flags = re.search(r'\[PERF30\] submit_diagnostics=(\d+) owners=(\d+) owner_overflow=(\d+) slow_event_drops=(\d+)', line)
        if flags:
            current.update(diagnostics_enabled=bool(int(flags[1])), owners=int(flags[2]),
                           owner_overflow=int(flags[3]), slow_event_drops=int(flags[4]))
        stage = re.search(r'\[STAGE30\] (\w+) n=(\d+) total_us=(\d+) gt100ms=(\d+) max_since_launch_us=(\d+)', line)
        if stage:
            n, total = int(stage[2]), int(stage[3])
            current['stages'][stage[1]] = dict(calls=n, total_us=total,
                mean_us=total/n if n else None, at_least_100ms=int(stage[4]),
                max_since_launch_us=int(stage[5]))
        active = re.search(r'\[ACTIVE30\] owner_slot=(\d+) handle=([\da-fA-F]+) stage=(\w+) object=([\da-fA-F]+) age_us=(\d+)', line)
        if active:
            current['active'].append(dict(owner_slot=int(active[1]), native_handle=active[2],
                                         stage=active[3], object=active[4], age_us=int(active[5])))
        slow = re.search(r'\[SLOW30\] handle=([\da-fA-F]+) stage=(\w+) object=([\da-fA-F]+) start_tick=(\d+) us=(\d+)', line)
        if slow:
            current['slow'].append(dict(native_handle=slow[1], stage=slow[2], object=slow[3],
                                       start_tick=int(slow[4]), us=int(slow[5])))
        value = re.search(r'\[VALUE30\] (\w+) last=(\d+) max_since_launch=(\d+)', line)
        if value:
            current['values'][value[1]] = dict(last=int(value[2]), max_since_launch=int(value[3]))
    return dict(perf30_marker_present='pes13-nx-0.2.0-perf30-submit-stages' in text,
                diagnostic_report_windows=sum('diagnostics_enabled' in v for v in windows),
                windows=windows,
                limitations=['Nested host wall spans can overlap; do not add as frame/GPU time.',
                    'Present counts do not measure simulation speed or unique rendered frames.',
                    'Maxima are launch-wide; slow events and active snapshots are incomplete.',
                    'No goal/foul timing or cause is inferred from these counters.'])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    reports = []
    for path in args.logs:
        raw = path.read_bytes()
        result = parse_log(raw.decode('utf-8', errors='replace'))
        result.update(file=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        reports.append(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reports, indent=2) + '\n', encoding='utf-8')
    print(f'{len(reports)} logs, {sum(r["diagnostic_report_windows"] for r in reports)} PERF30 report windows -> {args.output}')

if __name__ == '__main__':
    main()
