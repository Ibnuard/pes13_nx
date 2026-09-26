"""Decode the read-only PES timing probe; API presents are not simulation ticks."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import re
import struct


def analyze(data):
    samples = []
    game = None
    for line in data.decode(errors='replace').splitlines():
        if line.startswith('[FEX3-GAME] object='):
            game = {k: int(v, 16 if k in ('object','flags','scale_bits') else 10)
                    for k, v in re.findall(r'(\w+)=([0-9a-f-]+)', line)}
            game['scale_float'] = struct.unpack('<f', struct.pack('<I', game['scale_bits']))[0]
            if not math.isfinite(game['scale_float']):
                game['scale_float'] = None
        elif line.startswith('[FEX3-GCLOCK]') and game:
            clock = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)}
            span = clock['host_delta_us']
            clock['last_frame_clock_ratio'] = (round(clock['ring_delta_us'] / span, 4)
                                               if span and clock['ring_delta_us'] else None)
            samples.append({'game': game, 'clock': clock})
            game = None
        elif line.startswith('[FEX3-PACER]') and samples:
            samples[-1]['pacer'] = {
                k: int(v, 16 if k == 'flags' or k.endswith('_bits') else 10)
                for k, v in re.findall(r'(\w+)=([0-9a-f]+)', line)}
    return {
        'input_sha256': hashlib.sha256(data).hexdigest(), 'samples': samples,
        'limits': [
            'Last-frame clock ratios require continuous frames; frozen/reset rings are not fresh QPC reads.',
            'Scale bits identify the display/timing object; scoreboard or simulation speed is not measured directly.',
            'Non-atomic snapshots can straddle state changes. Repeated sustained values matter more than one sample.',
            'Pacer ring gaps are guest clock durations, not unique displayed frames or simulation-step counts.',
        ],
    }


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('log', type=Path)
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    text = json.dumps(analyze(args.log.read_bytes()), indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text)
