# Wine relative sleep: deadline monotonic, emitter + VSync off + 540p

Paket ini satu overlay gabungan di atas build emit-vsync yang terakhir dites.
Perilaku baru ada pada NRO Wine; FEX emitter, DXVK VSync off, ketiga settings
960×540 16:9 tetap disertakan agar cukup memasang satu folder `switch`.
Belum ada hasil gameplay Switch untuk NRO ini. Stutter, kickoff, dan slow motion
belum dinyatakan selesai.

## Temuan log terbaru

Input 271.695 byte, SHA256
`09c1c17e34a666fd64ac605e8ca930ebacf540f7964378bf2d005979d6fe90ae`.
Pengguna menutup PES saat slow motion akibat offside masih berlangsung, lebih
dari satu menit setelah onset. Karena itu transisi terakhir pada label event
292–294 bukan penanda onset yang pasti. Counter event bukan stopwatch presisi.

- Marker emitter aktif, settings `0288 vsync=0`, DXVK IMMEDIATE: paket sebelumnya
  memang terpasang. Tidak ada `[EXC]`; akhir log adalah close manual menurut
  pengguna, bukan bukti crash.
- Translasi masih terjadi: 39.237 kompilasi, 45,35 detik kumulatif dan puncak
  102,5 ms. Waktu antar-thread/stage dapat tumpang tindih. Aksi pertama masih
  dapat terkena pekerjaan JIT, tetapi log tidak menandai shooting secara tepat.
- Dua window akhir mempunyai **nol pembuatan pipeline graphics baru**. Masing-
  masing masih memuat 31 gap 50–100 ms, dan window terakhir satu gap >100 ms.
  Pembuatan shader/pipeline baru bukan penjelasan tunggal untuk bagian ini.
- Window terakhir sekitar 10,01 detik memiliki 383 Present; native Present
  rata-rata 0,393 ms, driver Present 0,284 ms. Panggilan pendek tidak meniadakan
  GPU/queue wait di jalur lain. Present bukan frame 3D unik atau laju simulasi.
- Thread Wine **52** menyelesaikan 418 sleep dengan total permintaan 4,781 detik,
  tetapi waktu di dalam API 9,380 detik: kelebihan 4,599 detik pada window itu.
  Identitas/fungsi gameplay thread ini belum dipetakan. Ini bukti keterlambatan
  sleep, bukan bukti mutex miliknya terkunci atau seluruh waktu itu CPU aktif.
- Resume tetap bergerak: laporan akhir 34.474 wait / 34.472 return, aktif 2.
  Dua worker parkir sesaat bisa normal. Penghitung agregat tidak menunjukkan
  apakah worker yang sama tertahan terus. `scale_bits=0.8` juga stabil jauh
  sebelum penutupan, sehingga tidak cukup untuk dipaksa menjadi 1.0.

Sebagian besar window warm mempunyai sekitar 20 gap 50–100 ms per laporan.
Histogram tidak menyimpan timestamp setiap gap; jumlah yang konsisten belum
membuktikan periodisitas tepat 500 ms. Analisis tidak mengasumsikan semua
stutter berasal dari satu penyebab.

## Perubahan runtime yang diterapkan

Jalur nonalertable relative `NtDelayExecution` sebelumnya mengubah durasi
negatif ke deadline wall clock, menjalankan `NtYieldExecution`, lalu tidur.
Yield itu dapat menyerahkan core sebelum timer sleep dipasang. Deadline relatif
juga bisa berubah akibat koreksi jam sistem.

Jalur baru menghitung durasi menggunakan counter monotonic yang sudah dipakai
QPC runtime, lalu langsung memanggil sleep native untuk sisa durasi. Wake lebih
awal mengulang terhadap deadline awal; wake terlambat tidak ditambah sleep
lagi. Sleep panjang dibatasi per chunk satu jam untuk menghindari overflow.
Konversi `INT64_MIN` memakai aritmetika unsigned. Tidak ada busy-spin, forced
resume, perubahan prioritas, atau skala clock game.

`Sleep(0)`, wait alertable/APC, wait infinite dan timeout absolute mengikuti
jalur sebelumnya. Ini koreksi umum Wine di Horizon, tidak berisi offset PES.
Windows membedakan relative wait yang tidak terpengaruh perubahan jam sistem
([KeDelayExecutionThread](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-kedelayexecutionthread)).
Sleep tetap dapat kembali terlambat karena thread baru berstatus siap jalan,
belum tentu langsung dijadwalkan ([Sleep](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-sleep)).
Karena itu perbaikan ini menghapus satu overhead dan memperbaiki deadline,
bukan menjamin setiap sleep persis atau membuktikan akar slow motion.

Diagnosis tambahan:

- `[FEX3-WAIT] tid=... suspend=... parked_us=...` mencatat umur self-suspend
  aktif setiap laporan resume, maksimum 16 baris. Snapshot memegang mutex
  predicate yang sudah ada; log ditulis setelah mutex dilepas. Tidak ada
  perubahan suspend count atau pause/resume diagnostik baru.
- Laporan thread/progress berlanjut sekitar tiap 10 detik hingga akhir run,
  sehingga slow motion late-game tidak lagi menunggu laporan dua menit.
- Resume/umur wait berada di batch logger; tidak memaksa flush SD per baris.

## Validasi

- Build native ARM64 lulus; NRO dicocokkan dengan ELF menggunakan `elf2nro`.
  Delta source native hanya `sync.c`, `horizon.c`, `runtime.c`. PE ntdll/wow64,
  FEX DLL, Mesa/SDK, settings dan DXVK sama dengan baseline terverifikasi.
- Binary lama/baru dieksekusi di Unicorn dengan scheduler buatan: sleep 5 ms
  yang terkena yield ke peer 25 ms kembali pada 25 ms di lama, 5 ms di baru.
  Koreksi wall clock -100 ms membuat lama 105 ms, baru tetap 5 ms.
  Ini **fault injection**, bukan angka perbaikan pada Switch atau kejadian
  koreksi jam yang terbukti pada log perangkat.
- Sleep pendek, hourly chunk, early wake, oversleep, counter wrap, konversi
  `INT64_MIN`, zero/absolute wait lulus. Cabang alertable/infinite source cocok
  persis dengan baseline; tidak ada klaim uji delivery APC di perangkat.
- ASan/UBSan pada report source hasil patch: umur 60/70 detik, batas 16 worker,
  laporan idle dan suspend count yang tetap lulus.
- 15 skenario ARM64 suspend/resume, 16 binding observer pipeline, serta unwind
  FEX/Wine dengan 576 operasi tree lulus. Receipt terikat hash binary disertakan.

## Pasang dan uji

1. Tutup PES lewat HOME → X dan simpan log lama.
2. Ekstrak `pes13-fex3-sleep-deadline.zip`; salin folder **`switch`** ke root SD,
   timpa file pada instalasi terakhir. Ini overlay enam file, bukan game lengkap.
3. Pertahankan cache, clock dan konfigurasi match seperti tes sebelumnya.
4. Log harus menunjukkan `[BUILD] pes13-fex3-sleep-deadline`, `[FEX3-SLEEP] v1`,
   `[FEX3-EMIT] v1`, `vsync=0` dan `VK_PRESENT_MODE_IMMEDIATE_KHR`.
5. Uji kickoff pertama, shot/belok/bola turun, lalu offside. Bila slow motion
   muncul, biarkan sekitar 30 detik sebelum memicu event lain; lanjutkan sekitar
   30 detik setelah pulih. Catat event pemicu/pemulih dan simpan log sebelum
   launch berikutnya. Ini memberi bagian lambat dan pulih dalam run yang sama.

Rollback: HOME → X, lalu salin **folder `switch` di dalam `rollback`** ke root
SD. Ini kembali ke emit-vsync yang terakhir terasa lebih ringan: VSync tetap
mati dan FEX emitter tetap aktif, sedangkan NRO sleep kembali ke baseline.
