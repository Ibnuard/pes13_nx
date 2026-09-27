"""Summarize the sync-pacing device regression without labeling presents as FPS."""
from pathlib import Path
import argparse
import hashlib
import json
import re
from typing import Any


def summarize(path):
    raw = path.read_bytes()
    text = raw.decode(errors='replace')
    windows, sync, delays, self_waits = [], [], [], []
    for line in text.splitlines():
        values = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)}
        if line.startswith('[FEX3-PACE] elapsed_ms='):
            values['host_presents_per_second'] = (
                round(values['ok'] * 1000 / values['window_ms'], 3)
                if values['window_ms'] else None)
            windows.append(values)
        elif line.startswith('[FEX3-SYNC] targeted='):
            sync.append(values)
        elif line.startswith('[FEX3-DELAY] tid='):
            delays.append(values)
        elif line.startswith('[FEX3-SELF-WAIT]'):
            self_waits.append(values)
    totals: dict[str, Any] = {k: sum(v[k] for v in sync) for k in (
        'notices', 'candidates', 'notified', 'filtered', 'sleeps')} if sync else {}
    if totals:
        assert totals['candidates'] == totals['notified'] + totals['filtered']
        totals['filtered_percent'] = (
            round(100 * totals['filtered'] / totals['candidates'], 2)
            if totals['candidates'] else None)
    return {
        'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
        'build': re.search(r'^\[BUILD\] (.+)$', text, re.M)[1].strip(),
        'windows': windows, 'routing_totals': totals,
        'sleep_excess_peak_us': max((v['excess_peak_us'] for v in delays), default=None),
        'sleep_late20_count': sum(v['late20'] for v in delays),
        'last_self_suspend': self_waits[-1] if self_waits else None,
        'shared_clock_peak_us': max(map(int, re.findall(
            r'\[FEX3-PIPE\] shared_clock_gap .*?peak_since_launch_us=(\d+)', text)), default=None),
        'exceptions': len(re.findall(r'^\[EXC\]', text, re.M)),
    }, text


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('log', type=Path)
    ap.add_argument('--previous', type=Path, required=True)
    ap.add_argument('--elf', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    from elftools.elf.elffile import ELFFile

    current, text = summarize(a.log)
    previous, _ = summarize(a.previous)
    with a.elf.open('rb') as f:
        elf = ELFFile(f)
        functions = [s for s in elf.get_section_by_name('.symtab').iter_symbols()
                     if s['st_info']['type'] == 'STT_FUNC' and s['st_value']]
        observer = next(s['st_value'] for s in functions if s.name == 'wine_nx_fex_stall_probe')
        actual = int(re.search(r'\[FEX3-HANG\].*?observer=([a-f0-9]+)', text)[1], 16)
        bias = actual - observer
        rows = []
        callers = {}
        for line in text.splitlines():
            if line.startswith('[FEX3-HANG-CALLERS]'):
                tid = int(re.search(r'tid=(\d+)', line)[1])
                for value in line.split('round=', 1)[1].split()[1:]:
                    off = int(value, 16) - bias - 4  # ARM64 return address
                    match = next((s for s in functions if s['st_value'] <= off < s['st_value'] + s['st_size']), None)
                    if match:
                        names = callers.setdefault(tid, [])
                        if match.name not in names:
                            names.append(match.name)
            if not line.startswith('[FEX3-HANG-PC]'):
                continue
            fields = dict(re.findall(r'(\w+)=([a-f0-9]+)', line))
            pc = int(fields['pc'], 16)
            row = {'tid': int(fields['tid']), 'pc': hex(pc), 'jit': int(fields['jit'])}
            off = pc - bias
            match = next((s for s in functions if s['st_value'] == off or
                          s['st_value'] <= off < s['st_value'] + s['st_size']), None)
            if match:
                row['native_function'] = match.name
                row['native_function_offset'] = hex(off - match['st_value'])
            else:
                row['guest_block_label'] = fields['guest_block']
            if row not in rows:
                rows.append(row)
    report = {
        'current': current, 'previous': previous,
        'native_elf_sha256': hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        'load_bias': hex(bias), 'hang_samples': rows, 'native_callers': callers,
        'user_report': 'CPU-only OC; heavier 3D and complete freeze before kick-off.',
        'interpretation': [
            'No match measurement: the tester never reached kick-off in the current run.',
            'The new router filtered notifications, but that does not establish a performance benefit.',
            'Delay excess includes scheduling, contention and preemption; it is not a GPU timer.',
            'Main waits in the native thread-alert/futex path; another sampled worker repeats guest atomics/yield.',
            'The final self-suspend sample has no outstanding self-suspend; it is not a complete live wait graph.',
            'Changing schedule can expose an existing race. The exact cause is not established by this log.',
            'Rollback the new routing as default; do not change guest clocks, FEX profile or DXVK in the same test.',
        ],
        'limitations': ['No controlled same-scene/clock FPS comparison.',
                        'Presents are API calls; stages and replay/menu phases differ between runs.',
                        'A guest block label is not an exact x86 PC or a verified module identity.'],
        'hardware_recovery_verified': False,
    }
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({
        'input': current['sha256'], 'router': current['routing_totals'],
        'final_window': current['windows'][-1], 'sleep_excess_peak_us': current['sleep_excess_peak_us'],
        'self_suspend': current['last_self_suspend'], 'hang_samples': rows,
    }, indent=2))


if __name__ == '__main__':
    main()
