"""Summarize the same-NRO PERF38 diagnostic run and preserve its full hot blocks."""
from pathlib import Path
import argparse, hashlib, importlib.util, json

p=Path(__file__).resolve().parents[1]
def load(name):
    path=p/'tools'/name
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod
cadence=load('analyze-perf29-result.py')
capture=load('decode-perf17.py')

def analyze(path):
    run=cadence.parse(path)
    if run['build']!=['pes13-nx-0.2.0-perf38-region-fusion']:
        raise ValueError('Expected one PERF38 NRO run; check the log build marker')
    if not run['sampler'] or run['sampler'][0]=='off':
        raise ValueError('The submitted run has CPU sampler off; install diagnostics overlay')
    blocks=capture.extract(path.read_text(errors='replace'))
    hot={hex(b['guest']):dict(slot=slot,guest_bytes=len(b['x86']),arm_bytes=len(b['arm64']),
                            x86_sha256=hashlib.sha256(b['x86']).hexdigest(),
                            arm64_sha256=hashlib.sha256(b['arm64']).hexdigest())
         for slot,b in blocks.items() if slot in (6,7)}
    if not hot:
        raise ValueError('Sampler active, but no target math-block capture; inspect PERF17 status')
    intervals=[]
    for row in run['rows']:
        if row['uptime_s']<80:continue
        profiles=[]
        for tid,prof in row['profiles'].items():
            if not tid.endswith('w') or not prof['samples']:continue
            profiles.append(dict(tid=tid,cpu_percent=row['threads'].get(tid),
                samples=prof['samples'],missed=prof['missed'],
                x86_modules=prof['sites'].get('x86 by module',{}),
                x86_top=prof['sites'].get('x86',{}),native_top=prof['sites'].get('native',{})))
        intervals.append(dict(end_s=row['uptime_s'],presents_per_s=round(
            1000*row['presents']/row['interval_ms'],2),cores=row.get('cores'),
            quiet_gap_ms=round(row['frames']['gap_quiet']['avg_us']/1000,2),
            sampled_gap_ms=round(row['frames']['gap_sampled']['avg_us']/1000,2),
            threads=sorted(profiles,key=lambda v:-(v['cpu_percent'] or 0))))
    return dict(log_sha256=run['sha256'],sample_mode=run['sampler'][0],
                hot_blocks=hot,intervals=intervals,
                limits=['Sampler targets lag one CPU report and can miss transient workers.',
                        'Thread samples include waits; x86 and native PCs are top-site summaries.',
                        'Intervals are not synchronized to game events.',
                        'Quiet and sampled gaps should not be pooled for an FPS A/B.'])

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('log',type=Path)
    ap.add_argument('--output',type=Path)
    args=ap.parse_args()
    result=analyze(args.log)
    target=args.output or p/'local/perf38/results'/result['log_sha256'][:12]/'diagnostics.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():assert json.loads(target.read_text())==result
    else:target.write_text(json.dumps(result,indent=2)+'\n')
    capture_dir=target.parent/'captures'
    capture_dir.mkdir(exist_ok=True)
    for slot,block in capture.extract(args.log.read_text(errors='replace')).items():
        if slot not in (6,7):continue
        for kind in ('x86','arm64'):
            file=capture_dir/f'slot-{slot}-{kind}.bin'
            if file.exists():assert file.read_bytes()==block[kind]
            else:file.write_bytes(block[kind])
    print('PERF38 diagnostics:',len(result['intervals']),'intervals, blocks',result['hot_blocks'],
          'output',target)

if __name__=='__main__':main()
