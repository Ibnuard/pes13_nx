# Hasil perangkat DXVK core 3 v1 — izin offload belum tersedia

Capture SHA-256:
`3c38f0f07c9b068ba98d9f3a451859fd7f51db7bff97aae3195eadedcdd3ead0`,
1.755.458 byte. Salinan dan JSON analyzer berada di
`local/fex3/review-dxvk-core3-3c38f0f07c/`. Pengguna menandai T+03:10, 03:40,
04:36; stutter terasa berkurang, kickoff pertama lebih ringan tetapi belum
hilang, dan interval frame paling terasa saat bola/kamera bergerak cepat.

## Eksperimen core 3 belum berjalan

Build benar (`pes13-fextendo-dxvk-core3-v1`), short trace ON, overlay ready,
clock JIT 19,2 MHz. Origin Play `10598325805968`. Tetapi baris 31 mencatat:

```text
[FEX3-DXVKCORE] v1 requested=1 enabled=0 cores=7 priorities=ffffffff0000000 core_rc=0 priority_rc=0 auto_core3=0
```

Mask dibaca sebagai heksadesimal: `0x7` hanya core 0–2;
`0x0ffffffff0000000` hanya priority 28–59, tidak mencakup 63. Kedua query
kernel berhasil. Ini bukan kegagalan INI: sakelar ON sudah terbaca, tetapi
**dua izin proses** belum tersedia. Baris 836 mengonfirmasi
`name=dxvk-cs tried=0 active=0 core=1 mask=2 priority=59` saat diberi nama.

Perasaan lebih ringan tetap merupakan hasil pengguna, tetapi belum dapat
diatribusikan ke offload yang tidak berjalan. Satu capture baru berlangsung
sampai sekitar T+427,9. Perbedaan durasi/scene juga melarang kesimpulan dari
perbandingan jumlah gap mentah dengan sesi sebelumnya.

Nama worker kini terkonfirmasi: TID 12 `dxvk-submit`, 16 `dxvk-queue`,
20 `dxvk-descriptor`, 24 `dxvk-cs`, 28 `dxvk-shader-l`. TID 168 adalah
`gameThread`. Nama ini memperkuat pemetaan yang sebelumnya masih inferensi;
offload tetap memilih nama, bukan nomor TID hardcoded.

## Frame pacing

Record individual adalah end-to-end Present gap >50 ms, dipilih ±2 detik
dari penanda memakai tick absolut. Histogram adalah jarak **masuk** Present
per batch sekitar 10 detik. Waktu batch diperkirakan dari SHORT-STATS yang
dilaporkan kemudian pada putaran logger sama; bukan timestamp per frame atau
scanout layar. `PACE elapsed_ms` sendiri tidak dimulai dari tombol Play.

| Penanda | Gap >50 ms tersimpan, ±2 s | Batch histogram sekitar T+ | Rata-rata jarak masuk Present | Interval 20–33,334 ms | Interval 33,334–50 ms |
| --- | --- | --- | ---: | ---: | ---: |
| 03:10 | Tidak ada | 186,124–196,196 s | 20,930 ms | 291/481 = 60,5% | 6/481 = 1,2% |
| 03:40 | Tidak ada | 216,322–226,379 s | 18,475 ms | 164/545 = 30,1% | 44/545 = 8,1% |
| 04:36 | Satu, 59,772 ms | 266,629–276,717 s | 18,654 ms | 194/540 = 35,9% | 32/540 = 5,9% |

Batch 03:40 memuat satu interval masuk Present >50 ms di luar window ±2 s.
Gap 59,772 ms berakhir T+276,728, tepat setelah batch 04:36 selesai, sehingga
histogram batch tersebut masih nol pada bin >50 ms. Keduanya mengukur batas
Present dan window berbeda. Nilai `peak_since_launch` bukan peak batch.

Interval tetap tidak rata meski tidak selalu melampaui 50 ms. Untuk target
60 Hz, interval nominal sekitar 16,67 ms; gerak kamera cepat dapat membuat
ketidakrataan lebih terlihat. Capture tidak merekam posisi bola/kamera,
sehingga belum membuktikan kamera sebagai penyebab. Histogram tidak dapat
dipakai membuat urutan frame lengkap atau p99 presisi.

## Kompilasi dan wait

- **03:10:** `gameThread` TID 168 mencatat 1.627 `compile_code`, total
  3.010,612 ms pada T+186,906–191,685 (4,779 s), peak 27,172 ms. Ini
  akumulasi compile, **bukan satu freeze tiga detik**. Main TID 4 pada window
  berdekatan hanya 19 compile / 16,176 ms.
- **03:40:** TID 168 masih mencatat 289 compile / 567,072 ms pada
  T+216,760–221,688, peak 12,335 ms. Tidak ada wait >=20 ms tersimpan pada
  main/submit/CS/completion dalam ±2 s; histogram tetap tidak rata.
- **04:36:** TID 168 mencatat 483 compile / 1.190,178 ms pada
  T+271,928–276,601, peak 83,378 ms. Tujuh slow-event tidak disimpan karena
  batas per window, jadi peak tidak boleh ditempatkan pada waktu spesifik.
  Worker baru TID 172 `grRatingThread` muncul T+275,7; satu kompilasinya
  50,243 ms pada T+276,116–276,166.
- Gap T+276,668–276,728 = 59,772 ms di TID 12 hanya memuat 0,673 ms CPU
  thread Present. Akumulasi submit 42,895 ms; satu submit individual
  32,292 ms pada T+276,684–276,717, bersamaan dengan main wait 35,843 ms,
  waker TID 12. Compile 50 ms tadi lebih awal, bukan event yang sama.

Rata-rata native Present pada tiga batch hanya 0,413 / 0,435 / 0,541 ms;
lock Present rata-rata 0 us setelah pembulatan. Pipeline graphics baru:
0, 5 (46,209 ms total), 0. Data ini tidak mendukung penjelasan bahwa seluruh
stutter berasal dari compiler shader atau mutex Present. Submit/wait adalah
wall time termasuk scheduling; belum ada timestamp GPU untuk memisahkan
beban GPU dari penundaan CPU secara pasti.

Snapshot TID 168: 84,4%, 81,0%, 77,9% di core 0. Main TID 4: 62,6%, 72,5%,
71,1% di core 2. `dxvk-cs` TID 24: 21,9%, 26,3%, 24,7% di core 1. CPU cukup
padat dan kompilasi awal tetap relevan, tetapi belum membuktikan core 3
pasti memperbaiki frame pacing.

Tidak ada timeout heap `RtlpWaitForCriticalSection` atau capture hang.
Ketidakhadiran ini belum membuktikan timeout lama selesai. Seluruh capture:
293 gap tersimpan, 79 gap terbuang dari antrean lama; short trace 7.687 record
native, 5 drop, 261 teks JIT, 0 drop, 813 kegagalan pairing wait/wake.
Wait compiler idle panjang tidak dilabeli freeze. Gap terbesar 1.674,413 ms
terjadi T+23,619, jauh sebelum penanda pengguna; tidak dilabeli kickoff.

## Langkah berikutnya

Proses perlu memberi **core 0–3 dan priority 63**. Menyalin ulang NRO atau
mengaktifkan `fex_auto_core3` tidak menambah izin kernel. Jika memakai
forwarder HOME, izin berasal dari metadata proses forwarder dan perlu
disesuaikan di sana. Pertahankan address-space/no-alias yang sudah berhasil,
serta preset, clock, cache dan DLL FEX.

Referensi primer
[capability Autorun](https://github.com/autorunhq/autorun/blob/c2268252a28abb5977fec8ea385b43f0e9519a5f/horizon-wine/hbl/hbl.json)
dan [patch forwarder Autorun](https://github.com/autorunhq/autorun/blob/c2268252a28abb5977fec8ea385b43f0e9519a5f/horizon-wine/source/forwarder.c#L658)
memuat kedua izin, bukan sekadar empat CPU.

Jika menggunakan Sphaira, source yang diperiksa pada commit
`72a94b905816de24817594109fb012a8f7107d8c` menyediakan **CPU Cores → 4
(Advanced)** pada editor forwarder. Implementasi
[`npdm_kernel_flags`](https://github.com/NaGaa95/sphaira/blob/72a94b905816de24817594109fb012a8f7107d8c/sphaira/source/owo.cpp#L442)
memperluas izin menjadi core 0–3 dan priority 28–63, serta mem-patch ACI0
dan ACID. Jadi bukan sekadar mengubah default core. Label UI terverifikasi di
[`forwarder_editor.cpp`](https://github.com/NaGaa95/sphaira/blob/72a94b905816de24817594109fb012a8f7107d8c/sphaira/source/ui/forwarder_editor.cpp#L437).

Pasang ulang forwarder untuk `sdmc:/switch/pes13-fex/pes13-fex.nro` dengan
opsi tersebut, pertahankan mode **32-bit (no alias)** yang dipakai instalasi
berjalan. Penggantian file NRO saja tidak memperbarui metadata forwarder
terpasang. Jalur peluncuran dan versi Sphaira pengguna belum dikonfirmasi;
petunjuk ini berlaku bila memakai Sphaira dengan implementasi opsi tersebut.
Jika opsi tidak tersedia, jangan menganggap peluncuran melalui Album atau
hbmenu otomatis memberikan capability yang sama.

NRO eksperimen yang sama bisa dipakai setelah izin tersedia. Verifikasi
`enabled=1`, lalu `name=dxvk-cs active=1 core=3 mask=8 priority=63` dan
result/readback nol sebelum tes ON/OFF dengan forwarder sama. Tetap gunakan
`fex_auto_core3=0` agar balancer game di 0–2. Jika tidak membantu, arah berikutnya
adalah biaya JIT awal pada gameThread dan interval di bawah 50 ms, bukan
menambah patch shader tanpa bukti.
