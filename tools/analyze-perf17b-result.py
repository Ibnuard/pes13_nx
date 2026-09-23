"""Summarize the supplied PERF17B run and its bounded code snapshots."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import collections
import capstone

p = Path(__file__).resolve().parents[1]
raw = (p / 'local/perf18/perf17b-result.log').read_bytes()
text = raw.decode(errors='replace')
spec = importlib.util.spec_from_file_location('decoder', p / 'tools/decode-perf17.py')
decoder = importlib.util.module_from_spec(spec); spec.loader.exec_module(decoder)
blocks = decoder.extract(text)
frames = [dict(re.findall(r'(\w+)=([\d.]+)', line)) for line in text.splitlines() if line.startswith('[PERF8]')]
groups = {}
for label, lo, hi in [('menu_candidate', 30, 50), ('selection_candidate', 80, 100), ('match_candidate', 160, 210)]:
    rows = [r for r in frames if lo <= int(r['uptime_s']) <= hi]
    groups[label] = {'ending_seconds': [int(r['uptime_s']) for r in rows],
                     'weighted_fps': sum(int(r['presents']) for r in rows)*1000/sum(int(r['interval_ms']) for r in rows),
                     'host_present_ms_range': [min(float(r['host_present_ms_per_call']) for r in rows), max(float(r['host_present_ms_per_call']) for r in rows)]}
counts = {}
for slot, block in blocks.items():
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    instructions = list(md.disasm(block['arm64'], block['native']))
    counts[slot] = {'guest': hex(block['guest']), 'guest_bytes': block['guest_size'],
                    'native_bytes': block['native_size'], 'bigblock': block['bigblock'],
                    'fpcr_reads': sum(i.mnemonic == 'mrs' and i.op_str.endswith('fpcr') for i in instructions),
                    'fpcr_writes': sum(i.mnemonic == 'msr' and i.op_str.startswith('fpcr') for i in instructions),
                    'mnemonics': dict(collections.Counter(i.mnemonic for i in instructions))}
result = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'groups': groups,
          'last_policy': re.findall(r'^\[PERF17\].*$', text, re.M)[-1], 'blocks': counts,
          'limitations': 'Scene labels inferred; counters measure compilation, not block executions. Static instruction counts are not measured CPU time.'}
(p / 'local/perf18/result.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps({k: v for k, v in result.items() if k != 'blocks'}, indent=2))
print('Matrix capture:', {k:v for k,v in counts[0].items() if k != 'mnemonics'})
