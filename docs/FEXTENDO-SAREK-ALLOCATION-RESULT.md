# Sarek v2 — loading berputar, lalu proses berhenti

Log terbaru menunjukkan **terminasi proses setelah `std::bad_alloc`**.
Runtime memarkir proses setelah permintaan keluar dan frame terakhir tetap
terlihat. Asal alokasi yang gagal belum tercatat; ini belum membuktikan bug
dyasync atau RAM fisik habis.

## Bukti perangkat

Snapshot: `local/fex3/review-sarek-ace74fd1ee/device.log`, 175.092 byte,
SHA-256 `ace74fd1ee8661e739e80f0b5e67dd7738c196ac10036f618365970878bb2a08`.
Nomor baris di bawah merujuk ke snapshot tersebut.

- DXVK-Sarek v1.13.0, limiter efektif `0`, dyasync satu worker, `dxvk-cs`
  di core 3, disk cache FEX OFF.
- Counter Present naik 193 → 253 → 313 pada EVENT `elapsed_s=24/25/26`.
  Loading sempat menghasilkan sekitar 60 Present per detik. Masalah
  limiter 1 FPS sebelumnya sudah teratasi dalam run ini.
- Baris 1138–1139: `terminate called after throwing an instance of
  'std::bad_alloc'` dan `what(): std::bad_alloc`.
- Baris 1142: terminasi dilaporkan oleh TID 4, exit code 3. Baris
  1157–1158: `NtTerminateProcess(self) exit_code=0x00000003`, lalu
  `parked after self-terminate; close from HOME`.
- Present kemudian berhenti pada 374. Capture HANG pertama terjadi
  sesudah terminasi; worker idle di sana bukan bukti penyebab deadlock
  sebelum crash.
- Baris 1176–1178: native FEX heap `failures=0`, runtime heap sekitar
  1.152 MB terpakai / 761 MB bebas, section allocation failures 0.
  Counter ini tidak mengukur semua kegagalan heap guest atau ruang alamat;
  ruang bebas tidak menjamin setiap alokasi dapat dipenuhi.
- Baris 1190–1193: acquire/submit/fence/semaphore yang tercatat tidak
  melaporkan error/timeout. Peak pembuatan pipeline grafis 6,516 ms, dengan
  nol panggilan >50 ms (1196). Tidak ada bukti bahwa kompilasi panjang
  sedang menahan layar setelah proses keluar.

EVENT `elapsed_s` dihitung sejak runtime/launcher, **bukan T+ overlay**.
Origin overlay dari Play adalah tick 10771564601816 (19.200.000 tick/detik).
Pesan abort tidak memiliki tick sendiri; jangan memberi timestamp overlay
presisi pada abort dari urutan log yang sebagian dibatch.

## Batas diagnosis

`std::bad_alloc` adalah kegagalan alokasi C++; ukuran, pemanggil dan stack
exception tidak ada di log ini. Jangan langsung menganggap GPU kehabisan
memori, dyasync pasti rusak, atau jumlah thread pasti salah.

Kegagalan mapping `rc=0xd401` / `errno=17` terlihat lebih awal. Kegagalan
mapping juga terjadi pada run DXVK 3.1.1 yang berhasil bermain; pesan ini
dibatasi 24 per sesi. Korelasinya dengan abort belum terbukti, dan tidak
adanya pesan tambahan bukan bukti semua alokasi berikutnya sukses.

Source runtime `NtTerminateProcess` memang memanggil dump stderr lalu
memarkir thread tanpa kembali ke hbloader. Jalur allocation failure Vulkan
di source Sarek mencatat `DxvkMemoryAllocator: Memory allocation failed`
dan melempar `DxvkError`; pesan itu tidak muncul dalam capture ini. Hal
tersebut belum mengidentifikasi library yang melempar `std::bad_alloc`.

## Tes pembeda berikutnya

**`pes13-fextendo-sarek-control-none-v1.zip`** berisi config kontrol dari
paket Sarek **v2**. Ini eksperimen diagnosis, belum merupakan perbaikan
crash yang terverifikasi di Switch.

1. Tutup game melalui HOME.
2. Salin folder `switch/` dari ZIP ke root SD, merge/replace. Dua file aktif:
   `switch/pes13-fex/drive_c/PES13/dxvk.conf` dan
   `switch/pes13-fex/launcher/presets/dxvk.conf`.
3. Buka melalui forwarder yang sama, cukup uji sampai menu utama PES13.
4. Simpan log sebelum membuka launcher lagi. Config efektif harus tetap
   `d3d9.maxFrameRate = 0`, dengan penanda
   `DXVK: Shader compilation method: none`.

Satu perubahan opsi: `dxvk.shaderCompilationMethod = "dyasync"` → `"none"`.
DLL Sarek, limiter 0, VSync, worker state-cache, NRO, FEX, affinity dan
preset kualitas tetap sama. Mode none mematikan jalur async/dyasync Sarek;
state cache tetap aktif, sehingga ini bukan tes semua compiler dimatikan.
Tidak perlu build/re-forward atau menghapus cache. Jangan memakai config
kontrol dari paket Sarek v1 lama yang masih mengandung limiter `-1`.

Jika menu berhasil masuk, hasil itu mendukung keterlibatan jalur dyasync
atau perubahan kebutuhan alokasinya; satu run belum membuktikan akar bug.
Jika tetap abort dengan exception yang sama, lanjutkan fallback
DXVK-Async 1.10.3 Sporif sesuai rencana, tanpa menganggap fallback pasti
menyelesaikan kegagalan memori. Performa kickoff belum bisa dinilai dari
capture Sarek yang berhenti sebelum menu.

Untuk mengembalikan dyasync, salin kedua config dari patch loading-fix-v2
atau root `switch/` paket Sarek v2. DXVK 3.1.1 tersedia pada
`rollback-dxvk311/switch/` di paket lengkap v2.
