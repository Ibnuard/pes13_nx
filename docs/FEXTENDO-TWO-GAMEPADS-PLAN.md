# Dua gamepad dan Joy-Con horizontal

Status: pengguna mengonfirmasi preview v2 sudah bekerja pada Switch. Preview ini
memperbaiki reset HID saat Wine mulai dan interaksi halaman Gamepad. Konfirmasi
tersebut tidak mencakup klaim bahwa seluruh matriks kombinasi/reconnect telah diuji.
Dasar implementasi: production v1 dengan fix launching. Eksperimen DFE tetap
direvert. Pekerjaan ini berfokus pada input dan launcher.

## Mapping horizontal

Nama A/B/X/Y pada tabel ini adalah tombol logis Nintendo yang juga dipakai
launcher. Sesudah normalisasi, backend memakai terjemahan XInput yang sudah
ada: Nintendo B menjadi Xbox A, A menjadi Xbox B, Y menjadi Xbox X, dan X
menjadi Xbox Y. Karena itu label Nintendo tidak boleh langsung ditulis sebagai
bit tombol Xbox.

Joy-Con kanan dipegang horizontal dengan analog di sebelah kiri:

| Tombol fisik | Tombol logis Nintendo | Tombol XInput PES |
| --- | --- | --- |
| X | A | B |
| A | B | A |
| B | Y | X |
| Y | X | Y |

Joy-Con kiri dipegang horizontal dengan analog di sebelah kiri:

| Tombol arah fisik, dilihat saat Joy-Con tegak | Tombol logis Nintendo | Tombol XInput PES |
| --- | --- | --- |
| Bawah | A | B |
| Kiri | B | A |
| Atas | Y | X |
| Kanan | X | Y |

Analog ikut diputar: kanan `(x, y) -> (y, -x)`, kiri
`(x, y) -> (-y, x)`, dengan saturasi sebelum konversi ke sumbu 16-bit.
SL/SR menjadi L/R atau LB/RB, dan Plus/Minus yang tersedia menjadi Start.
ZL/ZR dan analog kanan tidak dipetakan pada single Joy-Con. Tombol arah pada
Joy-Con kiri berfungsi sebagai tombol aksi; tidak dikirim sekaligus sebagai
D-pad. Gamepad penuh mempertahankan seluruh mapping saat ini.

## Tile Gamepad

Tambahkan satu tile Gamepad pada launcher. Halamannya menampilkan:

- Dua tindakan saja: **Change Controller** dan **Test Controls**.
- Slot Player 1 dan Player 2, status koneksi, dan jenis controller.
- Indikator tombol/analog hanya merespons saat **Test Controls** aktif. Di luar
  tes, status koneksi/jenis tetap diperbarui dan indikator input tetap netral.
  Mapping yang diuji sama dengan backend game, termasuk rotasi single Joy-Con.
- Tindakan hubungkan/ubah controller melalui applet ControllerSupport Switch.

Jumlah pemain mengikuti controller yang tersambung; file lama `players.txt`
diabaikan. Slot wajib dibekukan saat Play agar disconnect selama loading tidak
mengurangi sesi menjadi satu pemain. P2 yang bergabung saat game berlangsung
juga menjadi bagian sesi, sehingga disconnect berikutnya memicu recovery.

Mode campuran diperbolehkan: full gamepad + single Joy-Con, dua full gamepad,
atau dua single Joy-Con. Slot XInput memiliki state dan packet counter
masing-masing. Nomor pemain mengikuti assignment Switch; P2 tidak boleh
dipromosikan diam-diam menjadi P1 saat P1 putus.

## Controller terputus

Alur yang diminta: controller sesi terputus -> game dipause -> applet
ControllerSupport bawaan Switch -> semua controller sesi tersambung kembali
-> game tetap pause -> pemain melanjutkan sendiri.

Permintaan pause harus idempotent: disconnect ketika game sudah pause tidak
boleh mengubahnya menjadi berjalan. Jangan memakai pulsa Start sebagai
mekanisme tunggal, karena Start dapat men-toggle menu pause. Menutup applet
juga tidak boleh menghasilkan Start atau tombol konfirmasi di game; tombol
harus dilepas sebelum input normal diterima kembali.

Jika applet dibatalkan, gagal dibuka, atau controller masih kurang, game tetap
tertahan dan jalur retry tetap tersedia. Satu kejadian disconnect hanya boleh
menjalankan satu applet. Semua controller terputus sekaligus tetap harus dapat
dipulihkan. Slot yang tidak dipakai pada sesi satu pemain tidak memicu recovery.

## Temuan kode dan hal yang harus dibuktikan

Backend native sekarang memakai dua slot dan packet counter terpisah. Launcher,
XInput, dan pointer fallback berbagi satu konfigurasi HID dua controller.
P2 tidak menggantikan P1 saat P1 putus. Joy-Con berpasangan dianggap putus
jika salah satu sisinya hilang, walaupun libnx masih menandai pad connected.

SDK libnx yang terpasang menyediakan single Joy-Con, orientasi horizontal,
ControllerSupport, serta AlwaysSuspend saat aplikasi kehilangan fokus.
Default SuspendHomeSleep tidak menjamin aplikasi berhenti saat library applet
controller tampil. Referensi API dan implementasi applet:
<https://github.com/switchbrew/libnx/blob/master/nx/source/applets/hid_la.c>.

Pengguna menyetujui layar **Game dijeda** milik FEXTendo untuk reconnect.
Tidak ada pulsa Start otomatis dan status menu pause PES tidak diubah.
Sesudah applet ditutup, runtime menunggu seluruh input netral, lalu A untuk
Lanjutkan, lalu pelepasan tombol lagi. X membuka applet ulang. Cancel atau
jumlah controller belum lengkap tetap menahan game.

Saat applet tampil, libnx memakai AlwaysSuspend. Selama layar FEXTendo tampil,
panggilan XInput serta dua jalur Vulkan AcquireNextImage menunggu condition
variable. Event/input worker tetap hidup untuk menjalankan recovery. Ini
menahan loop input/frame, bukan suspend paksa seluruh thread FEX; pekerjaan
background, audio yang sudah mengantre, serta jam sistem tidak dihentikan.
Pergerakan pertandingan, audio, dan lompatan waktu sesudah pause panjang harus
**dibuktikan di Switch** sebelum fitur dianggap siap rilis. Jika layar VI
recovery gagal dibuat, error native menjelaskan kegagalan dan aplikasi ditutup;
game tidak dilanjutkan diam-diam.

Uji wajib mencakup tombol dan sumbu kedua Joy-Con, input dua pemain bersamaan,
mode campuran, disconnect P1/P2/keduanya, disconnect ketika PES sudah pause,
cancel/retry applet, assignment setelah reconnect, serta tidak bocornya tombol
konfirmasi ke game. Perilaku menu pause dan pemilihan sisi PES perlu diuji
langsung pada Switch.

## Pemakaian preview

1. Ganti `sdmc:/switch/pes13-fex/pes13-fex.nro` dengan NRO preview. Aset launcher,
   preset, save, NSP forwarder, dan DLL FEX dari production v1 tetap dipakai.
2. Buka **Gamepad**, lalu **Change Controller**. Di applet,
   gunakan SL+SR untuk masing-masing single Joy-Con atau L+R untuk gamepad penuh.
3. Pastikan Player 1 dan Player 2 tersambung; **Test Controls** menampilkan input
   Nintendo setelah rotasi. Plus/Minus menyelesaikan tes. B kembali ke launcher.
4. Play, kemudian pilih sisi kedua pemain di PES. Tidak perlu mengubah jumlah
   pemain secara manual atau mengganti preset untuk setiap kombinasi controller.
5. Putuskan P1/P2 untuk mencoba reconnect. Setelah tersambung, lepaskan tombol,
   pilih A pada layar Game dijeda, lalu lepaskan A. PES yang sebelumnya berada
   di menu pause tetap berada di menu itu karena Start tidak dikirim otomatis.

Simbol teks arah `< ^ > v` pada kartu controller dihapus sesuai permintaan.
Single Joy-Con tidak mengirim ZL/ZR, D-pad, atau analog kanan. Full gamepad tetap
mengirim semuanya seperti sebelumnya. Rumble tetap belum diimplementasikan.

## Build dan validasi

`python3 tools/build-fextendo-gamepads.py` memerlukan snapshot lokal
`local/fex3/production-v1-launchfix` dan toolchain baseline yang sama.
Builder memverifikasi NRO baseline, seluruh input patch/adaptor, source Wine
asli, serta pustaka SDK/Mesa sebelum build terpisah. Delta generated source
hanya runtime launcher/input, XInput, dua gate akuisisi Vulkan, dan include CMake.
Startup fix, null log sink, FEX JIT, dan DLL PE tidak dibangun ulang/diubah.

- `tests/fextendo_gamepad.c`: ASan/UBSan untuk rotasi, ekstrem sumbu, siklus
  tombol, semua 65.536 chord full pad, slot, dan transisi recovery.
- `tests/fextendo_gamepad_binary.py`: menjalankan ARM64 hasil link dengan HID
  dan mutex yang dimodelkan; normalisasi, pemisahan P1/P2, packet counter,
  pasangan Joy-Con setengah putus, dan gate pause dieksekusi dari ELF asli.
- `tests/fextendo_ui.c`: renderer C asli, screenshot, stride, indikator netral
  di luar tes, dan migrasi global XInput untuk keempat preset di ketiga lokasi.
- `tests/fextendo_gamepad_startup.py`: reproduksi instruksi v1 yang mengirim
  max_players=1, audit semua pemanggil konfigurasi HID pada ELF v2, dan eksekusi
  initializer ARM64 dua controller dengan mask No1/Handheld dan No2 terpisah.
- Regresi ARM64 production: logging, crash startup, maintenance/affinity.

Preview ini tidak mengganti runtime input yang disetujui di GitHub Release/CI.
Fingerprint runtime release perlu diperbarui dengan binary yang telah diuji di
Switch; guard tersebut tidak dilewati hanya agar pipeline feature menjadi hijau.

## Perbaikan preview v2 (laporan perangkat)

P2 terputus sesudah launcher karena `pes13_controller_check()` versi lama
memanggil `padConfigureInput(1, ...)` **sebelum** memeriksa apakah tes diminta.
Jalur ini masih dipanggil di main setelah launcher pada preview v1; karena itu
controller_test=0 tidak mencegah reset. XInput hanya membaca controller dan
bukan penyebab reset konfigurasi HID tersebut. Fungsi ini tidak lagi dipanggil
atau disertakan pada runtime FEXTendo. Tes ELF sekarang memeriksa seluruh
pemanggil `padConfigureInput` dan penulis supported-ID/style, bukan hanya
menguji jawaban XInput setelah state HID dibuat oleh mock.

Dua settings.dat di TEST RESULT dan empat preset yang diperiksa sudah memiliki
flag XInput `0x0200` (flags `0x0289`) serta CRC valid. Preview v2 memastikan flag
itu aktif setiap kali preset diterapkan dan sebelum Play pada ketiga lokasi
settings.dat, menghitung ulang CRC, dan mempertahankan semua binding. Tidak
menyalin blok pertama ke P2: GUID blok pertama adalah `GUID_SysKeyboard`, bukan
profil gamepad Player 1. Tidak ada offset per-player yang ditebak atau save
pertandingan yang ditimpa. Penggunaan P2 melalui PES tetap perlu diuji perangkat.

**Change Controller** menerima satu sampai dua controller tanpa membatasi jumlah
berdasarkan file players.txt lama. Handheld tetap bisa menjadi P1 pada launcher/
game; applet konfigurasi multi-controller libnx meminta controller lepas dari
konsol atau gamepad penuh (single-mode applet akan membatasi kembali menjadi satu).
