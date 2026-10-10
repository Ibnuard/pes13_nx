# PES13 fixed-bias benchmark 0.2.0

Eksperimen berikutnya setelah probe AS32/AS39: ukur biaya penerjemahan alamat
guest 32-bit ke alamat host tinggi menggunakan satu offset tetap. Ini **belum
runtime PES13 39-bit** dan tidak membuka EXE, DLL, save, atau konfigurasi game.

## Menjalankan di Switch

1. Salin folder `switch` dari paket ini ke root SD. NRO menggantikan **probe
   eksperimen** sebelumnya di `switch/pes13-as39-probe/pes13-as39-probe.nro`.
2. Buka tile **PES13 39-bit Probe** dari HOME. Forwarder AS39 yang sudah dipasang
   pada tes sebelumnya tetap bisa dipakai; tidak perlu instal ulang. Salinan
   identik tersedia di `forwarders/PES13-AS39-Probe.nsp` bila dibutuhkan.
3. Pertahankan clock CPU/GPU/RAM sepanjang tes. Stock cukup untuk tes pertama.
   NRO ini tidak mengubah clock. Jangan membandingkan satu varian pada stock
   dan varian lainnya pada OC; keduanya otomatis diuji dalam satu proses.
4. Tunggu `[SUMMARY] BENCH-COMPLETE`, lalu tekan `+` untuk keluar. Tes berlangsung
   otomatis, biasanya puluhan detik; durasi perangkat belum diukur. `+` juga
   bisa membatalkan tes di antara pasangan sampel.
5. Kirim `sdmc:/switch/pes13-as39-probe/as39-bias-bench.log`.

Jangan membuka dari tile produksi, AS32 Probe, atau hbmenu. Mode yang salah
akan ditolak sebelum pemetaan/benchmark. Log sebelumnya dipertahankan sebagai
`as39-bias-bench.previous.log`. Kedua file ini berada di direktori probe saja.
Tidak ada ZIP dan tidak ada pemasangan runtime/game baru.

## Yang benar-benar diuji

- Reservasi **4 GiB alamat virtual** pada host 39-bit, bukan alokasi RAM fisik
  4 GiB. Backing data terbesar hanya 4 MiB dan dipakai ulang.
- Alamat guest `0x00400000` tetap terlihat sebagai nilai 32-bit, sedangkan
  data sebenarnya diakses pada `host_bias + 0x00400000` di atas 4 GiB.
- Pointer guest dengan bit tinggi, penjumlahan alamat 32-bit yang wrap,
  konversi pointer di batas guest/native, serta penolakan span yang melampaui
  domain 32-bit. Halaman null di dalam window tidak dipetakan.
- Lima pola akses: pointer berantai, scalar read/modify/write, vektor 128-bit,
  pasangan load/store 64-bit, dan atomik acquire/release tanpa kontensi.
- Perbandingan kernel ARM64 langsung versus offset tetap. Scalar/vector dapat
  menggunakan base+register; LDP/STP dan exclusive load/store membutuhkan ADD
  tambahan. Semua memakai adapter RW/RX JIT native FEX milik proyek.

Kernel ditulis sebagai prototipe instruksi ARM64. **Ini bukan kode yang
dihasilkan FEXCore yang sudah dimodifikasi**, bukan emulasi program x86, dan
bukan benchmark 3D/PES. Kelulusan tes ini hanya menentukan apakah jalur alamat
ini layak dilanjutkan ke integrasi FEX/Wine.

## Metode pengukuran

Kontrol langsung memakai guest `0x10000000` yang dapat dipetakan pada host
39-bit. Varian offset memakai data/pointer guest yang sama di window tinggi.
Backing fisik yang sama di-unmap/remap secara berurutan, bukan menyalin data
ke RAM fisik berbeda untuk kedua varian. Operasi map/unmap, inisialisasi,
verifikasi, baca clock, console, dan SD log ada di luar interval yang diukur.

Ada 15 kasus (5 pola x 16 KiB/256 KiB/4 MiB), masing-masing 9 pasangan sampel
dengan urutan AB/BA bergantian. Loop dikalibrasi pada kontrol ke sekitar
25 ms atau lebih; kedua varian menjalankan jumlah operasi yang sama. Waktu
diukur menggunakan physical system counter, bukan perkiraan siklus CPU.
Thread diminta berjalan pada core 2 dan hasil permintaan dicatat.

`paired_overhead_pct` adalah median `(bias_ticks/direct_ticks - 1) * 100`
per pasangan. Angka negatif hanya berarti varian bias lebih cepat pada
sampel tersebut; periksa sebaran/noise sebelum menyimpulkan keuntungan.
`ns_step` memakai satu hop untuk chase, satu iterasi untuk pola lainnya.
Tidak ada agregat FPS atau bobot campuran yang dibuat-buat.

Clock CPU/RAM dibaca tanpa mengubahnya. Pasangan yang terdeteksi berubah
clock dikeluarkan dari ringkasan. Clock yang tidak dapat dibaca ditandai
`UNKNOWN`, bukan dianggap stock/stabil. Perubahan singkat di antara bacaan
clock tetap mungkin tidak terdeteksi; pertahankan pengaturan selama tes.

Analisis di PC:

```sh
python tools/analyze-as39-bias-bench.py /path/to/as39-bias-bench.log --output result.json
```

## Batas kesimpulan dan langkah integrasi

Benchmark belum menghitung register pressure seluruh FEX, konversi pointer
Wine/WoW64 (termasuk pointer di dalam struktur), callback native, pencarian
kode, exception/fault address, SMC/invalidation, dispatch, dan grafik. Atomik
diuji tanpa kontensi; x86 memory-ordering secara keseluruhan belum diuji.
Helper pointer hanya memeriksa domain alamat, bukan permission/lifetime.

Peningkatan budget memori 39-bit dari probe sebelumnya tidak membuktikan
FPS akan naik. Apabila biaya akses dasar cukup kecil dan konsisten, tahap
berikutnya ialah prototipe guest x86 kecil dengan FEX, kemudian batas
Wine/WoW64. Mengaktifkan seluruh PES sebelum jalur tersebut konsisten
berisiko menghasilkan pointer salah atau korupsi memori.

## Build dan verifikasi host

```sh
python tools/build-as39-bias-bench.py --sdk C:/devkitPro
```

Builder memerlukan paket probe sebelumnya untuk forwarder yang sudah diuji
perangkat; hash NSP diperiksa sebelum dipakai. Keyset tidak diperlukan.
Unicorn/pyelftools diperlukan untuk mengeksekusi instruksi ARM64 yang benar-benar
di-link, disalin ke alamat JIT tinggi, dan dibandingkan dengan referensi.
Tes juga memeriksa x18/ABI, isi seluruh buffer, batas pointer, cleanup saat
map/permission gagal, dan penahanan backing saat unmap gagal.

`verification.json` adalah verifikasi host, **bukan pengukuran performa
Switch**. `build.json` tetap menyatakan `hardware_tested=false` sampai ada
hasil perangkat untuk NRO ini. `manifest.json` mencatat hash file paket.

Referensi implementasi:

- [FEX ARM64 MemoryOps](https://github.com/FEX-Emu/FEX/blob/main/FEXCore/Source/Interface/Core/JIT/MemoryOps.cpp)
- [libnx virtual memory interface](https://github.com/switchbrew/libnx/blob/master/nx/include/switch/kernel/virtmem.h)
- [Atmosphere MapCodeMemory](https://github.com/Atmosphere-NX/Atmosphere/blob/master/libraries/libmesosphere/source/kern_k_page_table_base.cpp)

Runtime produksi PES dan proyek F1 tidak diubah oleh builder ini.

## Hasil perangkat pertama: 0.2.0

Log yang dikirim user memiliki SHA-256
`3e16ea45c34455c04ac56ba8720331b1f3fcb8027e2d9e09d7eae5414181719b`.
Salinan log dan analisis tersimpan di
`local/as39-bias-device-results/3e16ea45c344/`.

Semua 14 pemeriksaan fungsi lolos, termasuk alamat guest `0x00400000` yang
diakses pada host `0x7a9bdbc000`, wraparound 32-bit, dan null/boundary rejection.
JIT berjalan di atas 4 GiB. Seluruh 15 kasus/135 pasangan sampel selesai;
cleanup berhasil dan thread berhasil dipasang pada core 2. Semua pembacaan
clock mencatat CPU 1020 MHz dan RAM 1331,2 MHz; tidak ada pasangan yang dibuang
karena perubahan clock.

Median perubahan waktu eksekusi per pasangan (positif = lebih lambat):

| Pola | 16 KiB | 256 KiB | 4 MiB |
| --- | ---: | ---: | ---: |
| Pointer berantai | +25,00% | -31,12% | -0,87% |
| Scalar read/modify/write | sekitar 0% | +0,08% | -0,55% |
| Vektor 128-bit | sekitar 0% | -6,71% | -2,68% |
| Pasangan load/store 64-bit | +5,91% | -8,55% | -1,20% |
| Atomik tanpa kontensi | sekitar 0% | -1,12% | -0,14% |

Pada pointer berantai 16 KiB, waktu meningkat dari sekitar 3,922 menjadi
4,902 ns/hop, setara sekitar satu siklus tambahan pada CPU 1020 MHz.
Hasil +25% muncul pada kedua urutan AB dan BA. Ini merupakan biaya pada
pola dependensi tersebut; tidak berarti FPS PES turun 25%.

Hasil yang lebih cepat, terutama pointer berantai 256 KiB, **belum mengisolasi
biaya penerjemahan alamat**. Tes mengubah bentuk instruksi sekaligus alamat
virtual, walaupun backing fisik sama. Pengaruh penempatan alamat/sistem
memori belum dipisahkan. Karena itu angka -31% tidak boleh dipakai untuk
menjanjikan peningkatan kecepatan game.

Keputusan: jalur alamat layak untuk prototipe lanjutan, dengan biaya nyata
pada sebagian pola. Gerbang selanjutnya adalah kontrol pada alamat virtual
yang sama untuk memilih bentuk instruksi, lalu guest x86 kecil melalui
FEXCore yang sebenarnya. Integrasi pointer Wine/WoW64, exception/SMC, dan
PES masih belum diuji. Artefak produksi tidak diubah oleh analisis ini.
