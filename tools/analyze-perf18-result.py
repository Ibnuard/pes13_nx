"""Archive-derived PERF18 measurements; scene boundaries remain approximate."""
from pathlib import Path
import hashlib
import json
import re

p=Path(__file__).resolve().parents[1]
raw=(p/'local/perf19/perf18-result.log').read_bytes()
text=raw.decode(errors='replace')
rows=[dict(re.findall(r'(\w+)=([\d.]+)',line)) for line in text.splitlines() if line.startswith('[PERF8]')]
groups={}
for name,lo,hi in [('selection_candidate',70,90),('match_candidate',140,180)]:
    r=[x for x in rows if lo<=int(x['uptime_s'])<=hi]
    groups[name]={'intervals_ending_s':[int(x['uptime_s']) for x in r],
                  'fps_weighted':sum(int(x['presents']) for x in r)*1000/sum(int(x['interval_ms']) for x in r),
                  'host_present_ms':[min(float(x['host_present_ms_per_call']) for x in r),max(float(x['host_present_ms_per_call']) for x in r)]}
report={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
        'last_policy':re.findall(r'^\[PERF18\].*$',text,re.M)[-1],
        'groups':groups,'limitations':'Scene labels inferred; clocks/scenes not controlled across runs. Host present time is not total GPU time.'}
(p/'local/perf19/perf18-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
