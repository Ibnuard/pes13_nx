# Audit stabilitas dan reusable runtime Wine/FEX di Horizon

Tanggal: 27 September 2026. Repository HEAD saat audit:
`c4ec5cb2d0262841c36c6cbb5472c8a2f3ea26e3`.

**Kesimpulan:** fondasi host ABI, dual mapping JIT, heap native, dan bridge exception
sudah cukup terpisah untuk dikembangkan menjadi runtime beberapa game x86.
Namun konfigurasi PES yang playable belum dapat dijadikan default kompatibilitas
umum. Ada masalah correctness yang dapat direproduksi di source, kebijakan
performa yang mengubah kontrak x86, dan asumsi executable PES di launcher.
Tidak ada temuan audit ini yang sudah dibuktikan sebagai penyebab stutter PES.

Audit tidak mengubah source runtime, konfigurasi, DLL/NRO, ataupun pekerjaan
suspend/resume agent lain. Hasil baru berupa dokumen ini dan bukti lokal di
`local/fex3/reusability-audit-20260927/`. Source cache yang dibaca disalin atau
hash-nya dicatat karena build tree sedang digunakan pekerjaan lain.

## Bukti runtime yang digunakan

| Bukti | Identitas | Interpretasi |
| --- | --- | --- |
| `TEST RESULT/fex-runtime.log` | SHA256 `8d2245dc98784b20de81cf09685603a8f2cc7247cddfc0259a886b19b5767593`, 207238 byte | Build marker event-diagnostic, marker same-core Sleep(0), preset Fastest |
| `config/drive_c/PES13/fex-runtime.log` | SHA256 `3b3014b410d4b507bc45819e9f7542cac719611a5257244c003ca5dd3ef8cf8b`, 250501 byte | Build timing-audit; dianalisis terpisah |
| `TEST RESULT/SysDVR_2026_09_27_17_06_55.mp4` | SHA256 `690e869d60182dc19f850b687991d36432d88ee82f8dca9c17a82eb6a4b514cf` | 1280×720, durasi 231.210 detik, nominal capture 30 fps |

Pada log terbaru, 27 interval berdurasi nonzero meliputi startup/menu/transisi/game.
Interval dengan present berada pada 16.382–57.331 panggilan present/detik.
Enam interval terakhir menghasilkan 2474 present dalam 60141 ms, atau 41.137/s.
Angka ini **bukan FPS unik yang tampil atau kecepatan simulasi**. Capture 30 fps
juga tidak membuktikan game menghasilkan 30 frame unik per detik.

Histogram mencatat 630 gap di atas 50 ms, termasuk 115 di atas 100 ms, dari
10243 sampel gap pada interval yang memiliki present. Puncak sejak peluncuran
998203 µs. Angka ini mencakup loading/transisi, bukan persentil khusus gameplay.
Rata-rata waktu native Present per interval hanya 283–1014 µs. Contoh log
baris 1462: 16.382 present/s dengan rata-rata native Present 335 µs. Ada pekerjaan,
pacing, antrean, atau penjadwalan di luar call ini; waktu call CPU tidak mengukur
GPU execution dan tidak cukup untuk menyatakan GPU bebas bottleneck.

Tidak ditemukan `[EXC]`/`[EXIT]`, error present, atau kegagalan heap privat pada
log terbaru. Sampel heap privat terakhir: live 27225 KiB, peak 30557 KiB,
failures=0. Ini bukan ukuran seluruh memori: JIT, guest VM, dan GPU terpisah.
`audio_under` meningkat dari 26 ke 69 antara laporan PROGRESS 116s dan 236s;
ada indikator underrun audio yang layak dikorelasikan dengan pacing. Nilai
itu sendiri tidak menetapkan sumber masalah.

Enam frame video diekstrak ulang secara independen pada seek 124/137, 153/168,
dan 196/225 detik. Terlihat scoreboard kira-kira 11:32→14:17, 14:53→16:53,
dan 17:47→24:07. Ini mendukung perubahan laju progres dalam satu rekaman;
seek tersebut bukan penyelarasan presisi dengan log. Catatan audit sebelumnya
memiliki pembacaan PTS lebih rinci dalam `local/fex3/samecore-audit/<hash>/`.
Tidak ada marker bersama yang membenarkan pencocokan kejadian video ke satu
baris log tertentu. Tidak ada baseline PC dengan pengaturan durasi match sama
untuk menetapkan laju absolut yang benar. Klaim tanpa overclock berasal dari
laporan pengguna; log tidak merekam clock CPU/GPU/RAM.

## Temuan berurutan menurut prioritas kompatibilitas

### 1. P1 — cache RW alias JIT dapat membaca metadata dari dua generasi

Lokasi: `src/fex/module_host.cpp:53`, fungsi `CachedAlias`.

Reader membaca `rx`, lalu `size` dan `rw` secara terpisah. Tidak ada pemeriksaan
generasi setelah metadata dibaca. Slot yang tidak terkait target dapat direlease
dan dipublish ulang di tengah pembacaan. Atomics per field mencegah akses
non-atomic, tetapi tidak menjadikan ketiga field satu snapshot konsisten.

Reproduksi dengan body fungsi asli dan injeksi urutan interleaving yang sah:

- Slot A awal: RX=0x100000, RW=0x200000, size=0x1000.
- Target di slot B tetap hidup: RX=0x110000, RW=0x500000, size=0x1000.
- Setelah reader mengambil RX lama A, A diganti: RX=0x300000,
  RW=0x400000, size=0x20000.
- Lookup target `0x110020` mengembalikan **0x410020**, seharusnya **0x500020**.

Retensi owner B tidak melindungi slot A yang sedang dipindai. Salah alamat
alias dapat merusak kode JIT jika hasil itu digunakan untuk menulis. Jalur
native `find_mapping` dalam `src/fex/horizon_jit.c` sudah memvalidasi generasi;
cache PE belum mempunyai perlindungan setara. Jalur patch dari unaligned-fault
juga menggunakan helper alias, sehingga serialisasi compiler saja tidak cukup
sebagai jaminan tanpa audit seluruh caller.

Status: kegagalan helper terbukti pada source-slice; belum direproduksi sebagai
race pada Switch atau DLL terpasang. Tes yang ada di `tests/fex_alias_cache.py`
mencakup reuse berurutan, belum interleaving ini.

Perbaikan yang disarankan: snapshot dengan generation counter/epoch yang
divalidasi kembali, fallback native bila slot berubah, sambil mempertahankan
aturan lifetime owner. Hindari mutex blocking pada jalur exception. Validasi
alokasi/free cache lain secara bersamaan dengan patch/flush kode target hidup.

### 2. P1 — transfer floating-point WOW64 belum memenuhi kontrak context

Lokasi source FEX yang dipersiapkan:
`Source/Windows/WOW64/Module.cpp:239–301,338`.

Uji body floating-point asli mereproduksi tujuh pelanggaran: import/export
MXCSR tidak ditransfer; import/export x87 dengan TOP=3 tidak dirotasi;
representasi internal F64 tidak dikonversi saat import/export x87 80-bit;
data register legacy `FloatSave.RegisterArea` tidak diisi saat export.
Tiga kontrol (TOP=0/full80, FCW, XMM roundtrip) lulus.

Reconstruction juga menetapkan `MxCsr=0x1f80`. Ini berisiko pada exception,
perubahan context, dan callback yang mengandalkan pembulatan/status floating-point.
FXSAVE milik core sendiri melakukan rotasi TOP dan konversi F64→80-bit;
bridge memakai memcpy langsung. Pemeriksaan register ARM64/FPCR/FPSR native
pada boot tidak menguji serialisasi x86 ini.

[Sumber FEX yang dipin](https://raw.githubusercontent.com/FEX-Emu/FEX/e2f973fe931e6dc2ce523795e51ca1ac3ca85816/Source/Windows/WOW64/Module.cpp).
Reproduksi memakai source lokal hasil persiapan, bukan sekadar salinan upstream.

Status: host source-slice dengan struktur/helper yang dimodelkan; bukan eksekusi
instruksi guest lengkap. Belum membuktikan dampaknya pada PES. Perlu regresi
x86 untuk context/SEH dengan TOP≠0, MXCSR nondefault, FCW dan MXCSR berbeda,
serta F64/full80. Pemisahan domain rounding x87 dan SSE di FPCR juga perlu
regresi tersendiri; tidak diberi label terbukti oleh harness ini.

### 3. P1 — Fastest bukan default kompatibilitas; tes guest memaksa Control

Lokasi: `src/fex/module_profile.cpp:12`, `src/fex/horizon_jit.c:337`.

Log menjalankan x87 reduced precision dan scalar/vector/memcpy TSO=0.
Itu perubahan semantik numerik dan memory ordering. Game dengan komunikasi
antarworker yang bergantung pada ordering x86 dapat berperilaku berbeda.
Tetap aktifnya LOCK dan SMC tidak mengembalikan seluruh kontrak TSO.

`pes13_fex_select_performance_profile` selalu mengembalikan Control ketika
`guest_tests=1`. Karena itu PASS stress guest tidak memvalidasi profil Fastest
saat main. Binary profile tests memeriksa nilai config, bukan seluruh perilaku
multithread game dengan config tersebut.

Default runtime umum sebaiknya baseline paling konservatif yang tersedia:
x87 80-bit, ordering aktif, tanpa optimasi khusus executable. Fast/Fastest
menjadi pilihan per game. Baseline Control sendiri tetap perlu perbaikan FPU
di atas. Sediakan tes guest dalam **profil yang akan dikirim**, mencakup
publikasi data lintas thread, atomics, SIMD/memcpy, callback, dan exception.

### 4. P1 — semantik waitable timer pada baseline masih salah

Lokasi: handler timer Wine Horizon; patch yang sudah tersedia di
`tools/fex_runtime_fixes.py`, regressions `tests/fex_runtime_fixes.py`.

Baseline membuat timer signaled saat set tanpa menunggu deadline. Cancel
menghapus signaled state. Kontrak Windows mengharuskan cancel menghentikan
aktivasi berikutnya tetapi mempertahankan state signaled saat ini.
[Microsoft CancelWaitableTimer](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-cancelwaitabletimer).

Uji baseline timer gagal pada ekspektasi bahwa timer masa depan belum signaled.
Baseline affinity juga gagal: cache mask diperbarui sebelum SVC sukses,
sehingga permintaan identik tidak mencoba ulang setelah kegagalan.
Uji patch yang sudah ada lulus, termasuk expiry/rearm, reset mode, cancel,
periodic catch-up/overflow, polling, dan retry affinity.

Ini pekerjaan yang **sudah ada**, bukan patch baru audit ini. Source native
yang dibaca masih memiliki timer baseline; recipe same-core/resume memisahkan
`runtime_fixes=False`. Log tidak membuktikan bug timer terpicu dalam PES atau
SVC affinity gagal. Integrasikan perbaikan sebagai perubahan terpisah setelah
kontrol candidate suspend/resume selesai, dengan receipt dan tes binary.
APC timer serta timebase relative/absolute masih perlu coverage lebih luas.

### 5. P2 — optimasi dan launcher masih membawa asumsi PES

- `src/runtime/pes13_preload.c:11`: guard fixed image `0x00400000` dengan ukuran
  `0x0189a000`. Executable lain dapat membutuhkan rentang berbeda sebelum
  alokasi native dimulai. Mengganti nama target saja tidak cukup.
- `tools/fex_wine_patches.py:396`: target PES dan registry instalasi diaktifkan
  untuk semua mode non-test. Jalur prefix/settings/input juga masih PES.
- `src/fex/module_smc.cpp:27`: pengurangan frekuensi SMC mengenali basename
  `pes2013.exe` atau `d3d9.dll`, ditambah layout section. Nama `d3d9.dll` tidak
  membedakan DXVK yang diuji dari WineD3D/proxy/mod dengan nama sama.
  Fingerprint identitas dan opt-in per profil diperlukan sebelum dipakai umum.
- `fex_game_timing*` memiliki alamat/object PES yang sudah fingerprint-guarded.
  Pertahankan guard itu, dan tempatkan observer sebagai diagnostik game.

### 6. P2 — batas API, memori, dan pemulihan harus eksplisit

`src/runtime/fex_self_suspend.h:11` menolak suspend thread lain yang sedang
berjalan; implementasi native juga menolak remote termination. Ini keterbatasan
nyata untuk game/tool yang memerlukan operasi tersebut, bukan sesuatu yang
boleh disamarkan sebagai sukses. Audit ini tidak membuktikan coverage APC,
child process/launcher, I/O asinkron, atau seluruh API Wine.

Backend dikonfigurasi sebagai WOW64 32-bit. Dukungan beberapa game berarti
mulai dari game Windows x86 dalam permukaan API yang diuji; dukungan x64 tidak
muncul otomatis dari reusable host ABI.

JIT memakai buffer awal 128 MiB dan, pada profil performa, cadangan generasi
128 MiB. Dual mapping menghabiskan ruang alamat RW/RX selain backing fisik.
Cadangan yang membantu PES belum tentu cocok untuk game lain yang besar di
texture/guest VA. Sediakan budget dan telemetry terpisah untuk guest VA,
private heap, JIT generation/alias, dan Vulkan. Jangan menghitung alias sebagai
salinan fisik independen atau menyamakan free heap dengan ruang VA kontigu.

Di `BTCpuProcessInit`, hasil `NtAllocateVirtualMemory` untuk trampoline belum
dicek sebelum pointer dipakai. Kegagalan dapat menjadi fault native. Jalur
unhandled exception Horizon saat ini mencatat lalu memarkir thread selamanya;
baik untuk debugging, tetapi pada runtime umum bisa tampak sebagai hang.
Butuh status fatal yang dapat diamati supervisor, flush bounded, dan keluar
terkendali. Jangan menghapus buffer JIT yang masih direferensikan demi recovery.
Tidak ada kegagalan ini yang tercatat pada run terbaru.

## Pemisahan minimal agar reusable

| Lapisan | Tanggung jawab |
| --- | --- |
| Horizon host | JIT RW/RX, flush cache, heap native, clock monotonik, exception entry, capability/error reporting; tanpa alamat/nama game |
| Wine + backend FEX | Kontrak thread/wait/timer, VM, context x86, invalidation dan lifetime; baseline konservatif |
| Manifest dan profil game | EXE/cwd/args, image reservation hasil inspeksi PE/manifest terverifikasi, DLL overrides, input, registry, save paths, budget, opt-in TSO/x87/SMC |
| Diagnostics | Metrik generik pacing/CPU/GPU/I/O/audio/memory; reader PES sebagai tambahan per game |

Host ABI 3 sudah merupakan titik pemisahan yang bagus. Pertahankan validasi
magic/version/size, pasangan artifact yang diuji, dan source hashes. Tambahkan
identitas fitur/build serta effective config pada boot agar marker yang sama
pada beberapa eksperimen tidak membuat hasil tercampur. Rename simbol PES
bukan prioritas correctness.

## Urutan tindak lanjut yang disarankan

1. Selesaikan perbandingan NRO-only resume-gate yang sedang berjalan; pertahankan
   DLL, preset, scene, save, clocks, dan cache agar hasil bisa dibandingkan.
2. Tangani alias-cache generation dan serialisasi FPU dalam perubahan terpisah;
   lakukan source regression, tes linked ARM64, lalu guest x86 di Switch.
3. Bawa timer/affinity patch yang telah memiliki regresi ke baseline terverifikasi;
   jangan mencampurnya dengan eksperimen pacing yang belum punya hasil.
4. Pisahkan launcher/manifest PES dan profil performa dari core; pilih satu
   aplikasi x86 kecil selain PES untuk validasi generalisasi. Pilih game kedua
   dari kebutuhan API/rendering, bukan hanya popularitas.
5. Jalankan siklus load→main→menu→reload dan thread/DLL/JIT churn berulang.
   Catat high-water memory, guest VA terbesar, audio underrun, compile time,
   queue wait, serta p50/p95/p99 frame time pada segmen gameplay bertanda.
   Selaraskan video/log memakai marker bersama dan timestamp counter fisik.

## Reproduksi audit

Folder bukti lokal:
`local/fex3/reusability-audit-20260927/`.

- `latest.log`, `older.log`, `*-speed.json`: snapshot dan hasil analyzer.
- `source-hashes.json`, `*.snapshot`: identitas source yang dibaca.
- `reproduce.py`, `fpu-contract.cpp`, `alias-contract.cpp`, `contracts.json`:
  source-slice reproductions, compiler invocation, exit status, stdout/stderr.
- `timer-affinity.json`: hasil baseline RED dan patch GREEN yang dijalankan ulang.
- `video-<seek>s.png`: enam frame yang diperiksa ulang.

Perintah lokal:

```sh
python3 -B local/fex3/reusability-audit-20260927/reproduce.py
python3 -B tests/fex_runtime_fixes.py
python3 -B tests/fex_runtime_fixes.py --unpatched --only timers --scenario normal
python3 -B tests/fex_runtime_fixes.py --unpatched --only affinity
```

Script reproduksi memakai path source cache lokal yang tertulis di dalamnya;
ubah path jika source dipindahkan. Harness C++ dikompilasi dengan ASan/UBSan.
Kedua contract binaries mengembalikan exit 1 **karena pelanggaran semantik yang
diharapkan**, tanpa laporan sanitizer; wrapper menyimpan hasil dan keluar 0.
Baseline timer/affinity juga diharapkan gagal, sedangkan patch lulus.
Ini bukan bukti bahwa seluruh FEX/Wine lulus sanitizer. Source helpers/transport
tertentu dimodelkan, alias interleaving diinjeksi secara deterministik, dan audit
ini tidak menjalankan NRO di hardware. Tidak ada klaim perbaikan FPS atau
sertifikasi kompatibilitas lintas game.
