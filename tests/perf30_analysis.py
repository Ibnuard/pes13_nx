"""Avoid mixing interval data, lifetime maxima, disabled and non-PERF30 logs."""
from pathlib import Path
import importlib.util
p = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('analysis', p/'tools/analyze-perf30.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
text = '''pes13-nx-0.2.0-perf30-submit-stages
[PERF8] uptime_s=10 interval_ms=10000 presents=180 fps=18.00
[PERF30] submit_diagnostics=1 owners=4 owner_overflow=0 slow_event_drops=3
[STAGE30] throttle n=100 total_us=5000000 gt100ms=2 max_since_launch_us=900000
[ACTIVE30] owner_slot=3 handle=ABcd stage=throttle object=ab12 age_us=123456
[SLOW30] handle=abcd stage=throttle object=ab12 start_tick=234567 us=120000
[VALUE30] slm_warp last=4096 max_since_launch=8192
[PERF8] uptime_s=20 interval_ms=10000 presents=150 fps=15.00
[PERF30] submit_diagnostics=1 owners=4 owner_overflow=0 slow_event_drops=3
[STAGE30] throttle n=40 total_us=40000 gt100ms=0 max_since_launch_us=900000
[STAGE30] unfinished n=4 total_us=
[PERF8] uptime_s=30 interval_ms=10000 presents=190 fps=19.00
[PERF30] submit_diagnostics=0 owners=4 owner_overflow=0 slow_event_drops=3
'''
r = m.parse_log(text)
a,b,c = r['windows']
assert r['perf30_marker_present'] and r['diagnostic_report_windows'] == 3
assert a['stages']['throttle']['mean_us'] == 50000
assert b['stages']['throttle']['mean_us'] == 1000
assert b['stages']['throttle']['max_since_launch_us'] == 900000
assert len(a['active']) == len(a['slow']) == 1 and not b['active'] and not b['slow']
assert a['values']['slm_warp'] == dict(last=4096, max_since_launch=8192)
assert 'unfinished' not in b['stages']
assert not c['diagnostics_enabled'] and not c['stages'] and not c['values']
old = m.parse_log('[PERF8] uptime_s=10 interval_ms=10000 presents=20 fps=2.00')
assert not old['perf30_marker_present'] and old['diagnostic_report_windows'] == 0
print('PERF30 interval attribution, disabled/absent diagnostics, truncated line and lifetime maximum tests PASS')
