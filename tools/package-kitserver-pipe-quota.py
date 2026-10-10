"""Package Kit13 pipe quota compatibility with exact FEX and Kit12 r2 rollback."""
import argparse,hashlib,importlib.util,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('build','native','kit12','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();old=json.loads((args.kit12/'manifest.json').read_text())
    assert old['passed'] and old['kind']=='kit12-anonymous-pipe' and old['package_revision']==2
    assert old['same_kit6_module']
    nro='switch/pes13-fex/pes13-fex.nro';dll='switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
    assert sha(args.kit12/nro)==old['nro_sha256']==old['files'][nro]
    assert sha(args.kit12/dll)==old['fex_sha256']==old['files'][dll]
    quota=json.loads((args.build/'tests/pipe-quota-arm64.json').read_text())
    assert quota['baseline_elf_sha256']==old['native_elf_sha256']
    host=json.loads((args.build/'tests/pipe-quota-host.json').read_text())
    assert host['checks'][0]['header_sha256']==old['files']['source/src/runtime/horizon_anon_pipe.h']
    audit=json.loads((args.build/'evidence/kserv-pipe-consumer.json').read_text())
    assert audit['passed'] and not audit['file_modified'] and len(audit['checks'])==3
    spec=importlib.util.spec_from_file_location('runtime_package',ROOT/'tools/package-runtime-fixer.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.package(args.build,args.native,args.output)
    manifest=json.loads((args.output/'manifest.json').read_text());assert manifest['version']=='0.3.9-kit13'
    def copy(source,name):
        target=args.output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    copy(args.kit12/dll,dll);copy(args.kit12/nro,'rollback/'+nro)
    for name,digest in old['files'].items():
        if name.startswith(('evidence/kit6/','source/kit6/')):
            assert sha(args.kit12/name)==digest,name
            copy(args.kit12/name,name)
    for name in ('device-analysis.json','kserv-pipe-consumer.json'):
        copy(args.build/'evidence'/name,'evidence/kit13/'+name)
    for name in ('tools/package-kitserver-pipe-quota.py','tests/kitserver_pipe_audit.py'):
        copy(ROOT/name,'source/'+name)
    copy(ROOT/'docs/KITSERVER-KIT13-PIPE-QUOTA.md','docs/KITSERVER-KIT13-PIPE-QUOTA.md')
    (args.output/'README.txt').write_text('''FEXTendo 0.3.9-kit13 - Pipe quota

Log Kit12: pipe berhasil dibuat pada detik 76,711, lalu thread pemuatan
tertahan di NtWriteFile. Permintaan buffer 2.101.740 byte dipotong Kit12
menjadi 1 MiB. Kitserver menulis BIN dahulu, baru memberi handle baca ke PES.
Tes lokal mereproduksi writer macet dengan 2.294 byte tersisa.

Kit13 memenuhi ukuran pipe yang diminta, mempertahankan batas kapasitas,
penantian dan penutupan normal. Tidak memakai file sementara di SD.
Kandidat ini lulus reproduksi host dan binary ARM64; belum diuji pada Switch.

PASANG
1. Tutup aplikasi. Salin folder switch/ ke root SD, gabungkan dengan SD:/switch/.
2. Timpa pes13-fex.nro dan drive_c/windows/system32/libwow64fex.dll.
3. Launch melalui NSP 32-bit no-alias, pilih Debug launch. Versi 0.3.9-kit13.
4. Gunakan preset Medium, renderer, clock dan plugin seperti tes Kit12.
5. Coba Exhibition -> controller -> team selection -> kick-off.
6. Simpan fex-runtime.log, termasuk bila berhasil. Jika masih freeze dan
   HOME merespons, tunggu sekitar 15 detik lalu HOME -> X -> Close.

Log ANON-PIPE v2 mencatat requested/capacity. ANON-IO v2 mencatat begin/end
baca dan tulis. Yang diharapkan adalah write selesai lalu game mulai membaca.
Launch biasa tetap tanpa log diagnostik. Configuration.ini tidak perlu ditimpa.
Tidak perlu Repair runtime saat perbandingan ini; jika dilakukan, salin ulang
kedua file utama agar versi FEX tepat.

ROLLBACK: salin isi rollback/switch/ ke SD:/switch/ untuk kembali ke Kit12 r2.
FEX DLL sama. Game dan plugin tidak diubah atau disertakan. Tidak ada ZIP.
Detail bukti, keterbatasan dan tes ada di docs/KITSERVER-KIT13-PIPE-QUOTA.md.
''',encoding='utf-8')
    manifest.update(kind='kit13-pipe-quota',same_kit6_module=True,fex_sha256=old['fex_sha256'],
        rollback_nro_sha256=old['nro_sha256'],anonymous_pipe_version=2,
        hardware_tested=False,freeze_fixed=False)
    manifest['files']={p.relative_to(args.output).as_posix():sha(p) for p in sorted(args.output.rglob('*'))
                       if p.is_file() and p!=args.output/'manifest.json'}
    assert sorted(p for p in manifest['files'] if p.startswith('switch/'))==sorted((nro,dll))
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for name,digest in manifest['files'].items():assert sha(args.output/name)==digest,name
    print(json.dumps({'directory':str(args.output),'nro_sha256':manifest['nro_sha256'],
        'fex_sha256':manifest['fex_sha256'],'verified_files':len(manifest['files'])}))
if __name__=='__main__':main()
