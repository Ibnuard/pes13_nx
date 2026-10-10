"""Package LW5 diagnostics and a reversible, single-module Kitserver control."""
import argparse, difflib, hashlib, json, re, shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
NRO='switch/pes13-fex/pes13-low-window.nro'
CONFIG='switch/pes13-fex/drive_c/PES13/kitserver13/config.txt'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())

def control(game):
    inputs={name:sha(game/name) for name in ('pes2013.exe','kitserver13/kserv.dll','kitserver13/config.txt')}
    assert inputs['pes2013.exe']=='c1400a5112259868d4807b7448807b0996570ea64272154d33c0cb1cd99994a7'
    assert inputs['kitserver13/kserv.dll']=='06a6fea90a0c4eedba6e2b3d205052f2f273cb9a7427fd01b66416efb4a31123'
    original=(game/'kitserver13/config.txt').read_bytes()
    section=b'';lines=[];count=0;prefix=b'; LW5 diagnostic control - custom GDB kits disabled: '
    for line in original.splitlines(keepends=True):
        stripped=line.strip()
        if stripped.startswith(b'['):section=stripped.lower()
        if section==b'[kload]' and re.fullmatch(rb'dll\s*=\s*kserv(?:\.dll)?\s*',stripped,re.I):
            line=prefix+line;count+=1
        lines.append(line)
    altered=b''.join(lines)
    assert count==1 and altered.replace(prefix,b'')==original
    return original,altered,dict(input_sha256=inputs,
        config_after_sha256=hashlib.sha256(altered).hexdigest(),hardware_tested=False,
        change='Disable only the kserv module; custom GDB kits may look different. No game files removed.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('runtime','previous-runtime','game','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--previous',type=Path,default=ROOT/'dist/pes13-low-window-v4-kitserver-control')
    parser.add_argument('--evidence',type=Path,default=ROOT/'local/lw5-newpatch-controller')
    a=parser.parse_args();a.output.resolve().relative_to((ROOT/'dist').resolve())
    assert not a.output.exists(),'Use a fresh package directory'
    build=read(a.runtime/'build.json');previous=read(a.previous/'package.json')
    assert build['built'] and build['version']=='0.3.9-lw5'
    assert previous['version']=='0.3.9-lw4' and previous['abi']=='fxtmem-v1'
    assert sha(a.runtime/'native-build/wine-nx-runtime.elf')==build['elf_sha256']
    assert sha(a.runtime/'pes13-fex.nro')==build['nro_sha256']
    assert sha(a.previous/NRO)==previous['payload'][NRO]==read(a.previous_runtime/'build.json')['nro_sha256']
    for rel,digest in previous['files'].items():
        if rel.startswith(('source/','licenses/')):assert sha(a.previous/rel)==digest,rel
    for rel,digest in build['inputs'].items():assert sha(ROOT/rel)==digest,rel
    tests=('binary-tests.json','policy-tests.json','wait-binary.json','assets-binary.json','pipe-binary.json')
    for name in tests:
        result=read(a.evidence/name)
        assert result['passed'] and result.get('elf_sha256',result.get('native_elf_sha256'))==build['elf_sha256'],name
    for name in ('wait-host.json','assets-host.json'):
        result=read(a.evidence/name);assert result['passed']
        for rel,digest in result['sources'].items():assert sha(ROOT/rel)==digest,rel
    old,new=(read(p/'prepared.json') for p in (a.previous_runtime,a.runtime))
    native={n for n in set(old['after'])|set(new['after']) if old['after'].get(n)!=new['after'].get(n)}
    feature={n for n in set(old['feature_after'])|set(new['feature_after'])
             if old['feature_after'].get(n)!=new['feature_after'].get(n)}
    assert native=={'wine-nx-probe/source/runtime.c','wine-nx-probe/CMakeLists.txt',
                    'dlls/ntdll/unix/horizon.c','dlls/ntdll/unix/horizon_asset_probe.h'},native
    assert feature=={'src/runtime/fextendo_wait_probe.h'},feature
    observer=(a.runtime/'feature/src/runtime/fextendo_wait_probe.h').read_text()
    assert observer.count('pes_vk_work_add(')==1 and observer.count('fx_wait_error_record(r);')==1
    # Check all prepared source inputs, not just changed files.
    for folder,key in (('native-source','after'),('feature','feature_after')):
        for rel,digest in new[key].items():assert sha(a.runtime/folder/rel)==digest,rel
    original,altered,comparison=control(a.game)
    a.output.mkdir(parents=True)
    def put(rel,data):
        target=a.output/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    def copy(source,rel):put(rel,source.read_bytes())
    def jsonfile(rel,obj):put(rel,(json.dumps(obj,indent=2)+'\n').encode())
    copy(a.runtime/'pes13-fex.nro',NRO);copy(a.previous/NRO,'rollback/'+NRO)
    put('kit-control/'+CONFIG,altered);put('kit-rollback/'+CONFIG,original)
    jsonfile('evidence/kit-control.json',comparison)
    for name in ('build.json','prepared.json'):copy(a.runtime/name,'evidence/'+name)
    for name in tests+('wait-host.json','assets-host.json','diagnosis.json'):
        copy(a.evidence/name,'evidence/'+name)
    copy(a.evidence/'parsed/analysis.json','evidence/device-analysis.json')
    copy(a.previous/'package.json','evidence/lw4-package.json')
    services={}
    for table in ('dlls/ntdll/ntsyscalls.h','dlls/win32u/win32syscalls.h'):
        for index,name in re.findall(r'SYSCALL_ENTRY\(\s*(0x[0-9a-f]+),\s*(\w+),',
                                    (a.runtime/'native-source'/table).read_text()):
            key=format(int(index,16),'x')
            assert key not in services or services[key]==name
            services[key]=name
    jsonfile('evidence/nt-services.json',services)
    for directory in ('source','licenses'):
        if (a.previous/directory).exists():shutil.copytree(a.previous/directory,a.output/directory/'lw4-baseline')
    sources=set(build['inputs'])|{'tools/package-pes-low-window-assets.py',
        'tests/fextendo_wait_probe.c','tests/fextendo_wait_probe_host.py','tests/fextendo_wait_probe_binary.py',
        'tests/horizon_asset_probe.c','tests/horizon_asset_probe_host.py','tests/pes_asset_probe_binary.py',
        'tests/pes_low_window_binary.py','tests/pes_gameplaytool_binary.py',
        'tests/fextendo_anon_pipe_binary.py','docs/PES13-LOW-WINDOW-V5-ASSET-TRACE.md'}
    for rel in sorted(sources):copy(ROOT/rel,'source/lw5/'+rel)
    delta=[]
    for folder,names in (('native-source',native),('feature',feature)):
        for rel in sorted(names):
            before,after=a.previous_runtime/folder/rel,a.runtime/folder/rel
            delta.extend(difflib.unified_diff(before.read_text().splitlines(keepends=True) if before.exists() else [],
                after.read_text().splitlines(keepends=True),fromfile='a/'+folder+'/'+rel,tofile='b/'+folder+'/'+rel))
            copy(after,'source/generated/'+folder+'/'+rel)
    put('source/lw5.patch',''.join(delta).encode())
    copy(ROOT/'docs/PES13-LOW-WINDOW-V5-ASSET-TRACE.md','DETAILS.txt')
    put('README.txt',('LW5 - diagnosis Exhibition > controller, bukan klaim fix crash.\n\n'
        '1. Salin folder switch ke root SD. Gunakan tile low-window yang sama.\n'
        '2. Debug launch, Medium, renderer/clock tetap; ulangi Exhibition > controller.\n'
        '   Simpan fex-runtime.log dan crash.log jika tersedia.\n'
        '3. Jika masih macet, simpan log pertama dengan nama berbeda. Salin folder\n'
        '   switch dari kit-control ke root SD lalu ulangi rute dan simpan log kedua.\n'
        '   Pembanding hanya mematikan kserv; kit GDB custom bisa tampil berbeda.\n'
        '4. kit-rollback/switch mengembalikan config asli patch baru ini.\n'
        '   rollback/switch mengembalikan NRO LW4.\n\n'
        'Jangan salin seluruh folder paket ke SD. Hanya folder switch yang dipilih.\n'
        'Launch biasa tanpa file diagnostik; catatan tambahan hanya Debug launch.\n'
        'Tidak perlu mengganti NSP atau Atmosphere. Tidak ada DLL/game asset di paket.\n'
        'Build + host/ARM64 checks selesai; hasil di Switch masih perlu diuji.\n').encode())
    files={p.relative_to(a.output).as_posix():sha(p) for p in sorted(a.output.rglob('*')) if p.is_file()}
    payload={n:h for n,h in files.items() if n.startswith('switch/')}
    assert payload=={NRO:build['nro_sha256']}
    assert not any(a.output.rglob('*.dll')) and not any(a.output.rglob('*.zip')) and not any(a.output.rglob('*.nsp'))
    jsonfile('package.json',dict(built=True,version=build['version'],abi='fxtmem-v1',hardware_tested=False,
        crash_fix_verified=False,game_speed_fix_verified=False,game_assets_changed=False,
        fex_changed=False,dxvk_changed=False,clock_scaled=False,
        native_elf_sha256=build['elf_sha256'],previous_nro_sha256=previous['payload'][NRO],
        change='Debug-only retained NT failures and bounded pipe snapshots; optional kserv-off control.',
        payload=payload,files=files))
    files['package.json']=sha(a.output/'package.json')
    put('SHA256SUMS.txt',''.join(f'{digest}  {rel}\n' for rel,digest in sorted(files.items())).encode())
    for rel,digest in files.items():assert sha(a.output/rel)==digest,rel
    for rel,digest in comparison['input_sha256'].items():assert sha(a.game/rel)==digest,rel
    print(f'Packaged LW5: {len(files)} verified files; no ZIP; active game unchanged.')

if __name__=='__main__':main()
