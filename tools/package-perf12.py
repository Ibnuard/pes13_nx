"""Package server suspend and the rebuilt historical fallback behavior."""
from pathlib import Path
import hashlib
import json
import zipfile
import struct
import pefile

p=Path(__file__).resolve().parents[1]
old=(p/'local/perf12/ntdll-perf3-rollback.dll').read_bytes()
new=(p/'local/perf12/ntdll-server-suspend.dll').read_bytes()
sha=lambda b:hashlib.sha256(b).hexdigest()
assert b'pes13-nx-perf3-fast-suspend' in old
assert b'pes13-nx-perf3-fast-suspend' not in new
assert new!=old
def interface(data):
    pe=pefile.PE(data=data)
    assert pe.FILE_HEADER.Machine==0xaa64
    exports={(e.name,e.ordinal,e.forwarder) for e in pe.DIRECTORY_ENTRY_EXPORT.symbols}
    imports={(field,d.dll,i.name,i.ordinal if not i.name else None)
        for field in ('DIRECTORY_ENTRY_IMPORT','DIRECTORY_ENTRY_DELAY_IMPORT')
        for d in getattr(pe,field,[]) for i in d.imports}
    assert any(e.name==b'RtlWow64SuspendThread' for e in pe.DIRECTORY_ENTRY_EXPORT.symbols)
    return exports,imports
assert interface(old)==interface(new),'PE interface drift'
pe=pefile.PE(data=new)
exports={e.name:e.address for e in pe.DIRECTORY_ENTRY_EXPORT.symbols}
wrapper=exports[b'RtlWow64SuspendThread']
instruction=struct.unpack('<I',pe.get_data(wrapper,4))[0]
assert instruction & 0xfc000000 == 0x14000000, 'Expected ARM64 tail branch'
offset=instruction & 0x3ffffff
if offset & 0x2000000: offset-=0x4000000
assert wrapper+4*offset==exports[b'NtSuspendThread'], 'Wrong linked branch target'
prefix='switch/pes13-nx/'
for variant,dll in [('suspend-status',new),('rollback',old)]:
    files={prefix+'drive_c/windows/system32/ntdll.dll':dll,
           prefix+'profile.txt':b'0\n',prefix+'perf8-turbo.txt':b'0\n',
           prefix+'drive_c/PES13/pes2013.wine-nx.txt':(p/'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes(),
           'PERF12.md':(p/'docs/PERF12.md').read_bytes()}
    files['PERF12-manifest.json']=json.dumps({'variant':variant,'hardware_tested':False,
       'runtime':'PERF11 unchanged','rebuilt_fallback_ntdll_sha256':sha(old),'test_ntdll_sha256':sha(new),
       'rollback':'Rebuilt PERF3 fallback function; not byte-identical to the deleted historical DLL',
       'historical_fallback_sha256':'c3361b6bb273df8a1c4f6b8ed901f4939abb9eb7570218f0c08117242056c66e',
       'pe_interface_unchanged':True,'files':{n:sha(b) for n,b in files.items()}},indent=2).encode()
    target=p/'dist'/f'pes13-perf12-{variant}.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in files.items():z.writestr(n,b)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert all(z.read(n)==b for n,b in files.items())
    print(target,sha(target.read_bytes()))
