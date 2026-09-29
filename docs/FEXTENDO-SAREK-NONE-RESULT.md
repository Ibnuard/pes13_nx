# Sarek 1.13.0 / none — berhasil bermain, pipeline masih mahal

Snapshot perangkat: `local/fex3/review-sarek-none-88a97a52e3/device.log`,
883.045 byte, SHA-256
`88a97a52e31399669e14cca8bbec732a89f6693b8e277fce6f1c2a0548cef763`.
Analyzer dan ringkasan terstruktur ada di direktori snapshot yang sama.

## Hasil

- Config efektif `d3d9.maxFrameRate = 0`; log mencatat
  `DXVK: Shader compilation method: none` dan satu worker compiler.
- Tidak ada `std::bad_alloc` atau `[EXIT]` dalam capture. Progress terakhir
  pada 316 detik runtime mencapai 14.022 frame, heap bebas sekitar 517 MB.
  Sukses melewati loading konsisten dengan laporan pengguna.
- 216 panggilan native pembuatan pipeline grafis yang dibatch menghabiskan
  total 19,079198 detik wall time. Ada **85 panggilan >50 ms**, dengan peak
  **645,732 ms**. Sebagai contoh, batch progress 65 detik mencatat
  28 pipeline / total 4,380978 detik / 17 panggilan >50 ms.
- Tersimpan 295 gap Present >50 ms, dengan 19 gap dropped. Gap terbesar
  4.668,476 ms berakhir sekitar T+00:52,376. Gap besar juga dapat berasal
  dari loading/pergantian scene; tidak tersedia timestamp scene pengguna
  untuk menetapkan semuanya sebagai stutter gameplay.
- Counter akhir FEX `compile_code` mencatat 35,641548 detik wall time
  lintas thread, peak 61,269 ms. Jadi pekerjaan guest/JIT juga tetap ada;
  total ini tidak boleh dijumlahkan ke pipeline sebagai waktu freeze game.

## Arti kontrol none

Mode `none` menonaktifkan jalur async/dyasync Sarek. Pipeline yang belum
tersedia dapat dikompilasi di jalur yang sedang menggambar, tetapi state
cache dan worker kompilasi tetap aktif. Jadi tidak semua pekerjaan shader
menjadi sinkron, dan tidak semua stutter otomatis berasal dari shader.

Menghilangnya abort saat none mendukung keterlibatan dyasync atau perubahan
kebutuhan alokasinya. Satu run tidak mengidentifikasi alokasi yang gagal
pada capture sebelumnya. Perbedaan durasi dan scene juga tidak mendukung
perbandingan persentase FPS dengan renderer sebelumnya.

Sesuai permintaan pengguna, trial berikutnya memakai **DXVK-GPLAsync
2.7.1-1 Ph42oN**, dengan async eksplisit. Lihat
[paket dan langkah tes](FEXTENDO-GPLASYNC-2.7.1-TRIAL.md).
