"""Package Kit11 VA headroom candidate with exact FEX and Kit10 rollback."""
import argparse,hashlib,importlib.util,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('build','native','kit10','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();old=json.loads((a.kit10/'manifest.json').read_text())
    assert old['passed'] and old['kind']=='kit10-menu-wait-probe' and old['same_kit6_module']
    nro='switch/pes13-fex/pes13-fex.nro';dll='switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
    assert sha(a.kit10/dll)==old['fex_sha256']==old['files'][dll]
    assert sha(a.kit10/nro)==old['nro_sha256']==old['files'][nro]
    spec=importlib.util.spec_from_file_location('runtime_package',ROOT/'tools/package-runtime-fixer.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.package(a.build,a.native,a.output)
    manifest=json.loads((a.output/'manifest.json').read_text());assert manifest['version']=='0.3.9-kit11'
    def copy(src,name):
        target=a.output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
    copy(a.kit10/dll,dll);copy(a.kit10/nro,'rollback/'+nro)
    for name,digest in old['files'].items():
        if name.startswith(('evidence/kit6/','source/kit6/')):
            assert sha(a.kit10/name)==digest,name
            copy(a.kit10/name,name)
    copy(ROOT/'tools/package-kitserver-guest-va.py','source/tools/package-kitserver-guest-va.py')
    copy(ROOT/'docs/KITSERVER-KIT11-GUEST-VA.md','docs/KITSERVER-KIT11-GUEST-VA.md')
    copy(a.build/'evidence/device-analysis.json','evidence/kit11/device-analysis.json')
    (a.output/'README.txt').write_text('''FEXTendo 0.3.9-kit11 - Guest VA headroom

Log Kit10: reservasi alamat 14,69 MiB gagal pada detik 75,787, lalu thread
pembaca file sibuk berulang saat menuju halaman controller. Frame presentation
masih berjalan; ini tidak sama dengan seluruh GPU/konsol berhenti.

Kit11 menjaga 255 MiB tambahan ruang alamat virtual game sejak startup,
tetap menyisakan setidaknya 256 MiB wilayah stack untuk runtime native.
Ini bukan tambahan pemakaian RAM fisik 255 MiB. FEX dan preset tetap sama.
Kandidat fix ini belum diuji di Switch; keberhasilan freeze belum diklaim.

PASANG DAN TES
1. Tutup aplikasi. Salin isi switch/ paket ini ke root SD.
2. Timpa pes13-fex.nro dan drive_c/windows/system32/libwow64fex.dll.
3. Jalankan lewat NSP 32-bit no-alias, pilih Debug launch. Versi 0.3.9-kit11.
4. Pertahankan plugin, preset Medium, renderer dan clock dari tes Kit10.
5. Coba Exhibition -> controller -> team selection -> kick-off.
6. Jika freeze tetapi HOME masih merespons, tunggu sekitar 15 detik lalu
   HOME -> X -> Close. Simpan fex-runtime.log, termasuk jika tes berhasil.

Marker: VA-PARTITION headroom=1 guest_end=0x30000000, WAIT-HOT, WAIT-RECENT.
Launch biasa tetap tanpa file diagnostik. gameplay.dll belum diubah/dinonaktifkan.

CONTROL OPSIONAL (bukan langkah wajib)
Pada configuration.ini yang sudah ada, tambahkan guest_va_headroom=0 di
bagian [compatibility] untuk batas reservasi lama pada NRO yang sama.
Nilai default 1; jangan menimpa seluruh konfigurasi atau membuat bagian duplikat.
Jika kembali ke Kit11 utama, gunakan 1 atau hapus baris tersebut.

ROLLBACK
Salin isi rollback/switch/ ke SD:/switch/ untuk kembali ke NRO Kit10.
FEX DLL keduanya identik. Jangan Repair runtime selama perbandingan; jika
dijalankan, timpa lagi dua file utama paket ini.

Folder tanpa ZIP. Tidak berisi binary game atau Kitserver. Detail di docs/.
''',encoding='utf-8')
    manifest.update(kind='kit11-guest-va-headroom',same_kit6_module=True,fex_sha256=old['fex_sha256'],
        hardware_tested=False,freeze_fixed=False,rollback_nro_sha256=old['nro_sha256'],
        added_protected_va_mib=255,native_stack_window_min_mib=256)
    manifest['files']={f.relative_to(a.output).as_posix():sha(f) for f in sorted(a.output.rglob('*'))
                       if f.is_file() and f!=a.output/'manifest.json'}
    assert sorted(n for n in manifest['files'] if n.startswith('switch/'))==sorted((nro,dll))
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for name,digest in manifest['files'].items():assert sha(a.output/name)==digest,name
    print(json.dumps({'directory':str(a.output),'nro_sha256':manifest['nro_sha256'],
        'fex_sha256':manifest['fex_sha256'],'verified_files':len(manifest['files'])}))
if __name__=='__main__':main()
