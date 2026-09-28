"""Summarize per-thread polling/placement without inventing per-core utilization."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def analyze(path):
    data = path.read_bytes()
    threads, delays, jit, warm, balances, jitlog, yield_latest = [], [], [], [], [], [], {}
    yield_adaptive, moves, reversals, last_move = [], [], [], {}
    event_seconds = None
    def values(line):
        return {k: int(v) for k,v in re.findall(r'(\w+)=(\d+)(?=\s|$|;)', line)}
    for number, line in enumerate(data.decode(errors='replace').splitlines(), 1):
        if line.startswith('[FEX3-EVENT] elapsed_s='):
            event_seconds=values(line)['elapsed_s']
        elif line.startswith('[THREADS]'):
            for tid,kind,core,pct in re.findall(r'(\d+)([ws])@(-?\d+) (\d+\.\d+)%',line):
                threads.append(dict(line=number,tid=int(tid),kind=kind,core=int(core),percent=float(pct)))
        elif line.startswith('[FEX3-DELAY] tid='):
            row=dict(line=number,**values(line))
            if row['yields']: row['mean_yield_us']=round(row['yield_us']/row['yields'],3)
            delays.append(row)
        elif line.startswith('[FEX3-JIT] phase=compile_code '):jit.append(dict(line=number,**values(line)))
        elif line.startswith('[FEX3-WARM] graphics_pipeline '):warm.append(dict(line=number,**values(line)))
        elif line.startswith('[BALANCE]'):
            entries=re.findall(r'(\d+)w (\d+|any)->(\d+) (\d+\.\d+)%',line)
            balances.append(dict(line=number,text=line,moves=len(entries),preceding_event_s=event_seconds))
            for tid,source,dest,pct in entries:
                row=dict(line=number,tid=int(tid),source=source,destination=dest,
                         percent=float(pct),preceding_event_s=event_seconds)
                previous=last_move.get(tid)
                if previous and event_seconds is not None and previous['preceding_event_s'] is not None:
                    gap=event_seconds-previous['preceding_event_s']
                    if 0<=gap<=4 and source==previous['destination'] and dest==previous['source']:
                        reversals.append(dict(**row,approx_gap_s=gap))
                moves.append(row);last_move[tid]=row
        elif line.startswith('[FEX3-JITLOG] queued='):jitlog.append(dict(line=number,**values(line)))
        elif line.startswith('[FEX3-YIELD] tid='):
            row=dict(line=number,**values(line));yield_latest[row['tid']]=row
        elif line.startswith('[FEX3-YIELD-ADAPT] initial='):
            yield_adaptive.append(dict(line=number,**values(line)))
    pauses=sum(r['pauses'] for r in yield_latest.values())
    yield_us=sum(r['actual_us'] for r in yield_latest.values())
    return {'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
            'limits':['Monitor observations concern individual cores, not overall CPU utilization.',
                      'THREADS lists measured thread CPU time and affinity/preferred core, not complete physical core utilization.',
                      'Polling reports aggregate about 10 seconds; no exact timestamp of the observed 99% spike.',
                      'Fast average yield does not prove all consecutive calls are ineffective; new policy measures each call.',
                      'JIT uptime is since translator initialization, not in-game match time.',
                      'Migration times use preceding EVENT seconds, not exact event or frame timestamps.',
                      'BALANCE before/after are projected registered-thread loads, not measured GPU or whole-system core load.'],
            'thread_rows_on_core3':[r for r in threads if r['core']==3],
            'top_wine_rows':sorted((r for r in threads if r['kind']=='w'),key=lambda r:r['percent'],reverse=True)[:12],
            'largest_polling_reports':sorted((r for r in delays if r['yields']),key=lambda r:r['yields'],reverse=True)[:12],
            'jit_at_175s':next((r for r in reversed(jit) if r['uptime_ms']<=180000),None),
            'jit_final':jit[-1] if jit else None,
            'graphics_peak_us':max((r['peak_since_launch_us'] for r in warm),default=0),
            'graphics_over50ms_calls':sum(r['over50ms'] for r in warm),
            'yield_totals':{'pauses':pauses,'actual_us':yield_us,
                            'mean_us':round(yield_us/pauses,3) if pauses else None,
                            'late2ms':sum(r['late2ms'] for r in yield_latest.values()),
                            'peak_us':max((r['peak_us'] for r in yield_latest.values()),default=0)},
            'yield_latest_by_tid':list(yield_latest.values()),
            'yield_adaptive_final':yield_adaptive[-1] if yield_adaptive else None,
            'balance_reports':len(balances),
            'balance_moves':len(moves),
            'largest_balance_batches':sorted(balances,key=lambda r:r['moves'],reverse=True)[:5],
            'balance_reversals_within_approx_4s':reversals,
            'last_jitlog':jitlog[-1] if jitlog else None}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('log',type=Path)
    print(json.dumps(analyze(ap.parse_args().log),indent=2))
