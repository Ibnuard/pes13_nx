# FEXTendo — DXVK-Sarek 1.13.0 trial

**Hasil perangkat terbaru:** perbaikan limiter v2 membuat loading bergerak,
tetapi proses kemudian keluar dengan `std::bad_alloc`. Uji kontrol
dyasync OFF sebelum menilai gameplay; lihat
[hasil alokasi dan langkah tes](FEXTENDO-SAREK-ALLOCATION-RESULT.md).

Paket `pes13-fextendo-sarek-1.13.0-v2.zip` mengganti renderer D3D9 dengan
rilis upstream **DXVK-Sarek 1.13.0**, mode **dyasync**. Cache disk FEX dimatikan
sesuai [hasil dua log](FEXTENDO-CACHE-TRIAL-RESULT.md). NRO, FEX DLL, forwarder,
game, save, preset kualitas dan OC tetap memakai instalasi yang sudah diuji.

**Paket v1 memiliki salah konfigurasi limiter yang menyebabkan sekitar
1 FPS.** V2 mengubah `d3d9.maxFrameRate` dari `-1` ke `0`. Untuk instalasi
Sarek v1 cukup gunakan patch kecil pada
[panduan perbaikan loading](FEXTENDO-SAREK-LOADING-FIX.md).

## Alasan memilih rilis

[Changelog 1.13.0](https://github.com/pythonlover02/dxvk-sarek/releases/tag/v1.13.0)
mencakup perbaikan antrean dyasync, batching command-stream, penghindaran
flush yang tidak perlu pada D3D9, dan perubahan allocator. Versi ini juga
memungkinkan pengujian `dyasync` versus `none` pada DLL yang sama.
Versi 1.12.0 memperkenalkan dyasync; 1.13.0 memberi kontrol eksperimen dan
perbaikan lanjutan yang lebih relevan untuk kasus ini.

Dyasync dapat menunda kompilasi varian pipeline sambil menggambar dengan
pipeline sementara. Shader pertama tetap dapat memerlukan kompilasi
sinkron; tampilan/blending sementara dapat berbeda. Mode ini belum diuji
pada Switch ini dan tidak menjanjikan semua freeze hilang.
[Penjelasan upstream](https://github.com/pythonlover02/dxvk-sarek/blob/v1.13.0/README.md#shader-compilation).

Konfigurasi trial:

```ini
d3d9.maxFrameRate = 0
dxvk.shaderCompilationMethod = "dyasync"
dxvk.numShaderCompilerThreads = 1
dxvk.numCompilerThreads = 1
dxvk.enableStateCache = True
dxvk.framePace = "max-frame-latency"
```

Dua pengaturan jumlah worker mengontrol **dua pool berbeda**, bukan total
satu thread untuk seluruh DXVK. Pilihan ini membatasi masing-masing pool.
VSync ON, antrean dua frame dan opsi kualitas lama dipertahankan. Nilai `0`
mematikan limiter Sarek pada presentInterval 1; nilai `-1` dari config
DXVK 3.1.1 justru diterjemahkan menjadi soft cap 1 FPS oleh Sarek 1.13.0.
Mode baru `low-latency` belum diaktifkan supaya dampaknya tidak tercampur
dalam trial.

## Instalasi

1. Tutup aplikasi. Backup file yang akan diganti di SD.
2. Salin **hanya folder `switch/` pada root ZIP** ke root SD, merge dan replace.
   Jangan salin `control-none/` atau `rollback-dxvk311/` pada tahap ini.
3. INI paket berasal dari salinan pengguna
   `dist/cache-trial-v1/switch/pes13-fex/configuration.ini`; hanya nilai
   `fex_diskcache` diubah dari `1` ke `0`. Jika INI di SD sudah diubah lagi,
   pertahankan INI SD dan ubah hanya `fex_diskcache=0` secara manual.
   File flag `fex_diskcache` juga berisi `0`, tetapi INI tetap lebih prioritas.
4. Gunakan forwarder empat core yang sama. Tidak perlu build/re-forward NRO.

File aktif yang diganti:

```text
switch/pes13-fex/
├── configuration.ini
├── fex_diskcache
├── drive_c/PES13/d3d9.dll
├── drive_c/PES13/dxvk.conf
├── drive_c/dxvk/d3d9.dll
└── launcher/presets/dxvk.conf
```

DLL di dua lokasi identik (PE32/x86). Template config launcher juga diganti
agar pemilihan preset tidak mengembalikan config renderer lama.

## Pengujian

Mainkan kickoff, umpan cepat, bola lambung dan shooting dengan tim/stadion/
kamera/preset/OC yang sama. Ambil log pertama sebelum membuka ulang aplikasi,
kemudian lakukan satu peluncuran kedua dan ulangi. Beri nama
`sarek-first.log` dan `sarek-reuse.log`, sertakan timestamp stutter dan
perubahan visual jika ada. Sarek menggunakan format state cache yang berbeda
dari DXVK 3.1.1 sehingga peluncuran pertama dapat membangun cache baru.

Penanda yang harus diperiksa:

- Versi DXVK menunjukkan `1.13.0` (nama build dapat memiliki suffix Sarek).
- Config efektif `d3d9.maxFrameRate = 0`.
- `DXVK: Shader compilation method: dyasync`.
- `DXVK: Using 1 dyasync compiler threads`; pool state-cache memakai satu
  worker saat dibuat, dengan penanda `Using 1 compiler threads`.
- `[FEX3-DISKCACHE] requested=0`.
- `[FEX3-DXVKCORE] ... name=dxvk-cs ... active=1 core=3 mask=8 priority=63`.

Sarek membaca `DXVK_STATE_CACHE_PATH`, bukan `DXVK_SHADER_CACHE_PATH` yang
dipakai build 3.1.1. Dengan environment eksplisit NRO saat ini, default yang
diharapkan adalah file relatif `C:\PES13\pes2013.dxvk-cache`; jika Wine
menambahkan `LOCALAPPDATA`, default bergeser ke subfolder `dxvk` di sana.
Periksa file nyata dan log valid-state-cache pada run kedua sebelum
menganggap reuse berhasil. File ini tidak menggantikan cache 3.1.1
`C:\dxvk-cache\86eaf3d9f8690dcd.dxvk.bin`. Jangan hapus cache Mesa/DXVK/FEX.

## Kontrol dan rollback

- **Kontrol dyasync OFF:** setelah menyimpan log dan menutup aplikasi, salin
  `control-none/switch/` ke root SD. DLL tetap Sarek 1.13.0; config hanya
  mengubah `dxvk.shaderCompilationMethod` menjadi `none`. Ini berguna untuk
  membandingkan dampak dyasync atau memeriksa artefak visual.
- **Kembali ke DXVK 3.1.1:** salin `rollback-dxvk311/switch/` ke root SD.
  Ini mengembalikan dua DLL D3D9 dan kedua config renderer. FEX disk cache
  tetap OFF. Tidak ada save/settings.dat/cache yang dihapus.
- **Kembali ke trial dyasync:** salin lagi root `switch/` dari ZIP.

## Provenance dan batas verifikasi

Sarek berasal langsung dari asset rilis maintainer, tidak dimodifikasi:
commit `37f397e142b977a343e920dbc4c7bf7ed2c63a81`, arsip SHA-256
`b42d8f2edeb5ed53d1e0009e17bcd765f53c1ac0fda6c936a76b70b2c289dcf8`,
PE32 D3D9 SHA-256
`0c9d2236aa507ff23761d24382e44ea47512d9e21a01c2722cf3a2bc03dfcd04`.
Source dalam rilis diperiksa terhadap tag tersebut.

Rollback DXVK 3.1.1 menggunakan DLL resmi SHA-256
`265888c31ca78dffa290c39cb7e50bfb02762590e41927906e46fb32f01497fa`,
sama dengan hash paket FEX3 sebelumnya. Kredit DXVK/Sarek beserta lisensinya
disertakan; pemilihan rilis dan konfigurasi trial adalah integrasi proyek,
bukan klaim membuat renderer tersebut.

Pemeriksaan meliputi hash asset/payload, arsitektur PE32, export D3D9,
resolusi import wajib terhadap dependency Wine yang cocok, konfigurasi,
template preset dan rollback. Import delay-load tetap dicatat dalam laporan;
hasil ini bukan klaim semua API dinamis atau rendering sudah bekerja di
hardware. Tidak ada pengujian Switch otomatis dari komputer ini.
