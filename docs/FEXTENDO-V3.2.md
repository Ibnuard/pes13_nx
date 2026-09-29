# FEXTendo v3.2 — glass, identity and original audio

Update untuk instalasi FEXTendo yang sudah berjalan. NRO: **PES13 - FEXTendo**,
author **AndroSwitch Project**, versi aplikasi **0.3.3**. Build ini telah
melewati pemeriksaan host/binary; belum diuji pada Switch.

## Perubahan

- Splash 2,4 detik: logo muncul sambil bergerak halus, sapuan cahaya tipis,
  subtitle bertahap dan fade keluar. Tombol untuk melewati splash tidak ikut
  meluncurkan game.
- Popup launch memakai kaca transparan dan blur latar, dengan bayangan kontak
  tipis. Struktur tetap judul, cover rounded dan spinner.
- Carousel PES13, Settings, Credits menampilkan dua tile utuh dan kira-kira
  setengah tile berikutnya yang memudar. Saat Credits dipilih, tile PES13
  terpotong dan memudar di sisi kiri. Glow hanya pada fokus; Play hanya aktif
  saat PES13 dipilih. Putaran cahaya tetap 12 detik.
- Settings dan Credits memakai artwork flat minimalis yang dibuat untuk
  proyek ini. Credits memuat AndroSwitch Project, Ibnuard, versi, changelog dan
  atribusi proyek upstream, termasuk FEX-Emu dan Autorun.
- Empat SFX mallet/click baru dan BGM ambient orisinal 16 detik. Tidak menggunakan
  musik atau sampel Autorun maupun MP3 yang diberikan. Switch `Menu sounds` dan
  `Background music` terpisah, tersimpan di SD, default ON. Musik hanya berjalan
  di launcher, dilepas sebelum game mulai.
- Perbaikan setup timestamp untuk kegagalan membuka display `0x1272`: pinjam
  display Default milik libnx, buat layer overlay dengan resource ID aplikasi.
  Log membedakan setup display/layer dan frame overlay pertama. Visibilitas
  di perangkat masih harus diuji.
- Empat log sesi sebelumnya disimpan otomatis agar sesi permainan tidak segera
  tertimpa ketika launcher dibuka lagi.

## Instalasi dan rollback

Tutup game melalui HOME → X. Salin folder utama `switch/` dari ZIP ke root SD
(replace). Update ini memerlukan instalasi FEXTendo/PES13 PC v1.0 yang sudah
berjalan, dengan game di `sdmc:/switch/pes13-fex/drive_c/PES13/`.

File game, save, `settings.dat`, cache, preset pilihan, timestamp, SFX dan Last
played tidak ditimpa. Preferensi musik baru disimpan di
`sdmc:/switch/pes13-fex/launcher/background-music.txt` (1/0); paket tidak
menimpa file itu. Settings dapat di-scroll sampai baris 7 untuk BGM.

Update NRO dan seluruh artwork bersama: ini memakai **aset format 4**. Jangan
hanya menyalin NRO karena dua tile dan PCM musik adalah file baru.

Rollback: tutup game dan salin `rollback/switch/` ke root SD. Ini mengembalikan
runtime/config/artwork v3.1 yang tercatat dalam manifest. File baru milik v3.2
boleh tetap berada di SD; v3.1 mengabaikannya. ZIP v3.1 asli tetap dipertahankan.

## Log permainan dan stutter awal

Log aktif: `sdmc:/switch/pes13-fex/fex-runtime.log`.
Riwayat: `fex-runtime.previous-1.log` (paling baru) sampai `previous-4.log` di
folder yang sama. Rotasi dilakukan saat launcher mulai; jika rotasi gagal,
logger berusaha append tanpa memotong log aktif dan merekam kesalahannya.

Capture terbaru menunjukkan pekerjaan awal FEX/pipeline/SD, sekaligus timeout
critical section heap Wine di sekitar gap 5,23 detik. Detail dan batas
kesimpulan ada di [review log](FEXTENDO-LOG-REVIEW-2026-09-29.md), juga disertakan
dalam `source/docs/` paket. **v3.2 belum merupakan perbaikan stutter gameplay.**
Guest DLL, adapter FEX, dependency native, affinity, JIT dan konfigurasi game
sama dengan v3.1. Perubahan native berada pada launcher/log/overlay di
`runtime.c` dan linker wrapper di CMake.

Saat Debug timestamp ON, stopwatch T+ seharusnya tampil di kanan atas selama
bermain. Jika belum terlihat, log baru menunjukkan tahap terakhir yang sukses;
`first overlay frame submitted` membuktikan buffer dikirim, bukan bahwa hasil
sudah terlihat di panel Switch. OFF tidak membuat worker/layer overlay.

## Validasi dan biaya menu

Sebelas pemeriksaan mencakup launcher/UI/lifecycle/audio/log/overlay serta
regresi runtime pada ELF final yang sama. ASan/UBSan memeriksa padded stride,
clipping, navigasi Credits, skip splash, pemisahan mute, PCM loop/fade, worker
join dan jalur kegagalan. Disassembly memastikan init window libnx memanggil
wrapper display yang ditautkan.

Preview memakai renderer C asli, bukan mockup. Baterai dan Last played di
preview adalah contoh. MP4 memperdengarkan BGM orisinal; tidak mensimulasikan
SFX controller maupun timing audio perangkat.

`evidence/ui-benchmark.json` membandingkan empat skenario umum dengan header
asli dari ZIP v3.1 terverifikasi. Angka host berada sekitar biaya render yang
sama, dengan variasi antar-run; ini bukan klaim kenaikan FPS Switch. Pengukuran
hanya CPU renderer, tidak termasuk audio/display/GPU. Bayangan tile yang tidak
perlu dihapus, clipping dihitung di luar loop piksel, dan dimming digabung dengan
penyalinan tile agar tidak ada pass rounded tambahan setiap frame.

Cache enam scene dan tiga set ukuran tile memakai sekitar 52,4 MiB dibanding
24,5 MiB di v3.1, di luar aset sumber; PCM BGM sekitar 1,46 MiB. Semuanya khusus
launcher dan dilepas sebelum handoff game. Persiapan cache lebih lama dan dicatat
terpisah dalam benchmark. Target menu tetap 60 Hz, bukan jaminan 60 FPS.

## Reproduksi dan atribusi

Flag runtime sama dengan v3.1, work directory `local/fex3/fextendo-v3.2`.
Bangun artwork dengan `tools/build-fextendo-assets.py`, runtime dengan
`tools/build-fex-runtime.py`, jalankan `tests/run_fextendo_checks.py`, lalu
`tools/benchmark-fextendo-v3.2.py --work local/fex3/fextendo-v3.2` saat host idle.
Preview: `tools/render-fextendo-preview.py RUNTIME_ROOT OUTPUT.mp4`.
Paket: `python3 tools/package-fextendo-v3.2.py`.

Provenance artwork/audio: `source/assets/fextendo-v3.2/GENERATION.md` dalam paket
atau [dokumen aset](../assets/fextendo-v3.2/GENERATION.md) di repository.
FEX-Emu adalah engine upstream; port dan integrasi Switch dikembangkan proyek
ini. Runtime Wine-NX/Autorun dan backport yang dipakai tetap dikreditkan secara
terpisah di `THIRD_PARTY.md`. Tidak ada file executable/data game dalam update.
