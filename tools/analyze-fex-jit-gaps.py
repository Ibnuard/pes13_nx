"""Find gap windows bracketed by unchanged compilation counters; not event attribution."""
import argparse
import bisect
import hashlib
import importlib.util
import json
from pathlib import Path


def analyze(path):
    spec=importlib.util.spec_from_file_location('pacing',Path(__file__).with_name('analyze-fex-pacing.py'))
    pacing=importlib.util.module_from_spec(spec);spec.loader.exec_module(pacing)
    data=pacing.analyze(path)
    jit=[r for r in data['jit'] if r['phase']=='compile_code']
    positions=[r['line'] for r in jit]
    windows=[w for w in data['windows'] if 'entry_gap' in w['stages']]
    flat=[]
    for previous,current in zip(windows,windows[1:]):
        # Reports may reach the logger later than their sample. Widen the
        # bracket by another report at each edge; still not exact clock sync.
        a=bisect.bisect_right(positions,previous['line'])-2
        b=bisect.bisect_right(positions,current['line'])+1
        if a<0 or b>=len(jit):continue
        span=jit[a:b+1]
        if any(r['calls']!=span[0]['calls'] or r['total_us']!=span[0]['total_us'] for r in span):continue
        gap=current['stages']['entry_gap'];large=sum(gap['bins'][5:])
        if not large:continue
        flat.append({'pace_elapsed_ms':current['elapsed_ms'],'window_ms':current['window_ms'],
                     'gap_over_50ms':large,'present_intervals':gap['n'],
                     'compile_counter':span[0]['calls'],
                     'jit_bracket_uptime_ms':[span[0]['uptime_ms'],span[-1]['uptime_ms']],
                     'jit_bracket_lines':[span[0]['line'],span[-1]['line']],
                     'native_present_mean_us':current['stages']['native_total']['avg_us']})
    return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'limits':['Queued JIT reports and PACE histograms have different clock origins.',
                      'Brackets are widened by report samples, not hardware-synchronized timestamps.',
                      'Counters include completed compiles only; an in-flight compile is not counted yet.',
                      'A flat bracket weakens new-compilation as the sole explanation, not all JIT/runtime overhead.',
                      'Presents are not unique 3D/simulation frames; no camera/ball event timestamps.'],
            'flat_compile_windows_with_gaps':flat}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('log',type=Path)
    print(json.dumps(analyze(ap.parse_args().log),indent=2))
