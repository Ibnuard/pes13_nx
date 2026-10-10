"""Copy-ready Kit8 native metadata fix with the established Kit6 FEX module."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('build', 'native', 'kit7', 'output'):
        p.add_argument('--'+n, type=Path, required=True)
    a = p.parse_args()
    old = json.loads((a.kit7/'manifest.json').read_text())
    assert old['passed'] and old['kind']=='kit7-directory-streaming' and old['same_kit6_module']
    dll='switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
    nro='switch/pes13-fex/pes13-fex.nro'
    assert sha(a.kit7/dll)==old['fex_sha256']==old['files'][dll]
    assert sha(a.kit7/nro)==old['nro_sha256']==old['files'][nro]
    spec=importlib.util.spec_from_file_location('runtime_package',ROOT/'tools/package-runtime-fixer.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.package(a.build,a.native,a.output)
    manifest=json.loads((a.output/'manifest.json').read_text())
    assert manifest['version']=='0.3.9-kit8'
    def copy(src,name):
        target=a.output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
    copy(a.kit7/dll,dll)
    copy(a.kit7/nro,'rollback/'+nro)
    for name,digest in old['files'].items():
        if not (name.startswith('evidence/kit6/') or name.startswith('source/kit6/')):continue
        assert sha(a.kit7/name)==digest,name
        copy(a.kit7/name,name)
    for name in ('tools/package-kitserver-metadata.py','docs/KITSERVER-KIT8-METADATA.md'):
        copy(ROOT/name,('source/' if name.startswith('tools/') else '')+name)
    (a.output/'README.txt').write_text('''FEXTendo 0.3.9-kit8 - Kitserver SD metadata

Kit8 mengurangi pemeriksaan SD berulang saat memindai folder besar.
Ukuran file memakai hasil scan; timestamp asli dan atribut Wine dipertahankan.
Debug launch menambahkan [HZDIR-COST] untuk membedakan bagian yang lambat.
Penyebab HOME ikut macet belum terbukti dari log Kit7. Kit8 perlu tes Switch;
ini bukan klaim bahwa hard freeze sudah selesai diperbaiki.

PASANG
1. Saat aplikasi sudah ditutup, salin seluruh isi switch/ ke root SD.
2. Timpa dua file:
   switch/pes13-fex/pes13-fex.nro
   switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll
3. Jalankan NSP 32-bit no-alias, pilih Debug launch untuk satu tes.
4. Periksa versi 0.3.9-kit8, [HZDIR] v3 dan [FEX-PROTECT] kit6 di log.
5. Kirim fex-runtime.log hasil run ini, terutama bila tetap macet.
   Jika HOME masih merespons, tutup lewat HOME. Tidak perlu terus menunggu
   apabila seluruh konsol sudah tidak merespons.

Launch biasa tetap tanpa log diagnostik. Save/pengaturan tetap berfungsi.
Tidak mengganti game, Kitserver/rld.dll, preset, renderer atau optimizer FEX.
Modul FEX tetap Kit6; tidak ada cache daftar file yang ditulis ke SD.

Jangan gunakan Repair runtime selama perbandingan: itu memulihkan FEX rilis.
Jika sudah Repair, pasang ulang dua file overlay ini.
Rollback: salin rollback/switch/ ke SD:/switch/ untuk kembali ke NRO Kit7.

Build dan hasil tes lokal ada di evidence/; rincian/batas validasi di
docs/KITSERVER-KIT8-METADATA.md. Folder siap salin, tanpa ZIP.
''',encoding='utf-8')
    manifest.update(kind='kit8-directory-metadata',fex_sha256=old['fex_sha256'],
                    same_kit6_module=True,hardware_tested=False,rollback_nro_sha256=old['nro_sha256'])
    manifest['files']={p.relative_to(a.output).as_posix():sha(p) for p in sorted(a.output.rglob('*'))
                       if p.is_file() and p!=a.output/'manifest.json'}
    assert sorted(n for n in manifest['files'] if n.startswith('switch/'))==sorted((nro,dll))
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for name,digest in manifest['files'].items():assert sha(a.output/name)==digest,name
    print(json.dumps({'directory':str(a.output),'nro_sha256':manifest['nro_sha256'],
                      'fex_sha256':manifest['fex_sha256'],'verified_files':len(manifest['files'])}))


if __name__=='__main__':main()
