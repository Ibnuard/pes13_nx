# FEXTendo v3.4 — audit CPU dan stutter awal

Audit 29 September 2026. Bukti perangkat berasal dari **v3.3**, bukan hasil
pengujian perangkat v3.4. Dua sasaran perubahan v3.4 adalah mengembalikan
`dxvk-cs` ke penyeimbang core aplikasi dan mengurangi benturan pencarian kode
FEX pada cache L1. Dampak FPS belum terukur; tidak ada persentase peningkatan
yang dapat dijanjikan dari log ini.

## Capture yang diperiksa

- Snapshot: `local/fex3/review-jit128-e7da6e2040/device.log`.
- SHA-256: `e7da6e20403e8a70b5f7dd0274c5b8c1c2f4848130e8ffa1aa9bc2e47ee968dd`.
- Ukuran 2.241.520 byte; build `pes13-fextendo-renderer-jit-v1`.
- **DXVK 3.1.1, JIT 128** terkonfirmasi. Capture GPLAsync sebelumnya memakai
  renderer dan batas JIT berbeda, sehingga bukan A/B terkontrol.
- Waktu T+ dihitung dari Play-origin tick `10886180884025`, frekuensi
  19.200.000 Hz. `uptime_ms` JIT dan detik `[PROGRESS]` mempunyai origin berbeda.
- Capture ini melaporkan timestamp requested `0`; korelasi T+ tetap dapat
  direkonstruksi, tetapi tidak membuktikan overlay aktif pada tes ini.

## Core yang lengang adalah petunjuk, bukan kapasitas yang otomatis terpakai

Snapshot terakhir, baris 14927, mencatat 64 thread terdaftar memakai total
2,38 core. Angka berikut adalah jumlah thread yang **ditampilkan** pada core
tersebut, bukan seluruh pemakaian core fisik/OS.

| Core kernel (mulai 0) | Thread yang tampak | Jumlah yang tampak |
| --- | --- | ---: |
| 0 | Main game TID 4 67,4%; server 4,4%; descriptor 2,3%; helper 1,6% | 75,7% |
| 1 | Helper game TID 112 17,7%; dsound mixer 8,2%; DXVK submit 3,2% | 29,1% |
| 2 | Game worker TID 248 82,9%; server pasangannya 4,6%; DXVK queue 2,2%; helper server 1,4% | 91,1% |
| 3 | `dxvk-cs` TID 24, priority 63 | 21,2% |

Jika monitor menamai core dari 1, “core ketiga” adalah **kernel core 2**.
Core OS yang dimaksud kebijakan offload adalah **kernel core 3**, yaitu core
keempat. Tanpa mengetahui label monitor, keduanya tidak boleh disamakan.
Nama TID 112 tidak tercatat; pola self-suspend-nya tidak cukup untuk memastikan
bahwa itu thread audio.

Satu game worker tidak dapat dipecah menjadi beberapa core hanya dengan
affinity. Memindahkan worker 82,9% ke core yang kosong tetap menyisakan satu
worker serial. Namun `dxvk-cs` adalah pekerjaan terpisah yang bisa dipindahkan.
Pada kebijakan lama, worker ini dikecualikan dari balancer dan dipaksa ke core
3/priority 63. Mengembalikannya ke core aplikasi 0–2/prioritas normal memberi
balancer kesempatan memakai ruang di core 1 dan menghindari antrean pada core
OS. Ini tidak otomatis mengurangi jumlah instruksi CPU.

Sebagai ilustrasi aritmetika saja, memindahkan beban tercatat 21,2 poin ke
core 1 mengubah subtotal 29,1% menjadi 50,3%. Waktu tunggu, cache lokal,
pekerjaan OS, dan pekerjaan yang tidak tercantum dapat mengubah hasil nyata.
Core game 0/2 tidak serta-merta menjadi ringan. Baca penempatan dan prioritas
hasil syscall di log, lalu ukur frame; jangan memakai proyeksi ini sebagai FPS.

## Pekerjaan pertama kali masih mahal di CPU

| Metrik kumulatif terakhir | Panggilan | Waktu wall agregat | Puncak satu panggilan |
| --- | ---: | ---: | ---: |
| FEX `dispatch_compile` | 1.113.966 | 53,616 s | 98,847 ms |
| FEX `compile_code` | 53.882 | 40,014 s | 98,105 ms |
| FEX invalidate | 60.055 | 1,354 s | 2,534 ms |
| Native graphics pipeline | 984 | 6,138 s | 65,257 ms |
| Native compute pipeline | 8 | 0,005 s | 0,836 ms |
| Mesa `disk_cache_get` | 1.867 | 5,689 s | 42,889 ms |

`dispatch_compile` mencakup pencarian kode yang sudah dikompilasi. Selisih
jumlah 1.060.084 panggilan bukan satu juta kompilasi baru. `compile_code`
sendiri juga dapat menemukan hasil kompilasi thread lain setelah menunggu.
Timer bersarang dan thread berbeda dapat tumpang tindih; angka dalam tabel
**tidak boleh dijumlahkan sebagai durasi game membeku**.

Selisih durasi dua tahap FEX adalah sekitar **13,602 detik**. Itu menunjukkan
besarnya wilayah pencarian/locking/administrasi di luar tahap CompileCode,
termasuk scheduling dan instrumentasi. Itu bukan pengukuran biaya L1 saja.
Menghapus seluruh wilayah tersebut adalah skenario ideal yang tidak realistis;
perubahan hash L1 hanya menyasar bagian benturan lookup. Tidak tersedia batas
peningkatan FPS yang aman dari angka ini.

Pada baseline, indeks L1 memakai bit rendah RIP, sehingga alamat berjarak
64 KiB dapat saling menggusur walau cache belum terpakai merata. Hash yang
mencampur bit lebih tinggi dapat mengurangi benturan tanpa menambah alokasi
1 MiB per thread. Semua jalur insert, lookup, invalidation dan probe ARM64
harus memakai hash yang sama; tag RIP penuh tetap menentukan kecocokan.
Kasus tertentu juga bisa mengalami benturan baru, jadi jumlah dispatch dan
frame stabil harus ikut diuji, bukan hanya tes kebenaran cache.
Tes binary juga menunjukkan tambahan satu instruksi XOR pada hit cache
(dispatcher 13 versus 12 instruksi termasuk target hook). Workload sintetis
beralamat 64 KiB terpisah membaik, tetapi kontrol dengan benturan hash baru
memburuk. Keduanya uji mekanisme, bukan estimasi FPS perangkat.

Game worker pertama TID 164 mencatat **7.570 CompileCode / 7,773 detik agregat**
pada T+105,055–157,598. Contoh burst T+117,041–121,879 berisi 2.429 panggilan /
2,207 detik agregat; panggilan terlama pada burst itu hanya 7,458 ms.
Artinya akumulasi banyak kompilasi pendek tetap dapat mengganggu frame.
Worker berikutnya jauh lebih sedikit: TID 176 mencatat 1.882 / 2,338 detik,
dan TID 248 mencatat 463 / 0,580 detik. Jendela dan pekerjaannya berbeda;
ini mendukung pola cold work, bukan angka persentase peningkatan antarworker.

Pada tiga interval laporan `[PROGRESS]` 137–167 detik, pipeline grafis baru
berjumlah nol, sementara kompilasi FEX TID 164 terus muncul. Read game hanya
bertambah 6 panggilan / 19 ms dan SD 6 / 18 ms. Memperbesar cache shader atau
SD tidak menjelaskan seluruh stutter pada bagian itu.

## Perbaikan berikut yang paling layak diukur

| Urutan | Bukti dan perubahan yang layak dicoba | Ukuran keberhasilan dan batas |
| --- | --- | --- |
| 1 | Penempatan `dxvk-cs` di core aplikasi; hash lookup FEX L1 | Core/prioritas benar, dispatch berkurang pada adegan sama, gap gameplay turun tanpa penurunan kecepatan game; CPU game serial tetap ada. |
| 2 | Kurangi biaya transisi QPC/zero-delay dan statistik syscall pada polling panas | Pertahankan counter/frekuensi, APC, hasil yield, dan deadline; ukur CPU per panggilan serta frame. Jangan memperlambat jam atau menambah sleep untuk membuat persentase CPU terlihat bagus. |
| 3 | Ukur biaya native allocator FEX dan gunakan kembali workspace kecil bila benar dominan | Catat jumlah/ukuran alokasi, durasi allocator dan kompilasi; uji lintas thread, kegagalan, alignment, dan peak memory. Jangan menambah pool besar sebelum tahu kebutuhan. |
| 4 | Verifikasi persistensi serta latency pembacaan cache Mesa | Pisahkan hit dalam proses dari hit setelah fresh launch; kaitkan panggilan lambat dengan frame. Jangan menganggap cache 10 GB lebih cepat tanpa bukti eviction. |
| 5 | Kurangi pembalikan affinity saat fase game berubah | Ukur migrasi bolak-balik, frame dan audio; cooldown kecil/hysteresis hanya jika lebih baik, dengan pengecualian worker baru yang salah core. |
| 6 | Audit jalur event/mutex Wine dan biaya diagnostik | Ukur CPU dan caller pada event/reset/release; pertahankan aturan handle, waiter, APC, timeout dan teardown. Cache/shortcut sinkronisasi memerlukan tes race, bukan sekadar menghilangkan server call. |

**Polling adalah kandidat kuat berikutnya.** Pada interval laporan
126→137 detik terdapat **537.668 `NtQueryPerformanceCounter`** (ID `0x31`) dan
**506.337 `NtDelayExecution`** (`0x34`). TID 164 sendiri mencatat 502.589 yield
dengan total waktu handler 642,085 ms, rata-rata 1,278 µs. Itu belum mencakup
seluruh biaya x86 → FEX → WOW64 → native sebelum masuk handler. Native QPC
sudah sederhana: membaca counter monoton dan mengembalikan frekuensinya.
Sasaran yang perlu diprofilkan adalah transisi/dispatch dan statistik atomik,
bukan “membuat QPC bergerak lebih lambat”. Anti-spin saat ini sudah aktif:
39.015 pause, 2,148 detik park agregat; memperbesar pause tanpa bukti bisa
mengembalikan slow motion.

Lokasi audit: Wine `dlls/ntdll/unix/sync.c` (`NtDelayExecution`,
`NtQueryPerformanceCounter`), `dlls/ntdll/unix/signal_arm64.c`
(`wine_nx_do_syscall` mempunyai dua penambahan counter atomik per syscall),
`dlls/ntdll/ntsyscalls.h` untuk pemetaan ID, serta
`src/runtime/fex_yield_burst.h`. Semua ID di atas diverifikasi pada source
Wine build ini; bukan diasumsikan sama dengan versi Windows lain.

**Allocator:** `[FEX3-NHEAP]` terakhir melaporkan **5.006.026 alokasi**, peak
26.124 KiB, tanpa kegagalan. Alokasi kecil FEX menyeberang callback PE/native
ke malloc dan counter atomik di `src/fex/horizon_jit.c`; realloc di
`src/fex/module_heap.cpp` selalu allocate/copy/free. Jumlah besar dengan live
memory kecil memberi alasan memprofilkan churn, tetapi belum membuktikan
berapa waktu yang bisa diselamatkan. Pool per-thread juga harus menangani
free pada thread lain dan tidak boleh menghidupkan lagi masalah ruang alamat.

**Cache driver:** `driver_cache_get` di `src/runtime/fex_warm_runtime.h`
adalah pembungkus **Mesa `disk_cache_get`**, bukan export
`vkGetPipelineCacheData`. Ada 1.867 hit, nol miss, tetapi hit dapat berasal dari
run yang sedang berjalan. Waktu 5,689 detik dapat berada di dalam timer pipeline
6,138 detik; keduanya tidak dijumlahkan. Pada cache hit pun baca file,
dekompresi/deserialisasi, dan pembuatan pipeline masih mungkin menghabiskan
waktu. Bukti ini mendahulukan audit latency/persistensi daripada menaikkan
batas ukuran secara sembarang.

**Balancer:** 39 perpindahan; 7 pembalikan terdeteksi dalam sekitar 2–4 detik,
terutama TID 112. Penyeimbang saat ini sudah satu perpindahan per dua detik
dengan syarat keuntungan proyeksi >5 poin. Burst pekerjaan baru dapat membuat
snapshot sebelumnya basi. Cooldown dapat mengurangi migrasi, tetapi dapat
pula menahan worker di core sibuk; perlu A/B setelah kebijakan DXVK baru.

**Server dan diagnostik:** interval terakhir memuat 19.740 `event_op`
(rata-rata 42 µs), 16.015 `release_mutex` (30 µs), dan 24.168 `select`
(1.609 µs). Angka adalah wall time pulang-pergi dan wait, bukan CPU yang
seluruhnya bisa dihapus. Timer `suspend_thread` rata-rata 16,354 ms mencakup
park self-suspend; seluruh 35.712 self-wait sudah kembali pada snapshot
terakhir. Tidak ada bukti bahwa wait itu harus dipotong. Short trace memakai
antrean terbatas dan JIT log sudah dipindahkan dari jalur kompilasi; tetap
layak menjalankan satu pembanding diagnostik minimal untuk mengukur observer
overhead, tanpa mematikan penanganan fault atau menyembunyikan kegagalan.

## Yang tidak perlu diubah secara membabi buta

- **Thunks:** Wine Vulkan sudah menyeberang ke `winevulkan` native ARM64 dan
  Mesa/NVK yang dilink dalam NRO. FEX tidak menerjemahkan driver ARM64 itu
  sebagai x86. DXVK/game x86 dan konversi ABI tetap ada. Mengaktifkan satu
  variabel “FEX thunks” bukan jalan pintas baru untuk jalur yang sudah native;
  thunk API tambahan perlu profiling caller dan implementasi ABI yang tepat.
- **Memory-budget query:** tinggal lima panggilan, wall total tercatat 1 µs,
  nol query ≥1 ms. Ini bukan hotspot pada capture ini. Perbedaan resolusi
  timer menyebabkan total CPU terlapor 6 µs; jangan menafsirkan presisi µs
  tersebut sebagai benchmark.
- **GPU 99%:** dapat relevan untuk camera pan, tetapi bukan bukti tunggal
  penyebab freeze awal. Acquire/submit/fence adalah waktu CPU/parking, bukan
  GPU timestamp. Bandingkan 720p dan 540p hanya setelah kondisi CPU tetap,
  atau tambahkan timing GPU yang didukung driver. Pertahankan kecepatan
  simulasi dan pisahkan loading, replay, serta gameplay.
- **Lossless/frame generation:** menambah kerja capture/interpolasi/GPU dan
  memori. Ia membutuhkan frame asli sehingga tidak menghapus freeze kompilasi.
  Tetap OFF untuk A/B CPU; ukur FPS game dan frame tampilan secara terpisah.
  Dukungan backend dan kompatibilitas DLL pengguna harus diverifikasi sendiri.

## Pengujian yang membuat hasilnya dapat dipercaya

Mulai dari fresh launch dengan renderer **3.1.1**, JIT128, tim/stadion/camera,
preset dan OC yang sama. Ulangi kickoff, umpan cepat, shooting, bola lambung,
replay, lalu match kedua tanpa menutup aplikasi. Catat T+ dan simpan log sesudah
match kedua. Ulang minimal dua fresh launch per kondisi dengan urutan A/B lalu
B/A jika memungkinkan. Renderer, JIT cap, penempatan core, dan frame generation
tidak diubah sekaligus ketika membandingkan satu perubahan.

Bandingkan gap gameplay >50 ms, peak serta total waktu frame melewati budget,
jumlah/durasi CompileCode, dispatch, penempatan thread, dan kecepatan jam game
terhadap waktu nyata. Log ini memiliki **502 gap tercatat dan 85 dropped**;
data tersebut terbatas, sehingga tidak cukup untuk menghitung p99 seluruh
frame secara benar. Gap maksimum 5,512 detik berada pada
T+86,584–92,096, sebelum worker game awal terbentuk sekitar T+104; jangan
melabelinya kickoff tanpa penanda kejadian.

Laporan berikutnya harus menyebut perubahan yang benar-benar aktif, hasil
perangkat, dan regresi. Lulus tes host memastikan kebijakan dan ABI berjalan
sesuai kontrak; itu belum membuktikan pengalaman bermain lebih lancar.
