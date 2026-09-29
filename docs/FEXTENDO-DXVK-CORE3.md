# FEXTendo — DXVK core 3 trial v1

Eksperimen setelah **short trace v1**: pindahkan worker bernama tepat
`dxvk-cs` ke core 3 (core keempat), priority 63, jika proses mendapat izin.
Offload kini terverifikasi aktif pada Switch, tetapi belum ada klaim stutter
pertama sudah diperbaiki. Versi tampilan tetap v3.2 / NACP 0.3.3; marker log
build adalah `pes13-fextendo-dxvk-core3-v1`.

**Capture aktif:** `e5de465b0c` mengonfirmasi dxvk-cs di core 3 / priority 63
dengan 41 snapshot mask yang konsisten. Stutter awal masih ada; lihat
[hasil terbaru](FEXTENDO-DXVK-CORE3-ACTIVE-RESULT.md) untuk membedakan biaya
kompilasi game FEX dari shader/pipeline grafis. NRO eksperimen tetap sama.

**Capture sebelumnya:** `3c38f0f07c` sudah menjalankan build
ini, tetapi offload tidak aktif karena proses hanya mendapat core 0–2 dan
priority 28–59. Lihat [hasil analisis](FEXTENDO-DXVK-CORE3-RESULT.md). Izin
core 3 **dan** priority 63 harus tersedia sebelum mengulang A/B; paket ZIP
dan receipt pengujian awal tetap dipertahankan tanpa perubahan.

Jika menggunakan Sphaira dengan opsi **CPU Cores → 4 (Advanced)** seperti
source yang diperiksa pada analisis tersebut, pasang ulang forwarder dengan
opsi itu untuk memperoleh kedua izin. Target tetap
`sdmc:/switch/pes13-fex/pes13-fex.nro`; pertahankan address space/no-alias
instalasi berjalan. Verifikasi readback log di bawah sebelum tes penuh.

Analisis sesi sebelumnya ada di
[FEXTENDO-SHORT-TRACE-RESULT.md](FEXTENDO-SHORT-TRACE-RESULT.md). Di sekitar
kickoff, worker game melakukan banyak kompilasi FEX dan jalur render menunggu.
Setelah replay lalu kickoff kiper lawan, worker game berganti dan gap berkurang.
Penyebab tunggal belum terbukti; A/B ini menguji kontribusi penempatan DXVK.

## Instalasi dan tes ON

1. Gunakan instalasi **short trace v1 yang sudah berhasil dites**. Tutup
   aplikasi. Salin folder `switch` utama dari ZIP ke root SD, timpa file sama.
   Paket ini hanya mengganti NRO dan menambah file `fex_dxvk_core3` berisi `1`.
   FEX DLL diagnostik dari short trace v1 tetap dipakai; DLL tidak disertakan
   ulang. SHA-256 DLL yang dibutuhkan:
   `a8fc15d13e9f0e6443ccffc8974018bf3167aa8e2844c76cb2fb78e3c1d28e92`.
2. Aktifkan **Debug timestamp**. Tetap gunakan preset, clock/OC, tim, stadion
   dan cache yang sama. Short trace tetap ON (`fex_short_trace_off=0`);
   automatic core 3 tetap OFF (`fex_auto_core3=0`, default).
3. Mulai sesi baru. Ulangi kickoff, umpan cepat, shooting, dan bola lambung.
   Catat waktu **T+ overlay**, termasuk saat replay/kickoff kiper, lalu bermain
   sampai sekitar 4–5 menit agar bagian yang sudah lancar ikut tercatat.
4. Tutup aplikasi, salin `switch/pes13-fex/fex-runtime.log`, beri nama
   `dxvk-core3-on.log`. Ambil log sebelum membuka launcher lagi.

Jangan menyalin folder `control-off`, `rollback`, `source`, `evidence` atau
`licenses` sebagai bagian instalasi utama. Paket tidak berisi game.

## Pembanding OFF

Salin folder `switch` di dalam `control-off` ke root SD dan timpa file sama.
Ini mengubah **hanya** `switch/pes13-fex/fex_dxvk_core3` menjadi `0`. Mulai ulang
aplikasi dan ulangi adegan tes, ambil log bernama `dxvk-core3-off.log`.
Gunakan sesi baru untuk setiap kondisi; jangan membandingkan babak awal ON
dengan babak yang sudah lancar dalam proses yang sama. Jika ada perbedaan,
ulang dengan urutan OFF lalu ON untuk mengecek pengaruh cache/urutan tes.

Kembali ke ON dengan menyalin file `fex_dxvk_core3` dari folder `switch` utama
ZIP. Jika key ini pernah ditambahkan ke `configuration.ini`, nilai INI
didahulukan: gunakan `fex_dxvk_core3=1` atau `=0` sesuai kondisi tes.

Kirim kedua log dan catatan waktu stutter. OFF menggunakan NRO yang sama,
sehingga trace, game, preset dan modul FEX tetap sama. Jangan mengubah jumlah
compiler, OC, cache atau opsi JIT di antara kedua sesi.

## Memastikan eksperimen benar-benar aktif

Log startup ON harus memuat `[FEX3-DXVKCORE] v1 requested=1 enabled=1`.
Saat DXVK memberi nama worker, log harus menunjukkan:

```text
[FEX3-DXVKCORE] ... name=dxvk-cs ... active=1 core=3 mask=8 priority=63 rc=0 rollback_rc=0 read_core_rc=0 read_priority_rc=0 ...
```

Nama dan mask hasil readback menentukan apakah offload berhasil. Nomor TID
bisa berbeda setiap sesi. `enabled=1` sendiri belum membuktikan worker telah
dipindahkan. Jika nama tidak muncul, `active=0`, ada result error, atau
`enabled=0`, kirim log tersebut; hasilnya belum bisa disebut tes core 3 aktif.
Startup OFF harus menunjukkan `requested=0 enabled=0`.

Izin core 3 dan priority 63 diperiksa dari proses. Jika izin tidak tersedia,
offload tidak dijalankan. Bila `fex_auto_core3=1`, trial juga dinonaktifkan agar
tidak bercampur dengan kebijakan lama yang dapat menempatkan semua worker di
core 3. Jangan mengaktifkan opsi itu untuk percobaan ini.

Untuk trace, cek `[FEX3-SHORT] v1 enabled=1` dan `[FEX3-JIT-CLOCK]`; jika tidak
ada, pastikan DLL short trace terpasang dan `fex_short_trace_off=0`.

## Scope, pemulihan dan kredit

Balancer game tetap memakai core 0–2. Worker game berat sudah berada di core
1–2 pada bagian awal log sebelumnya; setelah lancar ada worker berat di core
0. Trial tidak memaksa ulang game ke 1–2 sekaligus. Hanya `dxvk-cs` yang dipilih,
bukan `dxvk-submit`, `dxvk-queue`, semua thread DXVK, atau thread server Wine.
Affinity eksplisit game dihormati. Nama berubah/affinity eksplisit memulihkan
penempatan dan priority; kegagalan syscall dicatat dan dapat dicoba kembali.

Untuk mengembalikan binary baseline **short trace v1** persis, salin folder
`switch` dari `rollback` ke root SD. Ini mengganti NRO dengan baseline dan
menonaktifkan flag eksperimen; DLL diagnostik tetap sama. Preset dan save game
tidak ditimpa. Rollback ini bukan kembali ke build v3.2 sebelum short trace.

Pemilihan worker berdasarkan nama, core 3 / priority 63, dan penghormatan
affinity mengadaptasi kode/desain
[Autorun commit c2268252](https://github.com/autorunhq/autorun/blob/c2268252a28abb5977fec8ea385b43f0e9519a5f/horizon-wine/source/thread_profile.c).
Pemisahan metadata, batas `dxvk-cs`, pemeriksaan capability/readback, logging,
rollback kegagalan dan integrasi port FEX Switch dikerjakan proyek FEXTendo.
FEX tetap FEX-Emu. Rincian kredit ada di `THIRD_PARTY.md`.

Paket menyertakan hash source/binary dan hasil tes di `manifest.json` serta
`evidence`: policy C dengan ASan/UBSan dan injeksi kegagalan; jalur nama UTF-16,
affinity dan balancer pada ELF ARM64 hasil link; serta regresi runtime dan
analyzer. Kelulusan tes host belum mengukur manfaat atau risiko performa di
Switch. Source default eksperimen OFF; file ON di paket mengaktifkan trial.
