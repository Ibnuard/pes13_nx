# PES13: eksperimen address space 39-bit

Paket ini adalah **probe memori/JIT**, belum runtime PES13 39-bit yang bisa
dipakai bermain. Tujuannya menguji penghalang pertama memakai kernel Switch
yang sebenarnya. Tidak ada game, DLL, save, pengaturan, atau NRO produksi
yang ditimpa. Tidak ada perubahan pada proyek F1.

## Cara tes

1. Salin folder `switch` ke root SD.
2. Instal dua NSP di `forwarders` menggunakan installer homebrew yang biasa
   dipakai. Keduanya punya Title ID sendiri, berbeda dari FEXTendo produksi.
3. Dari HOME buka **PES13 32-bit Probe**. Tunggu baris `[SUMMARY]`, lalu tekan
   `+` untuk keluar.
4. Dari HOME buka **PES13 39-bit Probe**. Tunggu ringkasan, lalu keluar.
5. Kirim dua file berikut:

   ```text
   sdmc:/switch/pes13-as39-probe/as32-probe.log
   sdmc:/switch/pes13-as39-probe/as39-probe.log
   ```

Probe selesai otomatis; tidak perlu membuka pertandingan. Clock stock cukup.
NRO yang sama dipakai kedua forwarder agar perbedaannya hanya mode alamat.
Menjalankan NRO dari hbmenu dapat menghasilkan mode lain; hasil tersebut
ditandai `INCONCLUSIVE`, bukan dianggap hasil tes 39-bit.

## Yang diperiksa

- Mode dan rentang alamat dari `svcGetInfo`, bukan nama NSP.
- Header EXE PES13 yang ditemukan di lokasi standar, dibaca saja.
- Satu halaman di `0x00400000`, memakai `svcMapProcessCodeMemory` seperti Wine.
- Seluruh rentang image PES referensi, jika tes satu halaman berhasil.
- Pemetaan ukuran image yang sama di `0x10000000` sebagai kontrol guest yang
  bisa direlokasi.
- Pemetaan native dan eksekusi fungsi ARM64 kecil.
- Adapter JIT FEX yang asli dari proyek: RW/RX terpisah, eksekusi, perubahan
  kode melalui RW, flush cache, eksekusi kembali, lalu pelepasan memori.

Jika pemetaan atau perubahan izin gagal, probe tidak mengakses alamat itu.
Jika unmap gagal, backing ditahan sampai proses keluar, tidak dikembalikan
ke allocator selama masih mungkin dipakai. Setiap tahap menulis result code
dan flush log. Hanya log di direktori probe yang ditulis dan dirotasi.

## Membaca hasil

- `MAPPING-PASS`: prasyarat pemetaan dan JIT lolos untuk mode yang tercatat.
  Ini **bukan** bukti Wine/PES berhasil berjalan.
- `BLOCKED`: alamat tetap PES ditolak, sedangkan kontrol alamat yang lebih
  tinggi dan JIT berhasil. Mengubah forwarder saja tidak cukup.
- `INCONCLUSIVE`: lihat tahap yang gagal, misalnya permission/handle,
  rentang sudah dipakai loader, backing allocation, atau pelepasan gagal.

Angka budget/used merupakan kondisi proses probe. Loader bisa lebih dahulu
memesan heap besar; jangan menafsirkannya sebagai pemakaian RAM pertandingan.
Lebar alamat virtual juga tidak menambah kapasitas RAM fisik Switch.

## Temuan kode sebelum tes perangkat

EXE PES lokal (`pes2013.exe` dan `pes2013_100.exe`) memakai image base
`0x00400000`, image size `0x0189a000`, flag `RELOCS_STRIPPED`, dan tidak memiliki
direktori base relocations. F1 2013 lokal memiliki direktori relokasi. Overlay
39-bit F1 mempertahankan host floor dan membiarkan loader merelokasi EXE.

Log/proyek F1 yang diperiksa memakai floor `0x08000000` pada mode 39-bit.
Kernel memvalidasi tujuan AliasCode terhadap region yang diizinkan; sebuah
reservasi software `virtmemAddReservation` bukan bukti halaman bisa dipetakan.
Lihat [validasi MapCodeMemory Atmosphere](https://github.com/Atmosphere-NX/Atmosphere/blob/master/libraries/libmesosphere/source/kern_k_page_table_base.cpp)
dan [aturan PE RELOCS_STRIPPED Microsoft](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format#characteristics).

Jika floor tersebut menolak alamat PES, jalur berikutnya memerlukan solusi
untuk alamat guest tetap: relokasi yang benar-benar lengkap, atau penerjemahan
alamat yang konsisten di FEX **dan** Wine/WoW64. Mengganti image base atau
mematikan pemeriksaan launcher saja tidak menyediakan solusi tersebut.

## Build dan verifikasi

Di WSL dengan toolchain devkitPro proyek:

```sh
python3 tools/build-as39-probe.py \
  --work /home/blekjek/pes13-build/as39-probe-v1 \
  --keys /path/to/local/prod.keys \
  --packer /path/to/pinned/hacbrewpack
```

Builder memakai snapshot loader yang sudah diverifikasi di
`local/production-input-fix/approved`, memeriksa hash sumber, dan menghasilkan
direktori biasa tanpa ZIP. Output harus kosong untuk mencegah payload lama
tercampur. Keyset hanya dipakai saat packing; tidak masuk ke paket atau log.

`build.json` merekam hash NRO/ELF/NSP, NPDM hasil kompilasi, kemampuan syscall,
dan pemeriksaan byte payload di dalam NSP. Source dan lisensi disertakan.
`verification.json`, bila disertakan, merangkum pemeriksaan host tambahan.
Status tes perangkat tetap **belum diuji** sampai log dari Switch diterima.

## Hasil perangkat: probe 0.1.0

Log `as32-probe.log` dan `as39-probe.log` dari user sudah membuktikan:

| Pemeriksaan | 32-bit no-alias | 39-bit |
| --- | --- | --- |
| Budget proses yang dilaporkan | 2048 MiB | 3285 MiB |
| ASLR/AliasCode floor | `0x00200000` | `0x08000000` |
| Halaman PES di `0x00400000` | PASS | Ditolak, `0xd401` |
| Seluruh rentang image PES di alamat tetap | PASS | Tidak dijalankan setelah penolakan halaman |
| Kontrol image di `0x10000000` | PASS | PASS |
| JIT FEX execute/backpatch | PASS | PASS, RX `0x707cefd000` di atas 4 GiB |
| Cleanup | Berhasil | Berhasil |

Header EXE di SD juga menunjukkan `relocs_stripped=1`, `reloc_rva=0`,
`reloc_bytes=0`. Hasil utama: **pemetaan langsung EXE PES saat ini terhalang
pada host 39-bit**, sementara adapter JIT native dapat memakai alamat tinggi.
Ini belum menguji Wine, seluruh FEXCore, game, atau performa pertandingan pada
mode 39-bit. Tambahan budget yang terlihat adalah 1237 MiB pada dua konfigurasi
tes ini, bukan janji budget untuk semua forwarder/perangkat.

Probe 0.1.0 memiliki kekeliruan pada tes native RX tambahan: ia mengubah mapping
AliasCode menjadi RW lalu mencoba RX pada mapping yang sama. Kernel mengubah
state halaman RW menjadi AliasCodeData, yang tidak lagi memenuhi pemeriksaan
FlagCode pada syscall tersebut. Akibatnya tes tambahan gagal `0xd401` pada
**kedua** mode dan ringkasan otomatis menjadi `INCONCLUSIVE`. Kegagalan ini
terpisah dari penolakan alamat tetap PES, dan JIT CodeMemory FEX tetap PASS.
Lihat [SetProcessMemoryPermission](https://github.com/Atmosphere-NX/Atmosphere/blob/master/libraries/libmesosphere/source/kern_k_page_table_base.cpp)
dan [flags AliasCode/AliasCodeData](https://github.com/Atmosphere-NX/Atmosphere/blob/master/libraries/libmesosphere/include/mesosphere/kern_k_memory_block.hpp).

Source 0.1.1 memperbaiki tes RX dengan menyiapkan instruksi di backing terlebih
dahulu lalu langsung memetakan RX. Model uji kini menerapkan perubahan state
kernel tersebut dan mereproduksi kegagalan ELF 0.1.0. Perbaikan ini hanya untuk
probe. Data perangkat 0.1.0 sudah cukup untuk kesimpulan alamat PES; user tidak
perlu mengulang tes hanya untuk memperoleh tulisan ringkasan yang berbeda.

Langkah port berikutnya harus menyelesaikan alamat guest tetap. Selain
penerjemahan alamat atau relokasi lengkap, audit berikutnya menemukan patch
kernel/loader Autorun yang menyediakan low window pada host 39-bit. Ini dapat
mengatasi penolakan `0x00400000` tanpa bias software untuk setiap akses guest.
Lihat [audit low window dan batas RAM fisiknya](AS39-LOW-WINDOW.md). Tidak ada
jalur tersebut yang sudah diimplementasikan oleh probe ini.
