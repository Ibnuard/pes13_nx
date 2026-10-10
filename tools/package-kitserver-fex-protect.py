"""Package the validated Kit6 module and exact Kit5 NRO, without a ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('base','module','work','rollback','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    base=json.loads((args.base/'manifest.json').read_text())
    build=json.loads((args.module/'build.json').read_text())
    assert base['version']=='0.3.9-kit5' and base['passed'] and build['built']
    assert build['dll_sha256']==sha(args.module/'libwow64fex.dll')
    assert build['baseline_dll_sha256']==sha(args.rollback)
    assert base['nro_sha256']=='2d3b0002f268e72a7e3872d4be885880525a9c575e8f5c1b129ef33cc26af5b5'
    for name,digest in base['files'].items():assert sha(args.base/name)==digest,name
    for name,digest in build['candidate_sources'].items():assert sha(args.work/'source'/name)==digest,name
    for name,digest in build['adapter_sources'].items():assert sha(args.work/'adapter'/name)==digest,name
    for name,digest in build['build_scripts'].items():assert sha(root/'tools'/name)==digest,name
    receipts=('protect-roundtrip','alloc-arm64','imports','smc-arm64','profile-arm64','fpu-arm64','counter-arm64')
    for name in receipts:
        receipt=json.loads((args.module/'tests'/(name+'.json')).read_text())
        assert receipt['passed'],name
        if 'dll_sha256' in receipt:assert receipt['dll_sha256']==build['dll_sha256'],name
        if name=='protect-roundtrip':
            assert receipt['baseline_bug_reproduced'] and receipt['candidate']['cases']>=10
            for path,digest in receipt['source_hashes'].items():
                actual=(root/path if path.startswith('tests/') else
                        args.work/'source/FEXCore/include'/path if path.startswith('FEXCore/') else args.work/path)
                assert sha(actual)==digest,path
    assert not args.output.exists(),'Choose a new, empty output directory'
    args.output.mkdir(parents=True)
    def copy(source,name):
        dest=args.output/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    for name in base['files']:
        if name=='README.txt':continue
        copy(args.base/name,name)
    dll_path='switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
    copy(args.module/'libwow64fex.dll',dll_path)
    copy(args.rollback,'rollback/'+dll_path)
    for name in ('build.json','source-report.json'):copy(args.module/name,'evidence/kit6/'+name)
    for name in receipts:copy(args.module/'tests'/(name+'.json'),'evidence/kit6/'+name+'.json')
    for name in ('fex-runtime.log','crash.log'):
        if (args.base/name).exists():copy(args.base/name,'evidence/kit6/input-kit5-'+name)
    for name in build['candidate_sources']:copy(args.work/'source'/name,'source/kit6/fex/'+name)
    for name in build['frozen_sources']:
        if name not in build['candidate_sources']:copy(args.work/'source'/name,'source/kit6/fex/'+name)
    for name in build['adapter_sources']:copy(args.work/'adapter'/name,'source/kit6/adapter/'+name)
    for name in ('tools/build-kitserver-fex-protect.py','tools/fex_protect_roundtrip_patches.py',
                 'tools/package-kitserver-fex-protect.py','tests/fex_protect_roundtrip.py',
                 'tests/fex_protect_roundtrip.cpp','tests/fex_alloc.py','tests/fex_smc.py',
                 'tests/fex_fast_native.py','tests/fex_fpu_binary.py','tests/fex_counter.py'):
        copy(root/name,'source/kit6/'+name)
    copy(root/'docs/KITSERVER-KIT6-PROTECTION.md','docs/KITSERVER-KIT6-PROTECTION.md')
    (args.output/'README.txt').write_text('''Kit6 - perbaikan protection round trip pada FEX

Log Kit5 memperlihatkan rld.dll berhasil dimuat, lalu write gagal pada halaman
yang sudah menjadi read-only. Bug ubah/pulihkan izin memori berhasil
direproduksi di tes kode FEX lama dan teratasi pada kandidat ini.
Tes lokal lulus; keberhasilan Kitserver di Switch masih perlu dibuktikan.

CARA PASANG
1. Tutup PES13 lewat HOME > X > Close.
2. Salin SELURUH folder switch/ ke root SD, timpa kedua file:
   switch/pes13-fex/pes13-fex.nro
   switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll
   NRO tetap persis Kit5; perbaikan Kit6 ada di modul FEX yang ikut disalin.
3. Jalankan lewat NSP 32-bit no-alias yang sama, pilih Debug launch.
4. Launcher tetap menampilkan 0.3.9-kit5. Log modul harus memuat:
   [FEX-PROTECT] kit6 v1 guest protection round-trip; normal optimization
5. Setelah tes, simpan fex-runtime.log dan crash.log jika terjadi crash.

Pakai game dan DLL Kitserver yang sama dengan tes Kit5. Preset, optimisasi
FEX, renderer, dan kebijakan log normal/debug tidak diubah. Launch biasa
tetap tanpa penulisan log diagnostik. Save/pengaturan tetap fungsional.

RUNTIME FIXER
Check runtime akan menandai libwow64fex.dll eksperimen ini sebagai changed
karena katalog masih memakai versi produksi. Repair runtime akan mengganti
modul ini dengan versi produksi; jangan menjalankannya selama tes Kit6.
Jika sudah terlanjur Repair, salin kembali kedua file dari switch/ Kit6.

ROLLBACK
Untuk kembali ke Kit5, salin isi rollback/switch/ ke SD:/switch/.
NRO tidak perlu diganti karena binarinya tetap persis Kit5.

Rincian dan batas validasi: docs/KITSERVER-KIT6-PROTECTION.md.
Paket berbentuk folder, tanpa ZIP. Tidak menyertakan game atau rld.dll.
''',encoding='utf-8')
    files={str(p.relative_to(args.output)).replace('\\','/'):sha(p)
           for p in sorted(args.output.rglob('*')) if p.is_file()}
    assert sorted(name for name in files if name.startswith('switch/'))==sorted([
        'switch/pes13-fex/pes13-fex.nro',dll_path])
    manifest={'kind':'kit6-fex-protection-roundtrip','passed':True,'hardware_tested':False,
              'nro_version':'0.3.9-kit5','nro_sha256':base['nro_sha256'],
              'fex_sha256':build['dll_sha256'],'rollback_fex_sha256':build['baseline_dll_sha256'],
              'receipts':list(receipts),'files':files}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'directory':str(args.output.resolve()),'nro_unchanged':True,
                      'fex_sha256':manifest['fex_sha256'],'verified_files':len(files)}))


if __name__=='__main__':main()
