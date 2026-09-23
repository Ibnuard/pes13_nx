"""Validate complete, truncated and malformed bounded capture records."""
from pathlib import Path
import importlib.util

p = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('decode_perf17', p / 'tools/decode-perf17.py')
decoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decoder)
header = ('[PERF17-BLOCK] slot=1 region=0 bigblock=1 guest=112fb80 guest_size=66 '
          'native=82001000 native_size=4 hash=1234abcd x86_bytes=66 arm_bytes=4\n')
code = ('[PERF17-CODE] slot=1 kind=x86 off=0 hex=' + '90' * 64 + '\n'
        '[PERF17-CODE] slot=1 kind=x86 off=64 hex=90c3\n'
        '[PERF17-CODE] slot=1 kind=arm64 off=0 hex=c0035fd6\n')
blocks = decoder.extract(header + code)
assert blocks[1]['guest'] == 0x112fb80 and blocks[1]['hash'] == 0x1234abcd
assert blocks[1]['x86'] == b'\x90' * 65 + b'\xc3'
assert blocks[1]['arm64'] == bytes.fromhex('c0035fd6')
bad = (
    header + code.splitlines()[0],  # missing chunks
    header + code + code,          # duplicates
    code,                         # no metadata
    header + code.replace('off=64', 'off=65'),
    header + code.replace('hex=90c3', 'hex=90'),
    header.replace('x86_bytes=66', 'x86_bytes=100000') + code,
    header + header + code,
)
for item in bad:
    try:
        decoder.extract(item)
    except ValueError:
        pass
    else:
        raise AssertionError('Malformed log was accepted')
print('PERF17 decoder: complete round trip and seven malformed/truncated cases PASS')
