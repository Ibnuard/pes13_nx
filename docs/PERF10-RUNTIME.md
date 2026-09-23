# PERF10 runtime + DXVK

## Paket utama

Gunakan **pes13-perf10-combined.zip** lebih dulu. Tutup PES dari HOME, salin
folder switch dari ZIP ke root SD, lalu overwrite. Jalankan forwarder yang
sama: path tetap switch/pes13-nx/pes13-nx.nro, dengan satu NRO dan icon PES.
Settings.dat, save, dan file game tidak diganti.

Paket utama menggabungkan:

- NRO PERF10 dengan perbaikan ResumeThread: notifikasi penunggu server hanya
  ketika hitungan suspend benar-benar berubah dari 1 ke 0. Resume thread yang
  sudah berjalan tidak lagi membangunkan penunggu tanpa perubahan state.
  Jalur lama memanggil pthread_cond_broadcast jika ada penunggu, sehingga
  semua penunggu objek bisa terbangun meskipun resume tidak mengubah state.
- DXVK 3.1.1 x86 resmi, pada folder game dan C:\dxvk.
- Preset Box64 Compatible dan kebijakan per-block PERF8, tetap -O1.
- Sampling dan verbose off. Telemetri performa tetap berkala, bukan per-frame.

Ini bukan implementasi baru suspend thread berjalan. Patch fast-suspend lama
masih ada; isu semantiknya belum diselesaikan. Upgrade Box64 upstream juga
belum masuk paket ini. Pengurangan wakeup sudah diuji dengan handler asli dan
helper state asli pada host, tetapi pengaruh FPS perlu diukur di Switch.
Ini mengurangi wakeup yang tidak diperlukan, bukan menghilangkan biaya IPC
ResumeThread atau menjamin thread game tidak melakukan busy-wait.

## Pengujian

Gunakan CPU 1728 / GPU 768 / RAM 1600 MHz, tim, stadion, kamera, dan pengaturan
grafis yang sama. Mainkan match minimal dua menit dan ulangi sekali agar
kompilasi awal tidak tercampur dengan FPS stabil. Kirim pes13-nx.log dan sebut
nama paket yang dipakai. Marker boot NRO: pes13-nx-0.2.0-perf10-resume-gate;
baris telemetri masih bernama [PERF8] karena memakai format yang sama.

Jika perlu pembanding setelah paket utama:

- pes13-perf10-dxvk271.zip: hanya mengganti DXVK ke 2.7.1.
- pes13-perf10-dxvk311-cpu.zip: kembali ke 3.1.1 dengan satu compiler worker
  dan constant-buffer streaming dimatikan. Dapat memperlambat kompilasi awal;
  belum terbukti membantu FPS stabil.
- pes13-perf10-dxvk311.zip: kembali ke konfigurasi DXVK paket utama.
- pes13-perf10-full-rollback.zip: kembali ke NRO PERF8 dan DXVK sebelumnya.
  Status patch x86 ntdll PERF9 tidak diubah oleh paket-paket ini.

Pasang satu paket setiap kali, jangan gabungkan semua ZIP bersamaan.
Paket utama sudah siap dicoba; tidak ada klaim 30 FPS sebelum tes perangkat.
