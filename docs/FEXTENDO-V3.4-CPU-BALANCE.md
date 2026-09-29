# FEXTendo v3.4 — CPU balance dan lookup FEX

App **0.3.5**, build `pes13-fextendo-cpu-balance-v2`. Kandidat ini mengubah
jalur CPU; perbaikan first-kickoff belum dikonfirmasi pada Switch.

- `dxvk-cs` kembali mengikuti penyeimbang core aplikasi **0–2** dengan prioritas
  biasa, sehingga core aplikasi yang lebih lengang dapat dipakai. Flag lama
  offload core 3 diabaikan ketika `fex_dxvk_balance=1`.
- Lookup kode FEX mencampur bit alamat agar blok berjarak 64 KiB tidak selalu
  bertabrakan. Kapasitas cache tetap 1 MiB/thread, JIT tetap 128. Ini menyasar
  pencarian ulang kode; tidak menghilangkan seluruh kompilasi pertama kali.
- Backend frame generation LSFG native ditambahkan sebagai eksperimen,
  **OFF secara default**. Dua pilihan DXVK tetap tersedia.

Audit beserta peluang selanjutnya ada di `PERFORMANCE-AUDIT.md` dalam ZIP
atau [dokumen audit](FEXTENDO-V3.4-PERFORMANCE-AUDIT.md) dalam repository.

## Pasang di atas instalasi v3.3 yang berjalan

1. Tutup FEXTendo. Dari `pes13-fextendo-v3.4-cpu-balance-v2.zip`, salin **hanya
   folder `switch/` paling luar** ke root SD dan timpa file yang sama.
   NRO dan `libwow64fex.dll` harus diganti bersama.
2. Path NRO tetap `switch/pes13-fex/pes13-fex.nro`. Forwarder yang membuka
   path itu dapat dipakai; forwarder yang menanam NRO perlu dibuat ulang.
3. Jika key berikut sudah ada di `configuration.ini`, sesuaikan karena INI
   didahulukan atas file flag. Tidak perlu mengganti seluruh INI:

   ```ini
   fex_dxvk_balance=1
   fex_auto_core3=0
   fex_jit_small=1
   fex_jit_large=0
   ```

   Pertahankan balancing aktif (`no_balance=0` bila key itu ada).

Paket tidak berisi game atau `Lossless.dll`; game PES13 versi 1.0 tetap
disediakan pengguna. Save, INI, pilihan renderer, dan preferensi launcher
tidak ditimpa. Folder `control-*`, `rollback`, `source`, `upstream`, `evidence`,
dan `licenses` bukan isi instalasi utama.

## Tes pertama

Pilih **DXVK 3.1.1**, Frame generation **OFF**, aktifkan Debug timestamp.
Gunakan preset, OC, tim, stadion dan camera yang sama dengan tes sebelumnya.
Mulai dari aplikasi ditutup penuh; catat T+ saat kickoff, shooting, umpan
cepat dan bola lambung. Lanjutkan match kedua tanpa menutup aplikasi, lalu
simpan log sebelum membuka launcher lagi.

Log seharusnya menampilkan:

```text
[FEX3-DXVKPOLICY] v2 balance=1 ... effective_offload=0
[FEX3-LOOKUP] v3 index=rip-xor-rip16 ...
[FEX3-JIT-LAUNCH] maxinst=128
[FEX3-JIT-CONFIG] maxinst=128
```

Thread `dxvk-cs` seharusnya memiliki `active=0` untuk offload lama dan memakai
core aplikasi/prioritas normal. Log readback dan `[THREADS]` menentukan
penempatan sesungguhnya; `balance=1` sendiri belum mengukur manfaat performa.
Nomor kernel mulai dari 0: core 3 adalah core keempat, bukan core ketiga.

## Pembanding dan pemulihan

Uji paket utama dulu. Gunakan pembanding hanya untuk mengisolasi perubahan:

| Folder yang disalin ke root SD | Perubahan |
| --- | --- |
| `control-core3/switch/` | NRO/FEX baru tetap dipakai; `balance=0`, legacy core3=1. Menguji kebijakan penempatan saja. |
| `control-lookup/switch/` | NRO v3.4 dan balancing baru; FEX persis v3.3 dengan indeks L1 lama. Menguji hash lookup saja. |
| `rollback/switch/` | NRO dan FEX persis v3.3/JIT128, kebijakan legacy core3. Renderer dan preferensi yang tersimpan tetap dipakai. |

Mulai setiap pembanding dari pemasangan `switch/` utama, lalu salin hanya
satu folder pembanding. Jika INI memiliki `fex_dxvk_balance`, gunakan `0`
untuk control-core3/rollback dan `1` untuk paket utama/control-lookup.
Control-core3/rollback memerlukan `fex_dxvk_core3=1` bila key itu ada, serta
izin proses core 3 dan priority 63 seperti instalasi sebelumnya. Jika izin
tidak tersedia, offload tidak aktif; itu bukan tes core 3 yang valid.

Kembali ke kandidat dengan menyalin `switch/` utama lagi dan memastikan
nilai INI di atas. Tidak perlu menghapus cache, save, atau folder profil.

## Status frame generation

DLL pengguna yang diperiksa adalah **Lossless.dll 3.2.1.0**, SHA-256
`8b7dbc11b2ea544650af2ed4ffc92da3abd88ec5afa09c36484c060fbc848834`.
Payload yang ditemukan berupa DXBC, sedangkan backend yang dipin memerlukan
shader SPIR-V. Karena itu DLL ini **belum kompatibel**; launcher menolak
mengaktifkan LSFG untuk payload tersebut. Mengganti nama atau lokasi file
tidak mengonversi format shader. Kode Windows dalam DLL tidak dieksekusi.

Path untuk DLL milik pengguna yang kompatibel nantinya:
`switch/pes13-fex/lsfg/Lossless.dll`. File tersebut tidak disertakan atau
diunduh oleh paket. LSFG tetap OFF untuk pengukuran CPU; ia menambah beban
GPU dan tidak memperbaiki freeze yang tidak menghasilkan frame asli.
Sinkronisasi frame, visual dan performa backend masih memerlukan tes Switch.

FEX tetap **FEX-Emu**; port Switch dan integrasi FEXTendo dikerjakan
**AndroSwitch Project / Ibnuard**. Wine-NX/Autorun, DXVK/GPLAsync, LSFG-VK,
dan port Horizon/Cemu-NX mempertahankan kreditnya di `THIRD_PARTY.md`.
Source backend LSFG GPL yang dipin, perubahan dan recipe build disertakan.
Tes host dan hash paket memverifikasi konsistensi binary/source, bukan
jaminan first-kickoff sudah bebas stutter.
