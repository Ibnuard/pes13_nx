"""Package a verified diagnostic overlay as a directory, never as a ZIP."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
from nro_assets import inspect_nro
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();work=a.build.resolve();out=a.output.resolve()
    assert not out.exists(),'Choose an unused output folder; do not overwrite another test package'
    report=json.loads((work/'build-report.json').read_text())
    assert report['passed'] and report['transition_trace'] and report['hardware_tested'] is False
    assert report['transition_trace_version']==3
    scratch=report.get('scratch_reserve',False)
    arena=scratch and report.get('scratch_reserve_version',1) in (2,3)
    scratch64=scratch and report.get('scratch_reserve_version',0)==3
    assert not scratch64 or report.get('scratch_reserve_mib')==64
    crash=report.get('crash_log_version',0) in (1,2)
    live=report.get('live_freeze_version',0)==1
    pages=report.get('page_store_version',0)==1
    stacks=report.get('thread_stack_reserve_version',0)==1
    spages=report.get('scratch_pages_version',0) in (1,2)
    general=report.get('scratch_pages_version',0)==2
    rust=report.get('rust_heap_version',0)==1
    assert not rust or general
    assert not spages or stacks
    assert not stacks or pages
    assert not pages or (scratch64 and live)
    assert not live or report['crash_log_version']==2
    assert sha(work/'pes13-fex.nro')==report['nro_sha256']
    assert sha(work/'high-trace.elf')==report['native_elf_sha256']
    for group in ('feature_sources','build_scripts'):
        for name,digest in report[group].items():assert sha(ROOT/name)==digest,name
    receipts=['host-trace.json','gamepad-arm64.json','keyboard-arm64.json','osk-arm64.json',
              'silent-arm64.json','trace-arm64.json','patch-integrity.json']
    if scratch:
        receipts+=['scratch-host.json','scratch-arm64.json','scratch-integrity.json']
    if crash:receipts+=['crash-host.json','crash-arm64.json']
    if live:receipts+=['live-arm64.json']
    if pages:receipts+=['page-store-host.json','page-store-arm64.json']
    if stacks:receipts+=['thread-stack-host.json','thread-stack-arm64.json']
    if spages:receipts+=['scratch-pages-host.json','scratch-pages-arm64.json']
    if general:receipts+=['fragmented-heap-arm64.json','fragmented-heap-addresses.json']
    if rust:receipts+=['rust-heap-host.json','rust-heap-arm64.json']
    for name in receipts:
        r=json.loads((work/'tests'/name).read_text());assert r['passed'] and r['hardware_tested'] is False,name
        if 'native_elf_sha256' in r:assert r['native_elf_sha256']==report['native_elf_sha256'],name
        for source,digest in r.get('sources',{}).items():assert sha(ROOT/source)==digest,source
        if 'adapter_sources' in r:assert r['adapter_sources']==report['native_fex_sources'],name
    if scratch:
        for name,digest in report['native_fex_sources'].items():assert sha(work/'native-fex'/name)==digest,name
    def copy(src,dest):
        target=out/dest;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
    rollback=ROOT/('local/high-fragmented-heap/pes13-fex.nro' if rust else 'local/high-scratch-pages/pes13-fex.nro' if general else 'local/high-thread-stack/pes13-fex.nro' if spages else 'local/high-page-store/pes13-fex.nro' if stacks else 'local/high-scratch64/pes13-fex.nro' if pages else 'local/high-live-freeze/pes13-fex.nro' if scratch64 else 'local/high-crashlog/pes13-fex.nro' if live else 'local/high-scratch-arena/pes13-fex.nro' if crash else 'local/high-scratch-reserve/pes13-fex.nro' if arena else
                   'local/high-trace-v3/pes13-fex.nro' if scratch else 'local/high-trace-v2/pes13-fex.nro')
    assert sha(rollback)==('b410d7b9e7790fa7d062208897faf089e52a2bc5837c89e7c0268ca4ecc7f63a' if rust else
                          '4bb3b382025500af926b9c5dcc31852173b98fc78df61549a7e6523812edf3e5' if general else
                          '055a586f244991543f24971ecfa0db95cd9cc7ae321d556e9069e52d93803c3c' if spages else
                          '186cf3be8fee1fbfdfb8f3b9f0b3014fae50644a98ae7a8e0ad22682e1fdebf8' if stacks else
                          'd6c6a6f0e28c902e726bf762b2ecdb593a4e6685d982c2df38e11a2434925136' if pages else
                          '26319d01e92774970b87c4917b99d291f490edc876735d06fa7caf568250af9e' if scratch64 else
                          '9daa21a9c78a5517418c398988cb8e91e71cd98ff09ec51592116eab242827f9' if live else
                          '4905633075c7fa50e04d78fd17cb72e1673200c8ce5ee37886155c50d0ed477b' if crash else
                          'd2f6417dc48d498eb3418e60953f2d813d87b2e35b7521edabb6b2c1b4340c8f' if arena else
                          '84aacd5f60acddf40e8f86328a075bad3319fdecd26844c91ba55e4b4cb5e241' if scratch else
                          '6d40a46dfcb15d88ad9dfc940250eb45712a2024054a2194da275f84dec2ab1e')
    copy(work/'pes13-fex.nro','switch/pes13-fex/pes13-fex.nro')
    marker=out/'switch/pes13-fex/launcher/diagnostics.txt';marker.parent.mkdir(parents=True);marker.write_bytes(b'1\n')
    copy(rollback,'rollback/switch/pes13-fex/pes13-fex.nro')
    for name in ['build-report.json','dependency-diff.json']:copy(work/name,'evidence/'+name)
    if general:copy(work/'candidate-diff.json','evidence/candidate-diff.json')
    if scratch64:copy(work/'input-analysis.json','evidence/input-analysis.json')
    for name in receipts:copy(work/'tests'/name,'evidence/'+name)
    copy(ROOT/('docs/FEXTENDO-HIGH-NATIVE-HEAP.md' if rust else 'docs/FEXTENDO-HIGH-FRAGMENTED-HEAP.md' if general else 'docs/FEXTENDO-HIGH-SCRATCH-PAGES.md' if spages else 'docs/FEXTENDO-HIGH-THREAD-STACK.md' if stacks else 'docs/FEXTENDO-HIGH-PAGE-STORE.md' if pages else 'docs/FEXTENDO-HIGH-SCRATCH64.md' if scratch64 else 'docs/FEXTENDO-HIGH-LIVE-FREEZE.md' if live else 'docs/FEXTENDO-CRASH-LOG.md' if crash else 'docs/FEXTENDO-HIGH-SCRATCH-ARENA.md' if arena else
               'docs/FEXTENDO-HIGH-SCRATCH-RESERVE.md' if scratch else 'docs/FEXTENDO-HIGH-TRACE-V3.md'),'DEVELOPER-NOTES.md')
    for name in ['LICENSE','THIRD_PARTY.md']:copy(ROOT/name,name)
    for source in (ROOT/'licenses').rglob('*'):
        if source.is_file():copy(source,str(source.relative_to(ROOT)))
    sources=set(report['feature_sources'])|set(report['build_scripts'])|{
        'tools/package-fextendo-high-trace.py','tools/build-fex-runtime.py','release/runtime-lock.json',
        'tests/fextendo_transition_binary.py','tests/fextendo_transition_host.py','tests/fextendo_transition_patches.py',
        'tests/fextendo_transition_trace.c','tests/fextendo_diagnostics.c','tests/fextendo_gamepad_binary.py',
        'tests/fextendo_keyboard_binary.py','tests/fextendo_osk_binary.py','tests/fextendo_keyboard_delivery.py',
        'tests/fextendo_silent.py','tests/fex_reservations.py','tests/fex_alloc.py'}
    if scratch:
        sources.update(('tests/fextendo_scratch_binary.py','tests/fextendo_scratch_host.py',
                        'tests/fextendo_scratch_patches.py','tests/fex_heap_native.c'))
        sources.add('tests/fextendo_scratch_arena.c' if arena else 'tests/fextendo_scratch_reserve.c')
        for name in report['native_fex_sources']:copy(work/'native-fex'/name,'source/generated/native-fex/'+name)
    if crash:sources.update(('tests/fextendo_crash.c','tests/fextendo_crash_host.py','tests/fextendo_crash_binary.py'))
    if live:sources.update(('tests/fextendo_live_threads.c','tests/fextendo_live_binary.py','docs/FEXTENDO-CRASH-LOG.md'))
    if stacks:sources.update(('tests/fextendo_thread_stack.c','tests/fextendo_thread_stack_host.py','tests/fextendo_thread_stack_binary.py'))
    if spages:
        sources.update(('tests/fextendo_scratch_pages.c','tests/fextendo_scratch_pages_host.py','tests/fextendo_scratch_pages_binary.py'))
        regressions=json.loads((work/'tests/scratch-pages-arm64.json').read_text())['regressions']
        assert len(regressions)==2 and all(r['succeeded']!=r['baseline'] for r in regressions)
    if general:
        sources.update(('tests/fextendo_fragmented_heap_binary.py','tests/fextendo_fragmented_heap_addresses.py'))
        regressions=json.loads((work/'tests/fragmented-heap-arm64.json').read_text())['regressions']
        assert len(regressions)==4 and all(r['succeeded']!=r['baseline'] for r in regressions)
    if rust:
        sources.update(('tests/fextendo_rust_heap.c','tests/fextendo_rust_heap_host.py','tests/fextendo_rust_heap_binary.py'))
        assert sha(work/'fextendo_rust_symbols.h')==report['rust_heap_binding']['header_sha256']
        assert report['native_dependencies']['mesa/libnak_rs.a']==report['rust_heap_binding']['libnak_rs_sha256']
        copy(work/'fextendo_rust_symbols.h','source/generated/fextendo_rust_symbols.h')
    if pages:
        sources.update(('tests/fextendo_page_store.c','tests/fextendo_page_store_host.py','tests/fextendo_page_store_binary.py'))
        receipt=json.loads((work/'tests/page-store-arm64.json').read_text())
        assert len(receipt['regressions'])==4
        assert all(r['succeeded'] != r['baseline'] for r in receipt['regressions'])
        host=json.loads((work/'tests/page-store-host.json').read_text())
        for name,digest in host['generated_sources'].items():assert report['generated_sources'][name]==digest,name
        for name in ('horizon.c','horizon_memfile.h','horizon_page_store.h','horizon_store_backing.h'):
            relative='dlls/ntdll/unix/'+name
            assert sha(work/'native-wine'/relative)==report['generated_sources'][relative],relative
            copy(work/'native-wine'/relative,'source/generated/native-wine/'+relative)
    for name in sorted(sources):copy(ROOT/name,'source/'+name)
    assets=inspect_nro((work/'pes13-fex.nro').read_bytes(),expected_title='PES13 - FEXTendo',expected_version='0.3.8-test')
    (out/'evidence/nro-assets.json').write_text(json.dumps(assets,indent=2)+'\n')
    (out/'README.txt').write_text('''FEXTendo HIGH Trace v3 - identifikasi alasan fatal FEX

PASANG
1. Tutup PES melalui HOME > X > Close.
2. Salin folder switch dari paket ini ke root microSD, timpa file yang sama.
   Isinya hanya pes13-fex.nro dan launcher/diagnostics.txt untuk mengaktifkan trace.
3. Pakai HIGH + Default DXVK dan clock yang sama dengan tes sebelumnya.
   Reproduksi replay/transisi yang membuat freeze.
4. Jika gambar freeze dan HOME masih merespons, tunggu sekitar 10-15 detik,
   lalu tutup. Jika aplikasi force-close sendiri, langsung ambil log.
5. Kirim switch/pes13-fex/transition.log sebelum menjalankan ulang.
   Jika tes dua kali, simpan juga transition.previous.log.
   Catat event terakhir dan apakah force-close sendiri atau ditutup manual.

Log harus memiliki baris TRACE_V3 di awal. Baris MODULE/FAILMSG merekam
alamat DLL serta alasan FEX menghentikan thread. Log mencatat setiap 2 detik,
maksimal 20 menit sejak frame game pertama. Tidak perlu forwarder baru.
Game, save, settings.dat, DXVK dan DLL FEX memakai instalasi yang sudah ada.
Menu settings berkelompok dan keyboard ringkas dari preview sebelumnya tetap ada.
Tidak ada perubahan preset, timing game, atau pembatas FPS khusus replay.

SELESAI TES / ROLLBACK
Hapus switch/pes13-fex/launcher/diagnostics.txt untuk mematikan trace.
Untuk kembali ke NRO diagnostik v2 sebelumnya, salin rollback/switch
ke root microSD. Jangan salin seluruh folder rollback sebagai instalasi.

STATUS
Build, pemeriksaan perubahan sumber Vulkan, tes host ASan/UBSan, serta tes
binary ARM64 dengan layanan OS simulasi lulus. Belum dites pada Switch.
Pencatatan aktif memiliki overhead; paket ini untuk mencari penyebab freeze,
bukan benchmark atau janji fix HIGH. Lihat DEVELOPER-NOTES.md dan evidence.
''',encoding='utf-8')
    if arena:
        (out/'README.txt').write_text('''FEXTendo HIGH - scratch arena v2 candidate

Temuan: cadangan 8 MiB berhasil dipakai ulang, tetapi transisi meminta
16 MiB dan gagal walaupun keempat blok sedang kosong. V2 memakai satu
area berurutan yang dapat dibagi dan digabung saat dilepas. Batas total
cadangan tetap 32 MiB. Belum diverifikasi di Switch.

PASANG DAN TES
1. Tutup PES lewat HOME > X > Close.
2. Salin folder switch dari paket ini ke root microSD, timpa dua file:
   switch/pes13-fex/pes13-fex.nro
   switch/pes13-fex/launcher/diagnostics.txt
3. Gunakan HIGH + Default DXVK dan clock tetap seperti tes sebelumnya.
4. Main sekitar 10 menit, beberapa kali bola keluar/replay, corner dan goal.
5. Kirim switch/pes13-fex/transition.log, termasuk jika tes berhasil.
   Jika freeze, tunggu sekitar 10 detik bila memungkinkan lalu tutup.
   Simpan transition.previous.log juga jika melakukan dua run.

Log yang benar memuat TRACE_V3 dan SCRATCH_V2. Baris SCRATCH_V2 kini
mencakup buffer 16 MiB dan ukuran lain, ruang kosong berurutan, serta
ukuran terakhir yang gagal. Pencatatan setiap 2 detik, maksimal 20 menit.
Game, save, preset, DXVK, DLL FEX dan timing tidak diubah paket ini.
Menu settings berkelompok dan keyboard ringkas tetap tersedia.

ROLLBACK
Salin rollback/switch ke root microSD untuk kembali ke versi cadangan
empat blok 8 MiB yang terakhir dites. Hapus launcher/diagnostics.txt
untuk mematikan trace; ini tidak mematikan arena memori.
Folder source/evidence/rollback tidak perlu disalin sebagai instalasi.

VALIDASI
Tes host ASan/UBSan dan ARM64 dengan layanan OS simulasi lulus.
Kasus empat buffer 8 MiB dilepas lalu meminta 16 MiB saat heap tertekan
gagal pada binary sebelumnya dan berhasil pada binary baru.
Lihat DEVELOPER-NOTES.md dan evidence untuk detail dan batas pengujian.
''',encoding='utf-8')
    elif scratch:
        (out/'README.txt').write_text('''FEXTendo HIGH - compiler scratch reserve candidate

Paket ini menargetkan kegagalan alokasi buffer kompilasi FEX 8 MiB
yang menghentikan pertandingan meskipun frame/penonton tetap berjalan.
Cadangan maksimal 32 MiB disiapkan saat startup dan dipakai ulang.
Ini kandidat perbaikan; belum diverifikasi di Switch.

PASANG
1. Tutup PES lewat HOME > X > Close.
2. Salin folder switch dari paket ini ke root microSD dan timpa dua file:
   switch/pes13-fex/pes13-fex.nro
   switch/pes13-fex/launcher/diagnostics.txt
3. Gunakan HIGH + Default DXVK dan clock tetap seperti tes sebelumnya.
4. Main sekitar 10 menit dengan beberapa replay, bola keluar, corner dan goal.
5. Kirim switch/pes13-fex/transition.log, termasuk jika tes berhasil.
   Jika freeze, tunggu sekitar 10 detik bila memungkinkan sebelum menutup.
   Simpan transition.previous.log juga jika mencoba dua kali.

Log memuat TRACE_V3 dan baris SCRATCH untuk melihat pemakaian cadangan.
Folder source/evidence/rollback tidak perlu disalin sebagai instalasi.
Game, save, DLL FEX, DXVK, preset dan timing tetap memakai yang sebelumnya.
Menu settings berkelompok dan keyboard ringkas tetap tersedia.
Kegagalan pemetaan memori saat startup pada log previous adalah masalah
berbeda; paket ini belum diklaim menyelesaikannya.

SELESAI TES / ROLLBACK
Hapus launcher/diagnostics.txt untuk mematikan trace (cadangan tetap aktif).
Untuk membatalkan perubahan cadangan, salin rollback/switch ke root microSD.
Rollback memulihkan NRO diagnostik v3 yang dipakai pada log terakhir.

VALIDASI
Build native, tes ASan/UBSan dan binary ARM64 dengan layanan OS yang
dimodelkan lulus. Lihat DEVELOPER-NOTES.md dan evidence untuk bukti,
batas tes, overhead trace, dan biaya memori cadangan maksimal 32 MiB.
''',encoding='utf-8')
    if crash:
        (out/'README.txt').write_text('''FEXTendo HIGH - direct crash.log v1

PASANG
1. Tutup PES melalui HOME > X > Close.
2. Salin folder switch dari paket ini ke root microSD dan timpa file yang sama.
   Paket berisi pes13-fex.nro dan launcher/diagnostics.txt, tanpa ZIP.
3. Jalankan HIGH + Default DXVK dengan clock tetap, lalu ulangi event
   bola keluar/replay/transisi yang biasanya memicu freeze atau force-close.

LOG YANG DIAMBIL
switch/pes13-fex/crash.log
switch/pes13-fex/transition.log

Tidak perlu memilih laporan berdasarkan tanggal. crash.log memuat build ID
NRO, identitas sesi, waktu sejak mulai, dan lokasi error yang tertangkap.
Jika aplikasi sudah dibuka ulang satu kali, ambil juga crash.previous.log
dan transition.previous.log. Sebaiknya salin log sebelum membuka ulang PES.

crash.log disiapkan saat startup, maksimum 18 KiB dan delapan record.
Saat error fatal terdeteksi, record ditulis dan di-flush langsung tanpa
menunggu worker dua detik. Gameplay normal tidak menulis crash.log terus.
Baris Status=armed saja berarti belum ada kegagalan yang tertangkap,
bukan bukti aplikasi keluar normal. Cari baris RECORD= untuk hasil capture.

Pencatat menangkap native exception yang tidak tertangani, FEX STOP,
nonzero guest exit, serta abort/diagAbortWithResult/svcBreak yang melewati
wrapper. Tidak semua crash bisa dicatat dari dalam proses: penghentian
langsung oleh sistem, exception entry kehabisan slot, atau FS tidak merespons
masih dapat membutuhkan laporan Atmosphere. Freeze tanpa fatal tetap
dianalisis lewat transition.log. Pencatat ini belum diuji pada Switch.

Kandidat mempertahankan scratch arena v2, preset, renderer, timing game,
DLL FEX dan semua perbaikan input/settings dari build sebelumnya.
Ini penambahan diagnosis; bukan klaim HIGH sudah sembuh atau FPS meningkat.

ROLLBACK
Salin rollback/switch ke root microSD untuk kembali ke scratch arena v2.
Hapus launcher/diagnostics.txt untuk menonaktifkan trace dua detik;
crash.log tetap aktif pada NRO kandidat ini. Folder source/evidence/rollback
tidak perlu disalin sebagai instalasi.

Tes host ASan/UBSan, binary ARM64 dengan layanan OS simulasi, integritas
wrapper Vulkan, scratch allocator, controller dan keyboard lulus.
Lihat evidence dan DEVELOPER-NOTES.md untuk ruang lingkup serta batas tes.
''',encoding='utf-8')
    if live:
        (out/'README.txt').write_text('''FEXTendo HIGH - live-freeze diagnostic v1

Ditujukan untuk pertandingan membeku sementara penonton masih bergerak.
Ini build diagnosis lanjutan, belum merupakan fix HIGH atau optimasi FPS.

PASANG
1. Tutup PES melalui HOME > X > Close.
2. Salin isi folder switch paket ini ke folder switch di microSD. Timpa:
   switch/pes13-fex/pes13-fex.nro
   switch/pes13-fex/launcher/diagnostics.txt
3. Gunakan HIGH + Default DXVK dan clock tetap seperti tes sebelumnya.
4. Uji half-time, bola keluar, replay atau transisi yang memicu freeze.
5. Jika pertandingan freeze tapi penonton bergerak, biarkan 15-20 detik
   sebelum menutup lewat HOME > X > Close. Ambil sebelum membuka ulang:
   switch/pes13-fex/transition.log
   switch/pes13-fex/crash.log
   Jika sempat membuka ulang sekali, ambil kedua file .previous.log juga.

Baris LIVE_TRACE_V1 dan CRASH_V2 menandai paket ini. Posisi thread kini
diambil setiap enam detik meskipun frame terus tampil, dengan waktu capture
tercatat. Alokasi gagal menyertakan alamat pemanggil dan errno. Build ID
crash.log diperbaiki agar binary dan alamat thread dapat dicocokkan.
Trace tetap dibatasi 600 sampel dua detik. Overhead pada Switch belum diukur.

Paket hanya menimpa dua file. Save, game, DXVK dan DLL FEX memakai instalasi
yang sudah ada. Menu dan keyboard tetap seperti preview sebelumnya.
Folder source, evidence dan rollback tidak perlu disalin sebagai instalasi.
Tidak perlu ZIP atau forwarder baru.

ROLLBACK
Salin rollback/switch ke microSD untuk kembali ke crash-log v1 sebelumnya.
Hapus launcher/diagnostics.txt untuk mematikan trace dan sampling thread;
crash.log tetap aktif pada NRO ini.

VALIDASI
Build native, ASan/UBSan, tes binary ARM64 dan integritas sumber lulus.
Belum dites di Switch. Bukti dan batas pengujian ada di evidence serta
DEVELOPER-NOTES.md. Hasil tes perangkat diperlukan untuk menetapkan fix.
''',encoding='utf-8')
    if scratch64:
        receipt=json.loads((work/'tests/scratch-arm64.json').read_text())
        assert receipt['compiler_overlap']['before_succeeded'] is False and receipt['compiler_overlap']['after_succeeded'] is True
        (out/'README.txt').write_text('''FEXTendo HIGH - scratch64 fix candidate v1

Log terakhir menangkap FEX STOP saat cadangan kompilasi 32 MiB penuh,
lalu permintaan buffer tambahan 8 MiB gagal. Thread utama berhenti.
Kandidat ini menyiapkan cadangan 64 MiB sebelum heap terfragmentasi.
Tambahan maksimal 32 MiB; bukan perubahan grafis, game speed atau FPS cap.

PASANG
1. Tutup PES lewat HOME > X > Close.
2. Salin folder switch dari paket ini ke root microSD, timpa dua file:
   switch/pes13-fex/pes13-fex.nro
   switch/pes13-fex/launcher/diagnostics.txt
3. Gunakan HIGH + Default DXVK dan clock tetap seperti tes sebelumnya.
4. Main melewati menit 7:10 dan half-time, idealnya 12-15 menit,
   dengan beberapa replay, bola keluar, corner dan free kick.
5. Kirim transition.log dan crash.log dari switch/pes13-fex sebelum
   membuka ulang, termasuk bila tes berhasil. Jika freeze, biarkan
   15-20 detik sebelum HOME > X > Close. Setelah satu kali relaunch,
   sertakan transition.previous.log dan crash.previous.log juga.

Log yang benar memuat SCRATCH_V3 capacity=67108864. Memori cadangan
yang gagal disiapkan akan dilaporkan dengan kapasitas lebih kecil.
LIVE_TRACE_V1 dan CRASH_V2 tetap aktif untuk menelusuri hasilnya.
Save, game, DXVK, DLL FEX, menu dan keyboard memakai versi sebelumnya.
Tidak perlu ZIP atau forwarder baru. Salin hanya folder switch.

ROLLBACK
Salin rollback/switch ke microSD untuk kembali ke live-freeze v1 (32 MiB).
Hapus launcher/diagnostics.txt untuk mematikan pencatatan berkala;
cadangan 64 MiB dan crash.log tetap aktif pada NRO kandidat ini.

VALIDASI
Kasus 16+8+8 MiB masih terpakai lalu meminta 8 MiB berhasil direproduksi
pada tes ARM64: binary lama gagal, kandidat baru berhasil tanpa merusak
buffer yang sedang dipakai. Tes host ASan/UBSan dan integrasi lokal lulus.
Belum diuji di Switch; ini kandidat perbaikan untuk kegagalan yang tertangkap,
bukan jaminan seluruh penyebab freeze HIGH sudah selesai.
Lihat DEVELOPER-NOTES.md dan evidence untuk bukti serta batas pengujian.
''',encoding='utf-8')
    if pages:
        (out/'README.txt').write_text('''FEXTendo HIGH - Wine page-store candidate v1

Perbaikan untuk alokasi Wine 5 MiB dan 16 MiB yang gagal menjelang full-time.
Jika satu blok besar tidak tersedia, Wine memakai potongan halaman kosong
dengan alamat guest tetap berurutan. Cadangan FEX 64 MiB tetap dipakai.
Ini kandidat perbaikan yang telah lolos tes lokal, belum diuji di Switch.

PASANG
1. Tutup PES lewat HOME > X > Close.
2. Salin folder switch dari paket ini ke root microSD, timpa dua file:
   switch/pes13-fex/pes13-fex.nro
   switch/pes13-fex/launcher/diagnostics.txt
3. Gunakan HIGH, renderer dan clock yang sama dengan tes terakhir.
4. Uji half-time, full-time sampai masuk result, lalu match berikutnya.
5. Simpan transition.log dan crash.log sebelum membuka ulang aplikasi.
   Jika freeze, tunggu 15-20 detik bila memungkinkan, lalu tutup.
   Sertakan file .previous.log jika sudah sempat relaunch.

Log baru memuat PAGES_V1 dan SCRATCH_V3. ALLOC_SITE ukuran besar masih
bisa muncul bila berhasil dipulihkan dengan potongan kecil; PAGES_V1
membedakan recovery dari kegagalan akhir. crash.log mencatat candidate
high-page-store-v1 dan build ID untuk memverifikasi NRO yang dijalankan.

Paket tidak mengganti save, game, DXVK, DLL FEX, preset atau game speed.
Tidak perlu ZIP atau forwarder baru. Salin hanya folder switch.

ROLLBACK
Salin rollback/switch ke root microSD untuk kembali ke scratch64 terakhir.
Hapus launcher/diagnostics.txt untuk mematikan trace berkala; fallback
memori dan crash.log tetap aktif. Folder source/evidence/rollback tidak
perlu ikut disalin sebagai instalasi.

VALIDASI
Kedua alokasi gagal direproduksi pada ELF sebelumnya dan berhasil pada
ELF baru dalam tes ARM64 dengan allocator/layanan OS simulasi. Tes host
ASan/UBSan dan pemeriksaan controller/keyboard/FEX juga lulus. Pengujian
lokal belum membuktikan transisi full-time HIGH pada perangkat; kirim
log juga ketika result berhasil terbuka. Detail ada di DEVELOPER-NOTES.md.
''',encoding='utf-8')
    if stacks:
        (out/'README.txt').write_text('''FEXTendo HIGH - native thread stack candidate v1

Log terakhir menunjukkan Wine berhasil memulihkan alokasi besar, tetapi
stack native sekitar 1 MiB gagal dialokasikan pada sekitar 2:25 sejak startup.
Build ini menyiapkan delapan cadangan stack sejak awal (total sekitar 8 MiB).
Cadangan hanya dipakai jika alokasi stack normal gagal. Ukuran stack dan
layout TLS libnx tetap sama; stack digunakan ulang hanya setelah dilepas OS.
Fallback Wine page-store dan cadangan FEX 64 MiB tetap aktif.

PASANG
1. Tutup PES lewat HOME > X > Close.
2. Salin folder switch ke root microSD, timpa file yang sama.
3. Tes HIGH dengan renderer dan clock yang sama, hingga full-time/result.
4. Simpan transition.log dan crash.log sebelum menjalankan ulang.
   Jika freeze, tunggu 15-20 detik bila memungkinkan, lalu tutup aplikasi.
   Catat event terakhir; sertakan .previous.log bila sudah membuka ulang.

transition.log kini memuat THREAD_STACK_V1: recovered menghitung alokasi
stack yang dipulihkan, failed menghitung threadCreate yang tetap gagal,
exhausted mencatat cadangan habis, quarantined mencatat stack yang belum
aman digunakan ulang. EVENT kind=12 mencatat waktu/kode kegagalan thread.
crash.log harus menunjukkan Candidate=high-thread-stack-v1.

Paket hanya memasang NRO dan launcher/diagnostics.txt. Save, game, preset,
DXVK dan DLL FEX memakai instalasi yang sama. Salin hanya folder switch.
Tidak perlu forwarder baru atau ZIP.

ROLLBACK
Salin rollback/switch ke root microSD untuk kembali ke high-page-store-v1.
Hapus launcher/diagnostics.txt untuk mematikan trace berkala; perbaikan
memori dan crash.log tetap aktif.

VALIDASI
Tes host ASan/UBSan dan tes ELF ARM64 dengan layanan OS simulasi dijalankan.
Lihat evidence dan DEVELOPER-NOTES.md. Belum diuji pada Switch; keberhasilan
alokasi lokal belum membuktikan semua penyebab freeze HIGH telah selesai.
''',encoding='utf-8')
    if spages:
        (out/'README.txt').write_text('''FEXTendo HIGH - fragmented compiler scratch candidate v1

Log terakhir: FEX meminta 16 MiB saat cadangan 64 MiB terpakai 56 MiB.
Heap masih memiliki sekitar 116 MiB bebas, tetapi blok berurutan 16 MiB
gagal dan FEX menghentikan worker. Clock RAM 1600 MHz bukan ukuran
kapasitas, sehingga log ini tidak membuktikan kebutuhan minimum OC RAM.

Build ini mempertahankan arena 64 MiB dan alokasi normal. Jika keduanya
tidak dapat melayani buffer compiler besar, runtime mengambil potongan
heap kecil (1 MiB, turun sampai 64 KiB) dan memetakannya menjadi satu
buffer virtual berurutan. FEX memakai buffer itu langsung, tanpa copy
per frame. Fallback memakai RAM saat dibutuhkan, maksimal 128 MiB total;
ini bukan tambahan cadangan resident 128 MiB saat startup.

PASANG
1. Tutup game lewat HOME > X > Close.
2. Salin hanya folder switch ke root microSD, timpa file yang sama.
3. Tes HIGH dengan renderer dan CPU/GPU/RAM sama seperti tes sebelumnya.
   Tidak perlu menaikkan clock RAM untuk tes ini.
4. Uji beberapa replay/transisi, half-time, full-time/result.
5. Simpan transition.log dan crash.log sebelum membuka ulang game.
   Jika freeze, tunggu 15-20 detik bila HOME masih merespons, lalu tutup.

crash.log harus menunjukkan Candidate=high-scratch-pages-v1.
transition.log menambah SCRATCH_PAGES_V1: recovered berarti buffer berhasil
dibentuk, failed berarti fallback tetap gagal. map_failed/last_result
membedakan kegagalan pemetaan dari kurangnya blok heap. quarantined
menandai memori yang ditahan karena OS belum berhasil melepas aliasnya.
THREAD_STACK_V1 dan PAGES_V1 tetap tersedia untuk jalur memori lainnya.

Kandidat ini belum diuji di Switch. Build, ASan/UBSan dan regresi ARM64
memeriksa alokasi, isi buffer, ownership, serta rollback. Tidak menjamin
semua freeze HIGH selesai. Preset grafis, limiter, DXVK dan DLL FEX tetap.

CAUTION SEMENTARA UNTUK USER
Preset HIGH masih eksperimental dan dapat freeze karena alokasi memori
runtime. Gunakan MEDIUM untuk penggunaan yang mengutamakan stabilitas.
Belum ada minimum clock RAM yang terbukti memperbaiki masalah ini.

ROLLBACK
Salin rollback/switch untuk kembali ke high-thread-stack-v1.
Hapus launcher/diagnostics.txt untuk mematikan trace berkala. Game, save,
settings.dat dan forwarder tidak perlu diubah. Detail: DEVELOPER-NOTES.md.
''',encoding='utf-8')
    if general:
        (out/'README.txt').write_text('''FEXTendo HIGH - general fragmented CPU heap candidate v1

Crash terakhir terekam pada 6:45: lookup FEX gagal memperoleh 1 MiB.
Sampel 0,44 detik sebelumnya masih menunjukkan sekitar 107 MiB total bebas.
Fallback sebelumnya mengecualikan permintaan di bawah 8 MiB.

Perbaikan ini berlaku untuk ukuran permintaan yang berbeda: scratch compiler,
lookup dan heap privat FEX memakai fallback halaman bersama. Jika alokasi
normal gagal, potongan heap dari 1 MiB hingga 4 KiB dipetakan menjadi satu
buffer virtual. Ukuran dibulatkan per halaman, tanpa pola ukuran crash khusus.
Memori dikembalikan setelah pemilik melepaskannya. Tidak ada copy per frame.
Maksimal 128 alokasi fallback dan 128 MiB total pada satu waktu; data diambil
saat diperlukan. Metadata tetap sekitar 1 MiB. Ini tidak menambah kapasitas
RAM dan tidak dapat menjamin alokasi ketika kapasitas/VA benar-benar habis.

PASANG
1. Tutup game lewat HOME > X > Close.
2. Salin hanya folder switch ke root microSD, timpa file yang sama.
3. Tes HIGH dengan renderer dan CPU/GPU/RAM yang sama.
4. Lewati beberapa bola keluar/replay, half-time, full-time dan hasil akhir.
   Jika lolos, lanjutkan match kedua dalam aplikasi yang sama untuk memeriksa
   pemakaian dan pengembalian memori pada event berulang.
5. Simpan crash.log dan transition.log sebelum membuka ulang game.

crash.log: Candidate=high-fragmented-heap-v1.
SCRATCH_PAGES_V1 sekarang mencatat fallback bersama scratch/lookup/heap FEX.
Tag dan field telemetry dipertahankan agar alat pembaca tetap kompatibel.
recovered/returned menunjukkan pemulihan/pengembalian; held_bytes menunjukkan
alokasi yang masih dimiliki; failed, map_failed, quarantined dan budget_refused
membantu membedakan kegagalan berikutnya. PAGES_V1 dan THREAD_STACK_V1 tetap
mencakup jalur Wine backing dan native stack.

DLL FEX, DXVK, grafis, limiter dan clock tidak diubah. Fallback tidak mengubah
alokasi kode JIT/GPU yang membutuhkan jenis mapping berbeda. Penyebab crash
terbaru terkonfirmasi, tetapi keberhasilan HIGH di Switch belum teruji.
Build dan tes lokal tersedia di evidence; detail di DEVELOPER-NOTES.md.

ROLLBACK
Salin rollback/switch untuk kembali ke high-scratch-pages-v1.
Hapus launcher/diagnostics.txt untuk mematikan trace berkala.
Game, save, settings.dat dan forwarder tidak perlu diubah.
''',encoding='utf-8')
    if rust:
        (out/'README.txt').write_text('''FEXTendo HIGH - native CPU heap candidate v1

Log terakhir berhenti di abort runtime Rust sekitar 1:53 sejak startup.
Fallback lookup 1 MiB sebelumnya berhasil dipakai lalu dilepas. Sampel
sebelum crash menunjukkan sekitar 66 MiB total heap bebas, tetapi angka
itu tidak menjamin ada satu blok berurutan yang cukup untuk permintaan baru.
Log lama belum membedakan Rust OOM dari panic/error compiler shader.

Kandidat ini mempertahankan alokasi normal terlebih dahulu dan memperluas
fallback CPU-page ke allocator Rust, termasuk alloc, zeroed, realloc dan
dealloc. Batas bersama tetap 128 MiB/128 pemilik, tanpa cadangan RAM baru.
Realloc yang gagal mempertahankan data lama. Alokasi GPU dan kode JIT
memakai jalurnya masing-masing.

PASANG DAN TES
1. Tutup game lewat HOME > X > Close.
2. Salin folder switch dari paket ini ke root microSD, timpa file yang sama.
3. Pakai HIGH dengan renderer dan clock yang sama dengan tes sebelumnya.
4. Uji bola keluar/replay, half-time hingga full-time/result. Jika berhasil,
   lanjutkan match kedua dalam aplikasi yang sama.
5. Simpan crash.log dan transition.log sebelum membuka ulang game.
   Jika force-close, ambil kedua log langsung; jika freeze, catat event terakhir.

crash.log harus menunjukkan Candidate=high-native-heap-v1.
RUST_HEAP_V1 pada transition.log mencatat alokasi Rust yang dipulihkan/gagal.
Jika abort lagi, NATIVE_CONTEXT menyimpan jejak pemanggilan yang dapat dibaca,
potongan output terakhir dan kegagalan alokasi terbaru pada thread tersebut.
RUST_ALLOCATION_FAILED berarti kedua jalur alokasi tetap gagal; record itu
sendiri belum berarti aplikasi crash, karena caller bisa menangani kegagalan.
Pencatatan detail dilakukan saat gagal, bukan logging tambahan setiap frame.

VALIDASI
Tes host dengan ASan/UBSan dan binary ARM64 dijalankan, termasuk kontrak
allocator Rust, mapping, rollback, alignment, serta jalur input/keyboard lama.
Belum diuji pada Switch. Ini kandidat pemulihan alokasi + diagnosis abort;
penyebab abort Rust pada run terakhir belum bisa dipastikan dari log lama.
Detail dan hasil validasi tersedia di DEVELOPER-NOTES.md dan evidence.

ROLLBACK
Salin rollback/switch untuk kembali ke high-fragmented-heap-v1.
Hapus launcher/diagnostics.txt untuk mematikan trace berkala.
Folder source/evidence/rollback tidak perlu disalin sebagai instalasi.
Game, save, settings.dat dan forwarder tetap menggunakan instalasi yang ada.
''',encoding='utf-8')
    assert sorted(str(f.relative_to(out/'switch')).replace('\\','/') for f in (out/'switch').rglob('*') if f.is_file())==[
        'pes13-fex/launcher/diagnostics.txt','pes13-fex/pes13-fex.nro']
    manifest={'hardware_tested':False,'baseline_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'nro_sha256':report['nro_sha256'],'rollback_nro_sha256':sha(rollback),
              'files':{str(f.relative_to(out)).replace('\\','/'):sha(f) for f in sorted(out.rglob('*')) if f.is_file()}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for name,digest in manifest['files'].items():assert sha(out/name)==digest,name
    print(json.dumps({'output':str(out),'files':len(manifest['files']),'nro_sha256':report['nro_sha256'],'hardware_tested':False},indent=2))
if __name__=='__main__':main()
