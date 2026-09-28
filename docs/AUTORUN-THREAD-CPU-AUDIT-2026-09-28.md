# Autorun: kandidat optimasi thread/CPU untuk PES13

Audit 28 September 2026 terhadap FEXTendo v2, checkpoint lokal
`7f08984c79555db8b7f33f611334f6ff5becf486` pada branch `fex-core-fast`.
Checkpoint tersebut sudah di-push. Audit ini hanya menambah dokumentasi;
NRO, DLL, ZIP, preset dan source runtime tetap sama.

**Ada teknik yang layak diuji, terutama penempatan worker grafis berdasarkan
perannya dan jalur sinkronisasi langsung. Belum ada bukti bahwa teknik itu
menjelaskan PES13 yang lancar di video.** Pengguna melaporkan CPU, RAM dan GPU
semuanya di-OC maksimum. URL video, angka MHz, perangkat, versi Autorun,
backend, resolusi dan preset belum diketahui. Ketiga clock yang berubah
bersama tidak memisahkan bottleneck CPU, GPU dan bandwidth memori.

## Revisi dan bukti

- [Source Autorun yang diperiksa](https://github.com/autorunhq/autorun/tree/c2268252a28abb5977fec8ea385b43f0e9519a5f):
  `c2268252a28abb5977fec8ea385b43f0e9519a5f`, timestamp commit
  2026-09-28 11:50:48 UTC. Folder runtime sudah bernama `horizon-wine`.
- [Rilis terbaru saat pemeriksaan, Test Build 4](https://github.com/autorunhq/autorun/releases/tag/test-build-4):
  dipublikasikan 24 September, tag mengarah ke
  `9b7170505f9084fee0ffe1a237b08557a6ab2868`. Source `runtime.c`,
  `launcher_settings.h` dan `thread_profile.h` pada tag tersebut berbeda
  dari HEAD: tidak memuat pilihan FEX, `four_cores` dan `fast_sync` yang
  ditemukan pada HEAD. Binary ZIP rilis tidak diaudit. Jangan menganggap
  fitur HEAD otomatis ada dalam build di video.
- 71 file source HEAD yang diunduh cocok dengan SHA-1 Git blob pada tree
  commit yang dipin. Snapshot API, source, hash SHA-256 dan hasil tes berada
  di `local/autorun-audit/c2268252a28abb5977fec8ea385b43f0e9519a5f/`.
  `verified-sources.json` mencatat pemeriksaan tersebut. Folder lokal ini
  diabaikan Git.
- Build FEXTendo v2 belum dicoba pengguna. Log perangkat terakhir masih
  `pes13-fextendo-mem-audit`, bukan v2. SHA-256 log:
  `99c459c5ac19874b5ee366519f03cab7a276001399df4732831341f67bb7c447`.

## 1. Worker grafis khusus pada core keempat

Autorun mengenali nama `dxvk-cs`, `wined3d_cs` dan `vkd3d_queue`. Dengan
opsi **4-core support** aktif, worker tersebut dapat dipin ke **core 3**
(core keempat, bukan core urutan ketiga), prioritas **63**. Compositor native
juga masuk jalur ini. `dxvk-submit` dan thread game sembarang tidak termasuk.
Guest tetap melihat core 0–2; wrapper affinity membuang core 3 dari mask
thread biasa. Default opsi ini mati.

Syaratnya process memiliki izin mask core `0x8` dan priority 63. Source
forwarder menyiapkan capability tersebut. Thread dengan affinity eksplisit
tidak di-offload; kegagalan perubahan priority mencoba mengembalikan mask,
dan perubahan nama atau affinity dapat mengembalikan penempatan semula.

Sumber:
[pemilihan nama](https://github.com/autorunhq/autorun/blob/c2268252a28abb5977fec8ea385b43f0e9519a5f/horizon-wine/source/thread_profile.h#L17),
[offload dan pemulihan](https://github.com/autorunhq/autorun/blob/c2268252a28abb5977fec8ea385b43f0e9519a5f/horizon-wine/source/thread_profile.c#L100),
[capability forwarder](https://github.com/autorunhq/autorun/blob/c2268252a28abb5977fec8ea385b43f0e9519a5f/horizon-wine/source/forwarder.c#L658).

Di runtime kita, worker otomatis memakai core 0–2 dan nama thread belum
diteruskan ke registry native. `fex_auto_core3=1` membuka core yang diberikan
untuk penempatan otomatis secara umum; itu **bukan** padanan offload grafis
Autorun. Mengaktifkannya tidak mengimplementasikan kebijakan di atas.

**Kandidat pertama:** teruskan nama thread untuk mengidentifikasi `dxvk-cs`,
catat mask/priority yang benar-benar diizinkan, lalu sediakan offload
`dxvk-cs` saja sebagai opsi mati secara default. Pertahankan affinity game
dan stable balancer. Mengurangi persaingan di core game merupakan hipotesis
manfaatnya; waktu tunggu worker pada core keempat dapat pula memperburuk
frame pacing. Verifikasi pemakaian dan performanya di perangkat diperlukan.

## 2. Sinkronisasi langsung dengan antrean per objek

HEAD mempunyai dua perubahan terkait: request tertentu bisa ditangani
langsung oleh thread pemanggil, lalu waiter ditautkan ke objek yang ditunggu.
Operasi yang didukung mencakup select, event, mutex dan semaphore. Request
lain tetap memakai jalur server biasa. Penanganan langsung tetap memakai
mutex objek bersama; ini bukan desain tanpa lock.

Antrean mendukung event, mutex, semaphore, timer, thread, message queue dan
completion. Notifikasi dapat memenuhi wait di bawah lock dan membangunkan
waiter terkait. Source menangani referensi objek, WAIT_ALL, signal-and-wait,
APC/suspend, serta deadline timer/queue. Recheck biasa dibatasi 250 ms untuk
respons quit, dengan deadline yang lebih dekat tetap membatasi wait.

Sumber:
[jalur request langsung](https://github.com/autorunhq/autorun/blob/c2268252a28abb5977fec8ea385b43f0e9519a5f/dlls/ntdll/unix/server.c#L367),
[antrean objek dan wake](https://github.com/autorunhq/autorun/blob/c2268252a28abb5977fec8ea385b43f0e9519a5f/dlls/ntdll/unix/horizon.c#L15143).
[Commit antrean](https://github.com/autorunhq/autorun/commit/0625c79c9dbb7bc71fa6cf9a244cb6332a377eed)
bertimestamp 26 September, sesudah publikasi Test Build 4. Opsi launcher
`sync=horizon` bersifat opt-in; default tanpa key tersebut memakai Standard.

Ini lebih luas daripada router notifikasi kita di
`src/runtime/fex_sync_horizon.h`, yang tetap melewati server dan masih
memakai recheck 20 ms. Eksperimen kita tersebut **pernah memperberat 3D dan
freeze sebelum kickoff**, lalu dinonaktifkan; lihat
[hasil perangkat](FEX3-SYNC-PACING.md) dan [pemulihan](FEX3-SYNC-RECOVERY.md).
Menyalakan kembali `fex_targeted_wake=1` tidak mengadopsi implementasi baru.

**Kandidat kedua:** backport terisolasi dengan sakelar control, setelah
uji lebih lengkap untuk wake yang terlewat, WAIT_ALL, reset event, lifetime
objek, timer, APC, self-suspend/resume dan quit. Jangan mengambil potongan
notifikasi saja. Tes host dalam audit ini belum memvalidasi seluruh jalur
direct-sync ataupun fairness kernel Switch.

## 3. Bagian yang tidak perlu disalin sebagai peningkatan

| Bagian | Autorun HEAD | Runtime kita / keputusan |
| --- | --- | --- |
| Balancer | Menyusun ulang worker dari yang terberat setiap pemeriksaan; dapat menghasilkan banyak perpindahan | Pertahankan stable balancer: maksimal satu perpindahan, manfaat proyeksi pasangan core >5 poin persentase. Log lama pernah mencatat 348 perpindahan dan 46 pembalikan arah. |
| Sleep(0) / yield | `svcSleepThread(-1)` dalam `NtYieldExecution` | Kita memakai yield tanpa migrasi serta jeda 50 µs setelah burst 64 yield tidak efektif. Upstream belum membuktikan jalur ini lebih baik untuk PES. |
| Futex | Address arbitration Horizon; infinite wait dipecah agar quit diperiksa | Dasar `svcWaitForAddress`/`svcSignalToAddress` sudah ada pada runtime kita. Pemecahan wait untuk quit bukan bukti peningkatan FPS. |
| Profiling server | Tick dan atomic counter hanya saat profiling aktif | Kita masih mencatatnya pada tiap request. Mematikan biaya diagnostik pada build performa layak diuji kemudian, sambil menjaga pencatatan gap untuk perbandingan. Besar manfaat belum terukur. |

Sumber:
[balancer](https://github.com/autorunhq/autorun/blob/c2268252a28abb5977fec8ea385b43f0e9519a5f/horizon-wine/source/thread_profile.c#L865),
[yield](https://github.com/autorunhq/autorun/blob/c2268252a28abb5977fec8ea385b43f0e9519a5f/dlls/ntdll/unix/sync.c#L2438),
[gating profiler](https://github.com/autorunhq/autorun/blob/c2268252a28abb5977fec8ea385b43f0e9519a5f/dlls/ntdll/unix/server.c#L407),
[stable balance lokal](FEX3-STABLE-BALANCE.md).

## 4. Backend dan preset turut memengaruhi perbandingan

Source HEAD mendukung pilihan **Box64 atau FEX-2609**, dengan dukungan FEX
bergantung pada build. Karena itu deskripsi lama bahwa Autorun hanya Box64
tidak cukup menggambarkan HEAD. Backend pada video belum teridentifikasi.

[Default opsi FEX HEAD](https://github.com/autorunhq/autorun/blob/c2268252a28abb5977fec8ea385b43f0e9519a5f/horizon-wine/source/fex_options.h#L45)
antara lain TSO off, x87 reduced, multiblock on, MAXINST 1000, SMC none,
L2 lookup cache disabled dan dynamic L1 enabled. Preset Fastest kita sudah
mematikan scalar/vector/memcpy TSO dan mengurangi precision x87; multiblock
juga sudah aktif. Menyalin ketiga opsi itu bukan optimasi tambahan.

Kita mempertahankan MTRACK dan pilihan MAXINST 500/5000. SMC none mengubah
penanganan modifikasi kode dan bukan perapian scheduler. MAXINST 1000 bisa
menjadi eksperimen lain, tetapi perlu wiring: profil lokal saat ini hanya
mengenali 500, selain itu mengembalikan 5000. Jangan menganggap menambah
environment `FEX_MAXINST=1000` sudah mengaktifkannya.

## Urutan perbandingan di Switch

1. Jalankan FEXTendo v2 yang sudah tersedia, pada satu konfigurasi clock
   tetap. Ukur dulu apakah trial memory-budget mengurangi jeda periodik.
   Temuan log memory-audit sebelumnya masih merupakan bukti yang paling
   langsung terkait gap kita; belum ada hasil v2 untuk mengonfirmasinya.
2. Untuk eksperimen worker, bandingkan A/B dengan **NRO yang sama** dan
   hanya sakelar offload yang berbeda. Cocokkan clock CPU/RAM/GPU, preset,
   resolusi, VSync, queue, stadion, kamera dan keadaan cache. Catat MHz
   aktual; istilah “mentok” tidak cukup untuk mengulangi eksperimen.
3. Ulangi kickoff, kamera mengikuti umpan jauh, shooting dan replay. Gunakan
   timestamp T+ v2 bersama log; pisahkan startup/loading dari gameplay.
   Bandingkan gap >50/100 ms per menit, distribusi gap dan audio underrun,
   bukan total gap dari run berbeda panjang atau FPS overlay saja.
4. Setelah hasil worker jelas, uji direct-sync atau pengurangan profiling
   sebagai perubahan lain. Jangan menggabungkan semuanya dalam satu build
   lalu mengaitkan hasil ke salah satu teknik.

## Validasi audit

Empat tes upstream dijalankan pada source yang dipin dengan ASan/UBSan:
`check_core_affinity.py`, `check_horizon_queue_wakes.py`, `thread_profile.c`
dan `fex_options.c`. Semuanya lulus setelah header deklaratif
`dxvk_releases.h` yang semula belum diunduh ditambahkan ke snapshot.
Receipt lengkap: `host-test-results.json`.

Tes core memakai kernel mock dan tes queue mengeksekusi potongan source;
keduanya bukan pengukuran performa Switch. Audit tidak menjalankan seluruh
suite upstream, membangun Autorun, memvalidasi video YouTube, atau mengklaim
PES13 sudah bebas stutter.
