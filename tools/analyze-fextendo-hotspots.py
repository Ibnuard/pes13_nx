"""Rank observed compiler blocks separately from sampled execution residency."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, math, re
spec=importlib.util.spec_from_file_location('short_trace',Path(__file__).with_name('analyze-fextendo-short-trace.py'))
trace=importlib.util.module_from_spec(spec);spec.loader.exec_module(trace)
FIELDS={'rip','begin_tick','end_tick','report_tick','calls','total_us','peak_us','decode_us','passes_us',
        'frontend_us','backend_us','generated','raced','empty','guest_inst','host_bytes','lost'}

def analyze(path, start=0, end=1e12):
    if not math.isfinite(start) or not math.isfinite(end) or not 0<=start<end:
        raise ValueError('Expected a finite 0 <= start < end')
    base=trace.analyze(path);origin=base['play_origin_tick']
    if origin is None or not base['short_trace']['time_correlation_available']:
        raise ValueError('Expected one consistent Play clock; do not merge app sessions')
    blocks=[];windows=[];samples=[];overhead=[];malformed=[];anchor=None
    for number,line in enumerate(path.read_text(errors='replace').splitlines(),1):
        f={k:int(v) for k,v in re.findall(r'\b(\w+)=(\d+)\b',line)}
        if line.startswith(('[FEX3-BLOCK] ','[FEX3-COMPILE] ')):
            if not FIELDS<=f.keys() or f['end_tick']<f['begin_tick'] or f['report_tick']<f['end_tick']:
                malformed.append(number);continue
            row={'line':number,**f}
            row['begin_s']=(f['begin_tick']-origin)/19200000
            row['end_s']=(f['end_tick']-origin)/19200000
            row['report_s']=(f['report_tick']-origin)/19200000
            if line.startswith('[FEX3-COMPILE] '):
                # Empty/loss-only windows have no begin/end; keep at report time.
                if (start<=row['begin_s'] and row['end_s']<=end) or (not f['calls'] and start<=row['report_s']<=end):windows.append(row)
            elif start<=row['begin_s'] and row['end_s']<=end:blocks.append(row)
        elif line.startswith('[FEX3-HOT] ') and 'tick' in f:
            anchor=(f['tick']-origin)/19200000
            if start<=anchor<=end:overhead.append({'line':number,'report_s':anchor,**f})
        elif line.startswith('[PROF] ') and anchor is not None and start<=anchor<=end:
            # Keep per-report counts and percentages intact. These are residency,
            # not on-CPU samples; the time anchor is the end of the interval.
            samples.append({'line':number,'report_s':anchor,'text':line})
    ranks={}
    for row in blocks:
        r=ranks.setdefault(row['rip'],{'guest_entry':hex(row['rip']),'observed_calls':0,'wall_us':0,
            'peak_us':0,'decode_us':0,'passes_us':0,'frontend_us':0,'backend_us':0,'generated':0,'raced':0,'empty':0,'lines':[]})
        r['observed_calls']+=row['calls'];r['wall_us']+=row['total_us'];r['peak_us']=max(r['peak_us'],row['peak_us'])
        for key in ('decode_us','passes_us','frontend_us','backend_us','generated','raced','empty'):r[key]+=row[key]
        r['lines'].append(row['line'])
    return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'play_origin_tick':origin,'range_s':[start,end],
        'compile_available':bool(windows or blocks),'execution_samples_available':bool(samples),
        'compile_windows':windows,'expensive_observed_blocks':sorted(ranks.values(),key=lambda r:r['wall_us'],reverse=True),
        'sampler_reports':samples,'sampler_cumulative_overhead':overhead,'malformed_lines':malformed,
        'limits':['Only top 12 retained compiler entries per window are logged; ranking is of observed entries, not an exhaustive execution profile.',
            'Compiler costs are completed-call wall time including scheduling. Frontend includes decode/passes; never add nested phases.',
            'Lost counts include table-capacity and producer-contention drops; only capacity drops remain represented in aggregate totals.',
            'Compiler windows crossing the requested boundaries are excluded, never prorated; in-flight calls are absent.',
            'Sampler percentages include waiting residency and use the report-end time; they are not pure CPU utilization or exact event timestamps.',
            'FEX guest labels are compilation-unit entries, not exact instruction PCs. Native offsets need the matching ELF for symbolization.',
            'Sampler overhead is cumulative. Diagnostic sampling pauses threads; use sampling OFF for performance comparisons.']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=Path)
    p.add_argument('--range',nargs=2,type=float,default=[0,1e12],metavar=('START_SECONDS','END_SECONDS'))
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.resolve()==a.log.resolve():p.error('Output must not overwrite the capture')
    result=analyze(a.log,*a.range);a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('compile_available','execution_samples_available','expensive_observed_blocks','malformed_lines')},indent=2))
if __name__=='__main__':main()
