"""Archive uploaded runs, verify build identities and summarize existing samples."""
from pathlib import Path
import hashlib, importlib.util, json

p = Path(__file__).resolve().parents[1]
w = p / 'local/perf32'
w.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location('previous', p / 'tools/analyze-perf29-result.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
seen = {}
for file in (p / 'local/perf31/results').glob('*.log'):
    seen[hashlib.sha256(file.read_bytes()).hexdigest()] = str(file.relative_to(p))
runs = []
for label, source in (
    ('reference25', 'dist/pes13-perf31-reference-perf25/switch/pref31-reference-pref25-log'),
    ('quiet_label', 'dist/pes13-perf31-quiet/switch/pref31-quiet-log'),
):
    for original in sorted((p / source).glob('*.log')):
        target = w / 'results' / label / original.name
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = original.read_bytes()
        if target.exists():
            assert target.read_bytes() == raw, 'Refusing to replace archived input'
        else:
            target.write_bytes(raw)
        run = previous.parse(target)
        run.update(label=label, source=str(original.relative_to(p)),
                   identical_earlier=seen.get(run['sha256']))
        seen.setdefault(run['sha256'], str(target.relative_to(p)))
        run['windows'] = {f'{a}-{b}': previous.summarize(run['rows'], a, b)
                          for a, b in ((100, 200), (210, 240), (250, 10000))}
        runs.append(run)
        print(label, original.name, run['build'], 'prior=', run['identical_earlier'])
        if not run['identical_earlier']:
            for row in run['rows']:
                if row['uptime_s'] >= 100:
                    print(' ', row['uptime_s'], round(row['presents']*1000/row['interval_ms'], 2),
                          'cores', row.get('cores'), 'top', sorted(row['threads'].items(), key=lambda item: -item[1])[:3])
(w / 'analysis.json').write_text(json.dumps(dict(runs=runs,
    warning='Both new long runs identify PERF25, not PERF31; folder labels are not build identity.'), indent=2)+'\n')

# Independent older sampling evidence, not samples from these new quiet runs.
prior = previous.parse(p / 'local/perf29/results/pes13-nx.log')
for tid in ('176w', '184w', '124w'):
    sites = {}
    samples = 0
    for row in prior['rows']:
        if row['uptime_s'] < 110:
            continue
        profile = row['profiles'].get(tid, {})
        n = profile.get('samples', 0)
        samples += n
        for site, percent in profile.get('sites', {}).get('x86', {}).items():
            sites[site] = sites.get(site, 0) + percent*n/100
    print('Historic PERF28', tid, 'samples', samples,
          sorted(sites.items(), key=lambda item: -item[1])[:24])
