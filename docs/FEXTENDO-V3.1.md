# FEXTendo v3.1 — focused glow and lighter menu rendering

Update untuk FEXTendo v3, dibuat setelah laporan pengguna bahwa perpindahan dan
animasi menu terasa berat di Switch. **Build ini belum diuji di Switch.**

## Perubahan

- Hanya tile yang fokus memiliki glow. Saat Settings dipilih, tile PES13 tidak
  berpendar dan Play redup, tanpa glow maupun animasi; tombol A membuka Settings.
- Putaran glow diperlambat dari 6 menjadi sekitar 12 detik. Gradasi dan halo tetap
  bergerak bersama. Animasi pembesaran tile dan scroll Settings tetap ada.
- Latar, blur/header/footer, logo, serta panel tetap digambar sekali ke cache.
  Ikon PES untuk 49 ukuran animasi dan mask antialiasing gear juga disiapkan sekali.
  Cahaya memakai Gaussian terpisah per sumbu dan tabel falloff; glow melewati
  bagian tengah yang tidak terlihat. Tidak ada supersampling gear atau scaling
  cover ulang setiap frame.
- Menu menargetkan 60 Hz, dengan durasi animasi berdasarkan waktu. Ini target,
  bukan klaim bahwa setiap Switch mencapai 60 FPS. Cache gambar menambah sekitar
  24,5 MiB selama launcher; semua dilepas sebelum game mengambil framebuffer.
- Popup loading berisi “Launching game”, cover PES membulat, dan spinner AA.
  Panel kaca gelap, gradasi, bayangan, highlight serta background blur diproses
  sekali. Selama loading hanya spinner kecil yang bergerak; menu di belakangnya
  tidak menjalankan animasi.
- Splash FEXTendo tampil sekitar 0,8 detik setelah aset siap. Tekan tombol untuk
  melewatinya; tombol yang melewati splash tidak sekaligus membuka game. + keluar.
- Last played, baterai, SFX, preset, serta overlay timestamp v3 dipertahankan.

Ketika launcher selesai, satu baris `[FEXTENDO] menu frames=...` merekam rata-rata
serta maksimum waktu draw + present. Tidak ada penulisan statistik per frame.
Data ini membantu mengecek hasil nyata di Switch; waktu present dapat mencakup
menunggu refresh layar. Statistik termasuk splash/loading dan bukan FPS game.

## Instalasi

Tutup game melalui HOME → X, lalu salin folder `switch/` utama dari ZIP ke root SD
(replace). File game, settings.dat, preset pilihan, debug timestamp, menu sounds,
Last played dan cache pengguna tidak ditimpa. Paket memerlukan instalasi game
FEXTendo yang sudah berjalan. NRO metadata menggunakan versi `0.3.2`; nama paket
adalah v3.1. Ikon NRO tetap cover PES2013.

Rollback: tutup game, salin `rollback/switch/` ke root SD untuk kembali persis ke
runtime dan artwork v3. ZIP v3 asli tetap dipertahankan.

## Bukti dan batas validasi

Sebelas pemeriksaan runtime terikat ke ELF yang sama. Renderer host diuji dengan
ASan/UBSan, termasuk glow hanya pada fokus, Play yang tetap statis ketika disabled,
clipping scroll, padded stride, serta loading yang hanya mengubah area spinner.
Lifecycle menguji pelepasan framebuffer/audio/cache sebelum game mengambil layar.

`evidence/ui-benchmark.json` membandingkan renderer dengan header asli dari ZIP
v3 yang hash-nya diverifikasi, dengan compiler/host sama dan tiga ulangan bergantian.
Pengukuran mencakup perpindahan tile dan scroll, bukan hanya menu diam. Waktu ini
hanya CPU host: tidak mencakup layanan display, GPU, driver, thermal atau clock
Switch. Waktu persiapan cache dilaporkan terpisah. Preview memakai renderer C asli;
angka baterai dan riwayat di preview adalah contoh.

Guest DLL, adapter FEX, dependency native dan konfigurasi game tetap sama dengan
v3/v2. Tidak ada perubahan scheduling game, clock, VSync atau memory-budget filter.
Lag kickoff dan keberhasilan tampilan timestamp tetap memerlukan bukti perangkat;
perubahan ini menargetkan menu dan popup loading.

Reproduksi: flag build sama seperti `docs/FEXTENDO-V3.md`, work directory
`local/fex3/fextendo-v3.1`. Jalankan `tests/run_fextendo_checks.py`, lalu
`tools/benchmark-fextendo-ui.py --work local/fex3/fextendo-v3.1` saat host idle.
Paket: `python3 tools/package-fextendo-v3.1.py`. Aset format 3 identik dengan v3.
