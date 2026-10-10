"""Package Kit7's tested native directory fix with the unchanged Kit6 FEX DLL."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'native', 'kit6', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    kit6 = json.loads((args.kit6/'manifest.json').read_text())
    assert kit6['passed'] and kit6['kind']=='kit6-fex-protection-roundtrip'
    dll='switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
    assert sha(args.kit6/dll)==kit6['fex_sha256']==kit6['files'][dll]
    spec=importlib.util.spec_from_file_location('package_runtime',ROOT/'tools/package-runtime-fixer.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.package(args.build,args.native,args.output)
    manifest=json.loads((args.output/'manifest.json').read_text())
    assert manifest['version']=='0.3.9-kit7'
    def copy(src,name):
        dest=args.output/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
    copy(args.kit6/dll,dll)
    for name,digest in kit6['files'].items():
        if not (name.startswith('evidence/kit6/') or name.startswith('source/kit6/')):continue
        assert sha(args.kit6/name)==digest,name
        copy(args.kit6/name,name)
    copy(args.kit6/'switch/pes13-fex/pes13-fex.nro','rollback/switch/pes13-fex/pes13-fex.nro')
    copy(ROOT/'tools/package-kitserver-directory.py','source/tools/package-kitserver-directory.py')
    copy(ROOT/'docs/KITSERVER-KIT7-DIRECTORY.md','docs/KITSERVER-KIT7-DIRECTORY.md')
    copy(ROOT/'docs/KITSERVER-KIT6-PROTECTION.md','docs/KITSERVER-KIT6-PROTECTION.md')
    (args.output/'README.txt').write_text('''FEXTendo 0.3.9-kit7 - Kitserver directory streaming

Log terakhir masih membaca daftar file Kitserver, bukan mencatat crash.
Wine sebelumnya membuka ulang folder dan mengulang semua entri terdahulu
untuk setiap file. Kit7 melanjutkan satu cursor per objek folder, mengurangi
log per-file, dan tetap memakai modul FEX Kit6 yang melewati error rld.dll.
Uji lokal lulus; waktu loading dan keberhasilan game perlu diuji di Switch.

PASANG
1. Tutup PES13 lewat HOME > X > Close.
2. Salin SELURUH isi folder switch/ ke root SD dan timpa dua file:
   switch/pes13-fex/pes13-fex.nro
   switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll
3. Jalankan NSP 32-bit no-alias seperti sebelumnya, lalu pilih Debug launch.
4. Launcher harus menampilkan 0.3.9-kit7. Log harus memuat kedua marker:
   [HZDIR] v2 persistent directory cursor; bounded trace
   [FEX-PROTECT] kit6 v1 guest protection round-trip; normal optimization
5. Biarkan startup selesai. Jika tetap macet, simpan fex-runtime.log dan
   crash.log dari run tersebut serta perkiraan durasi menunggu.

Preset, optimizer FEX, DXVK, game, Kitserver dan rld.dll tidak diubah.
Launch biasa tetap tanpa log diagnostik; Debug launch menulis log.
Tidak ada cache daftar file yang ditulis ke SD. Save/pengaturan tetap jalan.

RUNTIME FIXER
Check runtime masih bisa menandai modul FEX eksperimen sebagai changed.
Jangan pilih Repair runtime selama tes: Repair mengembalikan FEX produksi.
Jika sudah Repair, salin kembali kedua file dari switch/ paket ini.

ROLLBACK KE KIT6
Salin rollback/switch/ ke SD:/switch/. Modul FEX sama, jadi cukup NRO lama.

Rincian dan batas validasi: docs/KITSERVER-KIT7-DIRECTORY.md.
Folder siap salin, tanpa ZIP. Tidak menyertakan file game/patch.
''',encoding='utf-8')
    manifest.update(kind='kit7-directory-streaming',fex_sha256=kit6['fex_sha256'],
                    same_kit6_module=True,hardware_tested=False,
                    rollback_nro_sha256=kit6['nro_sha256'])
    manifest['files']={p.relative_to(args.output).as_posix():sha(p)
                       for p in sorted(args.output.rglob('*')) if p.is_file() and p!=args.output/'manifest.json'}
    assert sorted(p for p in manifest['files'] if p.startswith('switch/'))==sorted([
        'switch/pes13-fex/pes13-fex.nro',dll])
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for path,digest in manifest['files'].items():assert sha(args.output/path)==digest,path
    print(json.dumps({'directory':str(args.output),'version':manifest['version'],
                      'nro_sha256':manifest['nro_sha256'],'fex_sha256':manifest['fex_sha256'],
                      'verified_files':len(manifest['files'])}))


if __name__=='__main__':main()
