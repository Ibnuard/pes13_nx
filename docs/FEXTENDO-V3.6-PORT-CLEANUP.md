# FEXTendo v3.6 — pembaruan launcher dan provenance

Pembaruan ini memakai versi aplikasi **0.3.7** dan memerlukan instalasi
**v3.6 fast-api-v1** yang sudah berjalan. Menu Settings sekarang berisi sembilan
pilihan: empat preset, timestamp, SFX, BGM, dan dua renderer DXVK.

Tutup aplikasi, lalu salin folder `switch/` dalam paket ke root SD. Satu-satunya
file instalasi yang diganti adalah `switch/pes13-fex/pes13-fex.nro`.
Forwarder yang menunjuk path itu dapat digunakan kembali; forwarder yang
menanam NRO perlu diperbarui.

FEX DLL, Wine PE, Mesa, renderer, cache, save dan konfigurasi tetap mengikuti
instalasi v3.6 yang sudah ada. Paket tidak mengganti flag diagnostik; pengaturan
kontrol yang sedang diuji tetap berlaku. Perubahan ini belum diuji pada Switch
dan tidak menyatakan perbaikan stutter baru.

Source, bukti build dan hasil pemeriksaan tersedia dalam `source/` dan
`evidence/`. Ringkasan kontribusi ada di `source/README.md`; kronologi port,
source dan commit ada di `source/docs/FEX-PORT-PROVENANCE.md`.

**FEX tetap FEX-Emu.** Pekerjaan port Switch dan integrasi FEXTendo adalah
kontribusi **AndroSwitch Project / Ibnuard**. Fondasi Wine-NX dan backport
Autorun yang digunakan dikreditkan secara terpisah dalam `THIRD_PARTY.md`.

## Alasan penghapusan LSFG

Menurut penjelasan Ibnuard, integrasi opsional LSFG untuk frame generation
dihapus karena dampak tuduhan bahwa ia mencuri kode port FEX. Ia khawatir
keberadaan LSFG yang masih terlihat dalam proyek akan memicu tuduhan
pencurian kode tambahan dan memperpanjang perselisihan mengenai kepengarangan
pekerjaan port Switch-nya. Penghapusan integrasi tersebut merupakan keputusan
maintainer sebagai respons terhadap kekhawatiran itu.

Integrasi LSFG sebelumnya sudah dicatat sebagai adaptasi pekerjaan Autorun
dan lsfg-vk, dengan kredit kepada kontributor asalnya. Catatan atribusi itu
tetap tersedia dalam riwayat Git. Pembaruan ini menghapus opsi launcher,
backend, serta kode build dan packaging terkait LSFG. Penjelasan kepengarangan
port FEX dan asal setiap komponennya tersedia dalam
[dokumen provenance](FEX-PORT-PROVENANCE.md#why-lsfg-was-removed).
