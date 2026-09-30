# FEXTendo: inline predecessor storage

**Status: direvert pada 29 September 2026.** Pengguna melaporkan penurunan
performa setelah eksperimen DFE. Integrasi DFE telah dilepas dari builder;
DLL kembali ke decoder inline-64 sebelum eksperimen, SHA256
`17dcf3e78371a717a9c41da5bffa4d6a5755d6479afa0a8ade12abcc7639ad23`.
Dokumen di bawah merupakan catatan eksperimen yang telah ditarik.

Eksperimen `dfe-predecessors-v1` melanjutkan DLL **decoder inline-64** yang
sudah dicoba. Targetnya mengurangi alokasi sementara saat kompilasi pertama,
termasuk ketika FEX disk cache dimatikan. Ini kandidat optimasi lanjutan;
pengurangan stutter di Switch belum diukur untuk build ini.

## Instalasi

Tutup FEXTendo sepenuhnya. Salin folder `switch/` di paket ke root SD.
Satu-satunya file yang diganti:

```text
switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll
```

NRO, NSP, konfigurasi, renderer, cache dan save mengikuti instalasi yang sudah
ada. Paket juga bisa dipasangkan dengan NRO production tanpa log; DLL ini
menggunakan callback logger dari NRO sehingga tidak mengaktifkan kembali
logging yang sudah dimatikan di NRO tersebut.

Dengan NRO diagnostik, identitas kandidat tercatat sebagai:

```text
[FEX3-DECODE] v1 inline worklists=64; ordered-tree overflow; no persistent cache required
[FEX3-DFE] v1 inline predecessors=2; ordered vector overflow; flag optimization unchanged
```

Untuk kembali ke eksperimen inline-64 sebelumnya, tutup aplikasi dan salin
isi `rollback/switch/` ke root SD. Rollback mengembalikan DLL dengan SHA256
`17dcf3e78371a717a9c41da5bffa4d6a5755d6479afa0a8ade12abcc7639ad23`.

## Perubahan

Pass `RedundantFlagCalculationElimination` membangun graf aliran kontrol
sementara setiap kali dijalankan. Setiap blok sebelumnya memanggil
`Predecessors.reserve(2)` pada sebuah vector, sehingga mengalokasikan heap
bahkan untuk daftar predecessor yang kosong.

Kandidat menyimpan dua ID predecessor pertama langsung di objek. Daftar
dengan lebih dari dua entri berpindah ke vector memakai allocator FEX yang
sama. Jumlah entri tetap tidak dibatasi. Duplikat dan urutan penyisipan
dipertahankan karena keduanya dapat memengaruhi urutan pemrosesan worklist.
Algoritma penghapusan flag, aturan parity dan urutan worklist memakai kode
yang sama; perubahan terbatas pada penyimpanan daftar ini.

Satu alokasi awal dan pembebasannya dihindari untuk setiap daftar dengan
0–2 predecessor. Ini pengurangan pekerjaan pada struktur data yang ditarget,
bukan janji kenaikan FPS atau persentase pengurangan semua alokasi compiler.
Daftar yang lebih besar tetap menggunakan heap. Objek per blok bertambah
24 byte pada layout 64-bit yang diperiksa (sekitar 3 KiB untuk 128 blok).

## Pemeriksaan dan batas hasil

Paket menyertakan pemeriksaan container dengan sanitizer, kesetaraan urutan
pada graf sintetis, pengecekan bahwa source pass hanya berubah pada include
dan tipe daftar, serta pemeriksaan kontrak heap/profile, SMC dan penghitung
JIT pada binary ARM64. Pemeriksaan graf tidak menjalankan seluruh optimizer
IR maupun permainan; uji kompatibilitas dan stutter pada Switch tetap perlu.
Hasil lengkap ada di `evidence/checks/`.

NRO production menghilangkan log, tetapi kerja kompilasi pertama dan
pembuatan pipeline grafis masih ada. Review capture eksperimen sebelumnya
tersedia di `source/docs/FEXTENDO-DECODE-DEVICE-REVIEW.md`. Saat membandingkan
kandidat ini, pertahankan pilihan renderer, preset, JIT128, clock dan cache
yang sedang digunakan agar efek perubahan DLL lebih mudah dinilai.

FEX tetap proyek FEX-Emu; perubahan penyimpanan ini merupakan adaptasi port
Horizon. Asal komponen dan kontribusi ada di `FEX-PORT-PROVENANCE.md`.
