"""Exercise diagnostic parsing with a sampled worker and captured hot block."""
from pathlib import Path
import importlib.util,tempfile
p=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('diag',p/'tools/analyze-perf38-diagnostics.py')
diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)
small=('([BUILD] pes13-nx-0.2.0-perf38-region-fusion\n'
       '[PERF24] CPU sampler=2s/10s at 20ms; math flags\n'
       '[PERF8] uptime_s=100 interval_ms=10000 presents=185 host_present_calls=185\n'
       '[FRAME24] gap_quiet n=1 avg_us=54000 bins=0,0,0,1,0,0,0,0,0,0\n'
       '[FRAME24] gap_sampled n=1 avg_us=55000 bins=0,0,0,1,0,0,0,0,0,0\n'
       '[THREADS] 70 threads use 2.9 cores: 188w@1 89.0% 124w@2 76.0%\n'
       '[PROF] 188w samples=20 missed=0 translated=90.0%\n'
       '[PROF] 188w x86 by module: exe 90.0%\n'
       '[PROF] 188w x86: exe+0xd3027b 60.0%\n'
       '[PERF17-BLOCK] slot=6 region=6 bigblock=0 guest=113027b guest_size=1 '
       'native=82001000 native_size=4 hash=1234abcd x86_bytes=1 arm_bytes=4\n'
       '[PERF17-CODE] slot=6 kind=x86 off=0 hex=90\n'
       '[PERF17-CODE] slot=6 kind=arm64 off=0 hex=1f2003d5\n').replace('([BUILD]','[BUILD]')
with tempfile.TemporaryDirectory(prefix='perf38diag-') as temp:
    path=Path(temp)/'diag.log';path.write_text(small)
    parsed=diag.analyze(path)
    assert parsed['hot_blocks']['0x113027b']['arm_bytes']==4
    assert parsed['intervals'][0]['threads'][0]['tid']=='188w'
    assert parsed['intervals'][0]['threads'][0]['x86_top']['exe+0xd3027b']==60.0
    path.write_text(small.replace('CPU sampler=2s/10s at 20ms','CPU sampler=off'))
    try:diag.analyze(path)
    except ValueError as e:assert 'sampler off' in str(e)
    else:raise AssertionError('Accepted a quiet run as sampled diagnostics')
print('PERF38 diagnostics active/quiet and hot-block parse PASS')
