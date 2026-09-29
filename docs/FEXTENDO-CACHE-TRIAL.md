# Rencana uji cache FEXTendo

Hasil kedua run sudah direview dalam
[hasil trial](FEXTENDO-CACHE-TRIAL-RESULT.md): manfaat belum terlihat dan
reuse cache belum terkonfirmasi. Trial renderer
[Sarek 1.13.0](FEXTENDO-SAREK-TRIAL.md) selanjutnya mematikan FEX disk cache.
Instruksi di bawah disimpan sebagai catatan eksperimen ON sebelumnya.

Tujuan: mengurangi stutter match pertama setelah aplikasi dibuka dari kondisi
tertutup, dengan memakai ulang pekerjaan kompilasi. Tahap pertama memakai
NRO **DXVK core 3 v1** yang sama. Jalur ON/OFF disk cache sudah ada di binary;
environment-nya diperiksa terhadap ELF dan receipt paket. Ini belum
membuktikan database cache dapat ditulis/dipakai di Switch.

Baseline OFF empat core yang sudah tersedia: capture `e5de465b0c`, satu
match, penanda 01:55/02:19/02:30. Ringkasan di
[analisis core 3 aktif](FEXTENDO-DXVK-CORE3-ACTIVE-RESULT.md).

## Paket konfigurasi

`dist/pes13-fextendo-cache-trial-v1.zip` hanya mengubah satu flag; tidak
berisi NRO/DLL baru dan tidak memerlukan forwarder baru. Gunakan bersama
build **DXVK core 3 v1** yang sudah dipakai pada capture baseline.

Salin folder `switch/` dari ZIP ke root SD untuk menulis file
`switch/pes13-fex/fex_diskcache` berisi `1`. Jika `configuration.ini`
sudah memiliki key `fex_diskcache`, ubah key tersebut ke `1` juga:
**INI mengalahkan file flag**. Jangan mengganti seluruh INI.

Folder `control-off/switch/` berisi flag `0` untuk dikembalikan ke root SD
saat rollback. Jika ada key di INI, kembalikan juga ke `0`. Jangan menyalin
folder `control-off/` saat mengaktifkan tes. Salin log sebelum setiap
peluncuran berikutnya agar bukti Run A tidak tertimpa.

## Tahap 1 — uji FEX disk cache dalam dua peluncuran

1. Tutup aplikasi. Backup `switch/pes13-fex/configuration.ini`. Cari key
   `fex_diskcache`; ubah nilainya menjadi `1`. Jika belum ada, tambahkan satu
   baris ini pada file yang sama. Jangan membuat key duplikat atau menimpa
   seluruh INI dengan contoh ini:

   ```ini
   fex_diskcache=1
   ```

   Pertahankan `fex_dxvk_core3=1`, `fex_auto_core3=0`, short trace ON dan
   Debug timestamp ON. Flag core 3 yang sudah ada sebagai file boleh tetap
   dipakai; tidak perlu menduplikasi ke INI. Pertahankan JIT block size,
   preset, VSync, OC, tim, stadion dan kamera.

2. **Run A — pengisian.** Buka aplikasi dari kondisi tertutup, jalankan match
   seperti baseline sekitar 4–5 menit. Ulangi kickoff, umpan cepat, shoot dan
   bola lambung. Catat T+ overlay. Run pengisian dapat tetap stutter atau
   lebih lambat karena ada penulisan cache; belum menjadi ukuran keberhasilan
   pemakaian kembali cache.

3. Kembali ke menu setelah selesai, tutup aplikasi sepenuhnya lewat
   **HOME → X**. Salin `switch/pes13-fex/fex-runtime.log` dan beri nama
   `fex-cache-fill.log` sebelum membuka launcher lagi. Jika terbentuk,
   salin juga folder `switch/pes13-fex/drive_c/fex-jit-cache` untuk snapshot A.
   Folder cache asli tetap di SD.

4. **Run B — pemakaian kembali.** Buka aplikasi lagi dengan key tetap `1`,
   lalu mainkan match dan adegan yang sama sekitar 4–5 menit. Catat T+ stutter,
   terutama kickoff pertama. Tutup aplikasi, ambil log
   `fex-cache-reuse.log` dan snapshot folder cache B.

5. Kirim kedua log, waktu kejadian, serta folder cache A/B jika memungkinkan.
   Catat jika folder tidak terbentuk, kosong, atau aplikasi gagal berjalan.
   Menjalankan match kedua tanpa menutup aplikasi tidak menggantikan Run B,
   karena yang diuji adalah reuse setelah proses dimulai ulang.

Jangan menghapus cache DXVK yang sudah berisi 498 shader. Jika folder FEX
cache sudah ada sebelum tes, simpan snapshot awal juga dan laporkan; Run A
berarti penambahan cache existing, bukan cache kosong. Tidak perlu menghapus
data tersebut agar bisa memulai tes.

## Penanda dan kriteria

- Startup harus mencatat `[FEX3-DISKCACHE] requested=1`; core 3 tetap
  `name=dxvk-cs active=1 core=3 mask=8 priority=63` dengan readback sukses.
- Lokasi yang diharapkan dari source:
  `drive_c/fex-jit-cache/DiskCache/<bucket-hash>/RWCacheDB.foz` dan
  `RWCacheDB_idx.foz`. Hash bucket memisahkan konfigurasi/fitur CPU. Nama
  folder/file harus diperiksa dari output nyata, bukan dibuat manual untuk
  membuat tes tampak berhasil.
- File tidak kosong belum membuktikan cached code pernah dipakai. Review
  akan memeriksa isi/metadata cache, perubahan jumlah/waktu compile_code,
  dan gap frame pada adegan sebanding. Bila hanya status requested yang ada
  atau hasil ambigu, tahap selanjutnya adalah probe pembacaan/penulisan/
  penerimaan cached code pada FEX, bukan menganggap fitur sudah berhasil.
- Keberhasilan praktis: kickoff pertama Run B lebih ringan, beban kompilasi
  berkurang, dan bagian gameplay yang sudah lancar tidak memburuk. Tidak ada
  ambang FPS yang dianggap tercapai hanya dari counter Present.
- Jika ada manfaat, lakukan kontrol OFF (`fex_diskcache=0`) dengan forwarder
  dan kondisi sama untuk memeriksa pengaruh urutan tes. Cache boleh tetap
  tersimpan; OFF menghentikan pemakaiannya tanpa menghapusnya.

## Batas teknis yang sudah diketahui

Cache ini menyimpan kode CPU FEX, terpisah dari shader DXVK. Source yang
dipakai memiliki jalur lookup, load cached code, relokasi dan store; writer
bekerja di thread internal berprioritas rendah. Konfigurasi eksperimen
mematikan file mapping, anonymous-code caching dan memory LRU, dengan batas
64 MiB untuk file data utama per database (bukan seluruh folder beserta index
dan semua bucket).

Saat disk cache aktif, optimasi tertentu untuk guard kode statis tidak
dipakai (`WantsDiskCachePatching` pada Core.cpp). Karena itu manfaat pada
startup harus dinilai bersama kemungkinan penurunan performa steady-state.
Tes host sebelumnya memeriksa environment dan binary, bukan persistensi
database Switch. Log `requested=1` bukan cache-hit counter.

Rollback cukup kembalikan `fex_diskcache=0` lalu buka ulang aplikasi. Jika
aplikasi bermasalah, ambil log lalu gunakan OFF; NRO, forwarder, save game
dan cache DXVK tetap sama.

## Audit saran DXVK ASYNC, Mesa 10G, dan thunks

### `DXVK_ASYNC=1`

Log perangkat menyebut **DXVK v3.1.1**. Source upstream v3.1.1 yang diperiksa
tidak membaca `DXVK_ASYNC` dan tidak menyediakan opsi `enableAsync` atau
`gplAsync`. Menambahkan environment tersebut tidak mengaktifkan compiler
async pada build ini. Fork dengan patch async perlu dievaluasi sebagai
perubahan binary tersendiri, bukan dianggap bisa diaktifkan lewat INI.

Jalur yang didukung adalah Graphics Pipeline Library (GPL); log perangkat
sudah melaporkan `graphicsPipelineLibrary=1`. DXVK dapat memulai kompilasi
saat shader D3D dimuat. Shader yang baru diserahkan game saat draw tetap
dapat memicu pekerjaan baru. Karena itu jeda persiapan harus didasarkan pada
antrean kompilasi yang nyata, bukan timer tetap.

Referensi: [README DXVK v3.1.1](https://github.com/doitsujin/dxvk/blob/v3.1.1/README.md#graphics-pipeline-library)
dan [opsi DXVK v3.1.1](https://github.com/doitsujin/dxvk/blob/v3.1.1/src/dxvk/dxvk_options.cpp).

### `MESA_SHADER_CACHE_MAX_SIZE=10G`

Mesa yang terhubung ke NRO mendukung disk shader cache. Source build Switch
memilih **single-file Fossilize** secara default ketika ketiga selector
backend cache tidak di-set (`disk_cache_switch_single_file_default` dalam
`src/util/disk_cache.c`). Backend ini tidak menerapkan batas
`MESA_SHADER_CACHE_MAX_SIZE`. Tidak ada override selector Mesa pada
environment runtime yang diperiksa; status backend aktif di perangkat belum
dicetak langsung dalam log.

Untuk backend yang mendukungnya, `10G` adalah batas kapasitas disk, bukan
reservasi RAM, perintah precompile atau jaminan cache hit. Belum ada bukti
cache terhapus karena mencapai batas kapasitas. Angka **498 shader / 2,3 MB**
di log berasal dari cache DXVK, bukan ukuran cache Mesa.

Mesa adalah library native dalam NRO. Environment Windows untuk game dan
environment native proses adalah jalur berbeda; menambahkan key ini ke
`configuration.ini` tidak otomatis meneruskannya ke `getenv` milik Mesa.
Audit berikutnya perlu memastikan lokasi cache native, persistence dan
hit/miss lintas peluncuran sebelum mengubah batas ukuran. Pertahankan cache
Mesa dan DXVK saat menjalankan trial FEX ini.

Referensi: [environment Mesa](https://docs.mesa3d.org/envvars.html#envvar-MESA_DISK_CACHE_SINGLE_FILE).
Receipt runtime mencatat `libvulkan.a` SHA-256
`700892006eb2552bfdc6b51d5526f5eedb2e873737157da4ec89865b31288c08`
dan `libmesa_util.a`
`c5b7b2f2ab8334e0b85dab35fd9a000f090d2f592f1c4dfb1991dad9a60fe3c9`.

### FEX thunks / pemanggilan library native

Pada port WOW64 ini, FEX sudah menangani bridge Unix-call menuju dispatcher
Wine. `Source/Windows/WOW64/Module.cpp` memanggil `WineUnixCall`;
`dlls/winevulkan/vulkan_thunks.c` mengonversi argumen Vulkan 32-bit dan
memanggil entry point driver host. Mesa/Vulkan yang di-link adalah ARM64
native. Ini menjalankan tujuan pengalihan ke native untuk Vulkan, melalui
bridge Wine/WOW64; bukan bukti bahwa seluruh sistem Linux FEX thunks atau
semua library lain diaktifkan.

Kode game x86 dan DXVK x86 masih diterjemahkan FEX. Bridge yang sudah ada
tidak menghilangkan kompilasi pertama kode-kode tersebut, dan tidak membuat
kompilasi pipeline driver menjadi gratis. Tidak ada perubahan thunk OpenAL
atau OpenGL dalam trial ini; belum ada bukti kedua jalur itu menjadi
bottleneck adegan PES yang dilaporkan.

## Tahap 2 — persiapan shader/pipeline sebelum bermain

Sesudah hasil tahap 1 jelas, audit pembuatan pipeline DXVK yang masih terjadi
saat match. Log baseline sudah membaca 498 shader tetapi masih membuat
pipeline grafis pada beberapa adegan; shader cache tidak berarti semua
kombinasi pipeline siap.

Target implementasi: siapkan pekerjaan yang sudah diketahui sebelum match,
ukur antrean yang benar-benar pending/selesai, dan gunakan kembali hasil
yang valid. Bila data yang diperlukan baru tersedia ketika game melakukan
draw, tentukan apakah bisa direkam untuk dipersiapkan pada peluncuran
berikutnya. Jangan mengasumsikan semua shader/pipeline dapat diketahui
sebelum game pernah menggunakannya.

UI “Preparing game / Compiling…” baru ditambahkan setelah ada pekerjaan
dan indikator selesai yang nyata. Durasi tunggu tetap atau animasi loading
saja tidak mengurangi kompilasi. Pipeline dan cache FEX diuji terpisah agar
manfaat serta regresinya dapat diketahui; belum ada janji kompilasi cukup
sekali untuk semua versi, pengaturan, atau scene.
