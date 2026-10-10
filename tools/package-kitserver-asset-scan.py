"""Package tested Kit9 with unchanged Kit6 FEX and a Kit8 rollback NRO."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('build','native','kit8','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();old=json.loads((a.kit8/'manifest.json').read_text())
    assert old['passed'] and old['kind']=='kit8-directory-metadata' and old['same_kit6_module']
    nro='switch/pes13-fex/pes13-fex.nro';dll='switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
    assert sha(a.kit8/dll)==old['fex_sha256']==old['files'][dll]
    assert sha(a.kit8/nro)==old['nro_sha256']==old['files'][nro]
    spec=importlib.util.spec_from_file_location('runtime_package',ROOT/'tools/package-runtime-fixer.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.package(a.build,a.native,a.output)
    manifest=json.loads((a.output/'manifest.json').read_text());assert manifest['version']=='0.3.9-kit9'
    def copy(src,name):
        target=a.output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
    copy(a.kit8/dll,dll);copy(a.kit8/nro,'rollback/'+nro)
    for name,digest in old['files'].items():
        if not (name.startswith('evidence/kit6/') or name.startswith('source/kit6/')):continue
        assert sha(a.kit8/name)==digest,name
        copy(a.kit8/name,name)
    copy(ROOT/'tools/package-kitserver-asset-scan.py','source/tools/package-kitserver-asset-scan.py')
    copy(ROOT/'docs/KITSERVER-KIT9-ASSET-SCAN.md','docs/KITSERVER-KIT9-ASSET-SCAN.md')
    (a.output/'README.txt').write_text('''FEXTendo 0.3.9-kit9 - Kitserver asset filename scan

Di log Kit8, antara detik 20-82, 98.7% waktu habis membaca tanggal file SD.
AFS2FS yang diperiksa hanya memakai nama/atribut saat membangun indeks BIN.
Kit9 melewati pembacaan tanggal untuk daftar file Kitserver img/<arsip>.img
tersebut. Tanggal pada hasil listing aset ini kosong; query file langsung dan
folder lain tetap memakai tanggal asli. Tidak mengubah file game/Kitserver.

PASANG
1. Dengan aplikasi sudah tertutup, salin isi switch/ ke root SD.
2. Timpa pes13-fex.nro dan drive_c/windows/system32/libwow64fex.dll.
3. Jalankan NSP 32-bit no-alias, lalu Debug launch untuk satu tes.
4. Pastikan versi 0.3.9-kit9 dan marker [HZDIR] v4 asset_scan=1.
5. Jika belum berhasil, simpan fex-runtime.log hasil run ini. Counter
   [HZDIR-COST] asset_names menunjukkan jalur baru benar-benar terpakai.

Launch biasa tanpa log diagnostik. FEX Kit6, optimasi dan preset tetap sama.
Build/tes lokal lulus; hard freeze dan kecepatan startup belum diuji di Switch.
Jika HOME ikut tidak merespons, jangan terus dibiarkan menunggu.

KONTROL / ROLLBACK
Untuk memulihkan pembacaan tanggal seperti Kit8, tambahkan pada configuration.ini:
[compatibility]
kitserver_fast_scan=0

Atau salin rollback/switch/ ke SD:/switch/ untuk mengembalikan NRO Kit8.
Jangan Repair runtime saat perbandingan; Repair mengganti modul FEX eksperimen.
Jika terlanjur Repair, salin lagi dua file dari switch/ paket ini.

Rincian bukti dan batas validasi: docs/KITSERVER-KIT9-ASSET-SCAN.md.
Folder siap salin, tanpa ZIP; tidak berisi file game/patch.
''',encoding='utf-8')
    manifest.update(kind='kit9-kitserver-asset-scan',fex_sha256=old['fex_sha256'],same_kit6_module=True,
                    hardware_tested=False,rollback_nro_sha256=old['nro_sha256'])
    manifest['files']={f.relative_to(a.output).as_posix():sha(f) for f in sorted(a.output.rglob('*'))
                       if f.is_file() and f!=a.output/'manifest.json'}
    assert sorted(n for n in manifest['files'] if n.startswith('switch/'))==sorted((nro,dll))
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for name,digest in manifest['files'].items():assert sha(a.output/name)==digest,name
    print(json.dumps({'directory':str(a.output),'nro_sha256':manifest['nro_sha256'],
                      'fex_sha256':manifest['fex_sha256'],'verified_files':len(manifest['files'])}))


if __name__=='__main__':main()
