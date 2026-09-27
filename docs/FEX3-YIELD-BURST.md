# Polling backoff pada core sibuk

Checkpoint sebelum eksperimen: `1fcacf7`, sudah dipush ke `origin/fex-core-fast`.
Pengguna melaporkan preset 720p/Medium lancar setelah bagian awal pertandingan,
tetapi core **urutan ketiga** mencapai 99% bersamaan dengan lag/stutter.
Ini observasi satu core, bukan angka overall.

Satu ZIP update berisi runtime baru, preset 720p yang persis sama, FEX/DXVK
yang sama, dan rollback lengkap ke `pes13-fex3-camera-720`. Perubahan ini masih
eksperimen; hasil tes host tidak membuktikan stutter/kickoff selesai di Switch.

## Apa yang ditunjukkan log

Input: `TEST RESULT/fex-runtime.log`, 532.331 byte, SHA256
`a6a309f43d9d02d70240755e87385bf9293d8c9c3421057b372742585bd0b335`.
Snapshot asli dan analisis tersimpan di `local/fex3/core-pressure-feedback`.

- Runtime `camera-720` aktif, tiga prosesor, VSync off. Antrean JIT berfungsi;
  laporan `queued/written` terkejar tanpa drop yang teramati.
- Tidak ada thread pada core ID 3 di baris THREADS yang terekam. Menurut
  [dokumentasi Status Monitor](https://github.com/masagrator/Status-Monitor-Overlay#what-is-currently-supported),
  urutan core standar adalah ID 0–3; ID 0–2 untuk aplikasi/game, ID 3 untuk
  sistem/background/overlay. Jika UI menomori 1–4, urutan ketiga adalah ID 2.
  Tidak ada dasar bahwa core ketiga dan keempat adalah dua logical thread
  yang berbagi satu core. Log ini juga tidak membuktikan seluruh beban sistem
  pada core tersebut, karena THREADS hanya mencakup thread yang terdaftar.
- Worker Wine `164w@2` tercatat memakai 84,6% satu core dalam sebuah interval.
  Worker yang sama mencatat **513.660 Sleep(0) dalam satu laporan**,
  tetapi total waktu di jalur yield hanya 78.008 µs: rata-rata sekitar 0,152 µs.
  Artinya polling sangat padat dan kebanyakan panggilan segera kembali.
  Belum ada penanda tepat untuk menyamakan interval ini dengan spike 99%
  yang pengguna lihat. Thread yang sibuk pada run lain juga bisa berbeda ID.
- Menjelang uptime JIT 175 detik ada 35.963 translasi, dibanding 40.815 di
  akhir; biaya compile kumulatif 33,31 dari 43,67 detik. Ini wall time antar
  thread yang dapat tumpang tindih, bukan persentase utilisasi CPU.
- Satu pipeline di bagian awal mencapai **416.130 µs**, dan puncak seluruh
  run **580.063 µs**. Pekerjaan awal
  kompilasi masih nyata; memperbaiki polling tidak membuat semua kompilasi
  itu hilang. Uptime tersebut bukan menit pada jam pertandingan.
- Window Present akhir masih mempunyai gap >50 ms. Present bukan jumlah
  frame 3D unik atau FPS simulasi; kelancaran visual perlu dibandingkan di alat.

## Perubahan

Wine sebelumnya selalu memakai `svcSleepThread(0)` untuk yield. Saat tidak
ada peer yang dijalankan, polling guest dapat terus menghabiskan core.

Runtime baru tetap melakukan yield biasa terlebih dahulu. Hanya jika ada
**64 yield berturut-turut yang masing-masing selesai dalam <2 µs, seluruhnya
dalam jendela 2 ms**, thread diberi satu sleep **50 µs**. State terpisah per
thread. Yield yang memakan waktu ≥2 µs atau rentang panggilan yang renggang
memutus burst, sehingga tidak terus mengakumulasi yield antar-frame.

Ini berlaku pada jalur `NtYieldExecution`, termasuk nonalertable Sleep(0) dan
SwitchToThread. Jalur delay absolut yang sebelumnya memanggil fungsi yield
juga dapat melewati aturan ini. Implementasi wait relatif berdurasi positif,
APC/alertable/infinite, clock, affinity, priority, resume dan FEX tidak diubah.
Tidak ada alamat game atau ID thread yang di-hardcode dalam kebijakan.

50 µs adalah durasi **permintaan**, bukan jaminan durasi aktual. Kernel bisa
menjalankan thread lain lebih lama. Statistik `[FEX3-YIELD] tid=...` melaporkan
counter kumulatif `pauses`, `requested_us`, `actual_us`, `peak_us`, dan `late2ms`.
Catatan yang baru berubah ditulis oleh logger sekitar tiap 10 detik. Produser
hanya memperbarui counter atomik; tabel tetap 64 ID, overflow dilaporkan.
Overflow statistik tidak menonaktifkan kebijakan backoff pada thread tersebut.

Tradeoff: polling kehilangan sedikit waktu CPU untuk memberi kesempatan
thread lain. Jika polling itu justru berada pada jalur deadline sangat ketat,
atau sleep terlalu lama di hardware, hasilnya bisa memburuk. Karena itu ada
control di NRO yang sama: `fex_yield_backoff=0` dalam `configuration.ini`.
Default/tanpa key adalah 1. Tidak perlu menambah key untuk tes pertama.

## Pasang dan uji

1. HOME → X dan simpan log lama. Salin **folder `switch` utama** dari ZIP ke
   root SD, timpa instalasi camera-720. Ini overlay enam file, bukan instalasi
   game lengkap. Setting pengguna lain dan cache tetap berada di SD.
2. Pertahankan forwarder tiga core, tanpa OC, preset 720p dan kamera/stadium
   yang sama. Jangan hapus cache untuk perbandingan ini.
3. Pastikan marker `pes13-fex3-yield-burst` dan `[FEX3-YIELD] v1 enabled=1`.
   Perhatikan kickoff pertama, kamera cepat, urutan core ketiga ketika 99%,
   lalu lanjutkan melewati bagian awal yang sebelumnya berat. Simpan log.
4. Jika memburuk, gunakan control `fex_yield_backoff=0`, atau tutup PES lalu
   salin folder **`switch` di dalam `rollback`** untuk kembali tepat ke payload
   checkpoint 720p yang sudah kamu tes.

Grafis identik byte demi byte dengan camera-720 di ketiga settings.dat:
1280×720, VSync off, frame skipping off, field kandidat kualitas 0x1c=1.
Pengguna menyebut tampilan ini Medium; pemetaan retail field kualitas tetap
belum diverifikasi memakai settings.exe, sehingga metadata tetap jujur.

## Validasi paket

Generated C diuji dengan ASan/UBSan dan 8 pthread: batas 63/64 panggilan,
yield yang benar-benar memakan waktu, panggilan renggang, clock mundur, state
per-thread, control, batas tabel, dan laporan oversleep. Jalur ARM64 pada ELF
hasil build diuji untuk Sleep(0), direct yield, TLS terpisah, control, sleep
positif serta durasi aktual yang melebihi permintaan.

Tes affinity/core mask, suspend/resume, pipeline observer, JIT logger dan
unwind dijalankan terhadap ELF yang sama. Dependency PE, FEX, Mesa dan SDK
dibandingkan hash dengan checkpoint; delta source Wine hanya sync.c dan
runtime.c. Isi ZIP, rollback, setting, NRO/ELF dan receipt tes diperiksa hash.
Semua ini memverifikasi implementasi, bukan fairness kernel atau FPS Switch.
