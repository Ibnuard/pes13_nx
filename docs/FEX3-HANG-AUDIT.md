# Hasil log stability 540p dan revisi jalur present

Log terbaru: `TEST RESULT/fex-runtime.log`, 154.019 byte, SHA-256
`6e5abdc8dde67ca1292fa446fb864f30d5b553f7563600fe0325ca4f24c6c368`.
Salinan immutable dan analisis terstruktur ada di `local/fex3/hang-audit/`.

## Temuan yang benar-benar terlihat

- Build `pes13-fex3-stability-540p`, marker context FP dan alias generasi aktif.
  Swapchain **960×540** terkonfirmasi, termasuk present 3600. Jadi preset 540p
  sudah diterapkan pada run ini.
- Pada baris 1761 (`elapsed_s=166`) present mencapai **4626**, lalu tidak
  bertambah sampai akhir (`elapsed_s=175`). Log observer tetap berjalan.
  Ini render stream berhenti ketika bagian runtime lain masih hidup.
- Baris 1790: `RtlpWaitForCriticalSection section 016AD2E4 ... thread 0004,
  blocked by 0034`. Thread utama 4 menunggu lock yang saat timeout dilaporkan
  dimiliki **thread 52** (`0x34`). Pesan `retrying (60 sec)` adalah timeout
  percobaan berikutnya; bukan bukti game sudah hang selama 60 detik.
- Thread 52 dan 56 sebelumnya mencatat ratusan sleep per window. Window terakhir
  memuat sekitar separuh jumlah sleep biasanya, konsisten dengan aktivitas
  mereka berhenti di tengah window. Log tidak berisi PC/stack kedua thread itu.
- Tidak ada error Vulkan pada completed-call counters menjelang hang. Ini
  tidak meniadakan panggilan GPU yang masih menggantung karena durasinya belum
  tercatat sampai panggilan kembali.
- Snapshot `[FEX3-HANG-PC]` belum muncul. Gate lama memerlukan 10 detik tanpa
  progres yang diamati pada cadence lima detik; pada pola log ini snapshot
  pertama baru diharapkan sekitar counter 180, sesudah akhir file 175.

Kesimpulan: hang terakhir mempunyai bukti **main thread tertahan pada lock**.
Alasan pemilik lock tidak melepasnya belum teridentifikasi. Belum ada dasar
untuk memaksa unlock, membuang wait, menyalahkan GPU, atau menyatakan semua
freeze kickoff memiliki akar yang sama. Waktu kickoff tidak dapat ditandai
tepat dari log tanpa penanda/video run yang sama. `elapsed_s` juga berasal dari
loop log thread, bukan timestamp video yang telah dikalibrasi.

## Cacat jalur 540p yang diperbaiki sekarang

Jalur present berukuran berbeda dari layar menjalankan diagnostic GPU readback
pada scaled present 30, 90, lalu kelipatan 1800. Keempat readback tersebut
terlihat pada log ini. Kode membuat buffer/fence, menyalin frame GPU ke CPU,
menunggu fence dengan batas lima detik, lalu membaca piksel untuk log.
Pekerjaan ini tidak diperlukan untuk menampilkan game dan bisa menambah jeda.
Readback 3600 terjadi jauh sebelum hang pada 4626; belum ada bukti readback
menyebabkan hang terakhir.

Revisi menghapus readback itu dan mempertahankan compute blit untuk scaling
960×540 → 1280×720. QueueSubmit sekarang mengembalikan status, mencatatnya pada
observer submit yang sudah ada, dan caller melewati Present bila submit gagal.
Sebelumnya kegagalan submit diabaikan sehingga Present dapat menunggu semaphore
yang tidak akan diberi sinyal. Log saat ini tidak membuktikan error itu terjadi;
ini perbaikan jalur kegagalan yang ditemukan melalui pemeriksaan source.

Snapshot hang sekarang mulai setelah sekitar tiga detik tanpa present baru,
dipanggil pada cadence satu detik, maksimum tiga capture. Daftar thread
diperbarui saat capture dan mencakup hingga 64 Wine worker, termasuk yang
sedang tidur atau terblokir. Dua sampel per thread menyimpan PC/register/stack
host, serta label blok guest jika valid. Thread dipause satu per satu dan
segera di-resume sebelum logging. Snapshot mencantumkan self-suspended TID dan
suspend count tanpa mengubahnya. Dukungan snapshot tetap bergantung pada izin
SVC yang diberikan launcher.

## Pasang revisi

Paket `pes13-fex3-hang-audit.zip` adalah **update NRO saja** untuk instalasi
stability 540p yang menghasilkan log ini. Ketiga DLL, settings.dat, DXVK,
profil FEX dan clock tetap menggunakan pemasangan saat ini.

1. Tutup PES dengan HOME → X, lalu backup NRO dan log sebelumnya.
2. Salin folder `switch` dari ZIP ke root SD, timpa
   `switch/pes13-fex/pes13-fex.nro`.
3. Jalankan pola kickoff/passing/shooting yang sama pada clock stock. Jika hang
   lagi, tunggu sekitar **20 detik**, lalu simpan
   `switch/pes13-fex/fex-runtime.log` sebelum relaunch. Periksa marker build
   `pes13-fex3-hang-audit`, `[FEX3-SCALED]` dan `[FEX3-HANG] v2`.
4. Rollback cukup mengembalikan NRO backup, karena update ini tidak mengganti
   DLL maupun konfigurasi.

Profil log adalah **Fastest**: scalar/vector/memcpy TSO semuanya dimatikan.
Ordering yang lebih longgar tetap kandidat penyebab gangguan thread, belum
diagnosis yang terbukti. FEX menjelaskan biaya dan fungsi emulasi ordering
x86 pada ARM di [dokumentasi teknis resminya](https://fex-emu.com/Scourge-of-emulation/).
Untuk perbandingan terpisah dengan binary dan 540p yang sama, ubah
`fex_fast=1`, `fex_fastest=0`, `fex_relaxed_vectors=0` di configuration.ini;
profil Fast mengaktifkan ordering ketat dan dapat jauh lebih lambat.
Preset opsional disertakan di `profiles/conservative-ordering.ini`, di luar
folder switch. Mulai dengan profil existing agar hasil perubahan present
dapat dibandingkan. Jangan menganggap hilangnya satu hang acak dalam satu run
sebagai bukti penyebab telah terisolasi.

## Validasi dan batas hasil

Native build selesai. PE ntdll/wow64 dan semua adapter FEX tetap memiliki hash
yang sama dengan stability 540p. Source patch gabungan diverifikasi terhadap
receipt build. Tests pada source generated dengan ASan/UBSan mencakup 3.601
scaled submits, status gagal, preservasi semaphore/command, idle-worker
selection, batas kapasitas, resume setelah kegagalan pembacaan context, dan
snapshot waiter tanpa mengubah suspend count. Mutation test mendeteksi error
submit yang diabaikan.

Tests ARM64 pada binary yang dikemas memeriksa scaled submit, branch error di
caller, resume, routing sync, yield/delay, observer pipeline, exception dispatch
dan pasangan unwind. Batas kernel/GPU dimodelkan; **belum ada hasil Switch untuk
revisi ini**. Perbaikan readback adalah konkret, tetapi hang pemilik lock dan
freeze kickoff belum dinyatakan selesai.
