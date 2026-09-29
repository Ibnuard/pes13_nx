# FEXTendo v3.2 — hasil tes Switch 29 September 2026

Timestamp telah dikonfirmasi terlihat di layar oleh pengguna. Capture terbaru
juga membuktikan setup overlay selesai. Stutter yang ditandai pengguna masih ada;
**capture ini tidak mengulang timeout heap sesi sebelumnya**, sehingga masalah
heap belum boleh dinyatakan selesai maupun dianggap penyebab semua stutter.

## Capture dan penanda aksi

- Checkpoint source: `77082ed37cb064ab86e9ee14c31a0d25a0999f9a`, branch `fex-core-fast`.
- Log: `TEST RESULT/fex-runtime.log`, 298.530 byte, 2.929 baris.
- SHA-256: `0f89e8b8d787421eb4376a9ce9633afd5fe6adee1fb17501e086e596eb618ea2`.
- Marker: `version=0.3.3 release=v3.2`, `pes13-fextendo-v3.2-glass`.
- Salinan dan hasil analisis: `local/fex3/review-2026-09-29-v3.2/` (diabaikan Git).
- Penanda dari pengguna: kickoff freeze T+02:25; bola lambung/shooting stutter
  T+02:50–02:55; setelah bola keluar sekitar T+03:00 terasa lancar dan stabil.

Marker mengidentifikasi keluarga build; file NRO di SD tidak di-hash langsung.
Bukti build/ZIP yang disiapkan dan tes host sebelumnya tetap dipertahankan.

## Overlay bekerja

Baris 489–493 merekam `aruid=597`, `manager=1`, `display id=1204 borrowed=1`,
`overlay ready layer=1206`, dan `first overlay frame submitted`. Ditambah
konfirmasi pengguna, ini mendukung keberhasilan perbaikan duplicate-open display
pada perangkat ini. Jangan menyunting manifest ZIP lama menjadi
`hardware_tested=true`: hasil perangkat dicatat terpisah dari bukti pra-tes.

## Korelasi ke T+ yang tampil di layar

`origin_tick=9845190471456` (baris 102). Waktu gap dihitung dengan
`(tick - origin_tick) / 19200000`. Overlay menunjukkan waktu sejak Play, bukan
sejak kickoff. Nilai `elapsed_s`, `elapsed_ms` dan `uptime_ms` pada kelompok
statistik lain mempunyai titik awal berbeda; jangan menyamakannya dengan T+.

| Rentang T+ | Gap >50 ms yang tersimpan | Terbesar yang tersimpan |
| --- | ---: | ---: |
| 02:24–02:26, sekitar kickoff | 6 | 99,841 ms |
| 02:25–02:30, beberapa detik sesudahnya | 27 | 111,142 ms |
| 02:50–02:55, bola lambung/shooting | 11 | 82,499 ms |
| 03:00–03:10 | 24 | 86,123 ms |
| 03:10–03:20 | 7 | 72,475 ms |
| 03:20–03:30 | 9 | 114,438 ms |
| 03:30–03:40 | 8 | 70,276 ms |

Dua baris kickoff saling tumpang tindih; jangan dijumlahkan. Ini hitungan gap
Present yang tersimpan, bukan jumlah aksi atau freeze yang dirasakan pengguna.
Seluruh capture menyimpan 374 gap dan melaporkan 158 sampel terbuang. Batch yang
memuat kickoff menyimpan 32, membuang 8. Batch sekitar shooting tidak melaporkan
drop. Karena itu tabel bukan distribusi frame lengkap atau batas atas mutlak.

Gap tersimpan terbesar seluruh sesi adalah 2.410,177 ms pada T+25,155,
jauh sebelum kickoff yang ditandai. Tidak ada `[FEX3-HANG] capture=` dan tidak
ada `RtlpWaitForCriticalSection` pada sesi ini. Snapshot thread existing baru
terpicu setelah sekitar tiga detik tanpa progres Present. Rangkaian gap pendek
atau simulasi yang berhenti sambil frame terus dipresentasikan tidak memenuhi
pemicu itu.

## Apa yang mendukung dan melemahkan dugaan penyebab

**Pembuatan shader/pipeline baru bukan penjelasan tunggal.** Batch dengan gap
akhir T+143,691–150,504 mencatat nol graphics pipeline baru (baris 2351).
Batch berikutnya dengan gap T+153,761–163,668 dan T+163,825–173,810 juga nol.
Batch T+173,885–183,712 mencatat hanya lima pipeline dengan total 49,111 ms,
tanpa panggilan pipeline di atas 50 ms. Ini tidak meniadakan biaya GPU/submit,
material lama atau shader yang sudah dibuat; statistik yang diukur adalah
panggilan pembuatan pipeline yang telah selesai.

**Kompilasi kode FEX masih berlangsung.** Laporan `compile_code` sekitar area
kickoff (baris 2251→2327) bertambah 2.060 panggilan dengan akumulasi 3,686 detik
selama 10,001 detik menurut clock JIT. Di bracket berikutnya dekat shooting
(baris 2481→2560), bertambah 617 panggilan / 1,344 detik selama 10,001 detik.
Namun laporan ini kumulatif semua thread, dapat mengantre, dan tidak memiliki
tick absolut atau TID. Jangan mengatribusikan seluruh durasi tersebut ke satu
aksi, satu frame, atau worker tertentu. Kompilasi masih bertambah setelah
T+03:00 juga; “sudah lancar” tidak berarti kompilasi benar-benar berhenti.

**Ada worker yang layak diamati, belum ada thread terbukti bersalah.** `tid=164`
dibuat dengan entry `0x4da0e3` di executable game (baris 2229). Di window sekitar
kickoff tercatat menggunakan sekitar 84,9% satu core, main thread `tid=4` 52,7%,
`tid=24` 20,3% (baris 2334). Di sekitar shooting nilainya 82,7% / 56,7% / 20,2%
(baris 2500). Worker 164 tetap sekitar 78–83% ketika pengguna merasa lancar
setelah menit ketiga. CPU tinggi saja tidak membuktikan bahwa worker itu
menyebabkan stutter, atau bahwa memindahkannya ke core lain akan membantu.
`tid=24` pada sesi baru juga tidak otomatis mempunyai penyebab sama dengan
thread 24 yang timeout pada sesi lama.

Pada sampel sekitar kickoff, CPU thread penyaji umumnya di bawah satu ms selama
gap 50–100 ms. Beberapa submit native memakan puluhan ms wall time. Ini
mendukung inspeksi jalur wait/submit dan produsen frame, tetapi waktu submit
mencakup antrean/scheduling dan bukan waktu eksekusi GPU. Handle Present
`2556358` belum dipetakan ke Wine TID dalam probe existing; jangan menyamakannya
dengan worker 164. Lock native Present sendiri sangat singkat dan tidak sama
dengan critical section heap Wine.

**Pembacaan SD bukan gelombang besar pada rentang aksi ini.** Dua laporan
PROGRESS yang mengapit bagian kickoff bertambah satu read / 6 ms read dan
5 ms SD. Pada bracket lebih lebar dekat shooting kenaikannya beberapa read dan
puluhan ms. Ini melemahkan dugaan satu pembacaan SD beberapa detik pada titik
tersebut, meski report batch bukan pengukuran tepat pada awal/akhir aksi.

**Perbaikan rasa lancar sesuai tren, bukan bukti semua gap hilang.** Gap pendek
lebih jarang pada beberapa window setelah T+03:10. Frame Present tidak selalu
sama dengan langkah simulasi bola/kamera atau frame unik; pengalaman pengguna
tetap bukti terpisah yang dicocokkan dengan pencatat frame.

## Langkah teknis berikutnya

Data saat ini mempersempit masalah tetapi belum menentukan perubahan runtime
yang dapat disebut fix. Audit lanjutan yang tepat adalah trace terbatas untuk
stall pendek, bukan membuka paksa heap lock atau mengubah clock:

1. Rekam tick absolut dan TID untuk kompilasi FEX yang lambat, plus ringkasan
   jumlah/waktu kompilasi per thread agar banyak compile kecil juga terlihat.
2. Hubungkan handle thread Present ke Wine TID, dan rekam wait/submit panjang
   dengan awal/akhir tick dan result; pertahankan semantik timeout/wake.
3. Catat address wait, thread yang melakukan wake, dan hasilnya untuk kasus
   contention yang relevan. Heap owner perlu direkam saat contention jika
   timeout lama muncul lagi; `blocked by 0000` pada log lama tidak cukup.
4. Gunakan buffer memori berbatas, counter drop dan flush berkala. Hindari log
   SD atau penghentian semua thread pada tiap gap 50 ms karena dapat menambah
   stutter yang sedang diukur. Sertakan kontrol OFF untuk membandingkan biaya.

Langkah ini adalah rencana instrumentasi; **belum ada patch gameplay atau build
baru yang dibuat oleh review ini**. v3.2 dan checkpoint tetap utuh.

## Reproduksi analisis event

```sh
python3 tools/analyze-fextendo-run.py 'TEST RESULT/fex-runtime.log' --at 02:25 --window 5 --output kickoff.json
python3 tools/analyze-fextendo-run.py 'TEST RESULT/fex-runtime.log' --at 02:52.5 --window 2.5 --output shot-loft.json
python3 tools/analyze-fextendo-run.py 'TEST RESULT/fex-runtime.log' --at 03:15 --window 15 --output settled.json
```

Gunakan hash input di atas. Data hasil yang disimpan berada di
`local/fex3/review-2026-09-29-v3.2/review.json`; log mentah tidak diterbitkan.
