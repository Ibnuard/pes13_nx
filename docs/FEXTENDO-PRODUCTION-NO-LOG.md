# FEXTendo production tanpa log

Paket `production-no-log-v2` berisi NRO pengganti untuk instalasi FEXTendo
v3.6 fast-api yang sudah berjalan. Identitas aplikasi tetap **0.3.7**, dengan
ikon yang sama. Tutup aplikasi, lalu timpa
`switch/pes13-fex/pes13-fex.nro` menggunakan file dari paket ini.
Forwarder yang menunjuk ke path tersebut tetap dapat dipakai.

Build ini mematikan keluaran log runtime FEXTendo, FEX, Wine, Horizon,
stdout/stderr dan logger DXVK. File `fex-runtime.log`, rotasinya,
`horizon-trace.log`, `stdin.txt`, `stdout.txt`, dan `stderr.txt` tidak dibuka
oleh jalur logging runtime. Standard handles tetap valid, tetapi menggunakan
perangkat penampung tanpa penyimpanan; baca menghasilkan EOF dan tulis
mengembalikan jumlah byte yang diterima tanpa menyimpan isinya.

Pengaturan diagnostik lama di `configuration.ini`, flag legacy, atau profil
game tidak bisa mengaktifkan kembali logging runtime. Guest stress test juga
dinonaktifkan. Semua pilihan environment renderer menerima
`DXVK_LOG_LEVEL=none`, `DXVK_LOG_PATH=none`, `WINEDEBUG=-all`, dan
`FEXTENDO_TRACE=0`. Pesan error launcher tetap dapat tampil di layar.

Cache shader/JIT, konfigurasi, registry, dan save game masih dapat ditulis.
Thread pemeliharaan tetap menyimpan registry setiap detik dan menjalankan
CPU balancer setiap dua detik. File log lama tidak dihapus otomatis; boleh
dihapus setelah aplikasi ditutup. DLL game/mod eksternal yang membuat log
sendiri berada di luar jalur logger runtime ini.

Paket hanya mengganti NRO. DLL FEX, Wine PE, renderer, dan data game memakai
instalasi yang sudah ada. Build tidak mengubah batas core/address space yang
ditetapkan forwarder. Hasil ini belum diuji menjalankan game pada Switch;
pemeriksaan build, binary ARM64 dan hash paket tersedia di `evidence/`.

## Perbaikan startup v2

V1 dilaporkan tertahan di layar **Launching game**. Build tersebut menambahkan
`WINEDEBUG=-all` pada environment native, tetapi hanya menonaktifkan keluaran
logger Wine. Saat channel debug pertama kali diperiksa, `init_options()`
tetap membaca `main_argv[1]`. Launcher Horizon menggunakan entry khusus dan
tidak mengisi `main_argv`, sehingga pembacaan ini mengakses alamat `0x8`.

V2 langsung mengembalikan nol pada pemeriksaan channel debug, termasuk channel
yang sudah diinisialisasi. Inisialisasi opsi debug juga menetapkan nol tanpa
membaca environment, argumen program, atau filesystem. Output log tetap mati;
perangkat stdio dan pilihan renderer tetap sama dengan V1.

`tests/fextendo_silent_startup.py` mereproduksi akses alamat `0x8` pada ELF V1
dengan `WINEDEBUG=-all`, sementara kontrol tanpa variabel tersebut berhasil.
Tes memakai `fstat` libc ARM64 asli pada stderr production; environment dan
ketiadaan path Unix `/dev/null` dimodelkan. ELF V2 harus melewati pemeriksaan
channel dengan `main_argv` kosong dan environment kosong, `-all`, `+all`, serta
`help`, tanpa memanggil parser atau I/O. Ini membuktikan perbaikan jalur crash
yang direproduksi, tetapi keberhasilan launching penuh masih perlu diuji
di Switch. Pengujian V1 sebelumnya hanya mencapai awal pemasangan stdio dan
belum mencakup inisialisasi channel Wine ini.

## Rebuild

Gunakan `tools/build-fex-runtime.py` dengan semua opsi baseline fast-api,
ditambah `--silent-production`. Opsi ini menggunakan snapshot terpisah
`fex-experiment/wine3-production` agar build diagnostik tetap tersedia.
Untuk `--native-only`, siapkan `runtime-build.json` dan payload
`ntdll.dll`, `wow64.dll`, serta `fex-stress.exe` dari build baseline di direktori
output terlebih dahulu; builder memeriksa hash ketiganya.

Patch khusus production ada di `tools/fextendo_silent_patches.py` dan
perangkat stdio ada di `src/runtime/fextendo_silent_io.h`.
`tests/fextendo_silent.py` mengeksekusi fungsi ARM64 dari ELF hasil build,
dengan layanan kernel/pemeliharaan tertentu dimodelkan. Pemeriksaan tersebut
bukan pengganti uji perangkat keras.

Kredit dan asal komponen tercatat di `THIRD_PARTY.md` dan
`source/docs/FEX-PORT-PROVENANCE.md` dalam paket.
