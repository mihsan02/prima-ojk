# Dasar Regulasi PRIMA — Verifikasi T0.1

Diverifikasi 24 Agustus 2026 terhadap PDF resmi:
- POJK Nomor 27 Tahun 2024 (naskah asli, 178 halaman, jdih.ojk.go.id)
- POJK Nomor 23 Tahun 2025 (perubahan atas POJK 27/2024, ditetapkan 31 Oktober 2025, diundangkan 10 November 2025)

## Aturan 30/70 penyimpanan aset Konsumen

**Pasal 91 POJK 27/2024, ayat (2) dan (3). Halaman 61 naskah asli.
Tidak diubah oleh POJK 23/2025** (dikonfirmasi: daftar perubahan Pasal I
POJK 23/2025 melompat dari Pasal 89 ke Pasal 95, Pasal 90-94 tidak disebut).

> (2) Aset Keuangan Digital yang disimpan sendiri oleh Pedagang paling
> banyak 30% (tiga puluh persen) dari total Aset Keuangan Digital yang
> dimiliki oleh Konsumen dan sisanya wajib disimpan di Pengelola Tempat
> Penyimpanan.
>
> (3) Terhadap Aset Keuangan Digital yang disimpan sendiri oleh Pedagang
> paling banyak 30% sebagaimana dimaksud pada ayat (2), penyimpanannya
> dilakukan dengan paling sedikit 70% (tujuh puluh persen) secara luring
> atau cold storage dan paling banyak 30% (tiga puluh persen) secara
> daring atau hot storage.

**Catatan terminologi wajib.** Istilah resmi regulasi adalah "Pengelola
Tempat Penyimpanan." Kata "Kustodian" tidak muncul satu kali pun di
POJK 27/2024 maupun POJK 23/2025 (diverifikasi lewat pencarian teks
penuh 178 halaman). "Kustodian" adalah istilah internal PRIMA, bukan
istilah dari peraturan. Kode dan dokumen PRIMA boleh tetap memakai
"Kustodian" sebagai label UI, tapi setiap materi yang dikutip langsung
ke penguji atau ke slide harus menyebut nama resminya kalau merujuk
pasal ini secara langsung.

Ayat (3) belum ditemukan direpresentasikan di manapun dalam sistem
PRIMA saat verifikasi ini ditulis -- verdict PRIMA saat ini menguji
rasio 30/70 antara Pedagang dan Pengelola Tempat Penyimpanan, tapi
belum menguji split cold/hot storage di dalam porsi 30% milik Pedagang.
Di luar cakupan MVP tiga-chain, dicatat sebagai keterbatasan yang
diketahui bila ditanya penguji.

## Ekuitas minimum Pedagang

**Sebelum POJK 23/2025: Pasal 45 ayat (2), POJK 27/2024 asli, halaman 34.**
**Sesudah POJK 23/2025: Pasal 50 ayat (1) huruf o.**

Angka tidak berubah pada kedua versi: Rp50.000.000.000,00 (lima puluh
miliar rupiah).

Naskah asli (Pasal 45 ayat 2, sebelum amandemen):
> Pedagang wajib mempertahankan ekuitas paling sedikit
> Rp50.000.000.000,00 (lima puluh miliar rupiah).

Naskah berlaku sekarang (Pasal 50 ayat 1 huruf o, sesudah amandemen):
> o. mempertahankan ekuitas paling sedikit Rp50.000.000.000,00 (lima
> puluh miliar rupiah) dari modal disetor sebagaimana dimaksud dalam
> Pasal 45 ayat (1);

**Setiap kutipan "Pasal 45 ayat (2)" untuk aturan ekuitas di kode,
komentar, atau slide pitch adalah kutipan basi pasca 10 November 2025.
Kutipan yang benar sekarang adalah Pasal 50 ayat (1) huruf o.**

## Status keberlakuan

POJK 23/2025 ditetapkan 31 Oktober 2025, diundangkan 10 November 2025,
mulai berlaku pada tanggal diundangkan (Pasal I angka 12 batang tubuh
POJK 23/2025). Kedua pasal di atas berlaku penuh pada tanggal demo.

Satu ketentuan peralihan relevan yang belum tercatat sebelumnya di
proyek ini: Pasal II angka 4 POJK 23/2025 memberi masa penyesuaian 12
bulan sejak berlakunya (berakhir sekitar 10 November 2026) untuk
kewajiban kepemilikan/penguasaan/pengendalian sistem sebagaimana
dimaksud Pasal 20, 28, 36, 40, dan 45 -- di luar cakupan Pasal 91 dan
Pasal 50 di atas, jadi tidak mengubah kesimpulan T0.1 ini, tapi dicatat
untuk kelengkapan kalau penguji bertanya soal masa transisi regulasi.
