# Fextendo — PES13 launcher + VSync ON

Paket ini melanjutkan `pes13-fex3-gap-audit`, dengan menu console sebelum Wine
menjalankan PES13. Ini update untuk instalasi PES13 yang sudah berjalan; file
game dan Wine lengkap tetap memakai instalasi pengguna. Belum diuji pada Switch.

## Tampilan dan kontrol

- Wallpaper `assets/PES13WP.jpg`, logo `assets/logo.png`, dan **kedua tile** memakai
  `assets/icon.png` sesuai permintaan. Font Barlow Regular/SemiBold, berlisensi
  OFL, untuk nuansa antarmuka console/Steam. Branding kanan atas: **Fextendo by
  AndroSwitch Project**.
- D-pad atau stik kiri untuk memilih; **A** membuka PES13 atau Settings.
  Pada Settings: atas/bawah memilih preset, A menyimpan, B kembali. **+** keluar
  dari halaman utama. Tombol A harus dilepas sebelum guest mulai, agar tidak
  terbawa sebagai input pertama PES.
- PES13 menampilkan loading dengan animasi dan tahap startup, tanpa persentase
  buatan. Teks debug tetap masuk `fex-runtime.log`.
- Jendela GDI sementara tidak ditampilkan saat loading. Sebelum Wine meminta
  surface Vulkan/OpenGL, thread UI berhenti, menutup framebuffer pada thread
  pemiliknya, dibersihkan melalui join, dan membebaskan artwork/font. Launcher
  tidak terus menggambar saat pertandingan berjalan.
- File game hilang, preset gagal disimpan, kegagalan bootstrap yang kembali ke
  runtime, serta timeout sebelum surface 3D (180 detik) menampilkan popup.
  Error sebelum guest mulai dapat kembali ke menu. Setelah bootstrap dimulai,
  tutup lalu buka ulang; Wine tidak diinisialisasi ulang dalam proses yang sama.
  Exit sebelum frame pertama memakai popup sistem. Crash kernel/fatal exception
  yang mematikan proses tidak dijamin bisa menampilkan popup.

## Preset dan VSync

| Preset | Resolusi | Word kualitas |
|---|---|---|
| Medium 720p (default) | 1280 × 720 | 1 |
| Low 720p | 1280 × 720 | 0 |
| Extra Low 540p | 960 × 540 | 0 |
| High 720p | 1280 × 720 | 2 |

Semua menggunakan 16:9. Extra Low adalah Low dengan resolusi lebih rendah.
Pemetaan kualitas `0x1c` masih berdasarkan inferensi layout Kitserver dan preset
Medium yang sebelumnya dicoba pengguna. Belum ada pembuktian dari Settings.exe
retail; khususnya efek High perlu dibandingkan di perangkat. Resolusi, word
aspect, flag VSync, controller dan checksum diperiksa oleh tes.

**Lokasi utama** adalah `C:\KONAMI\Pro Evolution Soccer 2013\settings.dat`,
atau `switch/pes13-fex/drive_c/KONAMI/Pro Evolution Soccer 2013/settings.dat`
di SD. Pilihan preset mengubah display pada salinan file utama, mempertahankan
data kontrol/field lain, lalu menyamakan dua lokasi kompatibilitas di `PES13`
dan Documents. Jangan memindahkan game exe: tetap `C:\PES13\pes2013.exe`.

VSync aktif di flag `settings.dat` (preset bawaan `0x0289`) **dan** di
`drive_c/PES13/dxvk.conf`: `d3d9.presentInterval = 1`. Batas antrean tetap 2,
limiter DXVK tetap -1. Launcher menerapkan pasangan settings/DXVK sebelum launch.
Tidak ada perubahan OC, Wine DLL, FEX DLL, scheduler stable-balance, atau yield.
Gap probe dan opsi disk cache dari build sebelumnya tetap tersedia.

Preset memakai file template di `launcher/presets/`; pilihan disimpan di
`launcher/selected.txt`. Penulisan lima file disiapkan terlebih dahulu dengan
checksum, file sementara, backup dan jurnal. Update yang terputus dipulihkan
pada pembukaan launcher berikutnya; kegagalan recovery memblokir launch.

## Instalasi dan rollback

1. Tutup PES sepenuhnya. Simpan log dan settings.dat utama bila memiliki mapping
   kontrol sendiri: payload awal memasang preset Medium bawaan.
2. Salin **folder `switch` utama** dalam ZIP ke root SD, termasuk folder
   `launcher`. Jangan hanya mengganti NRO: artwork dan template adalah bagian
   wajib paket ini.
3. Buka NRO/forwarder yang sama. Default tanpa INI adalah launcher PES.
   Instalasi yang sengaja menyetel `run_guest_tests=1` tetap masuk guest test;
   set `run_guest_tests=0` untuk launcher. INI pengguna tidak ditimpa paket.
4. Tes perpindahan PES13 → loading → layar game, pilihan preset, VSync dan
   pacing. Tetap memakai konfigurasi clock/core yang sama untuk perbandingan.
5. Rollback: tutup PES dan salin `rollback/switch` ke root SD. Ini mengembalikan
   enam payload gap-audit, termasuk VSync OFF/Medium 720p. Folder launcher sisa
   tidak dipakai NRO lama dan boleh dibiarkan.

## Validasi dan reproduksi

Renderer C yang sama menghasilkan preview host 1280×720. ASan/UBSan memeriksa
rendering dengan stride berpading, seluruh preset dan checksum, pelestarian
kontrol dari KONAMI, 28 kegagalan penulisan/rename/power-loss yang disuntikkan,
template rusak, navigasi launch/cancel/error, serta pelepasan framebuffer sekali
pada thread pemilik. API libnx/GPU dimodelkan pada tes lifecycle, bukan Switch
sungguhan. Tes linked ARM64 memeriksa gap observer dan regresi runtime.

`tools/build-fextendo-assets.py` membutuhkan Pillow; font dan gambar asli ada
di assets. `tools/make-fextendo-presets.py config/fextendo/presets` menghasilkan
template dari baseline terverifikasi. Build runtime menambah `--launcher`
di atas flag gap-audit. Paket/receipt memuat hash sumber, dependency, payload,
rollback dan hasil tes. Tidak ada klaim perbaikan FPS/stutter dari tes host.

Font: [Barlow, Google Fonts](https://github.com/google/fonts/tree/main/ofl/barlow).
Lisensinya disertakan. Artwork PES berasal dari aset yang diberikan pengguna;
lisensi font tidak mencakup artwork atau game.
