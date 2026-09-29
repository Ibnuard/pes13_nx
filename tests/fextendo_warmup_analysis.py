"""Clock/boundary and cumulative-vs-interval regression cases for the audit."""
import importlib.util
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('warmup', ROOT/'tools/analyze-fextendo-warmup.py')
warmup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(warmup)


def tick(s):
    return 100000 + s * 19200000


def fixture():
    rows = ['[BUILD] fixture', '[FEXTENDO-TIME] origin_tick=100000 enabled=0',
            '[FEX3-JIT-CLOCK] origin_tick=200000 frequency=19200000',
            '[FEX3-DXVKCORE] tid=164 name=gameThread']
    for i, t in enumerate((100, 110, 120, 130)):
        rows += [f'[PROGRESS] 900s reads={i} read_ms={i*4} sd_reads={i} sd_ms={i*3} frames={i*5} syscalls={i*100}',
                 '[THREADS] 2 threads use 0.50 cores: 164w@2 40.0% 164s@2 10.0%',
                 '[FEX3-PACE] entry_gap n=5 avg_us=40000 bins=0,0,0,2,1,2,0,0,0',
                 '[FEX3-WARM] graphics_pipeline n=3 total_us=500',
                 f'[FEX3-SHORT-STATS] tick={tick(t)} rows=0']
    # A queued event outside log order must still use its physical clock.
    rows += [f'[FEX3-JIT-THREAD] tid=164 begin_tick={tick(99)} end_tick={tick(121)} calls=999 total_us=99999 peak_us=999',
             f'[FEX3-JIT-THREAD] tid=164 begin_tick={tick(105)} end_tick={tick(110)} calls=10 total_us=1000 peak_us=200',
             f'[FEX3-GAP] tick={tick(110)} handle=1 end_gap_us=60000 cpu_valid=1 thread_cpu_us=100']
    return '\n'.join(rows)+'\n'


with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)/'capture.log';p.write_text(fixture())
    r = warmup.analyze(p, [(100, 120)])['ranges'][0]
    assert r['jit_full_windows_only']['calls'] == 10  # crossing window never prorated
    assert r['jit_full_windows_only']['wall_us'] == 1000
    assert r['jit_full_windows_only']['per_thread'][164]['name'] == 'gameThread'
    assert len(r['full_report_batches']) == 2
    assert r['warm_stages_separate']['graphics_pipeline']['calls'] == 6  # interval counts summed, not differenced
    assert r['frame_histogram']['gt_50000_us'] == 4
    assert r['recorded_gaps']['count'] == 1
    for b in r['full_report_batches']:
        assert b['delta']['sd_ms'] == 3  # cumulative reads differenced
        assert b['displayed_thread_core_subtotals'] == {2: 50.0}
    for text, ranges in ((fixture().replace('origin_tick=100000', 'missing=100000'), [(100,120)]),
                         (fixture().replace('sd_ms=6', 'sd_ms=0'), [(100,120)]),
                         (fixture(), [(100,float('inf'))]),
                         (fixture()+'[FEXTENDO-TIME] origin_tick=200000 enabled=1\n', [(100,120)])):
        p.write_text(text)
        try:
            warmup.analyze(p, ranges)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid correlation/range/reset accepted')
print('PASS tick origins, delayed log order, JIT boundary exclusion, interval/cumulative counters, histogram and reset rejection')
