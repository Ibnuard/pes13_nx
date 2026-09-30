# Production v1 dengan perbaikan launching dan rollback DFE

Paket ini mengikuti pilihan pengguna: **revert eksperimen DFE**, dan gunakan
**source production v1** untuk NRO dengan hanya perbaikan crash launching.

Tutup FEXTendo sepenuhnya, lalu salin folder `switch/` ke root SD. Ada dua
file yang diganti:

- `switch/pes13-fex/pes13-fex.nro`: build ulang dari arsip production v1,
  dengan perbaikan inisialisasi channel debug Wine.
- `switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll`: DLL decoder
  inline-64 asli sebelum eksperimen DFE. SHA256:
  `17dcf3e78371a717a9c41da5bffa4d6a5755d6479afa0a8ade12abcc7639ad23`.

NRO tetap tanpa log. Ikon, versi tampilan 0.3.7, preset, batas JIT, renderer,
scheduler dan pengaturan cache mengikuti production v1. Forwarder yang
sudah ada tetap menunjuk ke path NRO yang sama. Cache dan save tidak perlu
dihapus. Mengganti NRO saja tidak membatalkan DFE apabila DLL eksperimennya
sudah disalin ke SD; gunakan kedua file di atas untuk rollback lengkap.

## Dasar build yang diperiksa

Source project diekstrak dari `pes13-fextendo-production-no-log-v1.zip`, SHA256
`99bd297a20cb3aaaea867ab43d554dd2b6d55117211c0c3d3b36106e9247de1e`.
Semua input yang tercatat dalam receipt v1 diverifikasi sebelum build.
Helper/header bersama yang tidak disertakan arsip lama dipulihkan dari
commit sebelum production v1, `ab1d9046c820ac13875d31e2347f12913731d6ea`;
hash file tersebut dicatat dalam `baseline-regression.json`.

Setelah menormalkan lokasi include absolut ke direktori project lama,
satu-satunya file Wine dengan perubahan kode adalah
`dlls/ntdll/unix/debug.c`. `init_options()` langsung menonaktifkan opsi debug,
dan `__wine_dbg_get_channel_flags()` mengembalikan nol. Ini menghindari
pembacaan `main_argv[1]` ketika `main_argv` belum diisi oleh launcher Horizon.
Kode `runtime.c`, seluruh adapter FEX, opsi build, library native dan payload
Wine PE sama dengan production v1. Identitas marker runtime v1 juga dipertahankan.

Hasil rebuild dari source arsip v1 identik byte demi byte dengan NRO launchfix
v2 yang sebelumnya diberikan (SHA256
`fd0e0dbb047289421d3d8a03e05d04cfcfda1e38999cbcbb1e90e7332434d463`).
Eksperimen DFE berada di DLL FEX terpisah; source adapter yang tercatat pada
receipt NRO v2 tidak seluruhnya dikompilasi ke NRO. Karena itu perubahan
binary untuk rollback performa pada paket ini adalah pengembalian DLL.

Source aktif dan snapshot FEX sudah dikembalikan ke patch set inline-64.
Kode eksperimen DFE diarsipkan di paket eksperimen lama; pengguna melaporkan
penurunan performa sehingga perubahan tersebut ditarik.

## Verifikasi dan batas hasil

Paket menyertakan bukti kesamaan baseline, tes crash startup ARM64, logging
nonaktif, resume thread dan perbandingan penempatan core. DLL rollback
merupakan file asli yang diverifikasi hash; bukan hasil build eksperimen baru.
Laporan tes launchfix digunakan kembali setelah ELF dan NRO hasil rebuild
terbukti identik byte demi byte dengan binary yang telah diuji.
Build ini belum diuji launching penuh pada Switch. Hasil performa setelah
rollback harus dinilai dari permainan di perangkat pengguna.

Rebuild NRO menggunakan
`tools/build-fextendo-production-v1-launchfix.py --build-root <cache-build>`.
Script menolak menimpa direktori hasil yang sudah ada. Bukti build dan patch
startup disimpan di `local/fex3/production-v1-launchfix/`.
