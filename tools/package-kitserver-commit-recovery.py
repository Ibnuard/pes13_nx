"""Package Kit15 with verified recovery tests and exact Kit14 rollback."""
import argparse, hashlib, importlib.util, json, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'native', 'kit14', 'output'): p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args(); old = json.loads((a.kit14/'manifest.json').read_text())
    assert old['passed'] and old['version']=='0.3.9-kit14' and old['kind']=='kit14-pipe-lifetime'
    assert old['same_kit6_module']
    nro='switch/pes13-fex/pes13-fex.nro'; dll='switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
    assert sha(a.kit14/nro)==old['nro_sha256']==old['files'][nro]
    assert sha(a.kit14/dll)==old['fex_sha256']==old['files'][dll]
    check=json.loads((a.build/'tests/commit-arm64.json').read_text())
    assert check['passed'] and check['baseline_elf_sha256']==old['native_elf_sha256']
    assert len(check['checks'])==2 and check['checks'][0]['baseline'] and not check['checks'][1]['baseline']
    assert all(r['preserved'] and r['retry_ok'] and not r['guard_gaps'] for r in check['checks'][1]['transactions'])
    assert check['checks'][1]['pressure']['recovered'] and not check['checks'][0]['pressure']['recovered']
    spec=importlib.util.spec_from_file_location('runtime_package',ROOT/'tools/package-runtime-fixer.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.package(a.build,a.native,a.output)
    m=json.loads((a.output/'manifest.json').read_text());assert m['version']=='0.3.9-kit15'
    def copy(src,name):
        target=a.output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
    copy(a.kit14/dll,dll);copy(a.kit14/nro,'rollback/'+nro)
    for name,h in old['files'].items():
        if name.startswith(('evidence/kit6/','source/kit6/')):
            assert sha(a.kit14/name)==h,name;copy(a.kit14/name,name)
    copy(a.build/'evidence/device-analysis.json','evidence/kit15/device-analysis.json')
    copy(ROOT/'tools/package-kitserver-commit-recovery.py','source/tools/package-kitserver-commit-recovery.py')
    copy(ROOT/'docs/KITSERVER-KIT15-COMMIT-RECOVERY.md','docs/KITSERVER-KIT15-COMMIT-RECOVERY.md')
    (a.output/'README.txt').write_text('''FEXTendo 0.3.9-kit15 - Commit recovery

Log Kit14: 23 commit memori gagal pada detik 146-148, lalu proses game
menutup dirinya sendiri. Buffer pipe Kit14 sudah terlihat dilepas.

Kit15 mempertahankan reservasi alamat sampai commit berhasil. Commit yang
gagal tetap dapat dicoba ulang. Arena backing yang benar-benar kosong dapat
dilepas saat alokasi gagal; memori aktif tetap dipertahankan.
Ada catatan MEM-FAIL/MEM-KERNEL terbatas hanya pada Debug launch.

Tes before/after pada ARM64 lulus. Ini kandidat perbaikan; belum diuji
di Switch dan belum diklaim menyelesaikan freeze pada patch ini.

PASANG DAN TES
1. Tutup PES13. Salin folder switch/ ke root SD, gabungkan dengan SD:/switch/.
2. Timpa pes13-fex.nro dan drive_c/windows/system32/libwow64fex.dll.
3. Buka NSP 32-bit no-alias lalu Debug launch. Pastikan 0.3.9-kit15.
4. Pertahankan Medium, renderer, clock dan patch seperti tes sebelumnya.
5. Exhibition -> game plan -> kick-off; kirim fex-runtime.log hasilnya.
6. Jika macet dan HOME merespons, tunggu sekitar 15 detik sebelum menutup.

Launch biasa tetap tanpa log diagnostik. Configuration.ini tidak ditimpa.
Tidak perlu Repair runtime untuk tes ini; bila dilakukan, salin ulang dua
file utama. FEX DLL sama dengan Kit14, game/plugin tidak disertakan.
Rollback: salin rollback/switch/ ke root SD untuk mengembalikan NRO Kit14.
Tidak ada ZIP. Rincian analisis: docs/KITSERVER-KIT15-COMMIT-RECOVERY.md.
''',encoding='utf-8')
    m.update(kind='kit15-commit-recovery',same_kit6_module=True,fex_sha256=old['fex_sha256'],
        rollback_nro_sha256=old['nro_sha256'],commit_recovery_version=1,
        hardware_tested=False,freeze_fixed=False)
    m['files']={p.relative_to(a.output).as_posix():sha(p) for p in sorted(a.output.rglob('*'))
                if p.is_file() and p!=a.output/'manifest.json'}
    assert sorted(n for n in m['files'] if n.startswith('switch/'))==sorted((nro,dll))
    (a.output/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    for name,h in m['files'].items():assert sha(a.output/name)==h,name
    print(json.dumps({'directory':str(a.output),'nro_sha256':m['nro_sha256'],
        'fex_sha256':m['fex_sha256'],'verified_files':len(m['files'])}))
if __name__=='__main__':main()
