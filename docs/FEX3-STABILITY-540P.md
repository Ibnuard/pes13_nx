# PES13 FEX3 stability + 540p candidate

Build ini menggabungkan perbaikan Wine/FEX yang sudah diuji pada host dan
binary ARM64 dengan preset **960×540, 16:9**. Belum diuji di Switch; belum ada
klaim stutter, freeze, atau slow motion sudah hilang. Clock tidak diubah.

## Mengapa bukan hanya menurunkan resolusi

Stutter saat bola cepat atau menjelang shooting tidak cukup untuk menentukan
GPU sebagai akar masalah. Capture sebelumnya memuat frame gap panjang dan
perubahan laju simulasi setelah event, tetapi tidak memiliki pengukuran GPU
tersinkron dengan video. Waktu pemanggilan Present yang pendek tidak meniadakan
GPU stall karena kerja GPU berlangsung asinkron. Log dari percobaan resume-gate
terakhir juga belum tersedia untuk dibandingkan.

540p mengurangi jumlah piksel 43,75% dari 1280×720. Itu mengurangi bagian beban
render yang bergantung pada resolusi; tidak menjanjikan peningkatan FPS sebesar
43,75%. Compilation shader/JIT, wait thread dan simulasi CPU tetap dapat
menghambat. Preset hanya mengubah width, height dan checksum settings.dat;
field aspect lama, controller, VSync dan frame skipping dipertahankan.
Ukuran backbuffer aktual masih perlu dikonfirmasi pada perangkat.

## Perubahan runtime

1. **Timer Wine:** timer baru menjadi signaled saat jatuh tempo, bukan saat
   dipasang. Polling mengikuti timer yang di-arm/cancel ketika thread sedang
   menunggu. Cancel mempertahankan status sinyal yang sudah ada; perhitungan
   tenggat dan periodic catch-up menangani overflow tanpa loop panjang.
2. **Affinity dan cache shader:** kegagalan penerapan affinity dapat dicoba lagi,
   bukan tercatat sebagai sukses. Runtime menyiapkan `C:\dxvk-cache` dan
   `DXVK_SHADER_CACHE_PATH`. Log directory created/existing belum membuktikan
   DXVK sudah membaca atau menulis cache; periksa file dan bandingkan run kedua.
3. **Cache alamat JIT FEX:** reader memvalidasi generasi snapshot RX/RW/size.
   Sebelumnya reader dapat menggabungkan RX lama dengan RW/size slot yang sudah
   dipakai ulang. Reader melewati slot yang sedang diubah tanpa spin di handler
   exception. Ini memperbaiki race yang direproduksi, bukan bukti penyebab freeze
   PES pada capture pengguna.
4. **Context floating-point FEX:** simpan/pulihkan MXCSR, rotasi stack x87 sesuai
   TOP, konversi format internal F64 ↔ x87 80-bit untuk profil reduced precision,
   dan isi register legacy FloatSave. Konversi integer tidak bergantung pada
   mode floating-point host. Alokasi trampoline syscall diperiksa sebelum
   alamatnya dipakai.

Isolated resume wake, same-core Sleep(0), observer frame/pipeline dan batching
log dari percobaan sebelumnya tetap dipakai. Paket sekarang benar-benar
menggabungkan timer/cache/affinity dengan resume-gate; paket resume-gate lama
hanya mengganti jalur wake.

Perubahan timer, retry affinity, context dan cache JIT tidak bergantung pada
event PES tertentu, sehingga bisa digunakan untuk game lain. Launcher, beberapa
reservasi alamat, registry dan aturan SMC masih khusus PES. Shim ini belum
dinyatakan kompatibel universal. Daftar temuan awal ada di
[audit](FEX-REUSABILITY-AUDIT-2026-09-27.md).

## Pasang pada instalasi FEX3 yang sudah berjalan

1. Tutup game dengan HOME lalu X. Backup log dan semua file yang akan ditimpa,
   terutama NRO, **ketiga DLL**, configuration.ini, dxvk.conf dan settings.dat.
2. Salin seluruh folder `switch` dari paket ke root SD dan izinkan overwrite.
   Forwarder tetap menuju `switch/pes13-fex/pes13-fex.nro`.
3. Paket berisi NRO, libwow64fex.dll, ntdll.dll, wow64.dll yang dibangun dan
   diperiksa bersama, serta fex-stress.exe dan konfigurasi. File game, save,
   registry, DXVK DLL dan Wine dependency lain menggunakan instalasi existing.
4. Settings 540p ditempatkan di `drive_c/KONAMI/Pro Evolution Soccer 2013/`
   (lokasi yang digunakan paket FEX), salinan Documents di bawah steamuser,
   serta `drive_c/PES13/`. Yang diganti hanya settings.dat, bukan folder save.
5. Langsung jalankan PES; `run_guest_tests=0`. Simpan log dan video sebelum
   relaunch. Pertahankan clock stock untuk perbandingan ini.

Marker build: `pes13-fex3-stability-540p`. Marker module: `[FEX3-FP] context v1`
dan `[FEX3-ALIAS] generation-validated PE alias snapshots`.
Log berada di folder `switch/pes13-fex/fex-runtime.log`.

Rollback harus memulihkan seluruh file backup yang ditimpa. Menyalin ZIP
resume-gate lama saja hanya memulihkan NRO, sehingga tidak mengembalikan DLL
dan konfigurasi lama.

## Uji yang paling berguna di Switch

Ulangi tim, stadion dan kamera yang sama: kickoff, passing cepat, shooting,
goal kick lawan, corner berulang, lalu bermain setidaknya 10 menit untuk
freeze acak. Tutup dan ulangi pertandingan tanpa menghapus cache. Pisahkan
penilaian cold run dan warm run; simpan log masing-masing sebelum relaunch.
Perhatikan kecepatan jam pertandingan, animasi dan input, bukan FPS saja.

Default tetap **Fastest**, karena profil itu sudah playable sekitar 30 fps
pada perangkat pengguna. `profiles/conservative-ordering.ini` di luar folder
switch adalah opsi diagnosis: salin menjadi configuration.ini untuk mencoba
Fast dengan ordering lebih ketat, tanpa mengganti binary atau resolusi.
Profil ini pernah jauh lebih lambat pada percobaan sebelumnya, sehingga bukan
default. Stress guest existing memaksa profil Control; hasilnya tidak boleh
dipakai sebagai bukti bahwa Fastest selalu aman.

`profiles/720p/settings.dat` tersedia untuk membandingkan 540p/720p memakai
binary yang sama. Salin ke ketiga lokasi settings di atas untuk perbandingan,
kemudian pulihkan 540p dari folder switch. Jangan ganti profil FEX bersamaan.
Jika resolusi lebih rendah tidak mengubah event stall, prioritaskan jalur
CPU/JIT/synchronization pada log berikutnya. Jika membaik, itu mendukung adanya
komponen beban render tetapi belum mengisolasi GPU dari perubahan workload CPU.

## Validasi lokal

- Native dan PE cross-build selesai, hash source dan payload tercatat.
- Reproducer race JIT: interleaving deterministik, 300.000 lookup bersamaan,
  overflow/boundary, ASan/UBSan. Menghapus validasi generasi membuat tes gagal.
- Tujuh kontrak context yang sebelumnya gagal sekarang lulus, dengan tiga
  control check; 100.000 round-trip pola bit, semua TOP/profil dan kasus rounding.
  80.000 konversi dibandingkan dengan operasi x87 long double melalui Rosetta.
- Binary ARM64 PE: 2.048 round-trip register, alias cache, callback ABI,
  pemilihan profil dan heap. Native ARM64: 15 skenario resume, yield/delay,
  routing sinkronisasi, binding observer pipeline dan exception dispatch.
- Unwind diuji dengan pasangan NRO/ntdll/wow64/FEX yang dikemas, termasuk
  576 operasi index. Timer/affinity dan 1.000 siklus resume diuji pada handler
  source gabungan di host dengan ASan/UBSan.
- Packager menolak hash binary/receipt yang tidak cocok, memeriksa source,
  metadata NRO dan reproduksi executable dari ELF, checksum settings serta
  hash readback seluruh ZIP. Evidence disertakan di direktori `evidence`.

Unicorn dan host tests memodelkan batas kernel; keduanya bukan pengukuran
scheduler, GPU, FPS atau kompatibilitas guest penuh di Horizon. Perbaikan
serialization MXCSR/x87 tidak menyelesaikan seluruh persoalan pemisahan mode
rounding x87/SSE pada FPCR host. Suspend remote thread yang sedang berjalan dan
penanganan exception terminal masih memiliki batasan dari audit sebelumnya.
