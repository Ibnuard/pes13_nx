# FEXTendo v2 — launcher, memory-budget trial and timestamp

Update untuk instalasi Fextendo/PES13 yang sudah berjalan. File game dan Wine
tetap memakai instalasi sebelumnya. **Belum diuji di Nintendo Switch.**

## Instalasi dan kontrol

1. Tutup PES sepenuhnya melalui HOME → X.
2. Salin seluruh folder `switch/` utama dalam ZIP ke root SD, replace file
   yang sama. NRO dan artwork harus diperbarui bersama.
3. D-pad/stik memilih PES13 atau Settings, A membuka, B kembali, + keluar.
   Paket tidak menimpa settings.dat atau preset pilihan pengguna.
4. Untuk merekam kejadian, pilih kartu Settings → **Debug timestamp** → A.
   Default OFF. Pilihan tersimpan di `launcher/debug-timestamp.txt`.

Latar memakai gradasi menyatu, tombol Play dan kartu aktif menggunakan glossy
animation tanpa outline, footer blur dengan helper rata tengah vertikal,
ikon branding membulat, gamepad flat serta wordmark rounded **FEXTendo**.
Tab kiri hanya PES13; Settings dibuka dari kartu, bukan tombol di samping Play.

## Perubahan memori

Log masukan: 574.466 byte, SHA-256
`99c459c5ac19874b5ee366519f03cab7a276001399df4732831341f67bb7c447`,
build `pes13-fextendo-mem-audit`. Ada 848 gap tercatat >50 ms dan 706 query
memori lambat. Sebanyak 555 gap memuat query di thread/handle yang sama;
median rasio CPU query terhadap CPU gap 97,71%. Ini menjelaskan sampel yang
cocok, bukan seluruh frame atau semua stutter.

Wine tidak mengiklankan ekstensi opsional `VK_EXT_memory_budget` ke guest
secara default. Kemampuan driver internal dan ekstensi lain dipertahankan.
[DXVK 3.1.1](https://github.com/doitsujin/dxvk/blob/v3.1.1/src/dxvk/dxvk_memory.cpp)
melewati pembaruan anggaran berkala bila ekstensi ini tidak tersedia. Ini
menghindari jalur query mahal tanpa membuat angka memori palsu atau cache
anggaran kedaluwarsa. Override `dxvk.enableMemoryDefrag = False` dihapus,
mengembalikan defragmentasi ke konfigurasi awal Fextendo.

Log default: `[FEX3-MEMBUDGET] client_extension=0`. Untuk A/B dengan NRO
yang sama, buat file `switch/pes13-fex/fex_memory_budget` berisi `1`, lalu
restart. Hapus file atau isi `0` untuk default baru. Paket tidak memasang
file override tersebut. Tidak ada pemindaian per-frame baru.

Tanpa ekstensi, DXVK memakai anggaran fallback sendiri. Sesi panjang dan
kondisi memori penuh tetap perlu diuji. First kickoff juga melibatkan
kompilasi dan pekerjaan game lain. Perubahan ini **belum membuktikan**
bahwa first kickoff, shooting, atau stutter keseluruhan sudah selesai.

## Timestamp dan uji perangkat

`T+ HH:MM:SS.d` menghitung waktu sejak Play. Worker 10 Hz menggunakan layer
VI terpisah; frame game yang berhenti tidak secara langsung menghentikan
stopwatch. Penjadwalan CPU/layanan display yang macet tetap bisa menundanya.
Rendering ditangguhkan saat aplikasi kehilangan fokus. OFF tidak membuat
worker maupun layer. Jika setup gagal, game tetap lanjut dan log mencatat
`overlay unavailable`; sukses mencatat `overlay ready`. Ketersediaan layer
dan tampilan overlay masih perlu dibuktikan di Switch.

`[FEXTENDO-TIME] origin_tick=...` mengikat waktu Play ke system tick pada
`[FEX3-GAP]` dan `[FEX3-MEMQUERY]`:

`elapsed_ms = (event_tick - origin_tick) / 19200`

Logger juga menulis elapsed_ms berkala. Pertahankan preset, clock dan cache
saat membandingkan. Rekam first kickoff (perkiraan pengguna: di bawah dua
menit dari Play), bola cepat/shooting, dan pertandingan kedua. Catat T+ saat
gangguan, simpan video, salin `fex-runtime.log` setelah menutup game. Bandingkan
timestamp OFF untuk mengukur pengaruh overlay. VSync ON, antrean dua frame.

## Rollback

Tutup game, salin `rollback/switch/` ke root SD. NRO dan dua konfigurasi kembali
persis ke **memory-trial**, artwork kembali ke Fextendo v1. Aset baru yang
tersisa tidak dipakai launcher lama. Preset pilihan, settings.dat, cache dan
toggle timestamp tidak dihapus atau ditimpa.

## Validasi dan reproduksi

Sebelas laporan terikat pada SHA-256 ELF yang sama: launcher, memory observer,
budget filter, gap observer, stable balance, bounded yield, worker cores,
resume, pipeline, JIT logger dan unwind. Launcher mencakup ASan/UBSan untuk
renderer, IO preset, navigasi, framebuffer dan timestamp: OFF, padded stride,
sepuluh kegagalan setup VI, fokus, shutdown dan pthread nyata dengan layanan
display dimodelkan. Ini bukan tes FPS/GPU atau Nintendo Switch.

Budget filter memakai layout bitfield Wine sebenarnya. Menghapus sisipan
filter mengembalikan source Vulkan memory-audit persis. Filter di-inline
compiler; tes tidak mengklaim menjalankan fungsi terpisah di emulator.
Regresi runtime lain menjalankan jalur ARM64 dengan batas kernel dimodelkan.

Build: `tools/build-fex-runtime.py` dengan profile launcher/memory-audit dan
`--memory-budget-filter`. Hash sumber, dependency dan flag ada di
`evidence/runtime/`. Tes: `tests/run_fextendo_checks.py --python ... --source
... --work local/fex3/fextendo-v2`. Paket: `python3 tools/package-fextendo-v2.py`.
Preview menggunakan renderer C produksi, bukan mockup browser.
