# Polling adaptif setelah checkpoint yang lancar

Checkpoint **cf4f43e** sudah dipush ke `origin/fex-core-fast`. Pengguna menguji
`pes13-fex3-yield-burst` dan melaporkan stutter kamera/frame pacing hampir
hilang, dengan sisa lag bola saat core urutan pertama penuh dan replay pada
core urutan kedua. Tujuan berikutnya mengurangi pekerjaan polling yang tidak
perlu pada semua thread, bukan membatasi persentase CPU.

ZIP ini satu overlay gabungan dengan rollback. Masih **build eksperimen dengan
diagnostik aktif**, memakai profil production pengguna. Belum diuji di Switch.

## Bukti dari run terakhir

Log 368.997 byte, SHA256
`197f0490990e252cfbd80abdae1ed6d5ceafa7a0afaa1c0cb07f7d7d67c169b7`.
Snapshot dipertahankan di `local/fex3/yield-feedback` dan ringkasan analisis
disertakan dalam paket.

- Build yield-burst aktif, tiga prosesor, VSync off. Continuous profiler off.
- Statistik terbaru masing-masing thread mencatat total **72.178 jeda**,
  durasi gabungan **3.907.695 µs**, rata-rata **54,14 µs** untuk permintaan
  50 µs. Ada **8** jeda ≥2 ms; puncak 9.010 µs. Statistik berakhir pada snapshot
  terakhir tiap thread, bukan tepat saat aplikasi ditutup. Waktu antar-thread
  dapat tumpang tindih dan tidak boleh dijadikan penghematan CPU terukur.
- Worker 164 tercatat di core ID 1 memakai 82,9%; worker 212 di core ID 0
  sampai 81,9%; worker 188 di core ID 2 sampai 81,8%. Baris BALANCE juga
  menunjukkan perpindahan penempatan thread. Patch sebelumnya sudah berlaku
  untuk semua thread yang melewati jalur yield, tidak khusus core ketiga.
- Worker 212 masih melakukan **391.118 yield** dalam satu laporan sekitar
  10 detik. Worker 132 pada awal run mencapai 943.476. Ini mendukung percobaan
  mengurangi polling yang berkelanjutan, tetapi tidak membuktikan setiap yield
  adalah kerja sia-sia atau memastikan waktu tepat spike yang dilihat pengguna.
- JIT akhir: 40.153 translasi, 44,80 detik wall time kumulatif, puncak 74,92 ms.
  Pada uptime JIT 176 detik sudah ada 36.947 translasi dan 37,53 detik biaya.
  Puncak pipeline grafis 162,126 ms; 25 panggilan >50 ms. Kompilasi awal tetap
  salah satu sumber beban. Uptime ini berbeda dari jam pertandingan.
- Window Present akhir masih memiliki gap >50 ms meski kelancaran visual
  membaik menurut pengguna. Present bukan FPS simulasi atau frame 3D unik.
  Antrean logging JIT tetap terkejar: 231 queued/written, tanpa drop.

Tidak ada rekaman utilizasi fisik per-core yang tersinkron dengan event bola
atau replay. THREADS berisi CPU time thread terdaftar dan penempatan affinity;
angka 100% di overlay merupakan observasi pengguna, bukan nilai yang disimpulkan
dari menjumlahkan beberapa baris THREADS.

## Perubahan pada runtime

Kebijakan dipasang per-thread di Wine `NtYieldExecution`, termasuk Sleep(0)
nonalertable dan SwitchToThread. Tidak ada nomor core, ID thread, atau alamat
PES yang di-hardcode.

1. Awalnya tetap 64 yield yang masing-masing kembali dalam <2 µs, dalam 2 ms,
   lalu meminta satu jeda 50 µs seperti checkpoint.
2. Sesudah empat jeda berturut-turut yang masing-masing selesai ≤100 µs,
   polling yang masih padat memakai ambang **32 yield**. Durasi jeda tetap 50 µs.
3. Jika yield asli memakan ≥2 µs, antar-panggilan renggang >2 ms, atau satu
   burst terlalu lama, kembali ke ambang konservatif. Jadi panggilan biasa
   tidak terus mengumpulkan kredit antar-frame.
4. Jika jeda tambahan melebar **>200 µs**, hentikan tambahan jeda adaptif selama
   **5 ms**, kemudian mulai lagi dengan ambang 64. Jeda 100–200 µs juga
   membatalkan ambang cepat tetapi tidak memulai cooldown.

Efek yang dituju adalah lebih sedikit pengulangan guest selama menunggu, agar
thread lain mendapat waktu CPU. Tidak ada jaminan core selalu di bawah 100%:
simulasi/render/JIT yang benar-benar bekerja tetap dapat memenuhi core. Satu
thread serial juga tidak otomatis menjadi pekerjaan paralel pada tiga core.
Jika polling itu berada pada jalur kerja/deadline penting, jeda lebih sering
bisa menurunkan throughput; hasil hardware tetap penentu.

Thread affinity, prioritas, FEX DLL, Mesa, clock, jalur wait berdurasi positif,
APC dan suspend/resume dipertahankan. Jalur delay absolut yang memanggil fungsi
yield masih dapat melalui kebijakan yield ini seperti pada checkpoint.

Statistik per-thread `[FEX3-YIELD]` tetap ada. Baris `[FEX3-YIELD-ADAPT]` berisi
counter kumulatif `initial`, `sustained`, `cooldowns`. Penulisan tetap oleh thread
logger sekitar tiap 10 detik; jalur polling hanya mengubah state lokal dan
counter atomik, tanpa alokasi/penulisan file.

## Pasang dan bandingkan

- HOME → X, simpan log. Salin **folder `switch` utama** dari ZIP ke root SD
  di atas instalasi yield-burst yang sudah diuji. Overlay mengganti enam file;
  satu-satunya file aktif yang berbeda byte adalah NRO runtime.
- Pertahankan tiga core, clock stock, stadion/kamera/cache yang sama. Semua
  settings.dat, Medium candidate 1280×720 16:9, VSync off dan FEX persis sama.
- Marker baru: `pes13-fex3-yield-adaptive`, `[FEX3-YIELD] v2 enabled=1`, serta
  `[FEX3-YIELD-ADAPT] v1 enabled=1`. Tidak perlu menambah config untuk tes awal.
- Nilai hasil dari sisa lag gerakan bola, replay dan kickoff; penurunan angka
  CPU saja belum cukup. Simpan log sebelum menjalankan PES lagi.
- Pembanding dalam NRO yang sama: **`fex_yield_adaptive=0`** pada
  `configuration.ini` mengembalikan aturan 64/50 µs checkpoint. Biarkan
  `fex_yield_backoff` tetap default/1. `fex_yield_backoff=0` mematikan seluruh
  perbaikan backoff, jadi itu bukan pembanding checkpoint.
- Rollback penuh: tutup PES lalu salin **folder `switch` di dalam `rollback`**
  ke root SD. Kembali tepat ke payload yield-burst yang dinyatakan lancar.

## Validasi

Generated C diuji dengan ASan/UBSan dan delapan pthread. Pengujian mencakup
ambang awal/adaptif, reset saat ada jeda nyata, burst renggang, clock mundur,
cooldown tepat 5 ms, laporan counter dan pemisahan TLS tiap thread.

Tes ARM64 menjalankan fungsi dari ELF hasil build: Sleep(0), direct yield,
state thread terpisah, oversleep/cooldown, control yang mereproduksi urutan
syscall versi lama, backoff off, dan durasi relative sleep yang tidak berubah.
Tes resume, unwind, affinity, pipeline dan logger juga memakai ELF yang sama.

Hash dependency PE/FEX/Mesa/SDK dipertahankan; delta native Wine hanya sync.c
dan runtime.c. NRO dicocokkan dengan ELF. Payload, receipt, setting dan rollback
diverifikasi dari manifest baseline serta readback ZIP. Tes ini tidak mengukur
FPS Switch dan tidak menjamin fairness scheduler hardware.
