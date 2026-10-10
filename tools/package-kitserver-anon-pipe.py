"""Package Kit12 anonymous-pipe support, exact FEX and Kit11 rollback."""
import argparse
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'native', 'kit11', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    old = json.loads((args.kit11 / 'manifest.json').read_text())
    assert old['passed'] and old['kind'] == 'kit11-guest-va-headroom' and old['same_kit6_module']
    nro = 'switch/pes13-fex/pes13-fex.nro'
    dll = 'switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
    assert sha(args.kit11 / dll) == old['fex_sha256'] == old['files'][dll]
    assert sha(args.kit11 / nro) == old['nro_sha256'] == old['files'][nro]

    spec = importlib.util.spec_from_file_location('runtime_package', ROOT / 'tools/package-runtime-fixer.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.package(args.build, args.native, args.output)
    manifest = json.loads((args.output / 'manifest.json').read_text())
    assert manifest['version'] == '0.3.9-kit12'

    def copy(source, name):
        target = args.output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    copy(args.kit11 / dll, dll)
    copy(args.kit11 / nro, 'rollback/' + nro)
    for name, digest in old['files'].items():
        if name.startswith(('evidence/kit6/', 'source/kit6/')):
            assert sha(args.kit11 / name) == digest, name
            copy(args.kit11 / name, name)
    copy(ROOT / 'tools/package-kitserver-anon-pipe.py', 'source/tools/package-kitserver-anon-pipe.py')
    copy(ROOT / 'docs/KITSERVER-KIT12-ANONYMOUS-PIPE.md', 'docs/KITSERVER-KIT12-ANONYMOUS-PIPE.md')
    copy(args.build / 'evidence/device-analysis.json', 'evidence/kit12/device-analysis.json')
    (args.output / 'README.txt').write_text('''FEXTendo 0.3.9-kit12 - Anonymous pipe (paket r2)

TEMUAN DAN PERBAIKAN
Log Kit11 memperlihatkan NtCreateNamedPipeFile gagal c0000002 sekitar
83 ribu kali/detik saat Exhibition menuju controller. Wine CreatePipe
mengulang permintaan ini karena server Horizon belum punya implementasinya.
Kit12 menambahkan pipe byte-stream sungguhan di RAM, termasuk read/write,
wait, peek, duplicate handle dan close. Buffer kosong/penuh menunggu dengan
condition variable; tidak memakai polling atau file SD.

Ini kandidat fix berdasarkan log, BELUM diverifikasi pada Switch.
FEX DLL, preset, renderer dan Kitserver tetap sama. Ruang alamat Kit11 tetap.
Error attach gameplay.dll yang terpisah belum ditangani oleh perubahan ini.

PASANG DAN TES
1. Tutup PES. Salin isi folder switch/ ke root SD.
2. Timpa pes13-fex.nro dan drive_c/windows/system32/libwow64fex.dll.
3. Jalankan melalui NSP 32-bit no-alias, pilih Debug launch. Versi 0.3.9-kit12.
4. Gunakan preset Medium, renderer, clock dan plugin yang sama dengan Kit11.
5. Coba Exhibition -> controller -> team selection -> kick-off.
6. Jika freeze tetapi HOME merespons, tunggu sekitar 15 detik kemudian
   HOME -> X -> Close. Simpan fex-runtime.log, termasuk jika berhasil.

Log debug: ANON-PIPE v1 status=00000000 saat create berhasil.
Keberhasilan harus dilihat dari perpindahan halaman, bukan hanya present FPS.
Launch biasa tetap tanpa file diagnostik. Tidak perlu mengganti configuration.ini.
Tidak perlu Repair runtime untuk tes ini; jika dijalankan, timpa lagi kedua
file utama paket ini agar versi FEX yang dibandingkan tetap tepat.

ROLLBACK
Salin isi rollback/switch/ ke SD:/switch/ untuk kembali ke NRO Kit11.
FEX DLL keduanya identik.

Folder tanpa ZIP; tidak berisi binary game atau Kitserver. Detail ada di docs/.
Uji host ASan/UBSan dan binary ARM64 lulus; tes ini tidak menjalankan PES di Switch.
''', encoding='utf-8')
    manifest.update(kind='kit12-anonymous-pipe', package_revision=2, same_kit6_module=True,
                    fex_sha256=old['fex_sha256'], hardware_tested=False, freeze_fixed=False,
                    rollback_nro_sha256=old['nro_sha256'], anonymous_pipe_version=1,
                    guest_va_partition_version=1)
    manifest['files'] = {f.relative_to(args.output).as_posix(): sha(f)
                         for f in sorted(args.output.rglob('*'))
                         if f.is_file() and f != args.output / 'manifest.json'}
    assert sorted(n for n in manifest['files'] if n.startswith('switch/')) == sorted((nro, dll))
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for name, digest in manifest['files'].items():
        assert sha(args.output / name) == digest, name
    print(json.dumps({'directory': str(args.output), 'nro_sha256': manifest['nro_sha256'],
                      'fex_sha256': manifest['fex_sha256'], 'verified_files': len(manifest['files'])}))


if __name__ == '__main__':
    main()
