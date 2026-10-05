"""Package the verified production NRO update as a directory, without ZIPs."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

from nro_assets import inspect_nro

ROOT = Path(__file__).resolve().parents[1]
GUIDE = 'docs/FEXTENDO-PRODUCTION-SCREEN-DEBUG.md'
RECEIPTS = (
    'host', 'production-arm64', 'startup-arm64', 'gamepad-arm64', 'keyboard-arm64', 'osk-arm64',
    'scratch-arm64', 'scratch-integrity', 'scratch-host',
    'page-store-arm64', 'page-store-host', 'thread-stack-arm64', 'thread-stack-host',
    'scratch-pages-arm64', 'scratch-pages-host', 'fragmented-heap-arm64',
    'fragmented-heap-addresses', 'rust-heap-arm64', 'rust-heap-host', 'maintenance-arm64',
    'crash-arm64', 'crash-host',
    'heap-pressure-arm64', 'heap-pressure-host',
    'mesa-heap-arm64','mesa-heap-host','pool-pressure-arm64',
    'virtmem-arm64',
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True, help='WSL build directory containing native-source and feature')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    work, native, out = args.build.resolve(), args.native.resolve(), args.output.resolve()
    out.relative_to((ROOT / 'dist').resolve())
    assert out != (ROOT / 'dist').resolve() and not out.exists(), 'Choose an unused directory inside dist'
    report = read(work / 'build-report.json')
    checkpoint = read(ROOT / 'local/high-native-heap/build-report.json')
    assert report['passed'] and report['hardware_tested'] is False
    assert report['production_screen_debug'] and report['launch_memory_gate']
    assert report['launch_memory_gate_version']==3
    assert report['diagnostic_file_writes']=='debug-launch-only' and report['scratch_reserve_mib'] == 64
    assert report['debug_console_scope']=='launcher-startup-only' and report['debug_gameplay_overlay'] is False
    assert report['private_heap_reserve_version']==2 and report['scratch_pages_version']==5
    assert report['virtmem_exhaustive_version']==1
    assert report['idle_pool_recovery_version']==1
    from fextendo_mesa_heap_patches import LIB_SHA256,OBJ_SHA256
    assert report['mesa_heap_binding']['library_sha256']==LIB_SHA256
    assert report['mesa_heap_binding']['object_sha256']==OBJ_SHA256
    assert sha(native/'feature/src/runtime/mesa-ralloc-recovery.o')==report['mesa_heap_binding']['bound_object_sha256']
    for group in ('native_dependencies', 'rust_heap_binding'):
        assert report[group] == checkpoint[group], ('checkpoint dependency changed', group)
    fex_changes={n for n in set(report['native_fex_sources'])|set(checkpoint['native_fex_sources'])
                 if report['native_fex_sources'].get(n)!=checkpoint['native_fex_sources'].get(n)}
    assert fex_changes=={'horizon_jit.c','horizon_scratch_reserve.h','horizon_scratch_pages.h','horizon_heap_pressure.h'}, fex_changes
    for name in ('src/runtime/fextendo_rust_heap.h', 'src/runtime/fextendo_thread_stack.h',
                 'src/runtime/horizon_page_store.h', 'src/runtime/horizon_store_backing.h'):
        assert report['feature_sources'][name] == checkpoint['feature_sources'][name], name
    assert sha(work / 'pes13-fex.nro') == report['nro_sha256']
    assert sha(work / 'production.elf') == report['native_elf_sha256']
    sources = set(report['feature_sources']) | set(report['build_scripts'])
    for group in ('feature_sources', 'build_scripts'):
        for name, digest in report[group].items():
            assert sha(ROOT / name) == digest, name
    for name, digest in report['generated_sources'].items():
        assert sha(native / 'native-source' / name) == digest, name
    for name, digest in report['native_fex_sources'].items():
        assert sha(native / 'feature/src/fex' / name) == digest, name
    rust_header = native / 'feature/src/runtime/fextendo_rust_symbols.h'
    assert sha(rust_header) == report['rust_heap_binding']['header_sha256']
    for name in RECEIPTS:
        receipt = read(work / 'tests' / (name + '.json'))
        assert receipt['passed'] and receipt['hardware_tested'] is False, name
        for key in ('native_elf_sha256', 'nro_sha256'):
            if key in receipt:
                assert receipt[key] == report[key], (name, key)
        for group in ('sources', 'test_sources'):
            for source, digest in receipt.get(group, {}).items():
                source = source.replace('\\', '/')
                assert sha(ROOT / source) == digest, (name, source)
                sources.add(source)
        if 'adapter_sources' in receipt:
            assert receipt['adapter_sources'] == report['native_fex_sources'], name
        for source, digest in receipt.get('generated_sources', {}).items():
            assert report['generated_sources'][source] == digest, (name, source)
    assets = inspect_nro((work / 'pes13-fex.nro').read_bytes(),
                         expected_title='PES13 - FEXTendo', expected_version='0.3.8-r6')

    def copy(source, relative):
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    def write(relative, value):
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')

    copy(work / 'pes13-fex.nro', 'switch/pes13-fex/pes13-fex.nro')
    copy(work / 'build-report.json', 'evidence/build-report.json')
    copy(ROOT / GUIDE, 'DEVELOPER-NOTES.md')
    for name in RECEIPTS:
        copy(work / 'tests' / (name + '.json'), 'evidence/' + name + '.json')
    write('evidence/nro-assets.json', assets)
    write('evidence/checkpoint-comparison.json', {
        'passed': True,
        'checkpoint_commit': 'd2c93a7d3233274ea856ebf88f158d4f4f828ec9',
        'checkpoint_nro_sha256': checkpoint['nro_sha256'],
        'production_nro_sha256': report['nro_sha256'],
        'same_native_dependencies': True, 'same_native_fex_sources': False,
        'native_fex_files_changed': sorted(fex_changes),
        'same_memory_recovery_headers': False, 'same_rust_heap_binding': True,
        'generated_files_changed': sorted(name for name in report['generated_sources']
            if report['generated_sources'][name] != checkpoint['generated_sources'].get(name)),
    })
    for name in ('LICENSE', 'THIRD_PARTY.md'):
        copy(ROOT / name, name)
    for source in (ROOT / 'licenses').rglob('*'):
        if source.is_file():
            copy(source, source.relative_to(ROOT))
    sources.update(('tools/package-fextendo-screen-debug.py', 'tools/build-fex-runtime.py',
                    'tools/nro_assets.py', 'tools/fextendo_package.py',
                    'release/runtime-lock.json', 'src/runtime/pes13_preload.c', GUIDE))
    sources.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'tests').glob('fextendo*') if p.is_file())
    sources.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'config/fextendo/presets').rglob('*') if p.is_file())
    sources.update(('tests/fex_reservations.py', 'tests/fex_alloc.py', 'tests/fex_heap_native.c'))
    for source in sorted(sources):
        copy(ROOT / source, 'source/' + source)
    for name in report['generated_sources']:
        copy(native / 'native-source' / name, 'source/generated/native-wine/' + name)
    for name in report['native_fex_sources']:
        copy(native / 'feature/src/fex' / name, 'source/generated/native-fex/' + name)
    copy(rust_header, 'source/generated/fextendo_rust_symbols.h')
    copy(native/'feature/src/runtime/mesa-ralloc-recovery.o','source/generated/mesa-ralloc-recovery.o')
    (out / 'README.txt').write_text('''FEXTendo 0.3.8-r6 production / CPU virtual-address recovery

PASANG
1. Tutup PES lewat HOME > X > Close.
2. Salin folder switch ke root microSD, timpa pes13-fex.nro.
   Paket hanya memperbarui NRO. Instalasi lengkap sebelumnya tetap dibutuhkan.
3. Buka melalui NSP FEXTendo dari HOME Menu.
   NSP tersedia di https://github.com/Ibnuard/pes13_nx/releases.

Mode memori diperiksa satu kali saat membuka launcher. Hanya 32-bit no-alias
yang diterima; mode lain menampilkan petunjuk NSP lalu berhenti sebelum Wine.
Hasil pemeriksaan dipakai ulang selama startup, tidak dipoll saat bermain.
Guard awal sebelum heap libnx tetap mencegah reservasi alamat PES pada mode salah.

DUA JALUR LAUNCH, SATU NRO
Tile PES13 biasa: loading GUI, tanpa console atau file log diagnostik.
Settings > Show debug launch > On, kembali ke Home, pilih Debug launch.
Layar launcher berubah menjadi console hitam berisi proses startup Wine.
Console dan thread launcher dilepas otomatis saat layar diserahkan ke game.
Tidak perlu menahan Minus. Tidak ada overlay/worker debug tambahan saat match.

LOG KHUSUS DEBUG LAUNCH
switch/pes13-fex/fex-runtime.log: startup dan output error/runtime setelah handoff.
switch/pes13-fex/crash.log: fatal error yang sempat ditangkap runtime.
Run debug sebelumnya disimpan sebagai fex-runtime.previous.log / crash.previous.log.
Crash.log yang hanya berisi header berarti belum ada fatal error tertangkap;
freeze tidak selalu menghasilkan crash record. Tutup normal tidak dijamin bisa
menyimpan pesan terakhir jika proses dimatikan mendadak oleh OS.
Kirim kedua file log terbaru untuk analisis, bukan screenshot overlay.

Runtime log dibatch oleh maintenance, maksimal 4 MiB per run. Crash capture
dibatasi 8 record. Debug launch tetap menambah beban format/log/SD; pakai tile
biasa untuk pengukuran FPS. Tidak ada profiling, thread sampling atau polling
HEALTH. File transition.log tidak dipakai di build ini. Log lama dibiarkan.
Save game, pengaturan, cache fungsional dan last played tetap bisa disimpan.

Log r5 berhenti sekitar detik 143: permintaan scratch 16 MiB tidak mendapat
alamat virtual (pages_stage=6), padahal sumber halaman berhasil dialokasikan.
Heap masih melaporkan sekitar 93 MiB bebas setelah rollback. Area pencarian
lama hanya mencakup alamat stack di bawah 1 GiB.
R6 memakai area pemetaan ASLR yang lebih luas untuk seluruh pemulihan data CPU
FEX/Mesa/Rust, dengan izin baca/tulis saja. Setelah pencarian acak gagal,
manager memeriksa celah alamat secara menyeluruh, termasuk reservasi Wine,
thread dan JIT. Bukan hanya perbaikan khusus ukuran 16 MiB.
Rollback juga menangani kegagalan izin akses tanpa membebaskan sumber yang
masih terpetakan. Cadangan resident tetap 64 MiB; preset dan timing tetap.
Fix allocator Mesa/Wine sebelumnya tetap disertakan.
Tes binary ARM64 mereproduksi kegagalan r5 pada area stack penuh dan r6
berhasil memakai celah ASLR yang sama-sama tersedia dalam model pengujian.
Peta lengkap memori perangkat saat gagal tidak terekam; stabilitas nyata
tetap perlu dikonfirmasi lewat pengujian HIGH di Switch.
Build dan tes lokal host/ARM64 lulus. Build baru ini masih perlu diuji di
Switch, termasuk layar penolakan, handoff console ke game dan satu match penuh.

Hanya folder switch yang perlu disalin. Folder source/evidence beserta
DEVELOPER-NOTES.md memuat bukti build dan tidak perlu dipasang ke SD.
''', encoding='utf-8')
    deployed = [p.relative_to(out).as_posix() for p in (out / 'switch').rglob('*') if p.is_file()]
    assert deployed == ['switch/pes13-fex/pes13-fex.nro'], deployed
    assert sha(out / deployed[0]) == report['nro_sha256']
    write('manifest.json', {'passed': True, 'hardware_tested': False,
        'nro_sha256': report['nro_sha256'], 'native_elf_sha256': report['native_elf_sha256'],
        'receipts': list(RECEIPTS), 'files': {
            p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}})
    print(json.dumps({'passed': True, 'directory': str(out), 'nro_sha256': report['nro_sha256'],
                      'validation_receipts': len(RECEIPTS), 'hardware_tested': False}, indent=2))


if __name__ == '__main__':
    main()
