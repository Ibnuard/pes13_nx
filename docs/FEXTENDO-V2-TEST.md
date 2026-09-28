# Uji FEXTendo v2 dan pencocokan timestamp

Status saat panduan ini dibuat: pengguna **belum mencoba v2**. Log yang ada
masih build `pes13-fextendo-mem-audit` dan identik dengan input analisis v2
(SHA-256 `99c459c5ac19874b5ee366519f03cab7a276001399df4732831341f67bb7c447`).
Belum ada bukti perangkat bahwa v2 mengurangi stutter. ZIP v2 tidak diubah
oleh penambahan alat analisis ini; tidak perlu mengunduh build baru.

## Run yang dibutuhkan

1. Tutup game, salin seluruh `switch/` dari `dist/pes13-fextendo-v2.zip` ke SD.
2. Pertahankan preset, clock dan cache dari run pembanding sebelumnya.
3. Di kartu Settings, aktifkan **Debug timestamp**, lalu Play.
4. Rekam first kickoff, bola cepat/shooting dan pertandingan kedua. Saat
   stutter, catat waktu `T+` yang terlihat. Jika stopwatch ikut berhenti,
   catat waktu sebelum dan sesudahnya juga.
5. Tutup game lalu salin `fex-runtime.log` ke `TEST RESULT/`.

Marker log untuk memastikan paket terpasang:

```text
[BUILD] pes13-fextendo-v2-budget
[FEX3-MEMBUDGET] client_extension=0
[FEXTENDO-TIME] origin_tick=...
[FEXTENDO-TIME] overlay ready ...
```

Jika `overlay unavailable` muncul, game tetap bisa berjalan tetapi tidak ada
stopwatch yang terlihat; simpan pesan error lengkapnya. `client_extension=1`
menunjukkan override pengaktifan kembali query masih terpasang. Ini bukan
default uji v2. Perbandingan timestamp OFF dapat dilakukan pada run terpisah
untuk melihat pengaruh overlay sendiri.

## Analisis log

Jalankan dari root proyek, memakai Python 3 tanpa dependency tambahan:

```sh
python3 -B tools/analyze-fextendo-run.py 'TEST RESULT/fex-runtime.log' \
  --baseline dist/pes13-fextendo-v2/evidence/input/fex-runtime.log \
  --output local/fex3/fextendo-v2/followup-analysis.json
```

Untuk kejadian di video, misalnya **T+ 00:01:32.4**, tambahkan
`--at 01:32.4 --window 2`. Waktu tersebut hanya contoh; ganti dengan waktu
kejadian yang benar. `--window` adalah jumlah detik di kedua sisi kejadian.

Laporan berisi identitas build, status query/overlay, ringkasan sampel,
nomor baris log, pencarian dua menit pertama, sepuluh gap terbesar, serta
gap dan query pada rentang `selected_event` bila `--at` digunakan.
Pencocokan memakai system tick dan native handle yang sama; urutan tulisan
log tidak menjadi acuan waktu karena logger menggunakan antrean.

CPU counter yang gagal ditandai tidak diketahui. Log tanpa origin Play,
beberapa origin, build tercampur atau timestamp yang tidak konsisten tidak
dipetakan ke T+ secara spekulatif. Captures yang identik ditandai
`comparison.same_capture=true`, bukan dianggap sebagai hasil sesudah perbaikan.

Gap yang tercatat terbatas pada >50 ms dan query individual >=1 ms, dengan
kapasitas antrean terbatas. Tidak adanya baris bukan bukti bahwa tidak ada
stutter. Jumlah gap antar-run juga tidak langsung menjadi persentase
perbaikan: durasi, adegan, preset dan clock harus dibandingkan.

Tes alat: `python3 -B tests/fextendo_analysis.py -v`.
