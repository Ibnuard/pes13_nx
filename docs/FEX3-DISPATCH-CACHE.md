# Perbaikan cache dispatcher FEX

Kandidat ini memperbaiki dua jalur cache CPU yang ditemukan setelah tes
`jit-latency`. Build dan pengujian lokal selesai sebelum paket dibuat;
kelancaran pertandingan dan freeze kickoff pertama belum diverifikasi di Switch.

Update checkpoint setelah tes pengguna: gerakan terasa lebih ringan, permainan
sudah stabil pada mid game, stutter jarang, dan freeze kickoff pertama lebih
singkat tetapi belum hilang. Ini laporan hardware pengguna, bukan pengukuran
FPS unik atau perbandingan pertandingan yang dikontrol.

Log sesudah perubahan berukuran 283.253 byte, SHA256
`e7945dd2f0be655381781153cf3b12ca8ed688e4e9569ab835945d03910ae0a0`,
mengonfirmasi `v2 dispatcher=L1-first` dan `maxinst=500`. Pada laporan terakhir
`uptime_ms=346115` ada 1.112.345 panggilan dispatch dan 39.211 panggilan
compile_code, dengan puncak masing-masing 92.658 dan 91.590 µs. Run sebelumnya
memiliki 17.293.185 dispatch pada 280.032 ms. Durasi dan jalur permainan berbeda,
sehingga angka ini mendukung penurunan pekerjaan dispatch tetapi bukan ukuran
kenaikan FPS. Kompilasi aksi pertama tetap terjadi.

Artefak checkpoint lokal: `dist/pes13-fex3-dispatch-cache.zip`, SHA256
`672b4f5b7bee57959b11739d1a67a8f9610a024df5de3c085e94b33a3185958e`.
DLL SHA256 `03e260572fe6dce301c28289d4e4ff2ce5410568c82c63823e0085ae164fdd25`.
Binary dan log mengikuti aturan `.gitignore`; Git menyimpan source, tes,
skrip build/packaging, dan catatan identitas artefak ini.

## Temuan pada log terbaru

Input: `TEST RESULT/fex-runtime.log`, 244.115 byte, SHA256
`d7b14a68e50eb43b212ac6ca49aafe540149cd1f5693ec271829fa06819991f4`.
Snapshot asli ada di `local/fex3/kickoff-investigation/<sha256>/`.
Analisis lengkap disertakan di `evidence/input-analysis.json` dalam paket.

- Build 500 instruksi memang aktif. Pada laporan `uptime_ms=280032`, jalur
  `dispatch_compile` dipanggil 17.293.185 kali, sedangkan `compile_code`
  38.521 kali. Dispatch mencakup pencarian kode yang sudah dikompilasi;
  17 juta panggilan itu bukan 17 juta translasi baru dan bukan seluruhnya
  terbukti cache hit L1.
- Puncak `compile_code` 199.894 µs, dengan 60 panggilan di atas 50 ms.
  Durasi ini mencakup penjadwalan CPU. Kompilasi tetap bisa mengakibatkan
  jeda meskipun batas instruksi sudah diturunkan.
- Puncak `dispatch_compile` 348.825 µs. Waktu stage ini bertumpuk dengan
  kompilasi; durasi lintas thread juga bertumpuk. Jangan menjumlahkannya
  sebagai waktu satu frame.
- Invalidasi yang diukur setelah memperoleh lock tidak melebihi 20 ms.
  Ini tidak mengukur semua waktu menunggu lock invalidasi.
- Pada akhir run, masih ada gap Present di atas 50 ms dalam interval tanpa
  pembuatan pipeline atau pembacaan cache driver. Jadi biaya pipeline saja
  tidak menjelaskan seluruh stutter. Ini juga bukan bukti GPU sepenuhnya bebas.
- Tidak ada marker yang menunjuk tepat ke shooting atau kickoff. Present
  dan animasi antarmuka tetap dapat berjalan ketika simulasi pertandingan
  berhenti. Probe `ring_count=0` belum mengukur progres simulasi tersebut.

Gejala membaik setelah aksi pernah dijalankan konsisten dengan pemanasan cache,
tetapi hubungan sebab-akibat antara kickoff pertama dan semua patahan frame
belum terbukti. Paket ini menghilangkan pekerjaan cache yang dapat dihindari;
tidak mengklaim menghapus kebutuhan kompilasi aksi yang belum pernah dijalankan.

## Perubahan

Dispatcher FEX sekarang memeriksa L1 sebelum masuk ke jalur L2/C++.
Sebelumnya, saat L2 dimatikan seperti dalam log ini, masuk kembali ke dispatcher
selalu melewati spill register, `CompileBlock`, pemeriksaan/lock dan observer
JIT, bahkan jika kode sudah ada di L1. Cache hit sekarang langsung menuju kode
host. Pengecekan trap flag tetap lebih dahulu, tag alamat guest diperiksa penuh,
pointer host nol ditolak, dan miss tetap mengikuti jalur FEX yang sama.

Saat L2 mati, L1 langsung menggunakan seluruh 65.536 entri. Versi sebelumnya
mulai pada 8.192 entri lalu memperbesar dan mengosongkan cache secara berkala,
meskipun alokasi native 1 MiB sudah sepenuhnya resident. Perubahan ini tidak
menambah alokasi memori; menghindari pemeriksaan waktu dan pergantian ukuran
pada mode tersebut. Bila L2 secara eksplisit diaktifkan, pertumbuhan dinamis
tetap berlaku.

Perubahan tidak menggunakan alamat atau event khusus PES, sehingga dapat
digunakan oleh game lain. NRO, Wine, batas JIT 500/5000, preset TSO/x87,
960×540 16:9, timer dan antrean frame tetap mengikuti build yang sedang dipakai.

## Instalasi

1. Gunakan di atas build `pes13-fex3-jit-latency` yang baru dites. Tutup PES
   lewat HOME → X dan simpan log run sebelumnya.
2. Salin **folder `switch` saja** ke root SD. Satu file yang diganti:
   `switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll`.
3. Jangan hapus cache atau mengubah konfigurasi untuk perbandingan pertama.
   Pertahankan opsi `fex_jit_large` seperti pada tes terakhir (log terakhir
   memakai 500). NRO masih menulis marker build `jit-latency`; marker modul
   yang membedakan kandidat ini adalah:
   `[FEX3-LOOKUP] v2 dispatcher=L1-first L2=off native=1 MiB/thread; full resident L1`.
4. Ulangi pertandingan lima menit yang sama dari launch baru. Perhatikan
   kickoff pertama, tendangan/shooting pertama, serta pengulangan aksi itu.
   Simpan `fex-runtime.log` sebelum launch berikutnya menimpanya. Catatan
   detik rekaman saat 3D berhenti membantu memisahkan freeze simulasi dari
   jeda seluruh frame.

Rollback: tutup aplikasi, lalu salin isi `rollback/switch` ke root SD.
Folder itu mengembalikan DLL dari paket `jit-latency` yang baru dites.

## Validasi lokal

Pengujian menjalankan constructor dispatcher ARM64 dari DLL dan kemudian kode
ARM64 hasil emit-nya. Binary lama mereproduksi masuk `CompileBlock` walau L1
berisi target yang cocok; binary baru langsung menuju target. Pengujian mencakup
alamat tinggi, benturan indeks, hit/miss, invalidasi dan penggantian kode,
cache clear/refill, pointer nol, trap flag, single-step, serta preservasi register
dan NZCV. Mode L2 aktif juga diperiksa.

Pengujian alokasi memastikan kapasitas tetap 1 MiB/thread dan tidak bocor.
Observer JIT serta jalur exception/unwind diperiksa dengan DLL baru dan NRO/Wine
yang sama. NT, clock dan alokasi host dimodelkan dalam tes ini; ini bukan
pengujian pertandingan atau pengukuran performa Cortex-A57.
