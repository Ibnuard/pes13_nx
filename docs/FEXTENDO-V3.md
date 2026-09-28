# FEXTendo v3 — blue glow, scrollable Settings and visible timestamp

Update untuk instalasi FEXTendo/PES13 yang sudah berjalan. Pengguna melaporkan
v2 lancar selama pertandingan, dengan lag di kickoff/awal game. V3 memperbarui
launcher dan jalur overlay. **Build ini belum diuji di Nintendo Switch.**

## Instalasi dan kontrol

1. Tutup PES sepenuhnya melalui HOME → X.
2. Salin folder `switch/` utama dalam ZIP ke root SD dan replace file yang sama.
   NRO dan artwork format 3 harus diperbarui bersama.
3. D-pad/stik memilih PES13 atau Settings; A membuka; B kembali; + keluar.
   Settings dapat di-scroll: tiga baris terlihat penuh, pilihan bergerak dengan
   animasi dan scrollbar menunjukkan posisi.
4. Debug timestamp mengikuti pilihan tersimpan. Pilih Settings → Debug timestamp
   → A untuk menggantinya. Menu sounds default ON dan bisa dimatikan di baris terakhir.

Paket tidak menimpa `settings.dat`, `selected.txt`, `debug-timestamp.txt`,
`menu-sound.txt`, `last-played.txt`, cache game, atau override pengguna. File game tidak disertakan.

## Tampilan dan audio

Play dan kartu menggunakan gradasi biru–hitam transparan dengan cahaya yang
mengitari tepi. Bagian terang memiliki halo biru di luar tepi; bagian lainnya
memudar, tanpa highlight putih pada bahan tombol. Gradasi dan halo mengikuti
sumber cahaya yang sama. Ikon dan teks Play dipusatkan sebagai satu grup. Di bawahnya, Last played
menunjukkan waktu relatif dari riwayat yang tersimpan setelah present pertama
berhasil. Present hanya menyimpan tick; penulis log yang sudah ada menyimpan
riwayat di SD, paling lambat ketika keluar secara normal. Sebelum ada riwayat,
tampil Never. Jam konsol yang mundur ditangani dengan label Recently.

Fokus membesarkan kartu yang dipilih dan mengecilkan kartu sebelumnya. Header
memiliki dua bidang blur yang memudar ke tengah, dengan gamepad flat, tab PES13,
ikon cover membulat, wordmark FEXTendo, byline dan persentase baterai. Footer
memakai blur dengan petunjuk tombol rata tengah vertikal. Baterai dibaca setiap
10 detik; bila layanan tidak tersedia, tampil `--`.

Kurva dan segitiga Play memakai antialiasing; sprite memakai sampling bilinear
premultiplied, font dirasterisasi pada 4×, dan helper controller berasal dari
SVG resolusi tinggi. Aset gamepad/wordmark memakai hasil generasi yang sama
seperti v2. NRO sekarang menyematkan cover PES2013 dari `assets/icon.png`.
Ikon HOME forwarder yang sudah terpasang merupakan metadata terpisah dan tidak
diperbarui dengan menyalin NRO.

SFX navigasi, konfirmasi, kembali dan error disintesis lokal. Audio launcher
ditutup sebelum game mulai memakai layanan audio. Tidak ada aset audio pihak ketiga.

## Debug timestamp

Kode v2 dapat melewati overlay ketika launcher memiliki override layer default.
V3 membuat dan membuka managed layer tersendiri secara eksplisit, tanpa
mengubah layer game, memasangnya pada display stack LCD/default serta mencoba
stack screenshot/recording. Posisi disesuaikan dengan resolusi logis display.

`T+ HH:MM:SS.d` dihitung sejak Play dan digambar pada framebuffer kecil terpisah
pada 10 Hz. Tidak ada lagi log timestamp berkala; hanya titik awal, status setup,
atau kegagalan untuk diagnosis. OFF tidak membuat worker/layer. Atlas kecil
memperhalus angka. Jika setup gagal, game tetap berjalan dan log menunjukkan
`overlay unavailable stage=...`; setup selesai mencatat `overlay ready`.

Kehadiran overlay di layar, capture, serta dampaknya terhadap frame time masih
perlu dikonfirmasi di Switch. Worker terpisah tidak menjamin tetap berjalan
ketika CPU atau layanan display berhenti. Uji timestamp ON/OFF pada preset,
clock, dan kondisi cache yang sama.

## Performa game dan rollback

Pengaturan runtime v2 dipertahankan: filter `VK_EXT_memory_budget`, stable
balance, bounded yield, worker cores, VSync ON dan antrean dua frame. Tidak ada
perubahan guest DLL, adapter FEX, dependency native, atau konfigurasi DXVK.

Lag awal belum didiagnosis dengan log v2 baru. Kompilasi atau pemuatan data
mungkin berperan, tetapi belum dibuktikan dari rekaman pengguna. V3 tidak
mengklaim menghilangkan lag kickoff. Rekam kickoff dan pertandingan kedua
beserta T+, lalu simpan log setelah keluar dari game untuk pencocokan.

Untuk rollback, tutup game dan salin `rollback/switch/` ke root SD. NRO dan
artwork kembali persis ke v2. Aset tambahan v3 yang tersisa tidak dibaca v2.
Pilihan preset, toggle dan cache tetap dipertahankan.

## Validasi dan reproduksi

Sebelas laporan terikat ke ELF yang sama: launcher, memory, budget, gap,
balance, yield, cores, resume, pipeline, JIT log dan unwind. Launcher memeriksa
renderer/stride dengan ASan/UBSan, clipping scroll, perpindahan fokus, IO preset,
navigasi, lifecycle framebuffer/audio, serta PCM dan ownership buffer audio.
Timestamp memakai pthread nyata dengan layanan VI dimodelkan, termasuk layer
game eksternal, empat stack, bounds parcel dan jalur kegagalan setup. Tes host
ini tidak membuktikan FPS, GPU, hak layanan VI atau audio pada hardware.

Preview menggunakan renderer C produksi. Sumber, hash aset, laporan build,
hash dependency, NRO metadata dan hasil tes ada di `source/` dan `evidence/`.
`manifest.json` mengikat seluruh isi ZIP dan baseline v2.

Aset: Python dengan Pillow dan CairoSVG, jalankan `tools/build-fextendo-assets.py`
ke `local/fex3/fextendo-v3/package/switch/pes13-fex/launcher`. Pada macOS, Cairo
mungkin memerlukan `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.
Build memakai flag v2 pada `tools/build-fex-runtime.py` dengan `--launcher`,
`--memory-audit`, `--memory-budget-filter`, output `local/fex3/fextendo-v3/runtime`.
Mode `--native-only` membutuhkan payload guest dan receipt dependency dari v2.
Tes: `tests/run_fextendo_checks.py --python ... --source ... --work
local/fex3/fextendo-v3`. Paket: `python3 tools/package-fextendo-v3.py`.

Referensi protokol: [libnx VI](https://github.com/switchbrew/libnx/blob/master/nx/source/services/vi.c)
dan [layer stack libtesla](https://github.com/WerWolv/libtesla/blob/master/include/tesla.hpp).
