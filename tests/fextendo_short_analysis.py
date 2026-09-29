from pathlib import Path
import importlib.util,tempfile
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'tools/analyze-fextendo-short-trace.py';spec=importlib.util.spec_from_file_location('trace',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as d:
    log=Path(d)/'test.log';origin=90000000000
    # Deliberately reverse write order: event clocks determine matching.
    lines=[f'[FEXTENDO-TIME] origin_tick={origin} enabled=1', '[FEX3-JIT-CLOCK] origin_tick=1 frequency=19200000',
        f'[FEX3-JIT-THREAD] tid=164 begin_tick={origin+140*19200000} end_tick={origin+150*19200000} calls=99 total_us=123456 peak_us=25000',
        f'[FEX3-SHORT] kind=5 tid=4 handle=99 begin_tick={origin+145*19200000} end_tick={origin+145*19200000+960000} result=257 waker=164 wakes=1',
        f'[FEX3-JIT-SLOW] tid=164 begin_tick={origin+145*19200000-480000} end_tick={origin+145*19200000} wall_us=25000',
        f'[FEX3-SHORT] kind=6 tid=4 handle=99 begin_tick=0 end_tick={origin+19200000}',
        '[FEX3-SHORT-STATS] rows=10 row_dropped=2 jit_rows=1 jit_dropped=0 wait_pair_lost=1',
        '[FEX3-SHORT-STATS] rows=20 row_dropped=3 jit_rows=2 jit_dropped=0 wait_pair_lost=2']
    log.write_text('\n'.join(lines));r=m.analyze(log,145000,100)['short_trace']
    assert r['events'][0]['kind_name']=='compile_code' and r['events'][1]['kind_name']=='alert_wait'
    assert r['events'][0]['end_tplus_ms']==145000 and r['events'][1]['duration_ms']==50
    assert r['compile_windows'][0]['total_us']==123456 and r['present_threads'][0]['tid']==4
    assert r['last_cumulative_stats']['row_dropped']==3
    log.write_text('\n'.join(lines[1:]));assert not m.analyze(log,145000,100)['short_trace']['events']
    log.write_text('\n'.join(lines+[lines[0]]));assert not m.analyze(log,145000,100)['short_trace']['time_correlation_available']
    log.write_text('\n'.join(lines).replace('frequency=19200000','frequency=24000000'));assert not m.analyze(log)['short_trace']['time_correlation_available']
print('PASS short-trace timestamps, reorder, mapping, window boundaries, cumulative drops, ambiguous/missing clocks')
