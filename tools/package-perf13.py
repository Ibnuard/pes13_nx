"""Package PERF13's suspend backoff with an exact PERF12 rollback."""
from pathlib import Path
import hashlib
import json
import zipfile
import pefile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

p = Path(__file__).resolve().parents[1]
new = (p/'local/perf13/ntdll-suspend-backoff.dll').read_bytes()
old = (p/'local/perf13/ntdll-perf12-rollback.dll').read_bytes()
sha = lambda b: hashlib.sha256(b).hexdigest()
assert sha(old) == '613a22358e6cdca18bb6bb1fc8522b5d79cf08e485e309997c2533b04ffca855'
assert old == (p/'local/perf12/ntdll-server-suspend.dll').read_bytes()
assert old != new
assert b'pes13-nx-perf3-fast-suspend' not in new

def interface(data):
    pe = pefile.PE(data=data)
    assert pe.FILE_HEADER.Machine == 0xaa64
    exports = {(e.name, e.ordinal, e.forwarder) for e in pe.DIRECTORY_ENTRY_EXPORT.symbols}
    imports = {(field, d.dll, i.name, i.ordinal if not i.name else None)
               for field in ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT')
               for d in getattr(pe, field, []) for i in d.imports}
    return exports, imports

assert interface(new) == interface(old), 'PE interface drift'
pe = pefile.PE(data=new)
exports = {e.name: e.address for e in pe.DIRECTORY_ENTRY_EXPORT.symbols}
begin = exports[b'RtlWow64SuspendThread']
# pefile does not expose ARM64 exception entries in this installation. Decode
# this small wrapper through its first return, bounded to 256 bytes, and check
# that every local branch stays inside it.
decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
instructions = []
for instruction in decoder.disasm(pe.get_data(begin, 256), begin):
    instructions.append(instruction)
    if instruction.mnemonic == 'ret':
        break
assert instructions and instructions[-1].mnemonic == 'ret'
for instruction in instructions:
    if instruction.mnemonic == 'b' or instruction.mnemonic.startswith('b.'):
        assert begin <= int(instruction.op_str.lstrip('#'), 0) <= instructions[-1].address
targets = {int(i.op_str.lstrip('#'), 0) for i in instructions if i.mnemonic == 'bl'}
assert targets == {exports[b'NtSuspendThread'], exports[b'NtDelayExecution']}, targets
(p/'local/perf13/linked-wrapper.txt').write_text('\n'.join(
    f'{i.address:08x} {i.mnemonic} {i.op_str}' for i in instructions)+'\n')

config = (p/'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes()
assert b'profile=0' in config and b'verbose=0' in config
prefix = 'switch/pes13-nx/'
for name, dll in [('suspend-backoff', new), ('rollback-perf12', old)]:
    files = {
        prefix+'drive_c/windows/system32/ntdll.dll': dll,
        prefix+'profile.txt': b'0\n', prefix+'perf8-turbo.txt': b'0\n',
        prefix+'drive_c/PES13/pes2013.wine-nx.txt': config,
        'PERF13.md': (p/'docs/PERF13.md').read_bytes(),
    }
    files['PERF13-manifest.json'] = json.dumps({
        'variant': name, 'hardware_tested': False,
        'runtime': 'PERF11 NRO unchanged; ARM64 PE DLL experiment',
        'delay_on_status': 'STATUS_NOT_SUPPORTED', 'delay_requested_ms': 1 if name == 'suspend-backoff' else 0,
        'test_ntdll_sha256': sha(new), 'perf12_ntdll_sha256': sha(old),
        'rollback_byte_identical_to_perf12': True,
        'pe_interface_unchanged': True,
        'files': {n: sha(b) for n, b in files.items()},
    }, indent=2).encode()
    target = p/'dist'/f'pes13-perf13-{name}.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, b in files.items():
            z.writestr(n, b)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert set(z.namelist()) == set(files)
        assert all(z.read(n) == b for n, b in files.items())
    print(target, sha(target.read_bytes()))
