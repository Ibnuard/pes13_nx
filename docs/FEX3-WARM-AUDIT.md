# Awal pertandingan berat, lalu lebih lancar

Input run antrean dua frame: `TEST RESULT/fex-runtime.log`, 291.278 byte,
SHA-256 `a5890910ed5f673f57fb5b5ccfb9300344beb33358b8de439c60a73bd53a410b`.
Salinan immutable dan histogram lengkap ada di `local/fex3/warm-start/`.
Pengguna melaporkan stutter kembali setiap aplikasi ditutup penuh dan dibuka.

## Temuan

- `d3d9.maxFrameLatency=2` aktif. Ini run baru dengan NRO hang-audit yang sama.
- Pada laporan pacing `elapsed_ms=110550` dan `120563` terdapat masing-masing
  22 dan 18 interval Present di atas 100 ms. Banyak laporan berikutnya nol,
  walaupun gap 50–100 ms masih ada. Timer laporan pacing dimulai pada laporan
  pertama, berbeda dengan counter event; jangan menyamakan keduanya atau
  menganggap jumlah Present sebagai jumlah frame simulasi yang unik.
- Pembacaan aset masih bertambah pada fase awal. Counter `read_ms` naik dari
  13.263 pada label progress 55s menjadi 20.449 pada 115s; SD read time naik
  dari 17.317 menjadi 22.641 ms. Ini total waktu panggilan lintas thread,
  bukan tambahan waktu tunggal yang seluruhnya menahan render.
- Ada setidaknya 262.144 blok yang dicatat jalur kompilasi FEX sebelum counter
  log mencapai batasnya. Tidak munculnya baris setelah batas ini **tidak**
  berarti kompilasi berhenti. Durasi translasi belum diukur di run tersebut.
- DXVK membaca cache **434 shader**, sama dengan run sebelumnya. Ini bukti
  cache DXVK terbaca, bukan bukti semua shader/pipeline driver sudah siap.
- Default `DiskCache` FEX pada source pinned adalah false, dan profil paket
  tidak mengaktifkannya. Cache translasi FEX dan cache shader DXVK berbeda.
  Jalur file FEX memakai LockFileEx serta positioned reads/writes; server
  Horizon saat ini belum mempunyai handler lock_file/unlock_file. Mengaktifkan
  setting disk cache saja belum merupakan implementasi cache yang tervalidasi.

Pola tersebut konsisten dengan pekerjaan saat pertama kali dipakai, termasuk
loading, translasi dan pipeline compilation. Belum ada atribusi masing-masing
freeze shooting/kickoff. GPU tetap dapat terlibat, tetapi kemampuan bermain
lebih lancar setelah warmup membuat beban grafis tetap bukan penjelasan yang
cukup. Slow motion sesudah event masih belum terpecahkan. Field game
`scale_bits=3f4ccccd` tetap muncul pada bagian lancar maupun transisi; nilainya
sendiri bukan alasan mengubah clock atau kecepatan simulasi.

## Perubahan NRO ini

Runtime lama melakukan `fflush` langsung untuk baris FEX di luar batch
diagnostik. Ini mencakup 65 baris counter kompilasi, 3 alokasi JIT, serta
58 pasang pesan create/ready thread pada log ini. Thread yang mengeluarkan
pesan ikut menanggung flush ke SD, termasuk saat kompilasi/penyiapan worker.

Revisi menunda forced flush hanya untuk prefix rutin yang dikenali tersebut,
serta laporan penghitung resume, ke flusher yang sudah berjalan. Fault,
allocation failure, pesan FEX yang tidak dikenal, exit dan kegagalan flusher
tetap memakai kebijakan sebelumnya. Baris tidak dibuang. Ini menghapus sumber
I/O sinkron yang tidak perlu, tetapi belum membuktikan bahwa flush tersebut
penyebab jeda shooting. `fwrite` masih dapat mengisi buffer dan memicu I/O;
ini bukan penggantian seluruh logger menjadi asynchronous.

NRO juga mengukur CPU wall time pada pembuatan pipeline graphics/compute
native dan lookup cache driver Mesa. `[FEX3-WARM]` melaporkan jumlah, waktu,
jumlah panggilan lebih dari 50 ms, serta hit/miss tiap sekitar 10 detik.
Observer tidak menambah sleep, allocation, pause thread, atau log per frame.
Cache pointer, key, size output dan hasil driver diteruskan tanpa perubahan.
Hit cache dapat berasal dari data yang ditulis pada run yang sama; belum
membuktikan persistensi antar-launch. Calls yang belum kembali belum masuk
counter, dan summed time dapat tumpang tindih antar-thread.

## Pasang dan bandingkan

1. Tutup PES lewat HOME → X; backup NRO dan log yang sekarang.
2. Salin folder `switch` dari `pes13-fex3-warm-audit.zip` ke root SD. Hanya
   `switch/pes13-fex/pes13-fex.nro` yang diganti. Pertahankan konfigurasi antrean
   dua frame, 540p 16:9, clock stock dan cache yang sudah ada.
3. Jalankan pertandingan yang sama sampai melewati fase awal yang berat dan
   simpan log sebagai run pertama. Catat perkiraan waktu shooting yang freeze.
4. Tutup penuh, buka kembali, ulangi pertandingan itu, dan simpan log kedua.
   Dua log ini akan membedakan pekerjaan berulang saat boot dari cache yang
   bisa digunakan kembali. Jangan hapus cache di antaranya.
5. Marker harus `pes13-fex3-warm-audit` dan `[FEX3-WARM] v1`.
   Rollback dengan mengembalikan NRO backup/hang-audit; dxvk.conf tetap dua.

Paket tidak mengaktifkan disk cache FEX, mengubah prioritas thread, menambah
compiler worker, menurunkan grafis lagi, atau mengubah timer. Tujuannya menjaga
baseline yang sudah terasa lancar setelah warmup sambil menghilangkan flush
rutin dan mengukur beban awal. **Belum diuji di Switch; stutter/kickoff/slow
motion belum dinyatakan selesai.**

## Validasi

Native build berhasil. FEX module adapter, PE ntdll/wow64, SDK dan Mesa tetap
cocok hash-nya dengan hang-audit. Source delta hanya runtime logger, empat
thunk pipeline creation dan linker wrapper cache. Host ASan/UBSan memeriksa
16.001 concurrent cache samples, hit/miss pointer/size passthrough, histogram
slow/error, serta preservasi forced flush fault/fallback. Uji ARM64 pada ELF
yang dikemas menjalankan wrapper cache dan memeriksa binding thunk serta
consumer cache Vulkan yang sebenarnya. Observer pipeline lama juga lulus.
NRO dicocokkan kembali dengan ELF dan ZIP dibaca ulang untuk validasi hash.
