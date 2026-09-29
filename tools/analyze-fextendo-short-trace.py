"""Correlate bounded JIT/wait observations with the independent Play timestamp."""
from pathlib import Path
import argparse, importlib.util, json, math, re
BASE=Path(__file__).with_name('analyze-fextendo-run.py')
spec=importlib.util.spec_from_file_location('base',BASE);base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
KINDS={0:'acquire',1:'submit',2:'fence',3:'semaphore',5:'alert_wait',6:'present_map'}

def analyze(path, at_ms=None, radius_ms=2000):
    result=base.analyze(path,at_ms,radius_ms)
    origin=result['play_origin_tick'];events=[];windows=[];maps=[];stats=[];clocks=[];malformed=[]
    for number,line in enumerate(path.read_text(errors='replace').splitlines(),1):
        f={k:int(v) for k,v in re.findall(r'\b(\w+)=(\d+)\b',line)}
        row={'line':number,**f}
        if '[FEX3-JIT-CLOCK] ' in line:
            clocks.append(row);continue
        if '[FEX3-SHORT-STATS] ' in line:
            stats.append(row);continue
        if '[FEX3-JIT-THREAD] ' in line:
            kind='compile_window';destination=windows;required={'tid','begin_tick','end_tick','calls','total_us','peak_us'}
        elif '[FEX3-JIT-SLOW] ' in line:
            kind='compile_code';destination=events;required={'tid','begin_tick','end_tick','wall_us'}
        elif '[FEX3-SHORT] kind=' in line:
            kind=KINDS.get(f.get('kind'));destination=maps if kind=='present_map' else events
            required={'tid','handle','begin_tick','end_tick','kind'}
        else:continue
        if not kind or not required <= f.keys() or f['end_tick']<f['begin_tick']:
            malformed.append(number);continue
        row['kind_name']=kind
        if kind=='present_map':row['begin_tick']=row['end_tick']
        if kind!='compile_window':row['duration_ms']=(row['end_tick']-row['begin_tick'])/19200
        destination.append(row)
    # Physical ticks must agree with libnx; never substitute JIT init for Play.
    if any(c.get('frequency')!=19200000 for c in clocks):
        origin=None;result['notices'].append('Unexpected JIT clock frequency: short-trace T+ disabled.')
    for row in events+windows+maps:
        row['begin_tplus_ms']=round((row['begin_tick']-origin)/19200,3) if origin is not None else None
        row['end_tplus_ms']=round((row['end_tick']-origin)/19200,3) if origin is not None else None
    def selected(rows):
        if at_ms is None:return sorted(rows,key=lambda r:r['begin_tick'])
        if origin is None:return []
        return sorted((r for r in rows if r['end_tplus_ms']>=at_ms-radius_ms and r['begin_tplus_ms']<=at_ms+radius_ms),key=lambda r:r['begin_tick'])
    result['short_trace']={'available':bool(events or windows or maps),'time_correlation_available':origin is not None,
        'events':selected(events),'compile_windows':selected(windows),'present_threads':maps,'clock_records':clocks,
        'last_cumulative_stats':stats[-1] if stats else None,'malformed_lines':malformed,
        'limits':['Compile windows cover all completed compiles in their span; do not assign their total to one frame or to a smaller selected interval.',
                  'Wait/compile wall time includes scheduling. A wait can be normal idle time; overlap does not prove causality.',
                  'Waker is the last observed NtAlertThreadByThreadId caller; its result is NTSTATUS, not the kernel SignalToAddress result.',
                  'Wake pairing is best effort; the alert may finish after the wait. Missing waker is not proof of a lost wake or heap lock ownership.',
                  'Queues can drop on contention/full; only completed calls are observed. Ongoing hangs need the existing hang capture.',
                  'No automatic claim of a stutter fix; compare trace ON/OFF with the same scene/settings.']}
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=Path)
    p.add_argument('--at',type=base.parse_time);p.add_argument('--window',type=float,default=2);p.add_argument('--output',type=Path);a=p.parse_args()
    if not math.isfinite(a.window) or a.window<0:p.error('window must be finite and nonnegative')
    if a.output and a.output.resolve()==a.log.resolve():p.error('output must not overwrite log')
    text=json.dumps(analyze(a.log,a.at,a.window*1000),indent=2,allow_nan=False)+'\n'
    if a.output:a.output.write_text(text)
    else:print(text,end='')
if __name__=='__main__':main()
