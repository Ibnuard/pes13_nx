# FEXTendo — DXVK-GPLAsync 2.7.1-1

Paket `pes13-fextendo-dxvk-gplasync-2.7.1-v1.zip` mengganti D3D9 dengan
DLL x86/PE32 resmi [Ph42oN v2.7.1-1](https://gitlab.com/Ph42oN/dxvk-gplasync/-/releases/v2.7.1-1).
Ini DXVK 2.7.1 dengan patch async, bukan DXVK vanilla yang hanya diberi
environment variable. DLL upstream tidak dimodifikasi oleh FEXTendo.

## Pasang dan tes

1. Tutup aplikasi melalui HOME. Simpan salinan DLL/config lama jika sudah
   memiliki perubahan pribadi.
2. Salin **hanya folder `switch/` pada root ZIP** ke root SD, merge/replace.
   Jangan salin folder rollback pada tahap ini.
3. Buka dengan forwarder yang sama. **Tidak perlu build/re-forward NRO.**
4. Uji satu fresh launch: menu, kickoff pertama, shoot dan bola lambung.
   Pakai preset/OC/tim/stadion/kamera yang sama. Catat timestamp overlay
   serta benda/efek yang sempat menghilang atau terlambat muncul.
5. Simpan log sebelum membuka launcher lagi. Jika startup dan visual baik,
   coba match kedua tanpa menutup aplikasi untuk membandingkan warmup.

Empat file aktif:

```text
switch/pes13-fex/drive_c/PES13/d3d9.dll
switch/pes13-fex/drive_c/dxvk/d3d9.dll
switch/pes13-fex/drive_c/PES13/dxvk.conf
switch/pes13-fex/launcher/presets/dxvk.conf
```

Paket ditujukan untuk instalasi core3 yang sedang diuji. NRO/FEX/Wine,
configuration.ini, disk cache FEX OFF, save, settings.dat, preset grafis
dan affinity tetap memakai instalasi saat ini. Cache lama tidak dihapus.
Template launcher ikut diganti supaya pemilihan preset tidak mengembalikan
config Sarek.

## Config dan batas async

`dxvk.enableAsync = True` mengaktifkan patch. Satu worker pipeline
(`dxvk.numCompilerThreads = 1`) dipertahankan; GPL memakai keputusan auto
upstream. Nama `dxvk-cs` tetap tersedia untuk aturan core 3 yang sudah ada.
VSync ON dan antrean dua frame tetap dipakai.

**Limiter kembali `d3d9.maxFrameRate = -1` sesuai implementasi 2.7.1.**
Metode swapchain versi ini mengubah nilai negatif menjadi target nol,
tanpa auto limiter saat VSync. Tes host ASan/UBSan atas metode upstream
memverifikasi perilaku tersebut termasuk kombinasi monitor/latencySleep.
Aturan Sarek yang salah menerjemahkan -1 menjadi 1 FPS tidak berlaku di sini.

Opsi khusus Sarek (`shaderCompilationMethod`, `numShaderCompilerThreads`,
`enableStateCache`, `framePace`) tidak dibawa ke config ini. GPLAsync
2.7.1 memakai jalur async yang berbeda: draw yang pipeline-nya belum siap
dapat dilewatkan hingga worker selesai. Patch mensyaratkan riwayat pemakaian
render target sebelum async diizinkan, jadi tidak semua pipeline pertama
akan async. Efek atau objek bisa muncul terlambat saat kompilasi awal;
catat jika itu terjadi. Tidak ada janji semua freeze langsung hilang.

DXVK state cache lama dan `gplAsyncCache` sudah dihapus di lini 2.7 ini.
Config tidak mengklaim reuse file `.dxvk-cache` Sarek atau `.dxvk.bin` 3.1.1;
cache driver adalah mekanisme lain. Trial ini bukan sistem precompile semua
shader satu kali sebelum bermain.
[Dokumentasi GPLAsync](https://gitlab.com/Ph42oN/dxvk-gplasync/-/blob/v2.7.1-1/README.md).

Periksa log berikutnya: versi **`v2.7.1-1-gplasync`**, config efektif
`dxvk.enableAsync = True`, satu compiler worker, dan `dxvk-cs` core 3 aktif.
Config aktif saja belum membuktikan setiap draw memenuhi syarat async.

## Asal dan verifikasi

- Recipe/patch GPLAsync: `209a3069a19d13efb019e111f27114c185e86092`.
- DXVK 2.7.1: `c3dd74be6baec53786d4e064a572185b70347a17`.
- Arsip rilis SHA-256:
  `590050b88be7b156cf641abe762e1ad47ebbe828f7f0edb2970aa4716ee3af6d`.
- D3D9 x32 SHA-256:
  `a2cd6841e102f37189527c118ec416fa5071ac4d3120762973d9a0c6c5fd067e`.

Arsip cocok dengan hash metadata file GitLab; version/async marker dan
export D3D9 diperiksa. Kedua patch upstream dapat diterapkan pada source
2.7.1. Required imports terjangkau terselesaikan terhadap Wine yang cocok;
125 isu deferred sama dengan baseline DXVK 3.1.1, tanpa isu baru. Ini tidak
mengesahkan dynamic loading, perilaku API, atau eksekusi di Switch. Tes
limiter menjalankan metode C++ upstream pada host dengan stub objek.
Paket belum diuji di perangkat; hasil gameplay memerlukan log berikutnya.

Kredit DXVK, Ph42oN, Sporif dan kontributor patch dipertahankan dalam
`THIRD_PARTY.md`, disertai lisensi DXVK. FEXTendo menyiapkan integrasi dan
konfigurasi, bukan menulis renderer atau patch async ini.

## Rollback

Salin `rollback-dxvk311/switch/` ke root SD setelah menutup aplikasi.
Ini mengembalikan dua DLL dan dua config DXVK 3.1.1 baseline. Tidak ada
NRO/configuration.ini/cache/save yang diganti oleh rollback tersebut.
