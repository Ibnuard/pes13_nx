"""Summarize per-thread polling/placement without inventing per-core utilization."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def analyze(path):
    data = path.read_bytes()
    threads, delays, jit, warm, balances, jitlog = [], [], [], [], [], []
    def values(line):
        return {k: int(v) for k,v in re.findall(r'(\w+)=(\d+)(?=\s|$|;)', line)}
    for number, line in enumerate(data.decode(errors='replace').splitlines(), 1):
        if line.startswith('[THREADS]'):
            for tid,kind,core,pct in re.findall(r'(\d+)([ws])@(-?\d+) (\d+\.\d+)%',line):
                threads.append(dict(line=number,tid=int(tid),kind=kind,core=int(core),percent=float(pct)))
        elif line.startswith('[FEX3-DELAY] tid='):
            row=dict(line=number,**values(line))
            if row['yields']: row['mean_yield_us']=round(row['yield_us']/row['yields'],3)
            delays.append(row)
        elif line.startswith('[FEX3-JIT] phase=compile_code '):jit.append(dict(line=number,**values(line)))
        elif line.startswith('[FEX3-WARM] graphics_pipeline '):warm.append(dict(line=number,**values(line)))
        elif line.startswith('[BALANCE]'):balances.append(dict(line=number,text=line))
        elif line.startswith('[FEX3-JITLOG] queued='):jitlog.append(dict(line=number,**values(line)))
    return {'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
            'limits':['Monitor observation concerns the third core, not overall CPU utilization.',
                      'THREADS lists measured thread CPU time and affinity/preferred core, not complete physical core utilization.',
                      'Polling reports aggregate about 10 seconds; no exact timestamp of the observed 99% spike.',
                      'Fast average yield does not prove all consecutive calls are ineffective; new policy measures each call.',
                      'JIT uptime is since translator initialization, not in-game match time.'],
            'thread_rows_on_core3':[r for r in threads if r['core']==3],
            'top_wine_rows':sorted((r for r in threads if r['kind']=='w'),key=lambda r:r['percent'],reverse=True)[:12],
            'largest_polling_reports':sorted((r for r in delays if r['yields']),key=lambda r:r['yields'],reverse=True)[:12],
            'jit_at_175s':next((r for r in reversed(jit) if r['uptime_ms']<=180000),None),
            'jit_final':jit[-1] if jit else None,
            'graphics_peak_us':max((r['peak_since_launch_us'] for r in warm),default=0),
            'graphics_over50ms_calls':sum(r['over50ms'] for r in warm),
            'balance_reports':len(balances),
            'last_jitlog':jitlog[-1] if jitlog else None}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('log',type=Path)
    print(json.dumps(analyze(ap.parse_args().log),indent=2))
