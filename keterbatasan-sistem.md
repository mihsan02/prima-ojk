# Keterbatasan Sistem PRIMA dan Rencana Mitigasi
### Dokumen Kejujuran Teknis — Versi 1.0

Terakhir diperbarui: Maret 2026

---

## Pendahuluan

Dokumen ini mendokumentasikan keterbatasan arsitektur PRIMA secara eksplisit.
Pendekatan ini didasarkan pada prinsip bahwa sistem pengawasan yang mengakui
batas kemampuannya lebih dapat dipercaya daripada sistem yang mengklaim
kemampuan yang tidak dapat dibuktikan.

Setiap keterbatasan disertai: deskripsi teknis, tingkat risiko, kondisi
yang memperburuk risiko, dan rencana mitigasi untuk versi berikutnya.

---

## 1. Circular Trust — Dompet yang Dideklarasikan Sendiri

### Deskripsi

PRIMA memverifikasi saldo pada alamat dompet yang dideklarasikan PAKD kepada
OJK. Sistem tidak memiliki kemampuan untuk menemukan dompet yang tidak
dideklarasikan secara mandiri. Jika sebuah PAKD menyembunyikan sebagian dompet
dari daftar yang dilaporkan, saldo tersebut tidak akan masuk dalam rekonsiliasi.

### Tingkat Risiko

Tinggi. Ini adalah keterbatasan fundamental dari pendekatan berbasis deklarasi
dan merupakan kelemahan yang sama yang ada pada sistem audit berbasis dokumen
konvensional.

### Kondisi yang Memperburuk Risiko

Risiko meningkat jika PAKD beroperasi dengan banyak dompet hot wallet yang
dirotasi secara rutin untuk keperluan operasional. Pola rotasi yang sering
membuat rekonsiliasi berbasis daftar statis kehilangan akurasi.

### Mitigasi Roadmap (v2.0)

Penambahan mekanisme random sampling audit independen oleh OJK: setelah
alert Tier 2 diterbitkan, OJK dapat memerintahkan PAKD untuk membuktikan
kepemilikan dompet tambahan melalui penandatanganan kriptografis pesan
yang ditentukan OJK. Dompet yang tidak dapat dibuktikan kepemilikannya
oleh PAKD dalam jangka waktu yang ditetapkan akan dianggap sebagai temuan
material.

### Status saat ini

Keterbatasan ini diakui dan didokumentasikan. PRIMA pada tahap MVP tidak
mengklaim kemampuan untuk mendeteksi penyembunyian dompet yang disengaja.
Posisi sistem: PRIMA meningkatkan biaya operasional kecurangan (lebih sulit
dan lebih berisiko), bukan mengeliminasi kemungkinannya sepenuhnya.

---

## 2. Window Dressing — Kerentanan Snapshot Tunggal

### Deskripsi

Rekonsiliasi pada MVP menggunakan satu titik waktu per periode (snapshot
tunggal). PAKD yang mengetahui jadwal rekonsiliasi dapat memindahkan aset
sementara ke dompet yang terdaftar menjelang tanggal snapshot, kemudian
memindahkannya kembali setelah verifikasi selesai.

### Tingkat Risiko

Menengah. Praktik ini memerlukan koordinasi yang disengaja dan meninggalkan
jejak transaksi on-chain yang dapat diaudit secara forensik di kemudian hari.
Bukan tanpa risiko bagi pelaku.

### Kondisi yang Memperburuk Risiko

Jadwal rekonsiliasi yang tetap dan dapat diprediksi (misalnya selalu tanggal
25 setiap bulan) meningkatkan kemungkinan window dressing terencana.

### Mitigasi Roadmap (v2.0)

Rekonsiliasi multi-titik: empat kali per bulan pada tanggal yang dipilih
secara acak oleh sistem. Tanggal rekonsiliasi tidak diinformasikan kepada
PAKD sebelumnya. Hasil dari empat titik digabungkan untuk menghasilkan
saldo rata-rata periode, bukan saldo titik tunggal. Pendekatan ini secara
signifikan meningkatkan biaya operasional window dressing.

### Status saat ini

Jadwal rekonsiliasi bulanan pada MVP bersifat tetap. OJK disarankan untuk
tidak mempublikasikan tanggal rekonsiliasi kepada PAKD sebagai mitigasi
parsial sementara v2.0 dikembangkan.

---

## 3. Cakupan Aset Terbatas — Tiga Chain Saja

### Deskripsi

MVP mencakup Bitcoin (BTC), Ethereum (ETH), dan Solana (SOL). Aset berikut
berada di luar cakupan saat ini:

- Token ERC-20 di jaringan Ethereum (USDT, USDC, dan lainnya)
- Token SPL di jaringan Solana
- Aset di jaringan Polygon, BNB Chain, Avalanche, dan lainnya
- Aset yang disimpan di layanan kustodian pihak ketiga

### Tingkat Risiko

Menengah, dan menurun seiring waktu seiring pertumbuhan dominasi ketiga
chain utama. Namun untuk PAKD yang memiliki portofolio nasabah dengan
konsentrasi token stablecoin (USDT/USDC), cakupan ERC-20 menjadi lebih
material.

### Kondisi yang Memperburuk Risiko

Jika porsi aset nasabah di PAKD tertentu didominasi oleh stablecoin atau
token di jaringan selain tiga yang dicakup, rekonsiliasi MVP akan menunjukkan
saldo on-chain yang jauh lebih rendah dari kewajiban yang dilaporkan — bukan
karena defisit nyata, melainkan karena aset tidak terlihat oleh sistem.

### Mitigasi Roadmap (v2.0 – v3.0)

Perluasan bertahap berdasarkan prioritas nilai aset:
- v2.0: Tambahkan ERC-20 (USDT, USDC, WBTC) melalui Etherscan Token API
- v2.5: Tambahkan BNB Chain dan Polygon melalui BscScan dan Polygonscan API
- v3.0: Evaluasi kebutuhan integrasi aset custodian berdasarkan regulasi OJK
  yang berkembang

### Status saat ini

Pada laporan kewajiban PAKD kepada OJK, disarankan untuk mewajibkan PAKD
mencantumkan proporsi aset per jenis dan per jaringan, sehingga OJK dapat
mengetahui berapa persen dari total kewajiban yang sudah tercakup oleh
rekonsiliasi PRIMA MVP.

---

## 4. Sumber Data Stress Test — Historis, Bukan Forward-Looking

### Deskripsi

Skenario stress test (-30%, -55%, -80%) didasarkan pada drawdown historis
harga Bitcoin yang terdokumentasi. Sistem tidak menggunakan model proyeksi
forward-looking, implied volatility dari pasar derivatif, atau skenario
kondisional (misalnya: "jika regulasi AS berubah, apa dampaknya?").

### Tingkat Risiko

Rendah dalam konteks MVP. Untuk tujuan pengawasan berbasis data yang dapat
diverifikasi, data historis memiliki keunggulan: tidak bergantung pada asumsi
model yang dapat diperdebatkan.

### Kondisi yang Memperburuk Risiko

Dalam kondisi pasar yang belum pernah terjadi sebelumnya (misalnya krisis
sistemik yang lebih dalam dari 80%), skenario historis tidak memberikan
panduan yang memadai.

### Mitigasi Roadmap (v3.0)

Integrasi data implied volatility dari pasar opsi kripto (Deribit API) untuk
menghasilkan skenario stress test yang lebih prospektif. Pada tahap ini,
skenario historis dipertahankan sebagai baseline dan skenario forward-looking
ditambahkan sebagai lapisan analisis tambahan.

### Status saat ini

Skenario yang digunakan sudah memadai untuk tujuan pengawasan solvabilitas
dasar dan konsisten dengan praktik stress test regulasi di sektor keuangan
konvensional (mengacu pada metodologi IMF Financial Sector Assessment Program
yang juga menggunakan skenario historis sebagai baseline).

---

## 5. Konsentrasi Risiko Operasional pada OJK

### Deskripsi

Karena PRIMA dioperasikan OJK secara in-house (bukan layanan cloud terdistribusi),
kegagalan infrastruktur teknis OJK berdampak langsung pada ketersediaan sistem
pemantauan. Tidak ada redundansi eksternal pada MVP.

### Tingkat Risiko

Menengah untuk ketersediaan sistem; rendah untuk integritas data (data tetap
ada di PostgreSQL meskipun dashboard tidak tersedia).

### Mitigasi Roadmap (v2.0)

Backup otomatis database PostgreSQL ke lokasi penyimpanan terpisah dalam
infrastruktur OJK; prosedur rekonsiliasi manual sebagai fallback jika sistem
otomatis tidak tersedia.

---

## Ringkasan Status Keterbatasan

| Keterbatasan | Tingkat Risiko | Target Mitigasi |
|-------------|----------------|-----------------|
| Circular trust | Tinggi | v2.0 |
| Window dressing | Menengah | v2.0 |
| Cakupan aset terbatas | Menengah | v2.0 – v3.0 |
| Stress test historis | Rendah | v3.0 |
| Konsentrasi operasional OJK | Menengah | v2.0 |

---

*Dokumen ini adalah bagian dari komitmen PRIMA terhadap transparansi teknis.
Versi dokumen diperbarui setiap kali arsitektur sistem mengalami perubahan material.*
