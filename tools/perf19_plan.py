"""Audit the complete captured matrix block and plan size-preserving branches.

This reads captured code; it does not run or change the game executable.
"""
from pathlib import Path
import hashlib
import json
import re
import struct
import capstone


def fnv64(blob):
    result = 0xcbf29ce484222325
    for byte in blob:
        result = ((result ^ byte) * 0x100000001b3) & 0xffffffffffffffff
    return result


def plan(native):
    assert len(native) == 7064
    assert hashlib.sha256(native).hexdigest() == '5d488141f88cca08425c7f3d64b5cce4f74947fbf6d1ee4b397c0c981563db41'
    words = list(struct.unpack('<' + 'I' * (len(native)//4), native))
    setups = [i for i, w in enumerate(words) if w == 0xb9431c01]
    restores = [i for i, w in enumerate(words) if w == 0xd51b4404]
    assert len(setups) == len(restores) == 143
    covered = set()
    for index, (start, end) in enumerate(zip(setups, restores)):
        assert words[start:start+2] == [0xb9431c01, 0x330a2c21]
        assert words[start+2:start+4] in ([0x53010425, 0x331f0025], [0x53010422, 0x331f0022])
        assert words[start+4:start+6] == [0xd53b4401, 0xaa0103e4]
        assert words[start+6] in (0xb36a04a1, 0xb36a0441)
        assert words[start+7] == 0xd51b4401 and start+8 < end
        assert index == 142 or end < setups[index+1]
        covered.update(range(start, start+8)); covered.add(end)
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    listing = list(md.disasm(native, 0))
    assert len(listing) * 4 == len(native)
    for ins in listing:
        i = ins.address//4
        if setups[0] <= i <= restores[-1] and i not in covered:
            assert not re.search(r'\b[wx][1245]\b', ins.op_str), (ins.address, ins.mnemonic, ins.op_str)
            assert ins.mnemonic not in ('b', 'bl', 'br', 'blr', 'ret', 'mrs', 'msr')
            assert not ins.mnemonic.startswith(('cb', 'tb', 'b.'))
    patched = words.copy()
    for start in setups[1:]: patched[start] = 0x14000008  # skip 8 setup instructions
    for end in restores[:-1]:
        patched[end] = 0x14000009 if end+1 in setups else 0xd503201f
    output = struct.pack('<' + 'I'*len(patched), *patched)
    stop = next(i.address for i in listing if i.mnemonic == 'ldr' and i.op_str.startswith('x3, #'))
    return output, {'setups': setups, 'restores': restores, 'stop_before_return_lookup': stop,
                    'native_fnv64': hex(fnv64(native)), 'patched_fnv64': hex(fnv64(output)),
                    'patched_sha256': hashlib.sha256(output).hexdigest(),
                    'bytes_changed': sum(a != b for a, b in zip(native, output))}


if __name__ == '__main__':
    p = Path(__file__).resolve().parents[1]
    native = (p/'local/perf18/captures/slot-0-arm64.bin').read_bytes()
    guest = (p/'local/perf18/captures/slot-0-x86.bin').read_bytes()
    patched, info = plan(native)
    info['guest_fnv64'] = hex(fnv64(guest))
    (p/'local/perf19/matrix-plan.json').write_text(json.dumps(info, indent=2)+'\n')
    (p/'local/perf19/matrix-planned.bin').write_bytes(patched)
    print({k:v for k,v in info.items() if k not in ('setups','restores')})
