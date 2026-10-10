"""Read paired address-bias microbenchmarks. Never extrapolates game FPS."""
import argparse
import json
from pathlib import Path
import re
from statistics import median

KINDS = ('chase', 'scalar', 'vector', 'pair', 'atomic')
FOOTPRINTS = (16384, 262144, 4194304)
EXPECTED = {(kind,size) for kind in KINDS for size in FOOTPRINTS}


def fields(line):
    return dict(re.findall(r'(\w+)=([^\s]+)',line))


def analyze(text):
    cases, samples, freq, pinned = {}, {}, 0, False
    for line in text.splitlines():
        if line.startswith('[CPU] '):
            f = fields(line)
            freq, pinned = int(f['tick_frequency']), int(f['rc'],16) == 0
        elif line.startswith('[CASE] '):
            f = fields(line)
            key = (f['kernel'],int(f['footprint']))
            if key not in EXPECTED or key in cases: raise ValueError('Unknown or duplicate case')
            cases[key] = {n:int(f[n]) for n in ('loops','steps','samples')}
            factor = 8 if key[0] == 'chase' else 1
            if cases[key]['steps'] != cases[key]['loops']*factor or cases[key]['loops'] <= 0 or cases[key]['samples'] != 9:
                raise ValueError('Invalid case size/step count')
            samples[key] = {}
        elif line.startswith('[SAMPLE] '):
            f = fields(line)
            key, pair = (f['kernel'],int(f['bytes'])), int(f['pair'])
            if key not in cases or pair in samples[key] or not 0 <= pair < 9: raise ValueError('Missing case or duplicate/invalid pair')
            if int(f['loops']) != cases[key]['loops'] or f['order'] != ('BA' if pair%2 else 'AB'): raise ValueError('Unpaired work/order')
            direct, bias = int(f['direct_ticks']), int(f['bias_ticks'])
            if direct <= 0 or bias <= 0: raise ValueError('Invalid measured ticks')
            cpu, ram = [int(v) for v in f['cpu_hz'].split(',')], [int(v) for v in f['ram_hz'].split(',')]
            if len(cpu) != 3 or len(ram) != 3 or any(v < 0 for v in cpu+ram): raise ValueError('Invalid clocks')
            changed = any(a and b and a != b for seq in (cpu,ram) for a,b in zip(seq,seq[1:]))
            known = all(cpu+ram)
            expected_clock = 'CHANGED' if changed else 'STABLE' if known else 'UNKNOWN'
            if f['clock'] != expected_clock: raise ValueError('Clock tag disagrees with raw values')
            samples[key][pair] = {'direct':direct,'bias':bias,'changed':changed,'known':bool(known)}
    output = []
    for key,case in cases.items():
        rows = list(samples[key].values())
        usable = [r for r in rows if not r['changed']]
        result = {'kernel':key[0], 'footprint_bytes':key[1], 'raw_pairs':len(rows), 'usable_pairs':len(usable),
                  'clock_verified':bool(usable) and all(r['known'] for r in usable),
                  'changed_clock_pairs_excluded':sum(r['changed'] for r in rows)}
        if usable:
            ratios = [r['bias']/r['direct'] for r in usable]
            result.update(paired_overhead_pct=(median(ratios)-1)*100, ratio_min=min(ratios), ratio_max=max(ratios))
            if freq:
                scale = 1e9 / (freq * case['steps'])
                result.update(direct_ns_step=median(r['direct'] for r in usable)*scale,
                              bias_ns_step=median(r['bias'] for r in usable)*scale)
        output.append(result)
    complete = (bool(re.search(r'^\[SUMMARY\] BENCH-COMPLETE cleanup_failed=0',text,re.M)) and
                '[CORRECTNESS] PASS' in text and freq > 0 and set(cases) == EXPECTED and
                all(len(samples[k]) == 9 for k in EXPECTED))
    warnings = []
    if not complete: warnings.append('Incomplete run: do not treat the measurements as a completed feasibility test.')
    if not pinned: warnings.append('Benchmark thread was not pinned to the requested CPU core.')
    if any(not r['clock_verified'] for r in output): warnings.append('Some clocks were unknown/changed; repeat with fixed clocks before judging small differences.')
    if any(r['usable_pairs'] < 5 for r in output): warnings.append('Fewer than five usable pairs in at least one case.')
    return {'complete':complete, 'pinned':pinned, 'tick_frequency':freq, 'cases':output, 'warnings':warnings,
            'scope':'Synthetic addressing kernels only. Excludes full FEX register allocation, Wine boundaries, faults, SMC, and game rendering.',
            'game_fps_estimated':False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('log',type=Path)
    p.add_argument('--output',type=Path)
    args = p.parse_args()
    report = analyze(args.log.read_text(encoding='utf-8',errors='replace'))
    text = json.dumps(report,indent=2)+'\n'
    if args.output: args.output.write_text(text)
    print(text,end='')


if __name__ == '__main__': main()
