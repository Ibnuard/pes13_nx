"""Synthetic hotspot logs must preserve clock, coverage and phase semantics."""
from pathlib import Path
import importlib.util,tempfile
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hotspots',ROOT/'tools/analyze-fextendo-hotspots.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def tick(s):return 100000+s*19200000
def row(kind,rip,start,end,cost):
 return (f'[{kind}] rip={rip} begin_tick={tick(start)} end_tick={tick(end)} report_tick={tick(end+1)} calls=2 '
         f'total_us={cost} peak_us=10 decode_us=3 passes_us=5 frontend_us=10 backend_us=7 generated=1 raced=1 empty=0 guest_inst=128 host_bytes=256 lost=0')
text='\n'.join(['[BUILD] fixture','[FEXTENDO-TIME] origin_tick=100000 enabled=1','[FEX3-JIT-CLOCK] origin_tick=200000 frequency=19200000',
 row('FEX3-COMPILE',0,100,105,999),row('FEX3-BLOCK',4198400,100,105,20),row('FEX3-BLOCK',4198400,110,115,30),
 row('FEX3-BLOCK',4198500,99,105,9999),f'[FEX3-HOT] pauses=100 pause_us=1000 peak_us=30 resume_failures=0 tick={tick(116)}',
 '[PROF] 164w samples=100 missed=0 x86=20.0%','[PROF] 164w x86: pes2013.exe+0x1000 20.0%'])+'\n'
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'capture.log';p.write_text(text);r=h.analyze(p,100,120)
 assert len(r['expensive_observed_blocks'])==1
 top=r['expensive_observed_blocks'][0];assert top['observed_calls']==4 and top['wall_us']==50 and top['frontend_us']==20
 assert r['compile_windows'][0]['total_us']==999 and len(r['sampler_reports'])==2
 assert r['sampler_reports'][0]['report_s']==116 and r['sampler_cumulative_overhead'][0]['pause_us']==1000
 p.write_text(text+'[FEX3-BLOCK] rip=1 calls=20\n');assert h.analyze(p)['malformed_lines']
 p.write_text(text.split('[FEX3-COMPILE]')[0]);r=h.analyze(p);assert not r['compile_available'] and not r['execution_samples_available']
 for t,bounds in [(text+'[FEXTENDO-TIME] origin_tick=99 enabled=1\n',(0,200)),(text.replace('frequency=19200000','frequency=10'),(0,200)),(text,(0,float('inf')))]:
  p.write_text(t)
  try:h.analyze(p,*bounds)
  except ValueError:pass
  else:raise AssertionError('Invalid clock/range accepted')
print('PASS hotspot ranking, nested phases kept separate, full windows, sample report anchors, malformed/missing records, clock/range rejection')
