# Review v3.6: kamera tersentak kembali dan kickoff pertama

Pengguna sebelumnya sudah mendapatkan kamera yang lebih mulus; keluhan terbaru
harus diperlakukan sebagai **regresi yang dilaporkan pengguna**, bukan dianggap
batas normal Switch. Capture saat ini mengonfirmasi interval render tidak rata,
namun belum menentukan perubahan mana yang menyebabkan regresi tersebut.

## Capture dan konfigurasi

Snapshot `local/fex3/review-fast-api-17c2cb8129/device.log`, 5.236.918 byte,
SHA256 `17c2cb8129340b81f8f2e85bba46a50f3e8cf229fbb6b9e0574632a01a05a69e`.
App 0.3.7/v3.6; satu origin Play `11028275038625`, 19,2 juta tick/detik.
Capture mencakup sekitar 773 detik. Pengguna memainkan satu pertandingan penuh
lalu sekitar 10 menit game pada pertandingan berikutnya tanpa menutup aplikasi;
setting durasi pertandingan 5 menit. Kickoff pertama diperkirakan T+02:00,
sementara timestamp kickoff kedua tidak diketahui.

| Yang diperiksa | Bukti di log |
| --- | --- |
| Execution sampler yang mem-pause thread | OFF, baris 55–56 |
| Short trace / catatan compiler | ON, baris 3 |
| Fast API / polling | ON, baris 35–36 |
| Renderer | DXVK 3.1.1, baris 13 |
| FEX | JIT128, Fastest, disk cache OFF; baris 77 dan 217–218 |
| Balancing | Stable, worker otomatis core 0–2; effective core-3 offload OFF, baris 33–38 |
| VSync / limiter | VSync ON; presentInterval=1 dan maxFrameRate=-1, baris 14, 372, 375 |
| Timestamp overlay | OFF, baris 11; origin Play tetap tersedia untuk analisis |

## Perbaikan kamera yang lama tidak ditarik

Perbaikan v2 menyembunyikan `VK_EXT_memory_budget` untuk menghindari query
memory-budget yang mahal secara berkala. Log terbaru masih menunjukkan
`client_extension=0` (baris 28) dan `extMemoryBudget=0` (baris 711).
Hanya lima query startup tercatat, dengan total wall time dibulatkan 0 µs dan
CPU 6 µs (baris 935), sebanding dengan lima query startup di capture v3.5.
Jalur query mahal yang pernah menyebabkan kamera tersentak **tidak teramati
aktif kembali**. Itu tidak meniadakan gejala regresi; penyebab baru dapat
menghasilkan gejala yang sama.

Yield-burst 64/2 ms/50 µs, balancer stable dan antrean JIT async juga tetap
aktif. Perbandingan ZIP v3.5/v3.6 mempertahankan dependensi Wine/Mesa/DXVK,
source Vulkan, dan bagian pengendali budget/yield tersebut. Perubahan baru
utama v3.6 adalah gateway QPC/delay, reuse realloc, dan pencatatan blok compiler.

## Kamera: frame datang tidak merata meski sudah warm

Batch sekitar T+354,57–364,63 s (baris 16187–16209) berisi:

- 548 interval masuk Present, rata-rata 18,355 ms.
- 91 interval <=8,334 ms, 39 >33,334 ms, 10 >50 ms.
- Sembilan pola interval >=50 ms disusul <8 ms: render terlambat lalu mengejar.
- Native Present rata-rata 0,476 ms, waktu lock dibulatkan 0 µs.
- Tidak ada pembuatan graphics pipeline atau driver-cache get pada batch itu.

Pada T+300–400 s, 93 dari 118 gap >50 ms yang tertangkap mempunyai waktu
submit-driver setidaknya separuh durasi gap. Median CPU time **thread Present**
pada gap-gap itu sekitar 0,732 ms. Contoh baris 16210–16219 menunjukkan
submit sekitar 31–48 ms di dalam gap 50–63 ms.

Ini mempersempit pencarian ke pasokan frame / blocking di jalur submit dan
scheduling. Waktu submit adalah wall time; belum membedakan menunggu GPU,
backpressure, descheduling, atau pekerjaan driver. Native Present yang cepat
bukan bukti GPU ringan, dan CPU thread Present tidak mewakili CPU gameThread.
Log tidak merekam posisi kamera atau timestamp scanout/frame unik.

## Kickoff: pekerjaan pertama masih ada, reuse dalam proses terlihat

| Cakupan window selesai, T+ detik | CompileCode | Total wall time | Puncak satu call |
| --- | ---: | ---: | ---: |
| 112,288–117,271 | 405 | 517,144 ms | 14,503 ms |
| 117,354–122,223 | 347 | 431,616 ms | 5,910 ms |
| 122,325–127,187 | 269 | 338,802 ms | 4,543 ms |

Sumber: baris 6169, 6333, 6574. Ada banyak pekerjaan translasi pertama sekitar
perkiraan kickoff, tetapi tidak ada satu call compiler ratusan ms yang dapat
langsung dinyatakan sebagai seluruh freeze T+02:00.

Burst berikutnya T+137,278–142,123 memuat 1.227 call / 2.885,674 ms wall,
melibatkan gameThread164 dan grRatingThread168 yang baru dibuat (baris 7245).
Ini lebih akhir daripada perkiraan kickoff dan tidak boleh dilabeli pasti
sebagai event yang sama.

Pada ekor T+731–772, hanya 174 call / 233,045 ms wall tercatat, tanpa race/loss.
Ada transisi loading dan gameThread344 baru; cocok dengan laporan match kedua,
namun titik kickoff keduanya belum pasti. Dari 1.723 baris blok yang dipertahankan,
tidak ada alamat entry yang berulang di window laporan selanjutnya. Ini
mendukung reuse kode dalam proses, bukan bukti disk-cache bekerja setelah
aplikasi ditutup.

Frontend mencakup sekitar 60,9% total wall compiler; decode dan IR passes
bersarang di dalamnya. Ini belum ukuran CPU murni. Blok game termahal yang
teramati adalah RVA `0x4b8679` pada T+236,493, 79,393 ms; bukan kickoff. Tanpa
executable game yang cocok, nama fungsinya belum bisa ditentukan.

## Pengaruh diagnostik dan kontrol yang konkret

Sampler pause-thread OFF, sehingga tidak menjadi penyebab run ini. Namun
short trace masih ON. Report compiler v3.6 memindai 2.048 slot dan memformat
maksimal 13 baris setiap >=5 detik **pada thread yang menyelesaikan kompilasi**.
Report berjalan sesudah timer CompileCode/dispatch selesai; biayanya tidak
terukur oleh kedua timer itu. Producer tidak menunggu penulisan SD, tetapi
pemindaian, pemformatan, callback serta logging background tetap memakai CPU.

Tidak ada bukti cukup untuk menyatakan diagnostik pasti penyebabnya maupun
menyatakannya bebas pengaruh. Langkah pertama mempertahankan binary dan
pengaturan yang sama, lalu mematikan short trace saja:

```ini
fex_short_trace_off=1
fex_hot_profile=0
fex_fast_api=1
```

Ubah key yang sudah ada dalam `switch/pes13-fex/configuration.ini`; jangan
menambahkan key duplikat karena parser memilih kemunculan pertama. Bila key
short-trace/sampler belum ada dalam INI, paket `trace-off-control` menyediakan
dua file flag untuk disalin. Paket tidak memuat NRO/DLL, jadi tidak perlu
rebuild atau memperbarui forwarder. Restart aplikasi diperlukan.

Konfirmasi log berikutnya `[FEX3-SHORT] v1 enabled=0`, `[FEX3-HOT] enabled=0`
dan `[FEX3-FASTAPI] v1 enabled=1`. Ini mematikan trace detail dan report blok
compiler, tetapi menyisakan histogram frame, statistik dasar JIT dan logger.
Jangan menyebut mode ini bebas seluruh diagnostik. Pertahankan renderer,
clock, preset, kamera dan cache. Perbandingan kamera cukup dimulai dari adegan
yang sama; tidak perlu bermain satu full match lagi hanya untuk melihat apakah
judder berulang hilang.

Jika judder tetap ada, kontrol berikutnya adalah **INI `fex_fast_api=0`** dengan
trace tetap OFF. Jangan mengubah dua variabel sekaligus pada kontrol pertama.
Jika perlu kembali ke binary sebelum v3.6, folder `rollback/switch/` di ZIP
v3.6 mengembalikan NRO+FEX persis v3.5. Tidak ada klaim rollback pasti
menghilangkan masalah tanpa konfirmasi perangkat.

### Koreksi kontrol OFF lama

Helper konfigurasi yang ter-build mengembalikan `legacy ? 1 : fallback`.
Karena default fast API adalah 1, file legacy `fex_fast_api` berisi `0`
**tidak mematikannya** bila tidak ada key INI. Folder kontrol API lama tidak
boleh dianggap pembanding OFF tanpa verifikasi marker. INI `fex_fast_api=0`
berfungsi, sedangkan `fex_short_trace_off=1` juga berfungsi dengan flag file.
Perilaku ini sudah direproduksi dengan fungsi produksi dalam harness sanitizer
(`config-control-test.json` pada folder review). Ini koreksi instruksi kontrol,
bukan klaim binary parser sudah diperbaiki dalam run yang sedang dianalisis.

## Hasil review

Tidak ada perubahan runtime atau klaim perbaikan FPS baru dalam review ini.
Prioritasnya memulihkan kelancaran kamera yang sebelumnya dicapai, mengisolasi
regresi v3.6 dengan kontrol yang benar, kemudian mengurangi cold-compile tanpa
mengorbankan pacing. Detail pendukung: `camera-audit.md`, `diagnostic-agent.md`,
`hotspots-agent-review.md`, `hotspots.json`, dan `warmup.json` dalam folder
snapshot lokal. Capture asli tetap dipertahankan.
