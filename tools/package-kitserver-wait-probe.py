"""Package the tested Kit10 probe, unchanged FEX and optional plugin control."""
import argparse,hashlib,importlib.util,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('build','native','kit9','plugins','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();old=json.loads((a.kit9/'manifest.json').read_text())
    assert old['passed'] and old['kind']=='kit9-kitserver-asset-scan' and old['same_kit6_module']
    nro='switch/pes13-fex/pes13-fex.nro';dll='switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
    assert sha(a.kit9/dll)==old['fex_sha256']==old['files'][dll]
    assert sha(a.kit9/nro)==old['nro_sha256']==old['files'][nro]
    plugins=a.plugins.read_text(encoding='utf-8-sig')
    assert [l.strip() for l in plugins.splitlines() if l.strip()]==['[plugin]','1=camera.dll','2=gameplay.dll']
    spec=importlib.util.spec_from_file_location('runtime_package',ROOT/'tools/package-runtime-fixer.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.package(a.build,a.native,a.output)
    manifest=json.loads((a.output/'manifest.json').read_text());assert manifest['version']=='0.3.9-kit10'
    def copy(src,name):
        target=a.output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
    copy(a.kit9/dll,dll);copy(a.kit9/nro,'rollback/'+nro)
    for name,digest in old['files'].items():
        if name.startswith(('evidence/kit6/','source/kit6/')):
            assert sha(a.kit9/name)==digest,name
            copy(a.kit9/name,name)
    copy(ROOT/'tools/package-kitserver-wait-probe.py','source/tools/package-kitserver-wait-probe.py')
    copy(ROOT/'docs/KITSERVER-KIT10-MENU-PROBE.md','docs/KITSERVER-KIT10-MENU-PROBE.md')
    copy(a.build/'evidence/device-analysis.json','evidence/kit10/device-analysis.json')
    control=a.output/'optional-gameplay-off/switch/pes13-fex/drive_c/PES13/kitserver13/plugin.ini'
    control.parent.mkdir(parents=True,exist_ok=True)
    control.write_text('[plugin]\n1=camera.dll\n; Test control: gameplay.dll omitted because Kit9 logged a failed initialization.\n',encoding='utf-8')
    copy(a.plugins,'reference-original/plugin.ini')
    (a.output/'README.txt').write_text('''FEXTendo 0.3.9-kit10 - Exhibition/controller stall probe

Kit9 sudah melewati startup. Log membuktikan scan 16.962 aset selesai sebelum
detik 20. Ada error inisialisasi gameplay.dll, tetapi penyebab freeze berikutnya
belum pasti. Kit10 menambah bukti tunggu Wine/Vulkan dan CPU thread.
Ini build diagnosis, belum merupakan klaim perbaikan freeze.

TES PERTAMA - plugin tetap seperti sekarang
1. Dengan aplikasi tertutup, salin isi switch/ paket ini ke root SD.
2. Timpa pes13-fex.nro dan drive_c/windows/system32/libwow64fex.dll.
3. Jalankan NSP 32-bit no-alias dan pilih Debug launch. Versi 0.3.9-kit10.
4. Coba Exhibition menuju controller settings. Jika membeku tetapi HOME tetap
   merespons, tunggu sekitar 15 detik, lalu HOME -> X -> Close.
5. Simpan fex-runtime.log. Marker baru: WAIT-PROBE, WAIT-INFLIGHT, WAIT-CPU.

TES PEMBANDING OPSIONAL - tanpa plugin gameplay.dll
Cadangkan file plugin.ini yang benar-benar ada di Switch terlebih dahulu.
Kontrol ini dibuat dari daftar dua plugin: camera.dll dan gameplay.dll.
Jangan timpa jika daftar milikmu berbeda; hapus/nonaktifkan hanya baris
gameplay.dll pada salinan konfigurasi milikmu.
Salin isi optional-gameplay-off/switch/ ke SD:/switch/ lalu ulangi Debug launch
dengan preset, renderer dan clock yang sama. Simpan log dengan nama berbeda.
Sesudahnya pulihkan plugin.ini dari backup. reference-original/plugin.ini
adalah referensi PC yang diperiksa, bukan backup otomatis dari Switch.

Launch biasa tetap tanpa log diagnostik. Optimasi, preset, renderer dan modul
FEX Kit6 sama. Pengamat tidak menghentikan thread; ia dapat melewatkan rekaman
saat sibuk, dan tidak menyimpulkan semua panggilan lama adalah deadlock.

Rollback: salin isi rollback/switch/ ke SD:/switch/ untuk NRO Kit9.
Jangan Repair runtime selama pembandingan; jika dilakukan, salin ulang kedua
file paket ini agar modul FEX eksperimen tetap sesuai.

Folder tanpa ZIP. Tidak berisi binary game/Kitserver. Rincian ada di docs/.
''',encoding='utf-8')
    manifest.update(kind='kit10-menu-wait-probe',same_kit6_module=True,fex_sha256=old['fex_sha256'],
        hardware_tested=False,freeze_fixed=False,rollback_nro_sha256=old['nro_sha256'],plugin_control='optional',
        reference_plugin_sha256=sha(a.plugins))
    manifest['files']={f.relative_to(a.output).as_posix():sha(f) for f in sorted(a.output.rglob('*'))
                       if f.is_file() and f!=a.output/'manifest.json'}
    assert sorted(n for n in manifest['files'] if n.startswith('switch/'))==sorted((nro,dll))
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for name,digest in manifest['files'].items():assert sha(a.output/name)==digest,name
    print(json.dumps({'directory':str(a.output),'nro_sha256':manifest['nro_sha256'],
        'fex_sha256':manifest['fex_sha256'],'verified_files':len(manifest['files'])}))
if __name__=='__main__':main()
