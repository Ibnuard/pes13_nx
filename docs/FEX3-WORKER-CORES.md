# Automatic worker placement: core 0–2

Satu overlay gabungan untuk instalasi PES13 FEX terakhir: Wine NRO baru,
FEX emitter yang sudah dites, DXVK VSync off dan ketiga settings 960×540 16:9.
Build dan pengujian lokal lulus; hasil kickoff, stutter dan slow motion pada
Switch masih harus diuji. Perbaikan sleep sebelumnya **belum menyelesaikan
gejala menurut hasil tes pengguna**; paket ini menguji penyebab yang berbeda.

## Temuan dari run terakhir

`TEST RESULT/fex-runtime.log`, 287.337 byte, SHA256
`c70e5f21777ed3b96367df8e22f2d9451f56d52d157861cc8b51a8a9ba166782`.
Marker `pes13-fex3-sleep-deadline`, `[FEX3-EMIT] v1`, settings `vsync=0` dan
DXVK IMMEDIATE memastikan run memakai eksperimen sebelumnya. Log aslinya
dipertahankan. Snapshot analisis mempunyai hash input yang sama.

Empat worker berurutan dibuat dengan entry `0x4da0e3` dan parameter
`0x1238c410` yang sama. Ini menguatkan dugaan peran yang sama, tetapi entry
wrapper belum membuktikan fungsi gameplay di dalamnya.

| Worker pada run ini | Core yang dilaporkan | Pemakaian CPU pada window stabil |
|---|---|---|
| 164 | 2 | sekitar 74–78% satu core |
| 176 | 1 | 72,9–73,1% |
| 188 | 1 | 74,0–74,6% |
| 200, sesudah transisi terakhir | 3 | 43,7% pada dua window akhir |

Di bagian akhir, proses turun dari sekitar 2,2–2,3 core aktif ke 1,79–1,81
core. Runtime melaporkan empat prosesor. Pengguna menjelaskan bahwa forwarder
default memakai tiga core, sedangkan opsi core keempat shared. Informasi ini
sesuai dengan hipotesis worker mendapat jatah CPU lebih sedikit di core 3;
log belum mengukur pemakaian core oleh sistem atau membuktikan sebab-akibat.
Baris THREADS lama juga hanya menampilkan preferred core, bukan full mask.

Kode lama memilih semua core yang diizinkan secara round-robin saat worker
mulai. Balancer menilai waktu CPU milik thread aplikasi; worker yang mendapat
jatah kecil bisa terlihat sebagai beban kecil. Pemindahan juga bisa dibatalkan
ketika maksimum beban tetap ditentukan main thread di core lain. Ini memberi
penjelasan yang bisa diuji untuk slow motion sesudah pergantian worker/event.

Temuan lain membatasi diagnosis:

- Self-suspend yang tersampel umumnya 92–733 µs, satu sampel 18,717 ms. Di
  akhir, resume wait/return 31.990/31.990, aktif 0. Ini tidak mendukung dugaan
  self-suspend tertentu tertahan sepanjang slow motion, tetapi tidak meniadakan
  jenis wait lain atau lock sementara.
- Window akhir sekitar 10,047 detik masih mempunyai 511 Present, dengan 13
  gap 50–100 ms dan tanpa gap >100 ms. Present bukan frame 3D unik atau FPS
  simulasi; angka tinggi masih dapat berdampingan dengan slow motion.
- Shader graphics baru pada window terakhir nol. Waktu CPU rata-rata native
  Present 376 µs / driver 280 µs tidak mengukur seluruh pekerjaan GPU.
- Translasi JIT tetap terjadi: 39.029 kompilasi, 43,23 detik kumulatif lintas
  thread, puncak 80,142 ms. Aksi baru masih berpotensi mengalami cold work.
  Core placement tidak diklaim menghilangkan seluruh stutter kompilasi.
- Sleep thread 52 masih terlambat: permintaan 4,110 detik, aktual 9,342 detik
  dalam window akhir. Menghapus yield sebelum sleep tidak cukup bila worker
  belum mendapat giliran CPU setelah siap jalan.

## Perubahan

1. Worker Wine dengan affinity otomatis memakai core yang tersedia dari 0–2.
   Forwarder dengan tiga core tetap memakai ketiganya; grant empat core tidak
   memasukkan core 3 ke rotasi otomatis.
2. Balancer memakai himpunan core yang sama, sehingga tidak mengembalikan
   worker otomatis ke core 3. Worker otomatis yang masih berada di luar
   himpunan tersebut dapat dipindahkan melalui jalur urgent yang sudah ada.
3. Affinity eksplisit dari game, processor count dan system affinity mask
   tetap mengikuti kontrak sebelumnya. Jika tidak ada core 0–2 yang diizinkan,
   runtime memakai grant yang tersedia. Ini bukan patch alamat/thread ID PES.
4. Server connection mengikuti mask client hanya setelah syscall pemindahan
   sukses. Jalur error tidak mempublikasikan perpindahan yang gagal.
5. Satu baris `[FEX3-COREMAP]` pada laporan berkala mencatat mask aktual dan
   `fixed` untuk maksimal 12 thread teratas. `fixed=1` berarti affinity game
   eksplisit; mask 0 berarti query tidak tersedia. Query memakai panggilan
   yang sudah ada dan penulisan log dilakukan setelah mutex dilepas.

FEX DLL, DXVK, ntdll/wow64 PE, Mesa/SDK, clock game dan profil grafis sama
dengan paket terakhir. Batas otomatis berlaku pada jalur worker Wine; ini
tidak memaksa semua thread native sistem/driver ke tiga core. Konsekuensi yang
perlu dinilai pada perangkat: pekerjaan otomatis berbagi tiga core, sehingga
perubahan ini dapat mengurangi throughput bila core keempat sebenarnya banyak
tersedia. Tidak ada jaminan FPS atau klaim bahwa kickoff sudah selesai.

## Validasi lokal

- Native ARM64 build lulus. NRO dicocokkan ke ELF dengan `elf2nro`; receipt
  memeriksa PE dependency, SDK, Mesa, source dan payload berdasarkan SHA256.
  Delta source native hanya `horizon.c`, `thread_profile.c`, `runtime.c`.
- Binary lama benar-benar memilih core 3 setiap startup otomatis keempat;
  binary baru memilih 0–2 pada model grant empat core. Grant tiga/sparse core,
  fallback core-3-only, dan mode control diuji pada instruksi ARM64 rilis.
- Balancer lama membiarkan worker core 3 pada skenario main thread tetap
  65%; binary baru memindahkannya. Ini model tick count, **bukan pengukuran
  peningkatan CPU/FPS Switch**.
- Affinity eksplisit single/multicore, processor count, no-balance, syscall
  failure, serta publikasi mask server melalui jalur ARM64 asli lulus.
- ASan/UBSan pada source laporan: 128 worker, batas 12 entri, sentinel query
  gagal, dan log di luar mutex lulus. Suspend/resume ARM64, binding observer
  pipeline, serta unwind FEX/Wine juga lulus pada ELF paket ini.

## Pasang dan uji

1. Tutup PES dengan HOME → X, simpan log sebelumnya.
2. Ekstrak `pes13-fex3-worker-cores.zip`, salin folder **`switch`** ke root SD
   dan timpa instalasi terakhir. Paket mengganti enam file, bukan game lengkap.
3. Untuk tes pertama, pertahankan pengaturan forwarder yang dipakai run
   terakhir, cache, clock stock dan match yang sama. Patch runtime sudah
   memilih core otomatis; tidak perlu membuat forwarder baru.
4. Verifikasi `[BUILD] pes13-fex3-worker-cores` dan `[FEX3-CORES] v1 ... prefer
   0-2`. Marker sleep/emitter, `vsync=0` dan DXVK IMMEDIATE tetap ada.
5. Uji kickoff pertama, shot/bola turun/kamera cepat, lalu replay dan goal kick
   atau offside. Jika slow motion muncul, biarkan sekitar 30 detik, lalu picu
   event lain dan lanjutkan sekitar 30 detik. Simpan log sebelum membuka PES
   kembali agar bagian lambat dan pulih dapat dibandingkan.

Control opsional pada NRO yang sama: `fex_auto_core3=1` di
`sdmc:/switch/pes13-fex/configuration.ini` mengembalikan rotasi semua core yang
diizinkan. Default adalah 0; nilai 0 mengembalikan kebijakan baru. Ini untuk
membandingkan hasil bila diperlukan, bukan paket kedua yang harus dipasang.

Rollback: tutup PES dan salin **folder `switch` di dalam `rollback`** ke root
SD. Ini kembali tepat ke payload sleep-deadline terakhir, termasuk emitter,
VSync off dan 540p. Source, receipt tes dan analisis disertakan dalam ZIP.
