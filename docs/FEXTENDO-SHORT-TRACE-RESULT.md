# Hasil perangkat short-trace v1 dan eksperimen DXVK core 3

Log terbaru merekam short-trace v1 aktif, termasuk clock JIT 19,2 MHz dan overlay.
SHA-256 input `c217f83d39bea79e9a464c413e58c3fa62e24bf8be1405ea6c41f0624ecee3d5`,
1.477.259 byte. Salinan immutable dan JSON event berada di
`local/fex3/review-short-trace-c217f83d39/`. Marker build tidak meng-hash NRO
terpasang; receipt binary yang didistribusikan tetap tersimpan terpisah.

Origin Play: `10552003464647`. Pengguna menandai T+01:50 (kickoff freeze),
02:07 (umpan cepat), 02:25, 02:38, 03:07 (stutter); di atas 03:25 terasa lancar.
Pengguna mengonfirmasi transisi menjelang lancar adalah **replay lalu kickoff
kiper lawan**, bukan restart aplikasi. Snapshot thread dan scene dapat berubah
pada transisi ini, sehingga ini bukan perbandingan A/B adegan identik.

## Event yang cocok

Window di bawah adalah ±2 detik dari tanda pengguna. Ini sampel Present >50 ms,
bukan jumlah freeze yang dirasakan atau seluruh frame. Semua interval memakai
tick kejadian, bukan posisi record dalam file yang ditulis secara batch.

| Penanda T+ | Gap tersimpan | Gap maksimum | Wait main TID 4 maksimum | Wait TID 12 maksimum |
| --- | ---: | ---: | ---: | ---: |
| 01:50 kickoff | 10 | 103,592 ms | 81,887 ms | 87,790 ms |
| 02:07 umpan cepat | 1 | 53,488 ms | 27,395 ms | 27,176 ms |
| 02:25 | 2 | 53,683 ms | 44,297 ms | 36,684 ms |
| 02:38 | 3 | 76,966 ms | 49,971 ms | 39,662 ms |
| 03:07 | 8 | 90,324 ms | 58,183 ms | 69,476 ms |
| 03:35, terasa lancar | 0 | — | tidak tersimpan >=20 ms | 23,141 ms |

Seluruh sesi: 286 gap tersimpan, 63 gap terbuang dari antrean lama. Trace baru
menyimpan 6.879 record native dan 236 teks JIT; drop masing-masing 5 dan 0,
serta 204 kegagalan memasangkan wait/wake. Angka ini kumulatif, tidak dijumlah
ulang per laporan. Gap terbesar 1.683,066 ms berakhir T+69,719, sebelum kickoff
pengguna. Tidak ada timeout heap `RtlpWaitForCriticalSection` atau capture
hang pada sesi ini. Masalah timeout pada capture lama tetap belum terulang,
dan tidak dapat dinyatakan selesai berdasarkan ketidakhadirannya di sini.

## Temuan thread dan kompilasi

Pemetaan baru mengidentifikasi **Present/submit TID 12**, handle 2556358
(baris 1192). Di gameplay, main TID 4 dan TID 12 berada di core 1; worker game
TID 164 di core 2; TID 24 di core 0. Indeks core adalah 0,1,2,3. Core 3 adalah
core keempat. Pengaturan sekarang hanya menempatkan worker otomatis di 0–2.

TID 164 dibuat dengan entry `0x4da0e3` dalam executable PES (baris 5395).
Window kompilasinya **T+108,308–112,458** memuat 1.039 `compile_code`, total
1.866,417 ms dan satu panggilan terlama 32,069 ms (baris 6139). Main TID 4 pada
window yang berdekatan hanya 14 compile / 11,618 ms. Jadi beban kompilasi baru
pada kickoff jauh lebih jelas terlokalisasi pada worker game. Total 1,87 detik
adalah akumulasi dalam rentang 4,15 detik; **bukan freeze tunggal 1,87 detik**
dan tidak membuktikan bahwa setiap stutter disebabkan JIT.

TID 164 masih mengompilasi pada window T+142,485–147,447: 226 panggilan /
642,693 ms; T+157,493–162,418: 313 / 728,694 ms; T+182,708–187,496:
293 / 858,045 ms. Setiap total adalah window utuh, bukan jatah tepat pada
penanda pengguna. Window T+108–112 termasuk compile lambat tunggal 20,167 ms
pada T+110,460–110,480; banyak compile yang lebih kecil tidak mempunyai record
individual, tetapi ikut ringkasan.

Setelah transisi replay, worker berat berganti (184 lalu 196) dan penempatannya
juga berubah. TID 184 masih mencatat 348 compile / 536,147 ms pada
T+212,551–217,320 meski pengguna merasa lancar. Sesudah T+230, window lengkap
sampai T+250 mencatat TID 196 sebanyak 95 compile / 261,934 ms. Warm-up berkurang,
tetapi tidak hilang total; pergantian scene/worker juga berpengaruh pada
perbandingan sebelum dan sesudah replay.

## Jalur tunggu grafis

Di sekitar kickoff, wait TID 12 teramati dibangunkan TID 24. TID 24 dibangunkan
main TID 4. Main TID 4 dibangunkan TID 12 atau 16; TID 16 juga menjalani wait
semaphore Vulkan. Ini menunjukkan urutan penyerahan kerja antarthread, bukan
bukti deadlock atau pemilik heap. Contoh T+110,703–110,791: TID 12 wait 87,790 ms,
waker terakhir 24. Contoh T+111,166–111,248: main wait 81,887 ms, waker 16.

Pada sekitar T+156,784, submit TID 12 dan semaphore TID 16 sama-sama sekitar
49,7–50,0 ms; main wait sekitar 50 ms. Waktu CPU TID 12 selama gap Present di
semua penanda umumnya kurang dari 1 ms (median window 0,63–0,85 ms). Waktu
tersebut mencakup antrean/scheduling/wait, bukan pengukuran durasi GPU.

`object=0` pada wait dalam sesi ini merupakan nilai argumen API yang dicatat;
Wine menggunakan alert per thread pada jalur ini. Itu tidak mengidentifikasi
alamat heap. Wait TID 28 sepanjang puluhan detik melintasi banyak penanda;
thread ini dapat sedang idle, jadi durasi panjangnya tidak boleh dilabeli
freeze pertandingan. TID 28 dibuat pada inisialisasi compiler DXVK.

Nama worker belum dicatat oleh baseline. Berdasarkan entry wrapper DXVK yang
sama, urutan pembentukan thread dan jalur native yang diamati, TID 12 konsisten
dengan `dxvk-submit`, 16 dengan `dxvk-queue`, dan 24 kandidat `dxvk-cs`.
**Label nama masih inferensi**. Build eksperimen merekam nama dari API Wine
sebelum mengubah affinity; tidak mem-pin TID 24 secara hardcoded.

[DXVK queue v3.1.1](https://github.com/doitsujin/dxvk/blob/v3.1.1/src/dxvk/dxvk_queue.cpp)
memisahkan submit dan completion;
[CS worker](https://github.com/doitsujin/dxvk/blob/v3.1.1/src/dxvk/dxvk_cs.cpp)
memproses command stream. `SetThreadDescription` memberi nama worker melalui
Wine; versi source DXVK sesuai versi 3.1.1 yang dilaporkan log.

## Pipeline dan penempatan core

Batch dekat kickoff T+112,223 mencatat nol graphics pipeline baru. Sebagian
besar batch sampai T+192,752 juga nol; batch T+152,488 memuat sembilan pipeline /
85,125 ms total, tanpa satu panggilan >50 ms. Pembuatan pipeline bukan penjelasan
tunggal seluruh stutter. Cache shader DXVK berbeda dari cache kode FEX.

Worker game berat sudah terpisah: sekitar gameplay TID 164 memakai 80–83%
core 2, main 55–69% core 1, TID 24 sekitar 19–26% core 0. Angka ini mendukung
pengujian pemisahan kerja DXVK, tetapi **tidak membuktikan core 3 akan lebih
cepat**, atau core 0 menganggur. Setelah lancar, worker berat justru berada di
core 0 pada beberapa snapshot. Memaksa semua worker game kembali ke 1–2
sekaligus akan mencampur dua variabel eksperimen.

## Eksperimen yang dibuat

Pendekatan [Autorun pada commit c2268252](https://github.com/autorunhq/autorun/blob/c2268252a28abb5977fec8ea385b43f0e9519a5f/horizon-wine/source/thread_profile.c)
memilih worker grafis berdasarkan nama dan memakai core 3 dengan priority 63,
dengan syarat capability tersedia dan affinity belum dipilih game. Ini bukan
memindahkan seluruh DXVK atau seluruh thread ke core keempat.

Trial FEXTendo menerapkannya untuk **`dxvk-cs` saja**. Balancer 0–2, thread game,
clock, jumlah compiler, FEX DLL dan konfigurasi grafis dipertahankan. Kontrol
ON/OFF memakai NRO yang sama; nama/mask/priority/result dibaca kembali untuk
memastikan offload benar-benar terjadi. Ini adaptasi kode/desain Autorun,
dengan penanganan rollback dan pembatasan scope proyek sendiri; kredit di
`THIRD_PARTY.md`. Patch bukan klaim sudah menghilangkan freeze pertama.

Jika A/B core 3 tidak membantu, data JIT game-thread memberi arah berikutnya:
penelusuran beban kompilasi awal pada worker game, terpisah dari eksperimen
scheduler. Jangan sekaligus mengubah blok JIT, cache, OC dan affinity sehingga
hasil tidak bisa diatribusikan.
