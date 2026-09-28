"""Summarize periodic present-thread CPU bursts and native memory-query overlap."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics


def analyze(path):
    gaps=[];queries=[]
    for number,line in enumerate(path.read_text(errors='replace').splitlines(),1):
        if '[FEX3-GAP] tick=' not in line and '[FEX3-MEMQUERY] begin_tick=' not in line:continue
        row={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)};row['line']=number
        (gaps if '[FEX3-GAP]' in line else queries).append(row)
    heavy=[g for g in gaps if g['cpu_valid'] and g['thread_cpu_us']>=25000]
    # A bounded tail makes the selected window explicit; not all recorded play.
    tail=heavy[-20:]
    intervals=[(b['tick']-a['tick'])/19200 for a,b in zip(tail,tail[1:])
               if a['handle']==b['handle']]
    matches=[]
    for g in gaps:
        start=g['tick']-g['end_gap_us']*19.2
        contained=[q for q in queries if q['handle']==g['handle']
                   and q['begin_tick']>=start and q['end_tick']<=g['tick']]
        if contained:
            matches.append({'gap_line':g['line'],'end_gap_us':g['end_gap_us'],
                            'gap_cpu_us':g['thread_cpu_us'] if g['cpu_valid'] else None,
                            'query_lines':[q['line'] for q in contained],
                            'query_wall_us':sum(q['wall_us'] for q in contained),
                            'query_valid_cpu_us':sum(q['thread_cpu_us'] for q in contained if q['cpu_valid'])})
    return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,
            'recorded_gaps_over_50ms':len(gaps),'gaps_with_valid_cpu_at_least_25ms':len(heavy),
            'last_20_heavy_gaps':tail,'same_handle_tail_interval_ms':intervals,
            'tail_median_cpu_us':statistics.median(g['thread_cpu_us'] for g in tail) if tail else None,
            'tail_intervals_within_450_to_550_ms':sum(450<=v<=550 for v in intervals),
            'recorded_slow_memory_queries':len(queries),'contained_query_matches':matches,
            'limits':['Gap sampling is bounded to 32 records per report and excludes intervals <=50ms.',
                      'Selected tail is descriptive; a 500ms cadence alone does not establish causation.',
                      'CPU counters concern the presenting thread, not complete physical core load.',
                      'Memory queries include only native driver-call time, excluding Wine conversion and DXVK allocator work.',
                      'Query overlap uses the same native handle and system clock; wait time may include descheduling.',
                      'No exact camera/ball event markers or mapping from native handles to Wine thread IDs.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=Path)
    print(json.dumps(analyze(p.parse_args().log),indent=2))
