# Review perangkat v3.5: stutter awal pertandingan

Checkpoint sebelum review: `8cb643363265330b28ed7c9b1b8a4db5581bedcf`,
branch `fex-core-fast`, sudah di-push ke origin. Review ini menambahkan
analisis dan alat reproduksi; belum menghasilkan binary runtime baru.

Kesimpulan terkuat adalah **pekerjaan kompilasi kode FEX saat pertama
digunakan masih besar pada thread game**, kemudian berkurang dalam sesi
yang sama. Ini mendukung pola awal pertandingan berat dan pertandingan
berikutnya lebih lancar. Belum membuktikan bahwa setiap hitch disebabkan
JIT, atau fase compiler mana yang harus dioptimalkan. Waktu submit grafis
dan penulisan SD masih perlu dibedakan dari kerja CPU compiler.

## Capture dan patokan waktu

- Snapshot lokal: `local/fex3/review-polling-20965fb3c7/device.log`.
- SHA-256: `20965fb3c738926b414d77cedd23a6e4d90893b8b51e070c7f916ecbb6a410d8`;
  2.291.444 byte. Tidak mengedit capture asli.
- App 0.3.6 / v3.5, marker `pes13-fextendo-polling-v1`, polling ON,
  DXVK 3.1.1, balancing ON, effective core-3 offload OFF, JIT maxinst 128.
- FEX disk cache `requested=0` (baris 106). Cache kode dalam RAM tetap ada.
- Origin Play `10960956053934`, clock 19.200.000 tick/s; laporan terakhir
  T+404,527 s. Pengguna mengonfirmasi menit 2:00 adalah **stopwatch sejak
  Play**, bukan jam pertandingan. Flag overlay internal pada capture ini 0.
- Record gap >50 ms tersimpan 390, dropped 59. Short trace 10.814 record,
  dropped 11; JIT 281 record, dropped 0; pasangan wait hilang 522.
  Karena capture terbatas, tidak boleh menyatakan semua stall tercakup.

## Perbedaan pekerjaan awal dan akhir

`tools/analyze-fextendo-warmup.py` memilih hanya window JIT yang lengkap
di dalam rentang. Window melintasi batas tidak diprorata. Angka berikut
adalah jumlah panggilan dan **wall time agregat**, bukan waktu CPU murni,
bukan jumlah blok unik, dan bukan durasi satu freeze.

| Window JIT di dalam rentang sejak Play | T+100–150 s | T+350–400 s |
| --- | ---: | ---: |
| Window lengkap | 34 | 10 |
| Panggilan `CompileCode` | 7.738 | 382 |
| Wall time agregat | 8.444,520 ms | 515,516 ms |

Pada rentang awal, `gameThread` TID 164 sendiri mencatat 6.930 panggilan
dan 7.198,431 ms. Nama thread berasal dari metadata log, bukan tebakan
berdasarkan core. Seluruh sesi mencatat 54.278 panggilan `CompileCode`
dengan 41,011 s wall time, sedangkan `dispatch_compile` 264.456 panggilan
dengan 50,854 s. **Keduanya bersarang; jangan dijumlahkan.**

Thread game kemudian berganti TID. TID 164 mencatat 8.052 panggilan pada
window T+99,737–145,671; TID 240 mencatat 174 pada T+356,432–371,885;
TID 252 mencatat 263 pada T+375,694–402,441. Rentang ini berbeda durasi
dan adegan, sehingga bukan benchmark persentase peningkatan. Pergantian
TID tidak dengan sendirinya berarti cache JIT seluruh proses hilang.

Statistik periodik memiliki batas pengambilan berbeda dari window JIT:

| Empat batch laporan lengkap | T+102,767–142,996 s | T+354,239–394,475 s |
| --- | ---: | ---: |
| Observasi interval masuk Present | 1.837 | 2.046 |
| Interval >33,334 ms | 333 | 165 |
| Interval >50 ms | 34 | 19 |
| Graphics pipeline: panggilan / wall time | 4 / 50,796 ms | 0 / 0 ms |
| Driver cache get: panggilan / wall time | 6 / 49,768 ms | 0 / 0 ms |
| Pembacaan SD: panggilan / wall time | 32 / 166 ms | 20 / 97 ms |

Timer pipeline/cache dapat bersarang; jangan menambahkannya. Batch
diposisikan memakai tick `SHORT-STATS` flusher terdekat, bukan timestamp
setiap operasi I/O. Adegan tidak identik. Data akhir memang lebih baik,
tetapi masih memiliki gap; ini bukan bukti bahwa seluruh stutter hilang.

## Sekitar kickoff T+02:00

Batch T+112,827–122,887 (PROGRESS baris 5857 dan 6280) mencatat **satu
pembacaan SD selama 4 ms**, graphics pipeline 0 dan driver cache get 0.
Kompilasi TID 164 tetap berjalan:

| Window JIT | Panggilan | Total wall time | Puncak satu panggilan |
| --- | ---: | ---: | ---: |
| T+112,479–117,351 | 1.132 | 1.273,388 ms | 34,292 ms |
| T+117,494–122,475 | 432 | 435,559 ms | 2,772 ms |
| T+122,542–127,397 | 595 | 650,828 ms | 3,900 ms |

Gap individual yang tersimpan berakhir pada T+118,007 (53,034 ms),
121,515 (54,931 ms), 121,979 (58,725 ms), dan 122,559 (64,867 ms).
Wall time submit yang menyertainya sekitar 25–34 ms. Ini dapat mencakup
kerja driver, scheduling, atau menunggu GPU; **bukan pengukuran waktu GPU**.
CPU time thread Present yang kecil juga tidak mengukur thread game.

Gap terbesar seluruh capture, 1.834,421 ms, berada pada
T+23,931–25,765 saat loading. Jangan menyebutnya freeze kickoff sekitar
T+120. Penanda pengguna bersifat perkiraan dan sebagian record dropped.

## Apakah flush ke SD penyebabnya?

Belum terbukti. Read counter tidak mengukur write, `fflush`, atau waktu
menunggu mutex logger. Yang sudah diperiksa pada source build:

- `wine-nx-probe/source/runtime.c:2404`: thread maintenance bangun tiap
  200 ms dan melakukan `fflush(log_file)` tiap lima detik pada production.
  `log_line` mengambil `log_mutex` saat menulis; isi buffer stdio juga
  dapat terkirim ketika penuh. Thread yang masih memakai logger sinkron
  dapat menunggu mutex ini. Durasi tersebut belum dicatat.
- JIT/short trace rutin sudah melalui antrean dan flush batching. Ini
  mengurangi I/O langsung pada jalur tersebut, bukan menjamin semua
  logging sudah bebas blocking.
- `dlls/ntdll/unix/horizon_registry_server.h:192`: registry diperiksa
  setiap detik, tetapi ditulis hanya bila generation berubah. Snapshot
  dibuat di bawah object mutex; operasi SD dilakukan setelah mutex itu
  dilepas. Waktu snapshot maupun write belum tersedia pada log.
- FEX disk cache OFF menghilangkan writer cache FEX pada sesi ini;
  tidak menghilangkan write logger, registry, cache driver, atau game.

Karena itu bukti saat ini melemahkan hipotesis **pembacaan SD besar pada
kickoff**, tetapi belum menyingkirkan penulisan/flush. Frekuensi flush
sendiri bukan bukti penyebab stutter awal; maintenance tetap berjalan
pada bagian akhir yang dirasakan lebih lancar.

## Mengapa core kosong tidak otomatis menyelesaikannya?

Pada snapshot T+122,887, gameThread 164 memakai rata-rata 81,1% satu core,
main thread 62,2%, dan DXVK-CS 21,7%. Jumlah thread yang ditampilkan per
core adalah 52,1%, 69,3%, 87,3% (core native 0/1/2). Ini rata-rata interval
dan tidak mencakup seluruh kerja OS/thread, sehingga burst 100% pada
monitor pengguna tetap mungkin.

Affinity dapat memindahkan pekerjaan thread, tetapi tidak membagi satu
urutan instruksi thread game menjadi beberapa thread. Balancing DXVK-CS
pada app cores sudah aktif. Memindahkannya lagi tanpa bukti benturan
waktu tidak menghilangkan kompilasi sinkron gameThread. Clock tinggi
memberi kapasitas tambahan, bukan bukti penyebab atau perbaikan software.

## Audit jalur compiler dan cache

Source FEX lokal yang diperiksa:
`~/.cache/pes13-nx-macos/fex-experiment/source-horizon`, upstream revision
`e2f973fe931e6dc2ce523795e51ca1ac3ca85816`, dengan patch Horizon build.

- `FEXCore/Source/Interface/Core/Core.cpp:892`: `CompileBlock` melakukan
  lookup cache dalam proses, lalu optional disk lookup/load, baru
  `CompileCode`. Timer compile tidak merupakan counter hit cache.
- `Core.cpp:832`: `CompileCode` mencakup decode/GenerateIR, optimasi IR,
  dan backend ARM64. Timer sekarang belum memisahkan fase tersebut.
  Compiler FEX sendiri native ARM64; bukan compiler x86 yang juga
  diterjemahkan FEX.
- `Core/JIT/JIT.cpp`: thread baru memakai shared code buffers dan shared
  lookup state. Pembuatan gameThread baru tidak memaksa seluruh kode
  dikompilasi ulang. Kompilasi baru, invalidation, dan reuse harus
  dihitung terpisah sebelum mengubah kebijakan cache.
- `Core/DiskCache.cpp:359,496,924`: database dapat gagal dibuka; lookup
  dapat gagal karena index, identitas region/hash, atau relokasi; store
  juga dapat ditolak. `requested=1` tidak membuktikan jalur ini bekerja.
- Allocator native melayani 5.057.825 alokasi sepanjang capture; tidak
  ada allocation failure. Counter ini tidak mengukur biaya allocator.
  Reuse beberapa buffer compiler sudah ada; jangan mengklaim pooling
  sebagai solusi baru tanpa mengukur jalur yang belum direuse.

Upstream memang menyediakan disk cache kode terjemahan opt-in untuk
reuse lintas proses ([rilis resmi FEX-2609](https://github.com/FEX-Emu/FEX/releases/tag/FEX-2609)).
Namun [trial sebelumnya](FEXTENDO-CACHE-TRIAL-RESULT.md) tidak menunjukkan
manfaat yang jelas dan tidak mengukur hit/store/open sukses. Mengaktifkan
flag itu lagi tanpa memperbaiki keterukuran akan mengulang eksperimen
yang tidak dapat menjawab sebabnya.

## Target perubahan berikutnya dan kriteria keberhasilan

Prioritasnya **mengurangi kompilasi sinkron saat permainan berjalan**.
Polling/yield v3.5 mengurangi overhead pencatatan waktu, tetapi tidak
menghilangkan pekerjaan ini. Tidak ada dasar untuk menjanjikan angka FPS
atau persen pengurangan stutter dari audit ini.

1. Ukur hit cache dalam proses, compile baru/recompile, serta fase
   decode/IR/backend dengan alamat kode relatif terhadap modul. Pisahkan
   waktu CPU thread dari wall time. Gunakan counter/antrean terbatas di
   RAM dan drain background agar pengukuran tidak menambah write sinkron.
   Ukur juga waktu flush/write logger, tunggu mutex, dan snapshot registry
   untuk menutup pertanyaan SD dengan bukti.
2. Audit round-trip cache FEX: open database, index yang dibaca, store
   berhasil, lookup hit, dan kode yang benar-benar terpasang. Catat alasan
   reject. Perbaiki jalur gagal yang terbukti, lalu verifikasi pada proses
   kedua. Pisahkan namespace cache berdasarkan identitas port/codegen;
   bucket upstream belum mencakup semua perubahan patch Horizon lokal.
3. Bila reuse terbukti bekerja, gunakan blok valid yang sudah dikenal
   untuk mengurangi compile pada pembukaan selanjutnya. Prewarm sebelum
   match harus mempersiapkan pekerjaan nyata dengan modul/state valid;
   menambah durasi loading saja tidak memanaskan kode. Run pertama tanpa
   cache tetap perlu fallback, dan kode dinamis mungkin tetap compile.
4. Jika fase tertentu atau allocator terbukti dominan pada miss yang
   tersisa, optimalkan fase itu. Jangan menonaktifkan SMC, memory ordering,
   register allocation, atau validasi cache untuk mengejar angka.

Validasi harus memakai renderer, OC, preset, tim, stadion, dan camera
yang sama: fresh launch pengisian, fresh launch reuse, serta match kedua
tanpa close. Keberhasilan berarti cache load terbukti, kompilasi sinkron
berkurang pada aksi yang sama, dan interval frame membaik tanpa slow
motion/corruption. Tes berulang binary yang sama tanpa metrik baru belum
diperlukan untuk menjawab celah audit di atas.

## Reproduksi analisis

Jalankan dari root repository:

```sh
python3 tests/fextendo_warmup_analysis.py
python3 tools/analyze-fextendo-warmup.py \
  local/fex3/review-polling-20965fb3c7/device.log \
  --range 100 150 --range 350 400 \
  --output local/fex3/review-polling-20965fb3c7/warmup.json
```

Uji mencakup asal clock, event antrean yang urutannya tertunda, penolakan
clock ambigu, window melintasi batas, counter kumulatif versus interval,
histogram, dan reset counter. PASS pada host; bukan validasi performa
hardware. JSON menyimpan hash capture, nomor baris sumber, batas waktu,
dan keterbatasan interpretasi.
