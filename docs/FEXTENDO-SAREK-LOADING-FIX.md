# Sarek 1.13.0 — perbaikan loading 1 FPS

Paket `pes13-fextendo-sarek-loading-fix-v2.zip` untuk instalasi Sarek v1
yang sudah terpasang. Salin folder `switch/` ke root SD ketika aplikasi
tertutup. Paket hanya mengganti:

```text
switch/pes13-fex/drive_c/PES13/dxvk.conf
switch/pes13-fex/launcher/presets/dxvk.conf
```

Perubahan perilaku satu opsi: **`d3d9.maxFrameRate = -1` → `0`**.
VSync tetap ON (`d3d9.presentInterval = 1`), dyasync tetap aktif, kedua
pool compiler masing-masing satu worker. FEX disk cache tetap OFF.
Tidak perlu mengganti NRO/DLL, forwarder, save, atau menghapus cache.

Jika sudah rollback ke DXVK 3.1.1, gunakan paket lengkap
`pes13-fextendo-sarek-1.13.0-v2.zip`, bukan patch config kecil ini.
Paket lengkap v2 juga sudah memperbaiki config `control-none/`;
jangan menimpa perbaikan dengan config dari paket v1.

## Temuan log

Capture `fex-runtime.log`, 326.261 byte, SHA-256
`83a8a6f8c85d39cbfc801ca124fa53d3116a11e3e295911ee1620e5411922d37`.
Snapshot dan hasil analyzer:
`local/fex3/review-sarek-83a8a6f8c8/`.

- Baris 325: DXVK-Sarek v1.13.0. Baris 339: config efektif
  `d3d9.maxFrameRate = -1`.
- Cache state dibaca (7 entry), dyasync satu worker aktif; disk cache FEX
  OFF dan helper `dxvk-cs` berhasil masuk core 3.
- Progress 45→55→65 detik mencatat frame 40→50→60. Pada batch 45 detik,
  interval masuk Present rata-rata **1.000,016 ms**, sedangkan total native
  Present rata-rata **0,345 ms**. Tidak ada pembuatan pipeline grafis baru
  pada batch ini.
- Worker submit TID 16 meminta 10 sleep, total **8,285 detik** dalam batch
  tersebut; sleep yang terukur 8,285 detik juga. Artinya waktu tunggu
  memang diminta oleh pemanggil, bukan oversleep beberapa detik oleh kernel.
- Pola satu frame per detik berlanjut sampai akhir capture; 150 gap >50 ms
  tersimpan, tanpa dropped gap. Karena masih ada Present setiap detik,
  ini bukan bukti deadlock renderer total.

## Akar masalah dan tanggung jawab integrasi

Paket v1 mempertahankan `-1` dari config DXVK 3.1.1. Pada DXVK 3.1.1,
`D3D9SwapChainEx::UpdateTargetFrameRate` menangani `-1` sebagai pengecualian.
Pada source Sarek 1.13.0, pengecualian itu tidak ada: nilai diteruskan ke
`FpsLimiter::setTargetFrameRate`, lalu nilai negatif diubah menjadi nilai
absolut. Akibatnya `-1` menghasilkan **10.000.000 tick × 100 ns = 1 detik**.
`0` menghasilkan interval nol saat presentInterval 1, sehingga limiter
tersebut mati dan VSync tetap berlaku.

Komentar pada template `dxvk.conf` upstream Sarek masih menyebut `-1`
mematikan limiter, tetapi implementasinya berbeda. Pemeriksaan paket v1
yang mempertahankan semua nilai config lama melewatkan perbedaan ini.
Ini kesalahan kompatibilitas konfigurasi pada paket integrasi kami;
belum ada dasar untuk menyimpulkan dyasync gagal atau Sarek perlu dibuang.

Referensi source yang dipin:
[swapchain Sarek](https://github.com/pythonlover02/dxvk-sarek/blob/37f397e142b977a343e920dbc4c7bf7ed2c63a81/src/d3d9/d3d9_swapchain.cpp)
dan [limiter Sarek](https://github.com/pythonlover02/dxvk-sarek/blob/37f397e142b977a343e920dbc4c7bf7ed2c63a81/src/util/util_fps_limiter.cpp).

## Verifikasi dan tes berikutnya

Regression test menjalankan metode C++ upstream yang diekstrak dari source
rilis yang dipin, dengan ASan/UBSan. Test mereproduksi interval satu detik
dari `-1`, memastikan `0` menonaktifkan jalur delay pada presentInterval 0/1,
dan memeriksa interval 2, limit positif serta environment override.
Ini tes host dengan stub timer/presenter, bukan eksekusi DLL/GPU di Switch.

Tes ulang masuk home terlebih dahulu. Log berikutnya harus menyebut
`d3d9.maxFrameRate = 0`. Jika menu sudah masuk normal, lanjutkan kickoff,
umpan cepat, shoot dan bola lambung untuk menilai tujuan awal trial.
Simpan log sebelum membuka launcher lagi.

Jika setelah config efektif `0` masih macet, berikutnya isolasi dyasync
dengan `control-none/` dari paket **v2**. Alternatif DXVK-Async 1.10.3 milik
Sporif memang tersedia, tetapi belum dipasang karena sekarang ada penyebab
konkret yang dapat diperbaiki tanpa mengganti renderer.

Untuk rollback, paket lengkap v2 menyediakan `rollback-dxvk311/switch/`.
Patch config ini belum diuji di Switch; konfirmasi hilangnya gejala dan
performa gameplay tetap memerlukan log perangkat berikutnya.
