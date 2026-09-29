# FEXTendo — short trace v1

Build diagnostik berbasis v3.2 untuk mencari penyebab stutter pertama saat
kickoff, shooting dan bola lambung. Belum merupakan perbaikan stutter.
Tampilan/version aplikasi tetap v3.2 / 0.3.3; marker runtime diagnostik adalah
`pes13-fextendo-short-trace-v1`.

## Pasang dan tes

1. Tutup game. Salin folder `switch` dari ZIP ke root SD dan timpa file yang
   sama. Ini update untuk instalasi FEXTendo v3.2 yang sudah berjalan; tidak
   berisi game. NRO **dan** `libwow64fex.dll` harus ikut diperbarui.
2. Aktifkan **Debug timestamp**. Pertahankan preset, clock/OC, tim dan stadion
   seperti tes sebelumnya agar hasilnya dapat dibandingkan.
3. Mulai sesi baru. Lakukan kickoff, shooting dan bola lambung beberapa kali,
   lalu lanjutkan sampai sudah terasa lancar. Catat waktu **T+ di overlay**
   setiap freeze/stutter, bukan waktu pertandingan. Sekitar 3–5 menit cukup
   jika semua gejala sudah muncul.
4. Tutup game lalu salin `switch/pes13-fex/fex-runtime.log` sebelum membuka
   FEXTendo lagi. Kirim log beserta waktu kejadian. Empat log sebelumnya
   disimpan sebagai `fex-runtime.previous-1.log` sampai `previous-4.log`, tetapi
   lebih aman langsung mengambil log sesi tes.

Jangan menyalin seluruh isi ZIP sekaligus ke SD: folder `control-off`,
`rollback`, `source`, `evidence` dan `licenses` bukan folder instalasi utama.

## Kontrol OFF dan rollback

Untuk membandingkan biaya probe, salin isi folder `control-off/switch` ke
`switch` di SD, kemudian mulai ulang aplikasi. Ini mengisi file
`switch/pes13-fex/fex_short_trace_off` dengan `1`. Jalankan adegan sama. Balik
ke ON dengan menyalin file `fex_short_trace_off` dari folder instalasi utama
ZIP (isinya `0`). Catat ON/OFF saat mengirim log.

Jika pernah menambahkan `fex_short_trace_off` ke `configuration.ini`, nilai
INI didahulukan: gunakan `fex_short_trace_off=0` untuk ON atau `=1` untuk OFF.
ZIP ini tidak menimpa INI, preset, save game, pilihan musik atau timestamp.
Log startup harus menampilkan `[FEX3-SHORT] v1 enabled=1` untuk ON. Record
`[FEX3-JIT-CLOCK]` mengonfirmasi modul FEX diagnostik juga aktif. Bila salah
satunya tidak ada, pemasangan/aktivasi perlu diperiksa sebelum menyimpulkan
hasil. Bila logger gagal dibuat, trace otomatis OFF.

Untuk kembali ke runtime v3.2 yang sudah dites, salin isi `rollback/switch`
ke `switch` di SD dan timpa NRO serta DLL. Rollback memakai NRO ZIP v3.2 dan
modul FEX emit-vsync yang sama dengan baseline v3.2. Kontrol OFF tetap memakai
binary diagnostik dengan pemeriksaan flag minimal; rollback mengembalikan
binary baseline persis.

## Data baru

- Kompilasi `compile_code` FEX: ringkasan per Wine TID, tick absolut awal/akhir,
  jumlah panggilan, total dan puncak waktu; laporan sekitar setiap lima detik
  ketika kompilasi selesai. Maksimal empat compile lambat >=20 ms per slot
  dalam window, disertai jumlah yang tidak disimpan.
- Wait `NtWaitForAlertByThreadId` >=20 ms: TID, handle native, alamat argumen
  wait, tick awal/akhir, status, serta pemanggil `NtAlertThreadByThreadId`
  terakhir yang teramati untuk target tersebut.
- Acquire, queue submit, fence dan semaphore >=20 ms: TID/handle, interval dan
  hasil. `object=0` pada stage GPU karena observer existing tidak menerima
  handle objek; jenis stage tidak sama dengan waktu eksekusi GPU.
- Pemetaan handle thread Present ke Wine TID dan counter drop kumulatif.

Catatan produsen memakai penyimpanan tetap dan try-lock: tidak menunggu mutex
probe, tidak mengalokasikan memori, tidak menghentikan thread dan tidak menulis
SD pada jalur yang diamati. Logger existing menguras maksimal 32 record native
serta 32 record JIT per putaran sekitar 200 ms. Kapasitasnya 256 record native,
128 teks JIT dan 128 slot wait/JIT. Tambahan logging tetap mempunyai biaya;
kontrol OFF disertakan untuk mengukurnya di perangkat.

Wait yang lama bisa merupakan idle normal. Waker/status yang tercatat adalah
observasi pada API Wine, **bukan** identitas pemilik heap atau hasil kernel
`SignalToAddress`. Alert dapat selesai sesudah wait kembali; kehilangan pasangan
atau sampel bukan bukti lost wake. Compile windows mencakup semua panggilan
yang selesai dalam rentangnya, bukan durasi satu frame. Trace yang selesai
belum menjelaskan wait yang masih menggantung; probe hang existing tetap ada.

Tidak ada perubahan baru pada affinity, timeout, yield/backoff, blok JIT,
shader cache, grafik atau kebijakan memory budget. Source/hasil tes host dan
hash binary disertakan di `evidence`/`manifest.json`. Build ini perlu diuji di
Switch; kelulusan tes host tidak membuktikan bahwa stutter telah diperbaiki.

## Analisis

Jalankan dari checkout repository:

```sh
python3 tools/analyze-fextendo-short-trace.py 'TEST RESULT/fex-runtime.log' --at 02:25 --window 2 --output kickoff.json
```

Analyzer menggunakan tick fisik 19,2 MHz yang sama dengan origin Play,
memisahkan compile window dari event individual, dan menolak korelasi waktu
jika origin ambigu atau clock tidak cocok. Jangan menganggap urutan penulisan
log sebagai urutan kejadian.

FEX tetap berasal dari FEX-Emu; integrasi/port Switch dan probe ini dikerjakan
proyek PES13/FEXTendo. Kredit sumber Wine, DXVK, Mesa, libnx dan referensi
Autorun tetap mengikuti `THIRD_PARTY.md` serta lisensi yang disertakan.
