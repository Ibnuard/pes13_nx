# Kandidat pacing setelah hasil hang-audit

Update ini mengubah satu setelan aktif: `d3d9.maxFrameLatency = 1` menjadi
`2`. Pasang di atas build **pes13-fex3-hang-audit** yang sudah dicoba.
Efek pada stutter **belum diuji di Switch**. Ini perbandingan terkontrol,
bukan klaim bahwa penyebab semua stop-frame sudah diketahui.

## Pasang

1. Tutup PES melalui HOME → X. Backup file
   `switch/pes13-fex/drive_c/PES13/dxvk.conf` dan log run sebelumnya.
2. Salin folder `switch` dari `pes13-fex3-smooth-queue.zip` ke root SD.
   Satu file `dxvk.conf` ditimpa. NRO, DLL Wine/FEX/DXVK, settings.dat,
   configuration.ini, save dan cache tetap memakai pemasangan saat ini.
3. Mainkan pertandingan yang sama beberapa menit dengan clock stock, terutama
   passing biasa tanpa event. Tetap gunakan 960×540, 16:9, dan cache existing.
4. Simpan `fex-runtime.log` setelah mencoba. Effective configuration harus
   mencantumkan `d3d9.maxFrameLatency = 2`; marker NRO tetap
   `pes13-fex3-hang-audit` karena binary tidak berubah.

Prioritas penilaian adalah frekuensi stop-frame pendek, kemudian kelancaran
gerak dan respons tombol. Batas antrean lebih longgar dapat menambah latensi
input. Bila terasa lebih buruk, salin isi folder `rollback/switch` ke root SD
untuk kembali ke batas satu frame, atau pulihkan backup konfigurasi sendiri.
Jangan menyalin folder rollback bersamaan dengan folder switch utama.

## Bukti dari run yang baru dicoba

Input: `TEST RESULT/fex-runtime.log`, 211.418 byte, SHA-256
`c86c6718a95e7b66a1f3d3f9d15e0348cf83c9531d23f520f7b56b6a9c6cddf2`.
Salinan dan ringkasan angka disimpan di `local/fex3/smooth-queue/`.

- Marker hang-audit dan penghapusan diagnostic readback aktif; swapchain
  960×540 terkonfirmasi. Perbaikan tersebut sudah ada pada run ini.
- DXVK berhasil membaca cache 434 shader. Cache terbaca tidak membuktikan
  semua shader/pipeline yang diperlukan sudah selesai dikompilasi.
- Tiga jendela terakhir, masing-masing sekitar 10 detik, masing-masing
  mencatat 20 interval masuk Present pada bin 50–100 ms. Data histogram
  tidak memberi jarak waktu antar-jeda; angka ini **bukan bukti jeda setiap
  tepat setengah detik**.
- Pada jendela tersebut rata-rata native Present sekitar 1,06–1,20 ms.
  Completed acquire/fence/semaphore/submit calls juga diukur, tetapi log
  tidak menghubungkannya dengan masing-masing gap. Durasi Vulkan wait
  mencakup scheduling CPU; ini bukan GPU timestamp.
- Pembacaan aset hampir tidak bertambah pada bagian permainan yang panjang,
  sementara gap pendek tetap ada. SD streaming bukan penjelasan yang cukup
  untuk semua gap. Log berakhir dengan Present tetap bertambah.
- Scoreboard yang masih beranimasi saat 3D berhenti menunjukkan sebagian
  game masih maju. Penghitung Present tidak membedakan frame 3D baru dari UI
  yang terus digambar; observer hang yang menunggu Present berhenti tidak
  dapat menangkap semua freeze simulasi seperti kickoff tersebut.

## Alasan perubahan

Konfigurasi efektif memaksa batas satu frame. Source
[DXVK 3.1.1 D3D9SwapChainEx](https://github.com/doitsujin/dxvk/blob/v3.1.1/src/d3d9/d3d9_swapchain.cpp#L1061)
menunggu frame-latency signal berdasarkan batas ini dan juga membatasinya
menurut nilai aplikasi serta jumlah backbuffer. Batas dua memberi ruang
lebih besar untuk menyiapkan frame berikutnya apabila aplikasi mengizinkan.
Hipotesisnya: variasi waktu kerja CPU lebih mudah diserap sehingga antrean
present tidak terlalu mudah kosong. Manfaatnya belum terbukti dari log ini;
antrean tambahan tidak menyembuhkan lock macet atau kompilasi yang lama.

Vsync/FIFO, penonaktifan limiter DXVK, jumlah compiler thread, kualitas grafis
dan profil FEX tetap sama. Bug kickoff ditunda sesuai prioritas pengguna.
Tidak ada manipulasi clock game atau pemaksaan unlock. Profil ini memakai
opsi umum DXVK sehingga dapat dicoba pada game D3D9 lain; jangan menetapkan
batas dua sebagai perbaikan universal sebelum ada hasil per game.

## Validasi lokal

Packager memeriksa bahwa satu-satunya perubahan opsi efektif adalah
`d3d9.maxFrameLatency: 1 → 2`, bahwa overlay aktif hanya berisi path konfigurasi
yang terbaca pada log, dan bahwa rollback sama persis dengan konfigurasi
baseline repository. ZIP dibaca kembali dan hash setiap file dicatat.
Tidak diperlukan rebuild NRO atau DLL untuk perubahan konfigurasi ini.
