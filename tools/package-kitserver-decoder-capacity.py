"""Package Kit16 FEX and the exact Kit15 host, with verified test receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','module','work','evidence','native-elf','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    a.output.resolve().relative_to((ROOT/'dist').resolve())
    assert not a.output.exists(),'Use a new dist subdirectory'
    b=json.loads((a.base/'manifest.json').read_text())
    m=json.loads((a.module/'build.json').read_text())
    assert b['passed'] and b['kind']=='kit15-commit-recovery' and b['version']=='0.3.9-kit15'
    assert m['built'] and m['kind']=='kit16-decoder-capacity'
    dll='switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
    nro='switch/pes13-fex/pes13-fex.nro'
    assert sha(a.native_elf)==b['native_elf_sha256']
    assert sha(a.base/nro)==b['nro_sha256']
    assert sha(a.base/dll)==m['baseline_dll_sha256']==b['fex_sha256']
    assert sha(a.module/'libwow64fex.dll')==m['dll_sha256']
    assert b'[FEX3-SCRATCH] v2 kit16' in (a.module/'libwow64fex.dll').read_bytes()
    for name,digest in b['files'].items(): assert sha(a.base/name)==digest,name
    for name,digest in m['candidate_sources'].items(): assert sha(a.work/'source'/name)==digest,name
    for name,digest in m['adapter_sources'].items(): assert sha(a.work/'adapter'/name)==digest,name
    for name,digest in m['build_scripts'].items(): assert sha(ROOT/'tools'/name)==digest,name
    receipts=('decoder-host','decoder-arm64','native-scratch-arm64','scratch-arm64',
              'alloc-arm64','smc-arm64','counter-arm64','fpu-arm64','profile-arm64','imports')
    source_files=set(m['build_scripts'])
    test_files={'tests/fex_decoder_capacity.cpp','tests/fex_decoder_capacity_host.py',
        'tests/fex_decoder_capacity_binary.py','tests/fex_decoder_native_scratch.py',
        'tests/fex_protect_roundtrip.py','tests/fex_scratch.py','tests/fex_lookup.py','tests/fex_memory.py',
        'tests/fex_alloc.py','tests/fex_smc.py','tests/fex_counter.py','tests/fex_fpu_binary.py',
        'tests/fex_fast_native.py','tests/fex_jit_native.py','tests/fextendo_scratch_binary.py',
        'tests/fextendo_silent.py'}
    for name in receipts:
        r=json.loads((a.module/'tests'/(name+'.json')).read_text());assert r['passed'],name
        if 'dll_sha256' in r: assert r['dll_sha256']==m['dll_sha256'],name
        if 'native_elf_sha256' in r: assert r['native_elf_sha256']==b['native_elf_sha256'],name
        for field in ('sources','test_sources'):
            for src,digest in r.get(field,{}).items():
                assert sha(ROOT/src)==digest,src
                test_files.add(src)
        if name=='decoder-host':
            assert r['cases']==384 and r['all_decode_traces_equal'] and r['asan_ubsan']
            assert r['source_hashes']['source']==m['candidate_sources']['FEXCore/Source/Interface/Core/Frontend.cpp']
            assert r['source_hashes']['before']==m['baseline_changed_sources']['FEXCore/Source/Interface/Core/Frontend.cpp']
            assert r['adapter_sha256']==m['adapter_sources']['horizon_decode_set.h']
        if name=='decoder-arm64':
            assert r['baseline_dll_sha256']==m['baseline_dll_sha256']
            assert r['results']['before']['pressure']['stopped']
            assert r['results']['candidate']['pressure']['served']==8
        if name=='imports':
            assert r['modules']['libwow64fex.dll']['sha256']==m['dll_sha256'] and not r['issues']
            for file in r['modules'].values():assert sha(Path(file['path']))==file['sha256']
    analysis=json.loads((a.evidence/'device-analysis.json').read_text())
    assert analysis['passed'] and sha(a.evidence/'kit15-device.log')==analysis['input_sha256']
    a.output.mkdir(parents=True)
    def copy(source,name):
        target=a.output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for name in b['files']:
        if name=='README.txt' or name.startswith(('rollback/','switch/')):continue
        copy(a.base/name,name)
    copy(a.base/nro,nro);copy(a.module/'libwow64fex.dll',dll)
    copy(a.base/nro,'rollback/'+nro);copy(a.base/dll,'rollback/'+dll)
    copy(a.base/'manifest.json','evidence/kit16/kit15-manifest.json')
    for name in ('build.json','source-report.json'):copy(a.module/name,'evidence/kit16/'+name)
    for name in receipts:copy(a.module/'tests'/(name+'.json'),'evidence/kit16/'+name+'.json')
    for name in ('device-analysis.json','kit15-device.log'):copy(a.evidence/name,'evidence/kit16/'+name)
    for name in m['candidate_sources']:copy(a.work/'source'/name,'source/kit16/fex/'+name)
    for name in source_files:copy(ROOT/'tools'/name,'source/kit16/tools/'+name)
    for name in test_files:copy(ROOT/name,'source/kit16/'+name)
    for name in ('tools/package-kitserver-decoder-capacity.py','tools/analyze-kit15-memory.py','tools/audit-fex-imports.py','tools/fex_toolchain.py'):
        copy(ROOT/name,'source/kit16/'+name)
    copy(ROOT/'docs/KITSERVER-KIT16-DECODER-CAPACITY.md','docs/KITSERVER-KIT16-DECODER-CAPACITY.md')
    (a.output/'README.txt').write_text('''Kit16 - buffer decoder FEX sesuai kebutuhan blok

Log Kit15: sekitar detik 122, permintaan buffer compiler 8 MiB gagal dan
thread dihentikan. Kit16 mengurangi buffer decoder pada maxinst=128 dari
8 MiB menjadi 16 KiB. Batas instruksi, preset dan renderer tetap sama.

Build dan tes lokal lulus. Belum diuji di Switch; keberhasilan kick-off
dan penghematan memori seluruh proses belum terukur.

PASANG
1. Tutup PES lewat HOME > X > Close.
2. Salin folder switch/ ke root SD dan timpa DUA file yang disertakan:
   switch/pes13-fex/pes13-fex.nro
   switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll
3. NRO tetap persis Kit15. Perbaikan Kit16 ada di libwow64fex.dll.
   Launcher masih menampilkan 0.3.9-kit15; ini memang sesuai paket.
4. Buka NSP 32-bit no-alias lalu Debug launch. Cari penanda log:
   [FEX3-SCRATCH] v2 kit16 decoder capacity follows block limit
5. Pakai Medium, renderer, clock dan patch yang sama. Coba Exhibition ->
   game plan -> kick-off. Kirim fex-runtime.log, termasuk jika berhasil.
6. Jika macet dan HOME masih merespons, tunggu sekitar 15 detik lalu tutup.

Launch biasa tetap tanpa log diagnostik. Pengaturan dan save tidak ditimpa.
Check runtime dapat menandai DLL eksperimen sebagai changed. Repair runtime
akan menggantinya; jika Repair dijalankan, salin kembali paket ini.

Rollback: salin rollback/switch/ ke root SD untuk mengembalikan pasangan
NRO dan DLL Kit15. Tidak ada ZIP maupun file game/plugin dalam paket ini.
Analisis dan batas pengujian ada di docs/KITSERVER-KIT16-DECODER-CAPACITY.md.
''',encoding='utf-8')
    files={p.relative_to(a.output).as_posix():sha(p) for p in sorted(a.output.rglob('*')) if p.is_file()}
    assert sorted(n for n in files if n.startswith('switch/'))==sorted((nro,dll))
    manifest=dict(passed=True,kind='kit16-decoder-capacity',version='0.3.9-kit16',
        nro_version='0.3.9-kit15',nro_unchanged=True,nro_sha256=b['nro_sha256'],
        native_elf_sha256=b['native_elf_sha256'],fex_sha256=m['dll_sha256'],
        rollback_nro_sha256=b['nro_sha256'],rollback_fex_sha256=b['fex_sha256'],
        hardware_tested=False,freeze_fixed=False,receipts=list(receipts),files=files)
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for name,digest in files.items():assert sha(a.output/name)==digest,name
    print(json.dumps({'directory':str(a.output),'nro_unchanged':True,
        'fex_sha256':m['dll_sha256'],'verified_files':len(files)}))


if __name__=='__main__':main()
