"""Decode the bounded PERF17 block snapshots without executing their contents."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import capstone

# PERF38 keeps the historical snapshot format, but its two measured math
# blocks need 12,296 native bytes. Older logs remain bounded by their own
# x86_bytes/arm_bytes metadata and the same contiguous-chunk validation.
MAX_X86_BYTES = 8192
MAX_ARM_BYTES = 16384

def extract(text):
    blocks = {}
    for line in text.splitlines():
        if line.startswith('[PERF17-BLOCK] '):
            fields = dict(re.findall(r'(\w+)=(\S+)', line))
            slot = int(fields['slot'])
            if slot in blocks:
                raise ValueError('Duplicate block slot; supply one run at a time')
            block = {key: int(value, 16 if key in ('guest', 'native', 'hash') else 10)
                     for key, value in fields.items()}
            if not (0 <= slot < 8 and 0 < block['x86_bytes'] <= MAX_X86_BYTES and
                    0 < block['arm_bytes'] <= MAX_ARM_BYTES):
                raise ValueError('Invalid snapshot bounds')
            block['chunks'] = {'x86': {}, 'arm64': {}}
            blocks[slot] = block
        elif line.startswith('[PERF17-CODE] '):
            fields = dict(re.findall(r'(\w+)=(\S+)', line))
            slot, kind, offset = int(fields['slot']), fields['kind'], int(fields['off'])
            if slot not in blocks or kind not in ('x86', 'arm64'):
                raise ValueError('Chunk without matching metadata')
            chunks = blocks[slot]['chunks'][kind]
            data = bytes.fromhex(fields['hex'])
            if offset in chunks or offset < 0 or offset % 64 or not (1 <= len(data) <= 64):
                raise ValueError('Duplicate or malformed chunk')
            chunks[offset] = data
    for block in blocks.values():
        for kind, size_key in (('x86', 'x86_bytes'), ('arm64', 'arm_bytes')):
            blob = bytearray()
            for offset, data in sorted(block['chunks'][kind].items()):
                if offset != len(blob):
                    raise ValueError('Missing/overlapping chunk')
                blob.extend(data)
            if len(blob) != block[size_key]:
                raise ValueError('Truncated snapshot; preserve the complete log')
            block[kind] = bytes(blob)
        del block['chunks']
    return blocks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    raw = args.log.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    blocks = extract(raw.decode('utf-8', errors='replace'))
    if not blocks:
        raise SystemExit('No completed PERF17 block snapshots found')
    target = args.output or Path(__file__).resolve().parents[1] / 'local/perf17/captures' / digest[:16]
    target.mkdir(parents=True, exist_ok=True)
    summary = {'log_sha256': digest, 'blocks': []}
    for slot, block in sorted(blocks.items()):
        metadata = {k: v for k, v in block.items() if k not in ('x86', 'arm64')}
        for kind, address, arch, mode in (
            ('x86', block['guest'], capstone.CS_ARCH_X86, capstone.CS_MODE_32),
            ('arm64', block['native'], capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM),
        ):
            blob = block[kind]
            stem = target / f'slot-{slot}-{kind}'
            stem.with_suffix('.bin').write_bytes(blob)
            md = capstone.Cs(arch, mode)
            md.skipdata = True
            listing = [f'{ins.address:08x}  {ins.bytes.hex():24s} {ins.mnemonic:10s} {ins.op_str}'
                       for ins in md.disasm(blob, address)]
            stem.with_suffix('.txt').write_text('\n'.join(listing) + '\n', encoding='utf-8')
            metadata[kind + '_sha256'] = hashlib.sha256(blob).hexdigest()
        summary['blocks'].append(metadata)
    (target / 'manifest.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(f'Decoded {len(blocks)} snapshots into {target}')
    print('ARM64 snapshots may end early and include embedded data; disassembly alone is not a semantic proof.')


if __name__ == '__main__':
    main()
