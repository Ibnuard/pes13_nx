"""Package Kit14 with source-bound lifetime tests and exact Kit13 rollback."""
import argparse,hashlib,importlib.util,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('build','native','kit13','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();old=json.loads((a.kit13/'manifest.json').read_text())
    assert old['passed'] and old['version']=='0.3.9-kit13' and old['kind']=='kit13-pipe-quota'
    assert old['same_kit6_module']
    nro='switch/pes13-fex/pes13-fex.nro';dll='switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
    assert sha(a.kit13/nro)==old['nro_sha256']==old['files'][nro]
    assert sha(a.kit13/dll)==old['fex_sha256']==old['files'][dll]
    host=json.loads((a.build/'tests/pipe-lifetime-host.json').read_text())
    binary=json.loads((a.build/'tests/pipe-lifetime-arm64.json').read_text())
    assert host['checks'][0]['header_sha256']==old['files']['source/src/runtime/horizon_anon_pipe.h']
    assert binary['baseline_elf_sha256']==old['native_elf_sha256']
    # The previous serial-handoff regression remains bound to its Kit12 baseline.
    for name,key in (('pipe-quota-host.json',None),('pipe-quota-arm64.json','baseline_elf_sha256')):
        assert sha(a.kit13/'evidence'/name)==old['files']['evidence/'+name]
        previous=json.loads((a.kit13/'evidence'/name).read_text())
        current=json.loads((a.build/'tests'/name).read_text())
        if key:assert current[key]==previous[key]
        else:assert current['checks'][0]['header_sha256']==previous['checks'][0]['header_sha256']
    spec=importlib.util.spec_from_file_location('runtime_package',ROOT/'tools/package-runtime-fixer.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.package(a.build,a.native,a.output)
    m=json.loads((a.output/'manifest.json').read_text());assert m['version']=='0.3.9-kit14'
    def copy(src,name):
        target=a.output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
    copy(a.kit13/dll,dll);copy(a.kit13/nro,'rollback/'+nro)
    for name,h in old['files'].items():
        if name.startswith(('evidence/kit6/','source/kit6/')):
            assert sha(a.kit13/name)==h,name;copy(a.kit13/name,name)
    for name in ('device-analysis.json','kserv-pipe-consumer.json'):
        copy(a.build/'evidence'/name,'evidence/kit14/'+name)
    copy(ROOT/'tools/package-kitserver-pipe-lifetime.py','source/tools/package-kitserver-pipe-lifetime.py')
    copy(ROOT/'tests/kitserver_pipe_audit.py','source/tests/kitserver_pipe_audit.py')
    copy(ROOT/'docs/KITSERVER-KIT14-PIPE-LIFETIME.md','docs/KITSERVER-KIT14-PIPE-LIFETIME.md')
    (a.output/'README.txt').write_text('''FEXTendo 0.3.9-kit14 - Pipe buffer lifetime

Kit13 sudah berhasil menulis/membaca BIN dan melewati halaman controller.
Log berikutnya merekam CreatePipe gagal c0000017 dan diulang sekitar
79 ribu kali/detik sampai tidak ada frame baru.

Kit14 melepas buffer ketika handle baca terakhir ditutup, walaupun handle
tulis masih terbuka. Kit13 menahan seluruh buffer sampai kedua sisi ditutup.
Ukuran pipe tetap mengikuti permintaan. Data yang masih dapat dibaca aman.
Handle tulis tetap valid, tetapi penulisan setelah pembaca ditutup mengembalikan
broken pipe. Tidak menambah batas RAM atau mengganti preset/renderer.

Tes tekanan memori lokal mereproduksi masalah pada Kit13. Kit14 melewati
1.200 siklus; tes pada biner ARM64 juga lulus. Belum diuji di Switch.

PASANG DAN TES
1. Tutup aplikasi. Salin folder switch/ ke root SD, gabungkan dengan SD:/switch/.
2. Timpa pes13-fex.nro dan drive_c/windows/system32/libwow64fex.dll.
3. Buka lewat NSP 32-bit no-alias, pilih Debug launch. Versi 0.3.9-kit14.
4. Gunakan setting yang sama dengan tes Kit13 (Medium, renderer, clock, patch).
5. Coba Exhibition -> controller -> team selection. Ganti beberapa tim,
   lalu coba kick-off. Simpan fex-runtime.log, termasuk bila berhasil.
6. Jika freeze dan HOME masih merespons, biarkan sekitar 15 detik untuk log,
   lalu HOME -> X -> Close.

ANON-PIPE v3 / ANON-MEM v1 mencatat ukuran, buffer aktif, buffer yang sudah
dilepas, dan kegagalan alokasi. Catatan dibatasi; launch biasa tetap tanpa
log diagnostik. Configuration.ini tidak perlu ditimpa. Tidak perlu Repair
runtime untuk perbandingan ini; jika dilakukan, salin ulang kedua file utama.

ROLLBACK: salin isi rollback/switch/ ke SD:/switch/ untuk kembali ke Kit13.
FEX DLL sama. Game/plugin tidak diubah atau disertakan. Tidak ada ZIP.
Analisis dan batas pengujian: docs/KITSERVER-KIT14-PIPE-LIFETIME.md.
''',encoding='utf-8')
    m.update(kind='kit14-pipe-lifetime',same_kit6_module=True,fex_sha256=old['fex_sha256'],
        rollback_nro_sha256=old['nro_sha256'],anonymous_pipe_version=3,
        hardware_tested=False,freeze_fixed=False)
    m['files']={p.relative_to(a.output).as_posix():sha(p) for p in sorted(a.output.rglob('*'))
                if p.is_file() and p!=a.output/'manifest.json'}
    assert sorted(n for n in m['files'] if n.startswith('switch/'))==sorted((nro,dll))
    (a.output/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    for name,h in m['files'].items():assert sha(a.output/name)==h,name
    print(json.dumps({'directory':str(a.output),'nro_sha256':m['nro_sha256'],
        'fex_sha256':m['fex_sha256'],'verified_files':len(m['files'])}))
if __name__=='__main__':main()
