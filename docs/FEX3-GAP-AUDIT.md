# Jeda kamera setelah kompilasi: gap audit dan opsi disk cache

Paket ini melanjutkan `pes13-fex3-stable-balance`. Pengguna melaporkan gerakan
umum kembali seperti checkpoint, tetapi bola cepat/udara dan kamera masih
tersendat, termasuk saat OC. **Ini build diagnostik dengan opsi cache, belum
perbaikan stutter yang terbukti.** Scheduler dan aturan yield tetap sama.

## Bukti run terakhir

Log 2.304.115 byte, SHA256
`3960ed25b0ba14ee345ad019613086d529dae17554d61c19704733f6715edc7f`.
Snapshot dan analisis: `local/fex3/stable-feedback/<hash>/`.

- Marker `stable-balance`, tiga prosesor, VSync off; kebijakan maksimal satu
  worker bekerja: 145 laporan, 145 perpindahan yang tercatat.
- Akhir run sekitar 49 menit: 47.327 kompilasi selesai, 42,14 detik wall time
  kumulatif, puncak 67,021 ms. Antrean statistik JIT 1.755 queued/written tanpa
  drop. Kompilasi awal tetap relevan, tetapi bukan penjelasan tunggal yang kuat
  untuk jeda sepanjang pertandingan.
- Ditemukan **64 window Present dengan gap >50 ms** yang diapit laporan JIT
  dengan counter kompilasi dan total waktu yang tetap. Contoh window PACE
  2.553.023 ms: 21 gap dalam 10.045 ms, counter 46.514 tetap pada laporan JIT
  uptime 2.541.620–2.566.631 ms. Bracket diperlebar satu laporan pada tiap sisi.
  Jam laporan berbeda dan JIT ditulis lewat antrean; ini bukan sinkronisasi
  timestamp hardware. Counter hanya menghitung kompilasi yang sudah selesai.
- Dua window lengkap terakhir: 21 dan 22 gap >50 ms, rata-rata Present native
  291 dan 310 µs. Present bukan frame simulasi/3D unik. Wait Vulkan mencakup
  penjadwalan dan waktu menunggu, bukan timestamp eksekusi GPU.
- Worker `432w@2` pada akhir run memakai 75,5% satu core dalam interval laporan,
  koneksi servernya 3,5%. THREADS tidak mencakup seluruh helper native/sistem;
  jangan menjumlahkannya sebagai pengukuran lengkap core urutan ketiga.

## MULTIBLOCK dan disk cache

`MULTIBLOCK` **sudah 1**, dipasang oleh `src/fex/module_profile.cpp` sebelum
context FEX dibuat, dengan batas 500 instruksi pada profil saat ini. Mengulang
key itu tidak menambah optimasi. Upstream juga menyebut multiblock dapat
memperpanjang kompilasi; bukan tombol yang selalu menghilangkan stutter.

Nama upstream adalah **`FEX_DISKCACHE=1`** pada environment atau `DiskCache`
pada config JSON, bukan `JIT_DISKCACHE`. `configuration.ini` proyek bukan
config FEX mentah. Build ini menyambungkan boolean **`fex_diskcache=1`** ke
environment FEX yang benar. Default **0**, karena stutter yang sedang dikejar
tetap terlihat saat counter kompilasi tidak bertambah.

Referensi upstream:
- [Konfigurasi FEX](https://github.com/FEX-Emu/FEX/blob/main/FEXCore/Source/Interface/Config/Config.json.in)
- [Catatan rilis disk cache](https://github.com/FEX-Emu/FEX/releases)

Mode eksperimen memakai implementasi disk cache yang sudah ada dalam FEX DLL:

- Parent cache `C:\fex-jit-cache\` melalui `FEX_APP_CACHE_LOCATION`. FEX tetap
  membuat subfolder berdasarkan hash konfigurasi/fitur CPU; tidak memakai
  `DiskCachePath` yang melewati pembagian otomatis itu.
- File mapping mati, anonymous-code caching mati, memory LRU mati. Batas file
  data utama 64 MiB per database; index dan banyak bucket bukan bagian batas
  tersebut. Tujuannya membatasi eksperimen dan memakai jalur salin kode ke
  writable alias yang sudah ada, bukan memetakan file SD sebagai kode.
- Cache ini berbeda dari cache shader DXVK. Launch pertama bisa menambah kerja
  penyimpanan. Di adapter kita, disk cache aktif juga melewati optimasi entry
  guard untuk text statis (`!WantsDiskCachePatching` di Core.cpp), sehingga
  throughput steady-state bisa turun. Keberhasilan perlu dibandingkan.
- Marker `requested=1` **hanya membuktikan permintaan**, bukan cache hit atau
  persistensi. Jalur ini belum diuji baca/tulis/launch ulang pada Switch. Tes
  host memverifikasi environment yang dikirim, bukan berfungsinya database.

## Apa yang dicatat build ini

`[FEX3-GAP]` mencatat maksimal 32 interval terlambat per periode laporan sekitar
10 detik. Catatan diproduksi tanpa alokasi, I/O file atau mem-pause thread;
buffer penuh/kunci sibuk dihitung sebagai drop. Logger melakukan penulisan.

Satu pembacaan CPU tick kernel ditambahkan setelah setiap Present sukses:

- `end_gap_us`: waktu antara dua akhir Present pada thread/queue/swapchain sama.
- `thread_cpu_us`: waktu CPU thread penyaji pada interval itu; baca hanya jika
  `cpu_valid=1`. Selisih wall–CPU mencakup blocking, scheduler dan kerja di
  thread lain; bukan otomatis waktu GPU atau bukti deadlock.
- `acquire_us`, `submit_us`, `fence_us`, `semaphore_us`: waktu panggilan Vulkan
  yang tercatat **pada thread penyaji itu saja** sejak Present sebelumnya.
  Panggilan pada thread lain tidak masuk. Nilai ini wall time dan dapat overlap
  dengan waktu CPU; jangan menjumlahkan semuanya sebagai komponen terpisah.
- `tick` memakai counter fisik yang sama dengan log BALANCE; `handle` adalah
  handle thread native, bukan Wine tid atau nomor core.

Riwayat terpisah per-thread. Ganti swapchain/queue, error Present atau counter
gagal tidak boleh menghasilkan delta CPU palsu. Statistik PACE/PIPE lama tetap
tersedia. Pengamatan mempunyai overhead; **`fex_gap_probe=0`** menonaktifkan
query tambahan dan catatan ini untuk pembanding dalam NRO yang sama.

## Cara tes

1. Tutup PES, simpan log, salin **folder `switch` utama** ke root SD. Tetap
   Medium 1280×720 16:9, VSync off, tiga core, tanpa OC untuk perbandingan awal.
   Tidak perlu mengubah INI: disk cache mati, gap probe aktif.
2. Reproduksi kamera/bola cepat beberapa menit, lalu simpan log. Marker baru
   `pes13-fex3-gap-audit`, `[FEX3-GAP] v1 enabled=1`, `DISKCACHE requested=0`.
   Ini run utama untuk menentukan arah perbaikan CPU/wait berikutnya.
3. Untuk percobaan disk cache terpisah **dalam paket yang sama**, ubah/tambah
   `fex_diskcache=1` di `switch/pes13-fex/configuration.ini`. Mainkan adegan sama,
   tutup penuh lewat HOME → X, buka lagi, dan bandingkan launch kedua. Simpan
   kedua log serta folder `drive_c/fex-jit-cache` jika terbentuk. Jangan hapus
   cache DXVK atau mengubah OC/grafis selama perbandingan ini.
4. `fex_diskcache=0` kembali ke tanpa disk cache, tanpa menghapus file cache.
   `fex_jit_large` tetap mempertahankan pilihan 500/5000 yang sudah ada.
5. Rollback: tutup PES, salin **`rollback/switch`** ke root SD untuk kembali
   tepat ke stable-balance. Seluruh perubahan runtime ada di NRO; lima payload
   pendamping, termasuk ketiga settings.dat dan FEX DLL, identik.

## Validasi

Tes sanitizer mencakup delta CPU/wall, delapan thread/TLS, batas antrean,
contention, counter gagal, reset stream dan disable. Tes linked ARM64 menjalankan
jalur Present-note sesungguhnya dengan kernel dimodelkan: interval 100 ms dan
CPU 10 ms harus terlapor benar, tanpa log dari produser. Empat environment
500/5000 × cache off/on diperiksa urutan, NUL, nilai dan keberadaannya dalam ELF.

Regresi balancer, yield, core mask, resume, pipeline, JIT logger dan unwind
dijalankan pada ELF yang sama. NRO/ELF, dependency, setting, rollback dan isi
ZIP diverifikasi. Tidak ada klaim FPS, cache hit atau stutter solved dari tes host.
