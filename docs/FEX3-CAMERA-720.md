# Camera pacing + 720p benchmark

Satu ZIP gabungan: Wine NRO baru, FEX emitter yang sama, VSync off, resolusi
1280×720 16:9, dan **kandidat Medium**. Preset pembanding dan rollback ada di
ZIP yang sama. Build serta tes lokal lulus; kickoff dan stutter belum dinyatakan
selesai pada Switch.

**Status kualitas:** field kandidat Medium diubah ke 1 berdasarkan inferensi
layout Kitserver. Pemetaan field ini pada `settings.dat` retail belum diverifikasi
dengan `settings.exe` asli. Karena itu hasil ini tidak boleh disebut sebagai
benchmark Medium retail yang sudah pasti. Resolusi dan checksum terverifikasi.

## Hasil run terbaru

Input `TEST RESULT/fex-runtime.log`, 416.007 byte, SHA256
`6c8901254a777a3fd3fff6cc5346341043034efe48f28eebb7a121dd396ca34b`.
Log asli dipertahankan; analisis snapshot disertakan.

- Marker worker-cores aktif; runtime sekarang melaporkan **3 prosesor**, sedangkan
  run sebelumnya 4. Konfigurasi forwarder juga berubah, jadi peningkatan tidak
  dapat diatribusikan ke patch affinity saja.
- Tidak ada baris Wine worker `@3`. COREMAP menunjukkan worker otomatis dengan
  mask 1/2/4, fixed=0. Worker sibuk sering memakai sekitar 82–84% satu core;
  proses akhir sekitar 2,42–2,45 core.
- Pengguna melaporkan lancar sampai half time tanpa slow motion yang teramati.
  Ini kemajuan sementara, bukan bukti bahwa bug slow motion sudah selesai.
- Pada banyak window warm masih ada sekitar 19–21 gap >50 ms per 10 detik.
  Window terakhir 10,062 detik memiliki 551 Present, 19 gap 50–100 ms, tanpa
  gap >100 ms. Native Present rata-rata 633 µs, driver 424 µs. Ini waktu CPU
  pada wrapper, bukan keseluruhan waktu GPU atau FPS simulasi/frame unik.
- Window terakhir tidak membuat pipeline graphics baru dan tidak membaca cache
  driver. Banyak stutter warm tidak dapat dijelaskan hanya oleh shader baru.
- JIT akhir: 40.934 compile_code, 43,946 detik kumulatif, puncak 172,254 ms;
  98 call >20 ms, 12 >50 ms. Total antar-thread/stage bisa tumpang tindih.
  First kickoff/aksi baru masih berpotensi menunggu translasi. Tidak ada
  penanda shooting/kamera per frame untuk memastikan lokasinya.
- Resume akhir: 50.700 wait / 50.700 return, aktif 0. Tidak ada EXC/FAIL di log
  ini. Pernyataan ini tidak meniadakan lock sementara atau wait jenis lain.

## Perbaikan runtime

`PES13FexJitReport` dipanggil dari jalur kompilasi thread game setelah lock
kompilasi dilepas. Setiap lima detik, tiga baris `[FEX3-JIT] phase=...` diteruskan
ke `wine_nx_runtime_trace` → `log_line`. Whitelist buffering sebelumnya tidak
memuat baris tersebut: **setiap baris memaksa fflush SD**. Run terbaru memiliki
273 baris itu. Durasi flush tidak diukur dalam log lama, sehingga belum bisa
menetapkan berapa stutter yang berasal darinya.

NRO baru mengantrekan hanya tiga jenis statistik JIT tersebut. Antrean tetap
32 × 512 byte memakai trylock, tanpa alokasi atau penulisan file pada producer.
Thread logger yang sudah ada menguras antrean setiap tick sekitar 200 ms,
dengan mutex antrean dilepas sebelum file ditulis dan di dalam batch log.
Jika penuh/terkunci, statistik dibuang dan penghitung `dropped` bertambah.
Pesan fault/error, pesan tidak dikenal, startup tanpa logger dan control tetap
melewati jalur logging asli. Tidak ada perubahan clock, resume, affinities,
DXVK queue, shader, prioritas, atau executable game.

`[FEX3-JITLOG] queued=... written=... dropped=...` melaporkan counter kumulatif
setiap laporan sekitar 10 detik. Statistik dapat muncul sedikit lebih lambat
dalam file; `uptime_ms` tetap waktu snapshot aslinya. Statistik yang belum
dikuras dapat hilang saat HOME → X, sama seperti data yang belum di-flush.
Ini menghilangkan satu jalur I/O sinkron pada game thread, bukan precompile
semua aksi atau jaminan menghapus seluruh stutter kamera/kickoff.

## Preset grafis dan batas verifikasi

Ketiga lokasi `settings.dat` diubah bersama. Resolusi 960×540 menjadi 1280×720
(jumlah pixel naik 77,8%). Flags tetap 0x0288: VSync off, frame skipping off,
XInput aktif; word rasio 0x18 tetap 1 dan semua byte controller tetap.

Kandidat Medium mengubah **word 0x1c dari 0 ke 1**, bukan word rasio 0x18.
Dasarnya: source [lodmixer](https://github.com/pes-modding/kitserver-tools-2010-2013/blob/ca8d588105c493c5d8777e9e77341eb5ec3e65d5/kitserver13/src/lodmixer.cpp#L114)
menempatkan picture quality satu DWORD setelah widescreen;
[GUI](https://github.com/pes-modding/kitserver-tools-2010-2013/blob/ca8d588105c493c5d8777e9e77341eb5ec3e65d5/kitserver13/src/lodcfgui.cpp#L616)
mengurutkan Low/Medium/High sebagai 0/1/2. Namun
[address table](https://github.com/pes-modding/kitserver-tools-2010-2013/blob/ca8d588105c493c5d8777e9e77341eb5ec3e65d5/kitserver13/src/lodmixer_addr.h#L1)
hanya mendukung demo1 dan membahas memory layout, bukan format disk retail.
Menggunakan susunan itu untuk 0x1c file retail adalah inferensi. Label Low pada
perubahan lama juga belum terbukti. Generator produksi terverifikasi tidak
diubah menjadi generator kualitas yang seolah-olah sudah pasti.

## Pasang dan benchmark

1. HOME → X, simpan log lama. Salin folder **`switch` utama** dari ZIP ke root
   SD dan timpa instalasi terakhir. Main overlay mengganti enam file.
2. Tetap gunakan forwarder tiga core, clock stock, teams/stadium/camera dan
   cache yang sama. Tidak perlu menghapus cache.
3. Pastikan marker `pes13-fex3-camera-720`, `[FEX3-JITLOG] v1 mode=async`,
   VSync off dan swapchain 1280×720. Uji kickoff pertama dan kamera cepat;
   teruskan sampai beberapa replay/set piece. Simpan log sebelum relaunch.
4. Untuk memisahkan pengaruh grafis, gunakan salah satu **preset settings-only**
   di folder `benchmark` setelah menutup PES. Semuanya memakai NRO baru yang
   sama; salin folder `switch` dari preset yang dipilih ke root SD:

| Folder dalam benchmark | Resolusi | Word 0x1c | Tujuan |
|---|---|---|---|
| `540-original` | 960×540 | 0, asli | Pembanding runtime baru dengan grafik run lama |
| `720-original` | 1280×720 | 0, asli | Bandingkan resolusi saja dengan baris pertama |
| `720-medium-candidate` | 1280×720 | 1, kandidat | Bandingkan field kualitas saja dengan baris kedua |

Ketiga preset mempunyai checksum independen yang valid. Bandingkan run awal
dan bagian sesudah warmup secara terpisah; peningkatan jumlah shader setelah
perubahan grafis bisa menambah cold work. Perbedaan FPS rata-rata saja belum
membuktikan penyebab stutter; nilai jumlah gap >50 ms dan gejala kamera juga.
Perbandingan langsung paket utama melawan build lama mengubah grafis dan
runtime sekaligus, sehingga tidak mengisolasi pengaruh GPU.

Control logging opsional: `fex_jitlog_sync=1` dalam configuration.ini memakai
jalur sinkron lama pada NRO yang sama; default/0 memakai antrean. Ini hanya
untuk membandingkan bila diperlukan. Tidak disediakan ZIP kedua.

Rollback lengkap: HOME → X lalu salin folder **`switch` di dalam `rollback`**
ke root SD. Kembali tepat ke payload worker-cores, 540p, field grafis asli.

## Validasi

- Build ARM64 native; delta Wine hanya runtime.c, dependency PE/Mesa/SDK/FEX
  sama. NRO dicocokkan dengan ELF, payload dan manifest diverifikasi hash.
- ASan/UBSan pada fungsi hasil patch: 32.000 laporan concurrent, full/busy
  queue, lifetime string, batas panjang, error dan fallback logger.
- Jalur ARM64 asli: timing lama masuk stdio, timing baru berhenti di antrean;
  antrean busy tidak melakukan I/O; error dan control tetap langsung.
- Suspend/resume 15 skenario, binding pipeline 16, dan unwind FEX/Wine pada
  ELF ini lulus. Tes bukan benchmark Switch.
- Preset: CRC diverifikasi dengan implementasi independen, delta byte dibatasi
  ke ukuran, kandidat 0x1c, dan checksum. Ini memverifikasi format/delta, bukan
  membuktikan game retail membaca 0x1c sebagai Medium.
