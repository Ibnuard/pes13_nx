"""Check the decoder accepts PERF38's complete math block and rejects truncation."""
from pathlib import Path
import importlib.util
p=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('capture',p/'tools/decode-perf17.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
guest=bytes.fromhex('90')*1113
native=bytes.fromhex('1f2003d5')*3074 # 12,296 bytes; actual hot-block size
def chunks(slot,kind,data):
    return ''.join(f'[PERF17-CODE] slot={slot} kind={kind} off={off} hex={data[off:off+64].hex()}\n'
                   for off in range(0,len(data),64))
head=(f'[PERF17-BLOCK] slot=6 region=6 bigblock=0 guest=113027b '
      f'guest_size=1113 native=82001000 native_size=12296 hash=1234abcd '
      f'x86_bytes={len(guest)} arm_bytes={len(native)}\n')
log=head+chunks(6,'x86',guest)+chunks(6,'arm64',native)
parsed=module.extract(log)
assert parsed[6]['x86']==guest and parsed[6]['arm64']==native
for bad in (log.rsplit('\n',2)[0]+'\n',log.replace('arm_bytes=12296','arm_bytes=16385'),
            log+chunks(6,'arm64',native[:64])):
    try:module.extract(bad)
    except ValueError:pass
    else:raise AssertionError('Accepted truncated, oversized or duplicate capture')
print('PERF38 full 12,296-byte capture and malformed-log checks PASS')
