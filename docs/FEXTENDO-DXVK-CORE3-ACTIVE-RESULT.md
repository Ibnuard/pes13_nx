# DXVK core 3 aktif — analisis beban awal match

Capture SHA-256
`e5de465b0c1c4524962209c715f1e1c134f4c9a3d5d8236664e30e13fc0f5ca8`,
2.289.139 byte, marker `pes13-fextendo-dxvk-core3-v1`. Salinan immutable,
event JSON, histogram batch, dan `review.json` berada di
`local/fex3/review-dxvk-core3-e5de465b0c/`.

Penanda pengguna T+01:55, 02:19, 02:30 hanya beberapa contoh stutter.
Pengguna mengonfirmasi capture ini **satu match**. Pengamatan bahwa kickoff
match kedua lancar tanpa menutup aplikasi berasal dari tes semalam, bukan
perbandingan dua match yang dapat diukur dari capture ini. Permintaan saat
review adalah memeriksa log dahulu; tidak ada perubahan runtime atau build
binary baru dari analisis ini.

## Affinity sudah berhasil

Baris 62:

```text
[FEX3-DXVKCORE] v1 requested=1 enabled=1 cores=f priorities=fffffffff0000000 core_rc=0 priority_rc=0 auto_core3=0
```

Baris 874 mengonfirmasi `name=dxvk-cs tried=1 active=1 core=3 mask=8
priority=63`, dengan seluruh result dan readback nol. Semua **41** snapshot
COREMAP yang memuat TID 24 menunjukkan mask 8. Pencocokan harus memakai TID
24 utuh, bukan substring `24:` yang juga cocok dengan TID 124.
Worker game tetap dibagi ke 0–2. Syarat forwarder kini terpenuhi.

Ini membuktikan offload terjadi, belum mengukur keuntungannya: belum ada
capture OFF dengan forwarder empat core, match dan kondisi identik. Membandingkan
dengan log sebelumnya juga mencampur perubahan izin/proses dan scene.

## Tiga penanda stutter

Origin Play `10640368602966`, clock 19,2 MHz, overlay ready, short trace ON.
Record gap di tabel dipilih **±2 detik** dari penanda. Histogram PACE memakai
batch sekitar 10 detik, waktunya diperkirakan dari SHORT-STATS dalam putaran
logger sama; bukan urutan frame atau waktu scanout layar. PACE elapsed tidak
dimulai dari tombol Play.

| Penanda | Gap akhir Present >50 ms tersimpan | Batch histogram sekitar T+ | Rata-rata jarak masuk Present | Interval 33,334–50 ms |
| --- | --- | --- | ---: | ---: |
| 01:55 | Tidak ada dalam ±2 s | 106,954–117,000 s | 21,871 ms | 64/459 = 13,9% |
| 02:19 | 5; maksimum 94,567 ms | 137,102–147,151 s | 23,158 ms | 28/434 = 6,5% |
| 02:30 | 1; 56,876 ms | 147,151–157,232 s | 19,284 ms | 43/524 = 8,2% |

Pada 01:55, 214/459 interval batch juga berada di 20–33,334 ms. Tidak ada
record >50 ms tepat di window bukan berarti frame rata. Sebagian stutter
kamera dapat terlihat di bawah ambang trace ini.

Pada penanda 02:19, gap terpanjang terjadi T+140,243–140,338. TID 12 hanya
menggunakan 0,654 ms CPU pada interval 94,567 ms. Wait submit 64,776 ms
(waker 24), main wait 61,599 ms (waker 12), dan completion wait 69,917 ms
(waker 12) saling bertumpang tindih. Waktu tersebut tidak boleh dijumlahkan;
ini observasi antrean kerja, bukan pengukuran langsung GPU atau bukti lock
heap. Pada penanda 02:30, gap 56,876 ms berakhir T+148,205, dekat awal window.

Native Present pada tiga batch rata-rata 1,085 / 0,874 / 0,653 ms; lock
Present rata-rata tercatat 0 us setelah pembulatan. Belum ada bukti mutex
Present sebagai sumber utama. Waktu submit/fence/semaphore mencakup scheduling.

## Shader/pipeline dan kode game adalah dua hal berbeda

**DXVK sudah membaca file shader cache.** Baris 898 dan 900:

```text
info: Found cache file: C:\dxvk-cache\86eaf3d9f8690dcd.dxvk.bin
info: Cache: 498 shaders (2.3 MB)
```

DXVK v3.1.1 melaporkan satu compiler thread, bernama `dxvk-shader-l` (TID 28).
Fitur graphicsPipelineLibrary dan shaderModuleIdentifier dilaporkan aktif.
Ini membuktikan file shader ditemukan/dibaca, bukan bahwa semua kombinasi
pipeline yang akan dipakai sudah selesai dipersiapkan sebelum kickoff.

Batch yang mencakup 02:19 mencatat **97 panggilan pembuatan graphics pipeline,
859,225 ms total**, dua panggilan >50 ms. Itu total sekitar 10 detik, bukan
satu freeze 859 ms; tidak ada timestamp per pipeline untuk menempatkan
seluruh biaya tepat pada penanda 02:19. Batch 01:55 nol pembuatan pipeline
baru; batch 02:30 lima, 25,731 ms total. Jadi pipeline relevan pada sebagian
kejadian, tetapi tidak menjelaskan semuanya. Counter driver-cache hit juga
dapat mencakup data dari proses saat ini, bukan bukti seluruh cache bertahan
dan siap lintas peluncuran.

**FEX menerjemahkan kode CPU game.** Worker bernama `gameThread`, bukan
compiler shader, masih menunjukkan beban berikut:

| Worker | Window T+ | Panggilan compile_code | Total kompilasi | Peak satu panggilan |
| --- | --- | ---: | ---: | ---: |
| TID 164 | 108,642–112,974 s | 1.594 | 2.907,441 ms | 33,381 ms |
| TID 164 | 112,997–117,977 s | 463 | 1.075,581 ms | 13,501 ms |
| TID 164 | 138,093–142,930 s | 995 | 1.563,306 ms | 15,266 ms |
| TID 176 | 147,988–152,972 s | 149 | 368,911 ms | 12,073 ms |

Total tiap window adalah akumulasi pekerjaan, bukan freeze tunggal atau biaya
satu frame. Di sekitar 01:55, worker game memakai sekitar 82,4% satu core,
main 60,9%, dan dxvk-cs 23,5% core 3. TID 168 `grRatingThread` juga dibuat
sekitar T+140,267 dan mengompilasi 99 kali / 168,082 ms dalam window singkat;
pergantian worker/scene bukan bukti kickoff match baru.

Untuk window kompilasi gameThread yang **seluruh intervalnya** berada di
T+100–160: 13 window, 4.409 panggilan, 8.885,823 ms total. T+300–360:
10 window, 177 panggilan, 388,256 ms total. Ini mendukung berkurangnya beban
kompilasi seiring sesi berjalan, tetapi bukan perbandingan adegan identik;
window yang melintasi batas sengaja tidak dibagi atau dimasukkan.

Baris 100 menunjukkan `[FEX3-DISKCACHE] requested=0`: cache kode FEX ke
penyimpanan masih OFF. Cache shader DXVK tidak menggantikan cache kode CPU
ini. Pilihan FEX disk cache sudah ada pada runtime, tetapi manfaat/hit dan
persistensinya pada port ini belum terbukti. Jalur disk cache juga melewati
optimasi guard tertentu, sehingga tidak boleh dipromosikan sebagai solusi
gratis atau otomatis diaktifkan berdasarkan nama opsi saja.

## Penilaian ide precompile di awal

Laporan match kedua lancar tanpa menutup aplikasi dan turunnya kompilasi
dalam sesi mendukung hipotesis **pekerjaan saat penggunaan pertama**.
Kandidatnya mencakup kode FEX, pipeline grafis, serta inisialisasi/resource
yang bertahan selama proses hidup. Log belum memisahkan kontribusi semuanya.

Tahap persiapan sebelum bermain masuk akal jika benar-benar menjalankan
pekerjaan yang dibutuhkan atau memuat hasil yang valid. Namun hanya menambah
layar “compiling shaders”, menunggu sejumlah detik, atau menganggap 498 shader
cache berarti semua pipeline siap tidak menyelesaikan bagian FEX. Belum ada
dasar menjanjikan seluruh kompilasi cukup sekali selamanya; jalur/varian baru
belum tentu pernah ditemukan pada match sebelumnya.

Prioritas audit berikutnya: buktikan pemakaian kembali kode FEX dan cache
pipeline antar peluncuran, serta deteksi selesai persiapan yang nyata sebelum
membuat loading/precompile UI. Untuk shader, ukur pipeline yang masih dibuat
saat bermain; untuk FEX, ukur cache hit dan penurunan compile pada peluncuran
berikutnya dengan adegan sama. Ini arah investigasi, bukan patch yang telah
diimplementasikan atau permintaan mengubah konfigurasi tes saat ini.

Tidak ada timeout heap `RtlpWaitForCriticalSection` atau capture hang.
Seluruh sesi: 484 gap >50 ms tersimpan, 99 gap dibuang; 10.599 short records,
5 drop, 290 teks JIT, 0 drop, 396 kegagalan pairing wait/wake. Banyak wait
compiler merupakan idle normal. Gap maksimum seluruh capture 1.522,145 ms
tidak diasumsikan sebagai kickoff; penanda pengguna hanya sampel.
