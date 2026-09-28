# Kembali ke yield-burst, kurangi perpindahan thread

Pengguna melaporkan kamera lebih mulus pada checkpoint `cf4f43e`
(`pes13-fex3-yield-burst`) daripada eksperimen `yield-adaptive`. Kandidat ini
mengembalikan seluruh jalur yield ke checkpoint tersebut dan mengubah balancer
agar tidak merombak penempatan banyak thread sekaligus.

**Build eksperimen dengan diagnostik aktif, bukan perbaikan stutter yang sudah
terbukti di Switch.** Profil production, Medium 720p dan VSync off tetap sama.
Tidak ada pembatas persentase CPU maupun pengubahan clock.

## Temuan log terbaru

Input 818.123 byte, SHA256
`7faa5ceffad038ce98ff9861c4a2ca69fd4361d1c59471a20a0078a64c7601e5`.
Snapshot asli tersimpan di `local/fex3/adaptive-feedback`; analisis masuk ZIP.

- `yield-adaptive` aktif, tiga prosesor. Counter terakhir: 220.950 jeda awal,
  63.054 jeda adaptif, 423 cooldown. Total durasi jeda dari snapshot terakhir
  masing-masing thread: 15.258.368 µs, rata-rata 53,73 µs, 12 jeda ≥2 ms.
  Durasi antar-thread dapat tumpang tindih. Ini bukan penghematan CPU terukur.
  Angka rata-rata yang kecil tidak menjamin jeda terjadi pada saat yang aman
  untuk deadline game. Laporan pengguna menjadi alasan menarik kebijakan ini.
- Ada 70 laporan balancer, 348 perpindahan thread yang tercatat, termasuk 46
  pembalikan arah dalam sekitar empat detik. Angka waktu memakai EVENT terdekat
  sebelumnya, bukan timestamp pasti frame. Run ini jauh lebih panjang dan
  mencampur stock/OC; totalnya tidak boleh dibandingkan mentah dengan run lama.
- Pada EVENT sekitar 954 detik, balancer memindahkan **13 thread**, termasuk
  main dan worker berat, untuk proyeksi beban maksimum 90,2% → 85,0%. Planner
  lama menyusun ulang semua worker dari awal, sehingga perbaikan proyeksi kecil
  dapat memicu banyak perpindahan. Nilai itu hanya proyeksi thread terdaftar,
  bukan pengukuran seluruh beban fisik CPU.
- Tiga window lengkap terakhir masing-masing mempunyai 21, 25, dan 21 gap
  antarpresent >50–100 ms. Rata-rata Present native 423, 485, dan 349 µs;
  native Present yang cepat tidak meniadakan waktu di submit, wait GPU, atau
  kerja game sebelum Present. Present bukan frame 3D unik atau FPS simulasi.
- Antrean statistik JIT terkejar: 570 queued/written, nol drop. Kompilasi masih
  berlangsung: 42.294 translasi, 48,59 detik wall time kumulatif; puncak pipeline
  sejak launch 346,613 ms. Ini tidak membuktikan setiap stutter berasal dari JIT.

Pengguna menaikkan CPU, GPU dan RAM bersamaan pada babak kedua serta match
kedua. GPU 70–80% setelah OC dan stutter yang bertahan belum memisahkan CPU,
GPU, pacing atau sinkronisasi sebagai penyebab. Tidak ada timestamp OC dalam
log. Bentuk glitch nameplate belum terkonfirmasi; keterlambatan posisi, tearing
VSync-off, dan korupsi tekstur perlu dibedakan sebelum menyimpulkan data race.

## Perubahan

1. **Tarik yield-adaptive**: generated `sync.c` identik byte demi byte dengan
   checkpoint yield-burst. Tetap 64 yield cepat dalam 2 ms → satu permintaan
   jeda 50 µs. Tidak ada ambang 32, adaptive heat atau cooldown tambahan.
2. **Balancer inkremental**: mulai dari penempatan saat ini. Per pemeriksaan
   sekitar dua detik, maksimal satu worker Wine dipindahkan, bersama publikasi
   affinity koneksi servernya. Pilih perpindahan yang menurunkan puncak beban
   proyeksi pasangan core lebih dari lima poin persentase. Jika manfaat sama,
   pilih worker lebih ringan sehingga worker terberat tidak ikut bergeser.
3. Worker otomatis sibuk yang belum berada pada salah satu core yang memenuhi
   kebijakan tetap bisa dipindahkan ke core valid. Affinity eksplisit dari game
   tetap dihormati, termasuk mask multi-core. `no_balance` tetap berlaku.
4. Log balancer menambahkan `policy=single`, tick dan biaya pemeriksaan dalam
   mikrodetik. Tidak ada sampler yang mem-pause thread setiap frame.

Tujuannya mengurangi perubahan penempatan yang tidak diperlukan, bukan membuat
semua thread paralel atau menjamin core tidak penuh. Adaptasi terhadap perubahan
beban besar bisa memerlukan beberapa pemeriksaan. Planner hanya melihat thread
yang terdaftar; helper native dan beban sistem masih menjadi keterbatasan.
Ini bukan implementasi sinkronisasi baru antara kamera, pemain dan nameplate.

FEX DLL, preset TSO, Mesa, prioritas, clock, wait, resume, grafis dan cache
dipertahankan. Tidak ada alamat PES, nomor thread game, atau event khusus dalam
kebijakan; perubahan dapat dipakai oleh game lain melalui runtime yang sama.

## Instalasi dan pembanding

- Tutup PES lewat HOME → X dan simpan log. Salin **folder `switch` utama** dari
  ZIP ke root SD, timpa instalasi yield-adaptive atau yield-burst. Ini overlay
  enam file; hanya NRO berbeda dari checkpoint. Ketiga settings.dat, FEX dan
  DXVK config identik dengan preset 1280×720 16:9/Medium yang sudah diuji.
- Tes awal tiga core, tanpa OC, cache tetap, kamera/stadion sama. Tidak perlu
  mengubah INI. Marker: `pes13-fex3-stable-balance`, `[FEX3-YIELD] v1 enabled=1`,
  `[FEX3-BALANCE] v1 stable=1`. Marker `YIELD-ADAPT` sudah tidak ada.
- Nilai kamera cepat, bola di udara, kickoff dan nameplate; simpan log sebelum
  launch berikutnya. Angka GPU/CPU rata-rata saja belum cukup untuk menilai pacing.
- Pembanding dalam NRO yang sama: `fex_balance_stable=0` di `configuration.ini`
  memakai planner checkpoint. Biarkan `fex_yield_backoff=1`/default. Key lama
  `fex_yield_adaptive` tidak dipakai oleh build ini.
- **Rollback di ZIP menuju yield-burst yang lebih mulus**, bukan eksperimen
  adaptif. Tutup PES lalu salin folder `switch` di dalam `rollback` ke root SD.

## Validasi

ASan/UBSan menjalankan 20.000 kombinasi penempatan: maksimal satu perpindahan,
affinity eksplisit tidak berubah, core valid, batas manfaat dan proyeksi beban.
Tes linked ARM64 membandingkan kasus yang membuat planner lama memindahkan
tujuh worker dengan kandidat yang cukup memindahkan satu. Control harus
mereproduksi seluruh urutan perpindahan lama, kegagalan syscall tidak boleh
mempublikasikan affinity palsu, dan beban tetap harus mencapai penempatan stabil.

Tes yield, core mask, suspend/resume, pipeline, antrean log dan unwind memakai
ELF kandidat yang sama. Model timer tes core diperbaiki agar membaca instruksi
CNTPCT ke register mana pun yang dipilih compiler, bukan hanya X0.

Delta native source terhadap checkpoint hanya `thread_profile.c` dan
`runtime.c`. Dependensi PE/FEX/Mesa/SDK, settings, rollback, kecocokan NRO/ELF
dan seluruh anggota ZIP diverifikasi. Tes host tidak mengukur FPS atau fairness
kernel Switch; klaim kelancaran menunggu pengujian perangkat.
