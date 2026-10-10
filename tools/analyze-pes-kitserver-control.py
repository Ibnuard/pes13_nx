"""Summarize Kitserver control runs; never interpret presents as simulation FPS."""
import argparse
import collections
import hashlib
import importlib.util
import json
from pathlib import Path
import re


def analyze(path):
    spec = importlib.util.spec_from_file_location('lwlog', Path(__file__).with_name('analyze-pes-low-window-run.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    raw = path.read_bytes()
    rows = mod.records(raw.decode(errors='replace'))
    live, clocks, cpu, io, modules = [], [], [], [], []
    for t, s in rows:
        fields = dict(re.findall(r'([a-zA-Z_]+)=([^\s;]+)', s))
        if s.startswith('[LW3-LIVESET] layout='): live.append(dict(seconds=t, **fields))
        if s.startswith('[LW3-CLOCKSITE] layout='): clocks.append(dict(seconds=t, **fields))
        if (s.startswith('[WAIT-CPU] tid=84w') and fields.get('valid') == '1'
                and all(fields.get(k, '').isdigit() for k in ('cpu_ms', 'interval_ms'))):
            cpu.append(dict(seconds=t, **fields))
        if s.startswith('[LW2-IO]'): io.append(dict(seconds=t, **fields))
        m = re.search(r'\[NXLDR\] attach name=(.*?) status=([0-9A-Fa-f]+) base=([0-9A-Fa-f]+)', s)
        if m and ('kitserver' in m[1].lower() or 'gameplaytool' in m[1].lower()):
            modules.append(dict(seconds=t, name=m[1], status=m[2], base=m[3]))
    periods = []
    for start, stop in ((75, 120), (130, 200), (200, 230), (250, 300)):
        samples = [r for r in cpu if start <= r['seconds'] <= stop]
        total = sum(int(r['interval_ms']) for r in samples)
        reads = [r for r in io if start <= r['seconds'] <= stop]
        periods.append(dict(sample_end_range_s=[start, stop], callback_samples=len(samples),
            callback_cpu_ms=sum(int(r['cpu_ms']) for r in samples), sampled_interval_ms=total,
            callback_core_fraction=round(sum(int(r['cpu_ms']) for r in samples)/total, 4) if total else None,
            io_samples=reads))
    targets = collections.defaultdict(set)
    for r in clocks: targets[r['role']].add(r.get('target', 'unknown'))
    return dict(input=str(path.resolve()), input_sha256=hashlib.sha256(raw).hexdigest(),
        duration_s=rows[-1][0], live_samples=len(live),
        frame_skip=dict(collections.Counter(r['frame_skip'] for r in live)),
        flags=dict(collections.Counter(r['flags'] for r in live)),
        crc=dict(collections.Counter(r.get('crc_valid', 'truncated') for r in live)),
        clock_targets={k: sorted(v) for k,v in targets.items()},
        optional_gameplay_plugin_mentions=sum('gameplay.dll' in s.lower() for _, s in rows),
        kitserver_attach=modules, candidate_loading_periods=periods,
        control_markers=[dict(seconds=t, line=s) for t,s in rows if '[LW4-KITCONTROL]' in s])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('logs', type=Path, nargs='+')
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    report = dict(runs=[analyze(p) for p in a.logs],
        limitations=['Thread 84 is matched to sysFileCallbackThread in these supplied runs; do not assume the same tid in another workload.',
                     'Sample end ranges are not user-timestamped prematch phase boundaries.',
                     'CPU fractions use kernel thread tick deltas, not per-function samples.',
                     'SD wall times can overlap and do not include all asset CPU work.',
                     'Loaded WECF snapshots and clock call targets do not measure simulation speed.',
                     'Native presents are not unique game frames; no FPS or loading gain is claimed.'])
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    for run in report['runs']:
        print(run['input_sha256'], run['duration_s'], 'live', run['live_samples'], 'skip', run['frame_skip'])
        print('module attaches', len(run['kitserver_attach']), 'callback fractions',
              [p['callback_core_fraction'] for p in run['candidate_loading_periods']])


if __name__ == '__main__': main()
