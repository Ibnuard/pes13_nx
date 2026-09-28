# Satu paket: emitter FEX + VSync off + settings 540p

Checkpoint `8939d56489cea2731a62c2760445e068dfbe556d` sudah dipush ke
`origin/fex-core-fast` sebelum perubahan ini. Paket `pes13-fex3-emit-vsync.zip`
menggabungkan semua perubahan berikut dalam satu pemasangan di atas build
`dispatch-cache` yang sudah dites pengguna:

- `libwow64fex.dll`: simpan alamat writable sekali per buffer kompilasi.
- `drive_c/PES13/dxvk.conf`: `d3d9.presentInterval = 0`.
- Ketiga `settings.dat`: flag `0289` → `0288` (VSync mati), CRC dihitung ulang.
  Resolusi tetap **960×540, 16:9**, frame skipping mati, XInput aktif.

Settings diterapkan di `drive_c/KONAMI/Pro Evolution Soccer 2013`,
`drive_c/users/steamuser/Documents/KONAMI/Pro Evolution Soccer 2013`, dan
`drive_c/PES13`. Preset controller/aspect mengikuti paket 540p sebelumnya.
Antrean dua frame, FEX 500 instruksi, dispatcher L1, Wine, NRO dan clock
mengikuti checkpoint. Paket ini belum dites gameplay di Switch; kickoff dan
stutter belum dinyatakan selesai.

## Perbaikan tambahan berdasarkan log dan kode

Log terbaru menunjukkan kompilasi FEX masih memakan waktu: 39.211 kompilasi,
69,51 detik kumulatif antar-panggilan, puncak 91,59 ms. Angka kumulatif bukan
waktu freeze total dan tidak membuktikan setiap jeda berasal dari JIT.

Audit menemukan setiap penulisan instruksi ARM64 melalui `Buffer::dcn`
memanggil pencari alias RX/RW. Untuk temporary buffer JIT biasa, pencarian
ini dapat memeriksa 64 slot lalu memanggil runtime native meskipun alamat
akhirnya sama. Sekarang `SetBuffer` menyimpan alamat writable untuk seluruh
rentang milik buffer, dan setiap store menggunakan alamat tersimpan selama
masih di dalam rentang tersebut. Alamat cursor/relokasi tetap menggunakan
view RX; akses di luar rentang tetap lewat pemeriksaan lama. Saat buffer
diganti atau dilepas, view ikut di-reset. Tidak ada cache alamat global baru.

Perubahan ini umum pada emitter FEX, tidak memakai alamat atau trigger khusus
PES, sehingga dapat dipakai game lain melalui runtime yang sama. Perubahan
profil `settings.dat` tetap khusus PES.

Validasi build baru:

- ASan/UBSan: 4.096 store cukup satu resolusi alamat; view RX/RW, buffer biasa,
  alignment, string, batas buffer, overflow dan penggantian buffer lolos.
- Eksekusi constructor dispatcher ARM64 sebelum/sesudah di Unicorn:
  panggilan host alias **2.124 → 157**. Instruksi/data yang dihasilkan identik
  setelah mengecualikan empat pointer literal yang berubah karena relinking.
  Ini pengukuran jumlah panggilan dalam uji emitter, **bukan persentase FPS**.
- 1.848 kasus dispatcher, invalidation/erase, single-step dan L2 opsional lolos.
- Emisi physical counter, deteksi modifikasi kode, timing JIT, serta unwind
  FEX/Wine ke handler guest lolos. Import/export PE tetap cocok.
- Ketiga settings identik, flag/resolusi/CRC diverifikasi, termasuk CRC dengan
  implementasi independen. ZIP dan folder hasil dibaca ulang dan dicocokkan.

Receipt dan source pendukung ada di `evidence/` dan `source/` dalam paket.

## VSync

DXVK 3.1.1 menerapkan override present interval setelah permintaan aplikasi;
interval 0 memilih present tanpa VSync. Presenter memilih IMMEDIATE jika
tersedia dan `tearFree` bukan True. Referensi:
[opsi](https://github.com/doitsujin/dxvk/blob/v3.1.1/dxvk.conf#L178),
[override D3D9](https://github.com/doitsujin/dxvk/blob/v3.1.1/src/d3d9/d3d9_swapchain.cpp#L118),
[presenter](https://github.com/doitsujin/dxvk/blob/v3.1.1/src/dxvk/dxvk_presenter.cpp#L1045).

ELF runtime yang sesuai receipt NRO sudah mengiklankan FIFO dan IMMEDIATE;
jalur IMMEDIATE memilih interval 0 pada `nwindowSetSwapInterval`. Swapchain
tetap tiga gambar. Pemeriksaan binary ini bukan pengukuran compositor Switch.
VSync mati bisa mengubah pacing/menimbulkan tearing; efeknya perlu dilihat
bersama kecepatan simulasi, bukan hanya jumlah Present.

## Instalasi

1. Tutup PES lewat HOME → X. Simpan log dan backup DLL/config/settings saat ini
   jika pernah dikustomisasi setelah build checkpoint.
2. Salin **folder `switch`** dari paket ke root SD, timpa file yang sama pada
   instalasi `dispatch-cache` terakhir. Ini satu paket gabungan, bukan instalasi
   game/runtime lengkap; tidak perlu memasang eksperimen lain lebih dulu.
3. Gunakan clock, tim, stadion dan kamera yang sama; pertahankan cache yang
   ada untuk perbandingan awal.
4. Log berikutnya seharusnya menampilkan:
   - `[FEX3-EMIT] v1 cached writable buffer`
   - `[FEX3-GAME] flags=0288 vsync=0 settings_skip=0`
   - `d3d9.presentInterval = 0`, `d3d9.maxFrameLatency = 2`
   - `VK_PRESENT_MODE_IMMEDIATE_KHR`
5. Periksa kickoff pertama, shooting/belok pertama, kelancaran mid game,
   kecepatan simulasi dan tearing. Simpan log sebelum launch berikutnya.

Jika flag game masih `0289`, settings aktif belum tertimpa. Jika DXVK masih
FIFO, periksa konfigurasi efektif/mode fallback. Jika perlu kembali, tutup
PES lalu salin **folder `switch` di dalam `rollback`** ke root SD. Rollback
mengembalikan kelima file ke preset checkpoint: DLL dispatch-cache, VSync on,
antrean dua, settings 960×540. Untuk kustomisasi sendiri gunakan backup sendiri.

## Pembacaan log dan cache

Log dasar: 283.253 byte, SHA256
`e7945dd2f0be655381781153cf3b12ca8ed688e4e9569ab835945d03910ae0a0`.
Pada sekitar 281 detik dispatch_compile tercatat 811.072 panggilan, sementara
run sebelumnya sekitar 280 detik tercatat 17.293.185. Pertandingan tidak
identik; ini mendukung pengurangan overhead, bukan pembandingan FPS terkontrol.
Pipeline GPU masih sempat mencapai sekitar 147,7 ms. Window akhir mencatat
sebagian gap 50–100 ms tanpa aktivitas pipeline baru, jadi shader bukan satu-
satunya kandidat. Tidak ada marker exception pada log ini. UI yang tetap
bergerak ketika 3D berhenti belum cukup untuk menentukan penyebab kickoff.

Optimasi dispatcher/L1 dan emitter berlaku sejak launch, termasuk untuk
pengguna baru. Tetapi kode hasil translasi FEX baru tersedia setelah jalurnya
dikompilasi. Disk cache FEX belum diaktifkan; cache kode proses dibentuk ulang
ketika PES ditutup penuh.

Cache shader DXVK/driver dapat tersimpan di SD. Run ini membaca **434 shader,
2,1 MB** dari cache DXVK. Pengguna dengan cache kosong masih dapat menghadapi
pekerjaan shader tambahan. Jadi peningkatan berasal dari optimasi runtime dan
terbantu cache; belum ada jaminan instalasi pertama langsung tanpa stutter.

Jumlah Present mendekati 60 per detik tidak membuktikan 60 frame 3D unik atau
simulasi 60 FPS. Pengujian berikutnya diperlukan untuk melihat dampak gabungan
VSync off dan emitter pada perangkat; tidak bisa mengatribusikan perubahan
hasil ke salah satu komponen saja dari satu perbandingan ini.
