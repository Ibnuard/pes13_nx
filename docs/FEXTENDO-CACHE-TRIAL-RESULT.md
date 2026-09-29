# Hasil trial FEX disk cache

Dua capture pengguna telah disalin ke direktori immutable berdasarkan hash:

| Capture | SHA-256 | Ukuran | T+ laporan short-trace terakhir |
| --- | --- | ---: | ---: |
| `fex-runtime-cache-1.log` | `3d76f124bf7ac02d980f49afd701568a9ddc008796d266de4670f35eafd77233` | 1.763.582 byte | 346,843 s |
| `fex-runtime-reuse.log` | `2c1fa451c72a52256383676850766fcb5aaa52008a426df998198cebc5e4dfa7` | 1.362.659 byte | 205,276 s |

Keduanya memakai `pes13-fextendo-dxvk-core3-v1`, `fex_diskcache=1`,
overlay aktif dan `dxvk-cs` berhasil ditempatkan pada core 3, mask 8,
priority 63. Tidak ditemukan timeout `RtlpWaitForCriticalSection`.
Baris konfigurasi `[FEX3-HANG] ... capture after 3s` bukan bukti hang capture
benar-benar terjadi.

## Temuan

Pengguna melaporkan stutter tetap terasa setelah aplikasi dibuka ulang.
Log mendukung bahwa pekerjaan kompilasi dan gap frame masih terjadi, tetapi
tidak menyediakan cache-hit counter FEX. Folder database cache tidak ikut
dikirim. Karena itu keberhasilan pembacaan/penulisan/reuse disk cache belum
dapat dikonfirmasi hanya dari `requested=1`.

Untuk menghindari membandingkan seluruh sesi yang durasinya berbeda, berikut
rentang T+100–200 detik pada keduanya. Ini rentang waktu yang sama, **bukan
jaminan adegan yang sama**. JIT hanya dihitung dari window kompilasi yang
seluruhnya berada dalam rentang tersebut, pada thread bernama `gameThread`.

| Pengamatan T+01:40–03:20 | Pengisian | Buka ulang |
| --- | ---: | ---: |
| Window JIT lengkap | 22 | 21 |
| Panggilan `CompileCode` | 5.753 | 5.432 |
| Total wall time `CompileCode` | 11,720 s | 11,458 s |
| Panggilan JIT terlama dalam window terpilih | 43,004 ms | 56,075 ms |
| Gap >50 ms yang tersimpan | 100 | 109 |
| Gap terbesar pada rentang ini | 284,667 ms, T+03:03,673 | 301,771 ms, T+02:52,605 |

Total JIT tersebut bukan satu freeze sepanjang 11 detik dan bukan waktu CPU
murni: wall time termasuk scheduling. Source menempatkan timer
`CompileCode` setelah jalur disk-cache lookup/load pada `CompileBlock`;
counter ini tetap bukan counter cache-hit atau jumlah alamat kode unik.

Kedua sesi masih membaca cache **DXVK 3.1.1** yang sama: 498 shader, 2,3 MB.
Sepanjang capture pengisian ada 967 panggilan pipeline grafis (4,662 s total,
7 panggilan >50 ms); capture reuse 896 (5,163 s total, 2 >50 ms). Angka seluruh
sesi ini tidak boleh dipakai menghitung peningkatan/penurunan performa karena
durasi dan adegannya berbeda. Cache shader yang ditemukan belum berarti
semua pipeline sudah siap.

Observer gap kehilangan 89/97 record, sedangkan short-trace kehilangan 6/3
record; statistik yang tersimpan tidak lengkap. Tidak ada timestamp kejadian
baru dari pengguna untuk menamai gap tertentu sebagai kickoff atau shoot.

## Keputusan

Matikan trial disk cache FEX pada eksperimen berikutnya (`fex_diskcache=0`),
karena manfaat pada perangkat belum terlihat. Ini tidak membuktikan fitur
tersebut menyebabkan regresi; untuk klaim itu diperlukan kontrol OFF dengan
adegan yang sama. Tidak perlu menghapus database atau membuang implementasi
opt-in dari NRO. OFF menghentikan lookup/store disk cache, sementara JIT dan
cache kode dalam proses tetap bekerja.

Lanjutkan eksperimen renderer terpisah dengan
[DXVK-Sarek 1.13.0](FEXTENDO-SAREK-TRIAL.md). FEX tetap OFF baik pada Sarek
maupun rollback DXVK 3.1.1. Bukti JSON lengkap berada di
`local/fex3/sarek-trial/cache-comparison.json`; sumber per-capture dan hasil
analyzer ada di `local/fex3/review-cache-<10-digit-hash>/`.
