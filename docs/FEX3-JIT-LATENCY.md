# Kandidat untuk stutter saat aksi pertama

Status: build dan pemeriksaan lokal selesai; hasil gameplay Switch belum diuji.
Paket ini menguji ukuran pekerjaan kompilasi FEX. Freeze kickoff dan slow motion
belum dinyatakan terpecahkan.

## Bukti dari run warm-audit

Input `TEST RESULT/fex-runtime.log`: 279.978 byte, SHA256
`636f1690d0306b3a56ef15c5a75da45539c80f818cd6b2529f66fc96808c4b56`.
Snapshot asli disimpan di `local/fex3/event-stall/<sha256>/`. Data laporan
yang diselaraskan berdasarkan urutan baris ada di
`local/fex3/jit-latency/input-analysis.json`.

- Marker mengonfirmasi `pes13-fex3-warm-audit`, sehingga pengukuran pipeline
  dan cache baru memang aktif dalam run ini.
- Tercatat 1.825 lookup cache driver, semuanya hit. Ini mencakup lookup dalam
  run yang sama; tidak membuktikan semua data berasal dari launch sebelumnya.
- Satu lookup memakan 313.103 µs; puncak pembuatan graphics pipeline
  314.467 µs muncul pada interval laporan yang sama. Kedua pengukuran bertumpuk:
  jangan dijumlahkan, dan jangan dianggap pengukuran GPU.
- Ada 959 panggilan pembuatan graphics pipeline. Setelah laporan pacing
  `elapsed_ms=120549`, banyak interval tidak lagi membuat pipeline, tetapi
  tetap memiliki gap Present. Contoh interval `310932`: nol pipeline baru,
  36 gap >50 sampai 100 ms dan dua gap >100 ms.
- Log tidak mempunyai marker tepat untuk belok, shooting, atau masuk area
  lawan. Jadi satu stall tertentu belum bisa dipetakan ke satu penyebab.
- Laporan pengguna bahwa animasi lain tetap berjalan sementara pemain/bola
  dan waktu pertandingan berhenti menunjukkan jalur simulasi perlu ditelusuri.
  Present yang terus berjalan membuat detektor lama "3 detik tanpa Present"
  tidak terpicu. `ring_count=0` juga berarti probe ring lama belum mengukur
  progres simulasi. Kelancaran penonton/banner sendiri tidak menetapkan jenis
  pipeline grafis yang dipakai masing-masing.

Kesimpulan: membaca cache dapat ikut menyebabkan jeda, tetapi tidak menjelaskan
seluruh stutter. Hipotesis berikutnya adalah pekerjaan translasi atau menunggu
kompilasi FEX ketika jalur aksi baru dijalankan. Run ini belum mempunyai durasi
kompilasi FEX, sehingga hipotesis tersebut belum terbukti.

## Perubahan kandidat

Launcher memasukkan `FEX_MAXINST=500` ke environment guest. Modul FEX sekarang
menerima nilai 500 itu sebelum membuat context, menggantikan override proyek
yang sebelumnya selalu 5.000. Untuk nilai lain dan profil guest-test/control,
batas tetap 5.000. `fex_jit_large=1` pada configuration.ini memilih environment
5.000 sebagai pembanding dengan binary dan observer yang sama.

Ini membatasi jumlah instruksi dalam satu pekerjaan kompilasi, bukan membatasi
berapa instruksi game boleh dijalankan atau mengubah clock. Multiblock tetap
aktif. Source pinned FEX sendiri menyebut multiblock dapat menyebabkan waktu
kompilasi panjang/stutter, tetapi memilih angka 500 di Switch tetap eksperimen.
Blok lebih kecil dapat mengurangi satu lonjakan kompilasi, sekaligus menambah
jumlah kompilasi dan overhead dispatch; total performa bisa membaik atau turun.

Referensi source FEX yang digunakan:
[Config.json.in pada pin proyek](https://github.com/FEX-Emu/FEX/blob/e2f973fe931e6dc2ce523795e51ca1ac3ca85816/FEXCore/Source/Interface/Config/Config.json.in).

Observer `[FEX3-JIT]` mencatat durasi CPU untuk:

- `dispatch_compile`: masuk jalur kompilasi/cache lookup, termasuk penantian
  lock yang berada di dalam fungsi;
- `compile_code`: frontend dan backend kompilasi;
- `invalidate`: invalidasi cache setelah memperoleh lock.

Counter kumulatif mencakup jumlah panggilan, total waktu, puncak, serta jumlah
di atas 20/50 ms. Stage dan thread dapat bertumpuk; jangan menjumlahkannya
menjadi waktu frame. Panggilan yang belum selesai belum masuk counter.
Laporan paling sering setiap lima detik, dipicu setelah CompileBlock selesai
dan lock lokalnya dilepas. Tidak adanya laporan baru bisa berarti tidak ada
CompileBlock yang selesai. `uptime_ms` dimulai saat modul diinisialisasi;
berbeda dari origin timer laporan Present.

Counter memakai atomics dan counter fisik yang sudah dipakai port ini.
Tidak ada alokasi di helper observer. Tiga baris laporan dibuffer oleh logger;
tidak memaksa flush per baris. Buffer stdio penuh tetap dapat melakukan I/O.
Observer menambah sedikit pekerjaan pada jalur kompilasi, bukan pada setiap
instruksi guest atau frame. Perubahan ini tidak bergantung pada alamat PES dan
bisa digunakan dalam diagnosis game lain.

## Instalasi dan perbandingan

1. Tutup aplikasi lewat HOME → X. Simpan log lama dan backup kedua file tujuan.
2. Salin **folder `switch` saja** dari ZIP ke root SD. Paket mengganti NRO dan
   `drive_c/windows/system32/libwow64fex.dll`; keduanya harus dipasang bersama.
3. Pertahankan konfigurasi saat ini: 960×540, 16:9, antrean dua frame, stock
   clock. Paket tidak mengganti configuration.ini, dxvk.conf, cache atau save.
4. Default kandidat adalah 500. Bila ada baris `fex_jit_large`, pastikan hanya
   satu baris dan bernilai `0`. Periksa log startup:
   `pes13-fex3-jit-latency`, `[FEX3-JIT-LAUNCH] maxinst=500`, dan
   `[FEX3-JIT-CONFIG] maxinst=500`.
5. Tes pertandingan lima menit yang sama. Catat freeze kickoff, shooting
   pertama, belok mendadak, masuk area lawan, dan kelancaran setelah fase awal.
   Simpan log sebelum membuka aplikasi lagi.
6. Untuk pembanding, ubah/tambahkan satu baris `fex_jit_large=1` di
   `switch/pes13-fex/configuration.ini`, tutup penuh lalu ulangi pertandingan
   yang sama. Kedua marker harus menunjukkan 5.000. Jangan hapus cache atau
   mengubah clock di antara percobaan. Hapus baris itu atau set `0` untuk kembali.

Jika kandidat menurunkan kelancaran setelah warmup, gunakan opsi 5.000.
Rollback penuh tersedia di folder `rollback/switch`: kembalikan kedua file
dari sana atau backup sendiri. Folder rollback tidak dipasang bersama folder
switch utama. Hapus opsi tambahan bila ingin konfigurasi persis seperti semula.

## Validasi lokal

Build native dan ARM64 PE selesai. ASan/UBSan menguji 24 kombinasi profil/nilai,
16.000 sampel bersamaan, batas 20/50 ms, gate laporan, preservasi environment,
dan whitelist flush. Pengujian instruksi ARM64 memeriksa caller kompilasi yang
sebenarnya, penghitung, gate lima detik dan preservasi x18 saat callback log.
Observer cache driver dan jalur exception/unwind juga diperiksa pada binary
yang dikemas. Ini bukan eksekusi pertandingan PES di Switch.

NRO berubah hanya pada runtime launcher/logger dibanding warm-audit. PE
ntdll/wow64, Mesa, preset TSO/x87, timer game dan grafis tetap sama. Paket
menyertakan receipt hash agar binary dan sumber pengujian dapat dicocokkan.
