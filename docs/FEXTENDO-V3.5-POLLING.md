# FEXTendo v3.5 — overhead polling waktu dan yield

App **0.3.6**, build `pes13-fextendo-polling-v1`. Kandidat ini menerapkan
optimasi dari audit v3.4. Dampak stutter/FPS pada Switch belum diukur.

## Perubahan yang diterapkan

Log yang diaudit mencatat sekitar 537 ribu QPC dan 506 ribu delay pada
satu interval laporan sekitar 10 detik. Pemanggilan sebanyak ini juga
membayar overhead pencatatan runtime, selain transisi FEX/WOW64.

- Counter QPC/delay sekarang ditulis ke slot milik masing-masing thread.
  Setelah pendaftaran sekali, jalur tersebut tidak lagi melakukan dua
  atomic read-modify-write pada counter global setiap panggilan. Angka
  tetap digabungkan ke laporan `syscalls`/`sys_top`, termasuk setelah
  thread berakhir. Tersedia 256 slot (16 KiB); jika penuh atau reentrant,
  pencatatan kembali ke counter lama.
- `Sleep(0)` memakai ulang sampel waktu yield untuk statistik delay:
  pembacaan clock normal turun **4 → 2**; saat backoff **6 → 3**.
  Direct yield dan Sleep(0) berbagi riwayat burst seperti sebelumnya.
  Statistik durasi jalur baru menggunakan clock beresolusi 100 ns,
  dilaporkan dalam mikrodetik.

Nilai/frekuensi QPC, kecepatan waktu game, deadline sleep, alertable wait,
dan jalur APC tetap mengikuti Wine. Kebijakan backoff tetap 64 yield
tidak produktif dalam jendela 2 ms, ambang 2 µs, pause 50 µs. Kandidat ini
tidak menghilangkan transisi FEX/WOW64, kompilasi JIT/shader awal, atau
pekerjaan GPU. Tidak ada perubahan pooling allocator pada paket ini.

Balancing core, hash lookup FEX, JIT128, renderer, serta LSFG sama dengan
v3.4. DLL FEX tidak berubah. Frame generation tetap OFF secara default;
`Lossless.dll` 3.2.1.0 pengguna yang sudah diperiksa belum kompatibel dengan
backend SPIR-V ini. Tidak ada DLL tersebut atau data game di dalam paket.

## Pemasangan

1. Tutup FEXTendo. Dari ZIP, salin **hanya `switch/` paling luar** ke root
   SD dan timpa file yang sama, di atas instalasi v3.4 yang berjalan.
2. Path tetap `switch/pes13-fex/pes13-fex.nro`. Forwarder yang membuka
   path ini tetap dapat digunakan; yang menanam binary NRO perlu
   diperbarui. Paket tidak menimpa save, INI atau preferensi launcher.
3. Jika key berikut sudah ada di `configuration.ini`, sesuaikan karena
   INI didahulukan atas file flag. Tidak perlu mengganti seluruh INI:

   ```ini
   fex_polling=1
   fex_dxvk_balance=1
   fex_auto_core3=0
   fex_jit_small=1
   fex_jit_large=0
   ```

   Pertahankan `no_balance=0` bila key itu ada. Tanpa key INI, flag paket
   mengaktifkan kandidat. Perubahan flag berlaku pada pembukaan berikutnya.

## Tes perangkat

Gunakan **DXVK 3.1.1**, Frame generation **OFF**, dan Debug timestamp ON.
Pertahankan preset, OC, tim, stadion serta camera tes sebelumnya. Tutup
aplikasi penuh, buka lagi, lalu mainkan dua match tanpa menutup aplikasi
di antaranya. Catat timestamp kickoff, shoot, bola lambung dan stutter;
simpan log sebelum membuka launcher lagi.

Konfirmasi marker log:

```text
pes13-fextendo-polling-v1
[FEX3-POLL] v1 enabled=1 ...
[FEX3-DXVKPOLICY] v2 balance=1 ... effective_offload=0
[FEX3-JIT-CONFIG] maxinst=128
```

Jumlah syscall tetap tercatat; penurunan overhead tidak berarti jumlah
QPC/delay harus turun. Bandingkan interval frame, durasi pause dan
timestamp stutter dengan durasi match serta pengaturan yang sama.

## Pembanding dan rollback

| Folder untuk disalin ke root SD | Efek |
| --- | --- |
| `switch/` | Kandidat polling ON. |
| `control-polling/switch/` | Binary v3.5 tetap dipakai, polling OFF; mengisolasi perubahan ini. |
| `rollback/switch/` | Mengembalikan NRO/FEX persis v3.4 beserta balancing/JIT128. |

Untuk pembanding, pasang `switch/` utama dahulu, lalu satu folder kontrol.
Jika INI memiliki `fex_polling`, ubah menjadi `0` untuk kontrol atau
rollback; kembalikan `1` untuk kandidat. Balancing tetap `1` pada semuanya.
Tidak perlu menghapus cache atau mengubah renderer. Folder `source`,
`upstream`, `evidence`, `licenses`, dan folder kontrol bukan instalasi utama.

## Validasi dan sumber

Paket memerlukan 19 kelompok pemeriksaan yang lolos dan terikat ke hash
binary/source. Uji polling memakai fungsi produksi, ASan/UBSan, delapan
thread/80.000 panggilan, counter saat thread aktif/keluar, fallback saat
slot penuh, wrap, mode OFF, dan dispatch argumen. Uji binary ARM64
memeriksa Sleep(0), direct yield, productive yield, oversleep serta deadline
relatif. Pembalikan patch sync/dispatch harus mengembalikan sumber v3.4
secara identik. Tiga laporan FEX dipakai ulang karena modul dan sumber
pengujiannya tidak berubah; pengujian runtime diulang pada ELF baru.

Hasil tersedia di `evidence/checks/`. Ini belum merupakan tes hardware
atau bukti freeze kickoff sudah hilang. Source modifikasi dan backend
LSFG GPL, patch, resep build serta kredit tersedia dalam paket.
FEX tetap FEX-Emu; port Switch/integrasi FEXTendo dikerjakan
AndroSwitch Project / Ibnuard. Lihat `THIRD_PARTY.md` untuk atribusi lengkap.
