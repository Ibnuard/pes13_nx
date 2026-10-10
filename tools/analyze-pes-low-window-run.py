"""Summarize a timestamped, console-wrapped PES low-window debug run."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import shutil


def records(text):
    result = []
    for raw in text.splitlines():
        m = re.match(r'^\[([0-9.]+)\] (.*)', raw)
        if not m: continue
        stamp, body = m.groups()
        if result and result[-1][0] == stamp and not body.startswith('[') and not re.match(r'[0-9a-f]{4}:', body):
            result[-1][1] += body
        else: result.append([stamp, body])
    return [(float(t), body) for t, body in result]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('log', type=Path); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); raw = a.log.read_bytes(); rows = records(raw.decode(errors='replace'))
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output/'device.log').write_bytes(raw)
    counts = collections.Counter(re.match(r'\[([^]]+)\]', s)[1] if s.startswith('[') else 'wine/other' for t,s in rows)
    wait = []
    for t, s in rows:
        m = re.match(r'\[WAIT-PROBE\] presents=(\d+) delta=(\d+) idle_ms=(\d+) dropped=(\d+)', s)
        if m:
            elapsed = t-wait[-1]['seconds'] if wait else None
            wait.append(dict(seconds=t, presents=int(m[1]), delta=int(m[2]), idle_ms=int(m[3]),
                per_second=round(int(m[2])/elapsed,2) if elapsed else None))
    suspicious = [(t,s) for t,s in rows if any(v in s for v in (
        '[MEM-FAIL]', '[FEX3-NHEAP-FAIL]', 'STOP compiler', 'Unhandled page fault', '[FAILURE]',
        '[EXIT]', 'vkAllocateMemory of', 'failed with', ' underrun'))]
    jit = [(t,s) for t,s in rows if s.startswith('[FEX3-JIT]')]
    threads = [(t,s) for t,s in rows if 'Thread renamed to' in s]
    gaps = sorted([(round(rows[i][0]-rows[i-1][0],3), rows[i-1],rows[i]) for i in range(1,len(rows))], reverse=True)[:25]
    report = dict(input_sha256=hashlib.sha256(raw).hexdigest(), duration_s=rows[-1][0],
        tags=dict(counts.most_common()), present_windows=wait, failures=suspicious,
        last_jit=jit[-9:], threads=threads, log_gaps=gaps,
        limitations='Present counters are not unique simulation FPS. Silence between log entries is not proof of a render stall.')
    (a.output/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
    (a.output/'logical.log').write_text(''.join(f'[{t:.3f}] {s}\n' for t,s in rows))
    print(json.dumps({k:report[k] for k in ('input_sha256','duration_s','tags','failures','last_jit')},indent=2))
    print('PRESENT WINDOWS (s, present/s, max current idle ms)')
    for x in wait: print(x['seconds'], x['per_second'], x['idle_ms'])


if __name__ == '__main__': main()
