# Review sesi Switch 29 September 2026

Capture ini berisi gameplay, berbeda dari log menu yang sebelumnya tertimpa.
Pengguna melaporkan stutter saat kickoff, tembakan pertama dan bola lambung,
lalu stabil setelah aksi tersebut diulang. Log mendukung adanya pekerjaan awal
yang mahal, tetapi juga menunjukkan satu timeout sinkronisasi yang harus
diselidiki terpisah. Belum ada bukti bahwa satu perubahan shader akan
menghilangkan semua jenis freeze.

## Identitas bukti

- Input: `TEST RESULT/fex-runtime.log`, 525.644 byte / 4.597 baris.
- SHA-256: `a7e19a355925a607a85f89bf67192017f2cbeeb270813fe30ec19b8485424cfa`.
- Salinan lokal dibekukan di `local/fex3/fextendo-v3.2/evidence/device-2026-09-29.log`.
- Analisis terstruktur: `evidence/device-review.json` di paket v3.2. Log mentah
  tidak dimasukkan ke paket. Waktu T+ dihitung dari `origin_tick` saat Play,
  dengan 19.200.000 tick/detik, bukan urutan penulisan log.

## Timestamp tidak muncul

Baris 426 merekam `overlay unavailable stage=display rc=0x1272`. Kegagalan terjadi
sebelum pembuatan layer dan sebelum satu frame overlay dikirim. Fullscreen Wine
bukan penjelasan untuk kegagalan setup ini.

[Lifecycle default window libnx](https://github.com/switchbrew/libnx/blob/master/nx/source/display/default_window.c)
membuka display Default sebelum `main`. Implementasi lama meminta Default lagi
dalam sesi VI yang sama. v3.2 menangkap hasil pembukaan awal lewat linker wrapper
`viOpenDisplay`, meminjam display itu, lalu membuat layer overlay tersendiri dengan
application resource user ID milik aplikasi. Kepemilikan display tetap pada
libnx. Jalur penutupan overlay tidak menutup display/window game.

Disassembly ELF v3.2 memastikan `__nx_win_init` benar-benar memanggil wrapper;
uji host mencakup pembukaan ganda yang gagal, kepemilikan display, kegagalan
setup layer/framebuffer, dan cleanup thread. **Visibilitas di Switch belum
terverifikasi.** Log baru membedakan `display ... borrowed=1`, `overlay ready`,
dan `first overlay frame submitted`, atau nama tahap setup yang gagal.

## Freeze besar dan sinkronisasi heap

| Akhir gap (T+ sejak Play) | Durasi gap Present | CPU thread selama gap |
| --- | ---: | ---: |
| 107,603 detik | 5.228,539 ms | 776 us |
| 25,175 detik | 2.599,454 ms | 582 us |
| 69,544 detik | 2.026,012 ms | 690 us |

Probe mengambil selisih kernel CPU tick thread antara dua akhir Present.
Angka kecil menunjukkan thread Present lebih banyak menunggu atau tidak
dijadwalkan selama gap; tidak mengukur beban seluruh core atau thread game
yang lain. Acquire/submit/fence pada sampel gap 5,23 detik juga hanya sekitar
0,668 / 11,090 / 11,370 ms. Itu tidak menjelaskan keseluruhan jeda beberapa detik.

Di sekitar capture hang, baris 2180 merekam `RtlpWaitForCriticalSection` untuk
`main process heap section`: timeout pada thread `0018`, `blocked by 0000`,
lalu retry 60 detik. Kode Wine menggunakan timeout pertama 5 detik, konsisten
dengan skala jeda yang terlihat. Angka `blocked by 0000` tidak membuktikan siapa
pemilik sebelumnya atau sebuah deadlock permanen; keadaan owner bisa sudah
berubah ketika pesan dicetak.

Symbolication menggunakan ELF v3.1 yang cocok, dengan load base `0x50d76000`
yang diperiksa dari beberapa alamat SVC. Dua sampel main thread berhenti di
`svcWaitForAddress`, dengan caller `horizon_futex_wait` →
`NtWaitForAlertByThreadId` → Wine syscall dispatch. Banyak worker lain memang
sedang menunggu. Pesan heap tidak memiliki event tick sendiri, sehingga
kedekatan dengan gap bukan bukti kausalitas tunggal. Namun temuan ini cukup
kuat untuk memprioritaskan audit address-wait/wake dan contention heap.

v3.2 tidak memendekkan timeout, membuka paksa lock, menambah thread, atau
mengubah affinity/clock berdasarkan capture ini. Perbaikan sinkronisasi harus
lebih dahulu menunjukkan wake yang hilang atau owner yang menahan lock,
termasuk urutan publish flag → wake dan nilai kembali address arbitration.

## Pekerjaan awal yang mahal

- 1.230 pembuatan graphics pipeline, akumulasi wall time 8,943 detik; 18 panggilan
  di atas 50 ms, puncak 101,049 ms. Driver cache mencatat hit; hit dapat berasal
  dari sesi yang sama dan tidak membuktikan cache disk berhasil dipulihkan.
- Sampel FEX `compile_code` terakhir: 40.370 panggilan, akumulasi 41,743 detik,
  puncak 74,621 ms; 78 di atas 20 ms dan 4 di atas 50 ms.
- Window awal memuat SD/read selama beberapa detik. Window sesudah pemanasan
  banyak yang sangat rendah, dengan beberapa gelombang pipeline baru kemudian.

Total kompilasi/pipeline bukan tambahan waktu frame: pekerjaan dapat berjalan
pada thread berbeda, dan statistik phase lain bisa saling mencakup. Data
menunjukkan pekerjaan saat jalur kode/material/aset pertama digunakan; belum
membedakan persis mana kickoff, tembakan atau bola lambung tanpa penanda aksi
atau video bertimestamp. Antrean gap juga bounded dan melaporkan sampel yang
terbuang, sehingga log bukan frame trace lengkap atau bukti semua frame stabil.

Statistik menu lama: 1.029 frame, rata-rata draw+Present 23,079 ms, maksimum
47,941 ms, target 60 Hz. Itu mencakup menunggu display dan bukan FPS game.
Benchmark renderer host v3.2 dilaporkan terpisah; bukan pengganti pengukuran Switch.

## Reproduksi

```sh
python3 tools/analyze-fextendo-run.py 'TEST RESULT/fex-runtime.log' --at 107.603 --window 6 --output run-analysis.json
```

Gunakan capture dengan hash di atas untuk angka dokumen ini. Pembukaan launcher
v3.2 menyimpan empat sesi sebelumnya sebagai `fex-runtime.previous-1.log` sampai
`fex-runtime.previous-4.log`, sehingga membuka menu sekali lagi tidak langsung
menghilangkan sesi permainan terakhir.
