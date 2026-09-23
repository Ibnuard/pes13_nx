"""Build measured-math-page guard fusion, retaining the PERF36 preset."""
from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parents[1];w=p/'local/perf38'
tests=json.loads((w/'fusion-tests.json').read_text())
assert tests['branch_cases']>=512 and tests['whole_block_bit_identical']
for name,digest in tests['source_sha256'].items():
    assert hashlib.sha256((p/name).read_bytes()).hexdigest()==digest,name
path=p/'tools/build-perf36.py'
text=path.read_text().replace('local/perf36','local/perf38')
for old,new in [('runtime-perf36-scoped-fastnan','runtime-perf38-region-fusion'),
                ('pes13-nx-0.2.0-perf36-scoped-fastnan','pes13-nx-0.2.0-perf38-region-fusion'),
                ('PES13-NX PERF36 FASTNAN','PES13-NX PERF38 FUSION'),
                ('perf36_patches as perf23_patches','perf38_patches as perf23_patches')]:text=text.replace(old,new)
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
report=json.loads((w/'verification.json').read_text())
report.update(base='PERF36',actual_new_change='direct-control-flow FPCR fusion in measured math pages',
              performance_improvement_claimed=False)
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
