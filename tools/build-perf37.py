"""Build the sample-only probe, retaining PERF36 generated game instructions."""
from pathlib import Path
import json
p=Path(__file__).resolve().parents[1]
path=p/'tools/build-perf36.py'
text=path.read_text().replace('local/perf36','local/perf37')
for old,new in [('runtime-perf36-scoped-fastnan','runtime-perf37-jit-probe'),
                ('pes13-nx-0.2.0-perf36-scoped-fastnan','pes13-nx-0.2.0-perf37-jit-probe'),
                ('PES13-NX PERF36 FASTNAN','PES13-NX PERF37 JIT PROBE'),
                ('perf36_patches as perf23_patches','perf37_patches as perf23_patches')]:
    text=text.replace(old,new)
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
w=p/'local/perf37'
report=json.loads((w/'verification.json').read_text())
report.update(base='PERF36',actual_new_change='sample-only JIT opcode/block attribution',
              performance_improvement_claimed=False)
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
