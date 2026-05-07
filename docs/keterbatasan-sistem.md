# Keterbatasan Sistem PRIMA dan Rencana Mitigasi
### Dokumen Kejujuran Teknis, Versi 2.0

Terakhir diperbarui: Mei 2026

---

## Pendahuluan

Dokumen ini mendokumentasikan keterbatasan arsitektur PRIMA secara eksplisit. Pendekatan ini didasarkan pada prinsip bahwa sistem pengawasan yang mengakui batas kemampuannya lebih dapat dipercaya daripada sistem yang mengklaim kemampuan yang tidak dapat dibuktikan.

Setiap keterbatasan disertai deskripsi teknis, tingkat risiko, kondisi yang memperburuk risiko, dan rencana mitigasi untuk versi berikutnya.

---

## 1. Window Dressing, Kerentanan Snapshot Tunggal

### Deskripsi

Rekonsiliasi pada MVP menggunakan satu titik waktu per periode (snapshot tunggal). PAKD yang mengetahui jadwal rekonsiliasi dapat memindahkan aset sementara ke dompet yang terdaftar menjelang tanggal snapshot, kemudian memindahkannya kembali setelah verifikasi selesai.

### Tingkat Risiko

Menengah. Praktik ini memerlukan koordinasi yang disengaja dan meninggalkan jejak transaksi on-chain yang dapat diaudit secara forensik di kemudian hari. Bukan tanpa risiko bagi pelaku.

### Kondisi yang Memperburuk Risiko

Jadwal rekonsiliasi yang tetap dan dapat diprediksi (misalnya selalu tanggal 25 setiap bulan) meningkatkan kemungkinan window dressing terencana.

### Mitigasi Roadmap (v2.0)

Rekonsiliasi multi-titik: empat kali per bulan pada tanggal yang dipilih secara acak oleh sistem. Tanggal rekonsiliasi tidak diinformasikan kepada PAKD sebelumnya. Hasil dari empat titik digabungkan untuk menghasilkan saldo rata-rata periode, bukan saldo titik tunggal. Pendekatan ini secara signifikan meningkatkan biaya operasional window dressing.

### Status saat ini

Jadwal rekonsiliasi bulanan pada MVP bersifat tetap. OJK disarankan untuk tidak mempublikasikan tanggal rekonsiliasi kepada PAKD sebagai mitigasi parsial sementara v2.0 dikembangkan.

---

## 2. Cakupan Aset On-Chain

### Deskripsi

PRIMA MVP mendukung 3 chain native (BTC, ETH, SOL) dan 4 token: USDT dan USDC di Ethereum (ERC-20) plus USDT dan USDC di Solana (SPL). Aset yang berada di luar cakupan saat ini:

- Token ERC-20 selain USDT dan USDC (misalnya WBTC, DAI, BUSD, LINK)
- Token SPL selain USDT dan USDC
- Aset di L1 lain (Polygon, BNB Chain, Avalanche, Tron, dan lainnya)
- Aset yang disimpan di layanan kustodian pihak ketiga di luar wallet PAKD yang dideklarasikan

Bitcoin proof-of-ownership belum diimplementasi (BIP-322 dijadwalkan Phase 2). Verifikasi kepemilikan dompet BTC saat ini hanya berdasarkan deklarasi PAKD tanpa cryptographic proof.

### Tingkat Risiko

Menengah, dan menurun seiring waktu seiring pertumbuhan dominasi tiga chain utama plus stablecoin USDT dan USDC. Untuk PAKD yang portofolionya didominasi oleh token di luar cakupan atau aset di chain yang belum didukung, rekonsiliasi tidak akan menggambarkan posisi solvabilitas yang sebenarnya.

### Kondisi yang Memperburuk Risiko

Jika porsi aset nasabah di PAKD tertentu didominasi oleh token altcoin di luar cakupan, atau aset di jaringan selain tiga yang dicakup, rekonsiliasi MVP akan menunjukkan saldo on-chain yang jauh lebih rendah dari kewajiban yang dilaporkan. Bukan karena defisit nyata, melainkan karena aset tidak terlihat oleh sistem.

### Mitigasi Roadmap (v2.0 sampai v3.0)

Perluasan bertahap berdasarkan prioritas nilai aset:

- v2.0: Implementasi BIP-322 untuk Bitcoin signature verification
- v2.0: Tambah token ERC-20 dan SPL prioritas (WBTC, DAI, BUSD)
- v2.5: BNB Chain dan Polygon via BscScan dan Polygonscan API
- v3.0: Custodial reporting standard untuk aset off-chain dan evaluasi kebutuhan integrasi aset custodian berdasarkan regulasi OJK yang berkembang

### Status saat ini

Pada laporan kewajiban PAKD kepada OJK, disarankan untuk mewajibkan PAKD mencantumkan proporsi aset per jenis dan per jaringan, sehingga OJK dapat mengetahui berapa persen dari total kewajiban yang sudah tercakup oleh rekonsiliasi PRIMA MVP.

---

## 3. Wallet Ownership Verification, Dua Mode dengan Trade-Off Berbeda

### Deskripsi

PRIMA mendukung dua mode verifikasi kepemilikan dompet PAKD.

Primary mode untuk production: off-chain signature submission via API endpoint `/api/wallet-verify`. PAKD generate signature menggunakan signing tool atau library standard di environment masing-masing, kemudian submit signature blob ke OJK via channel resmi (email, portal upload, atau direct API call). OJK supervisor input signature ke dashboard untuk diverifikasi backend. Mode ini sesuai dengan reality production: OJK supervisor dan PAKD adalah entitas berbeda di laptop berbeda.

Convenience mode untuk testing dan workshop: MetaMask integration in-browser, useful untuk internal OJK sandbox testing dan onboarding session dengan PAKD compliance officer di laptop netral. Mode ini mengasumsikan operator dashboard adalah pemilik wallet, asumsi yang tidak match dengan production reality.

Bitcoin signature verification belum tersedia (BIP-322 phase 2). Saat ini wallet BTC tidak dapat diverifikasi kepemilikannya secara kriptografis, hanya berdasarkan deklarasi PAKD.

### Tingkat Risiko

Rendah untuk Ethereum dan Solana (signature verification sudah berfungsi end-to-end via EIP-191 personal_sign dan Ed25519). Menengah untuk Bitcoin (no proof-of-ownership pada MVP).

### Mitigasi Roadmap (v2.0)

- BIP-322 implementation untuk Bitcoin signature verification
- Hardware wallet integration (Ledger, Trezor) untuk reduce risiko private key exposure di MetaMask convenience mode
- Multi-sig signature support untuk PAKD yang gunakan multi-sig wallet management

### Status saat ini

ETH dan SOL signature verification implementasi via library `eth-account` (EIP-191 personal_sign) dan `PyNaCl` plus base58 (Ed25519). Cryptographic verification konsisten dengan industry best practice.

---

## 4. Framework Stress Test Solvabilitas, Pasal 50 dan Pasal 91

### Deskripsi

PRIMA menjalankan satu stress test solvabilitas dengan dua sumber shock yang di-anchor ke pasal POJK 27/2024. Output keduanya adalah pertanyaan yang sama: apakah ekuitas pasca shock masih di atas ambang batas Rp 50 miliar yang diatur Pasal 50 ayat (1) huruf o.

#### Test 1: Risiko Pasar (Pasal 50)

Shock yang dimodelkan adalah penurunan harga aset kripto akibat pergerakan pasar. Aset yang terdampak adalah aset proprietary PAKD: Persediaan Aset Keuangan Digital (untuk dijual ke Konsumen) plus Simpanan milik PAKD (proprietary investment). Aset Konsumen tidak masuk perhitungan Risiko Pasar karena per regulasi PAKD berkewajiban mengembalikan unit Aset Kripto yang sama, bukan nilai rupiah yang sama. Risiko pergerakan harga aset Konsumen ditanggung Konsumen sendiri.

Tiga skenario penurunan harga: -25%, -50%, -80%.

Justifikasi historis:

- 25% sering terjadi dalam siklus pasar normal lintas tahun.
- 50% mendekati pergerakan BTC peak-to-trough dalam siklus tahunan. Contoh: BTC turun 64% sepanjang 2022 (sumber: Chainalysis 2024 Crypto Crime Report).
- 80% merefleksikan skenario severe peak-to-trough seperti BTC dari ATH November 2017 ke bottom Desember 2018, dan dekat dengan BTC ATH November 2021 ke bottom 2022.

Logic perhitungan per skenario:
dampak_idr  = (persediaan_akd_idr + simpanan_pedagang_akd_idr) × persentase_penurunan
equity_post = equity_idr − dampak_idr
pass_flag   = (equity_post >= 50_000_000_000)

#### Test 2: Risiko Siber dan Operasional (Pasal 91)

Shock yang dimodelkan adalah kehilangan Aset Kripto Konsumen akibat serangan siber atau insiden operasional. Per Pasal 91 ayat (1), kehilangan tersebut menjadi kewajiban PAKD untuk diganti, yang mereduksi ekuitas.

Tiga skenario kehilangan dengan benchmark historis insiden internasional:

- 23%, benchmark GDAC April 2023. Sumber: CoinDesk dan Cointelegraph 10 April 2023, GDAC kehilangan USD 13 juta atau 23% total custodial assets dari hot wallet.
- 45%, benchmark WazirX Juli 2024. Sumber: Decrypt Januari 2025 menyebut 45% reserves, Crystal Intelligence dan CloudSEK menyebut 50%, range 43 sampai 50% di pernyataan resmi WazirX. PRIMA menggunakan 45% sebagai angka konservatif yang defensible.
- 100%, benchmark Mt Gox Februari 2014. Sumber: Wikipedia Mt Gox dan filing kebangkrutan Tokyo Februari 2014, Mt Gox kehilangan 750.000 BTC milik Konsumen plus 100.000 BTC milik perusahaan. 200.000 BTC ditemukan kemudian dan disbursement ke kreditur baru dimulai Juli 2024 setelah 10 tahun proses.

Cakupan tanggung jawab: stress test cyber risk PRIMA hanya menghitung kewajiban penggantian atas Aset Kripto Konsumen yang berada di wallet yang dilaporkan PAKD. Tidak include Aset Konsumen yang ada di Pengelola Tempat Penyimpanan (PTP). Skema kustodi 70/30 (minimum 70% di PTP per regulasi POJK 27/2024) berarti PAKD dalam praktiknya hanya pegang maksimum 30% Aset Konsumen, dan stress test cyber risk PRIMA terbatas pada porsi tersebut.

Logic perhitungan per skenario:
liability_idr = customer_akd_idr × persentase_kehilangan
equity_post   = equity_idr − liability_idr
pass_flag     = (equity_post >= 50_000_000_000)

### Tingkat Risiko

Rendah dalam konteks MVP. Skenario historis konsisten dengan praktik stress test regulasi sektor keuangan konvensional, mengacu pada metodologi IMF Financial Sector Assessment Program yang juga menggunakan skenario historis sebagai baseline.

### Kondisi yang Memperburuk Risiko

- Kondisi pasar yang belum pernah terjadi sebelumnya, krisis sistemik dengan drawdown > 80%.
- Kehilangan custodial yang melibatkan PTP, di luar cakupan PRIMA MVP.

### Mitigasi Roadmap (v2.0 sampai v3.0)

- v2.0: Stablecoin stress scenario terpisah dari volatile assets, dengan threshold yang berbeda berdasarkan profil depeg historis (USDC pernah USD 0.87 saat SVB collapse 11 Maret 2023, Reuters reporting hari yang sama).
- v3.0: Implied volatility dari pasar opsi kripto (Deribit API) untuk skenario forward-looking sebagai layer tambahan di atas baseline historis.
- v3.0: Custodial scenario expansion mencakup Aset Konsumen di PTP berdasarkan regulasi yang berkembang.

### Status saat ini

Dual-test framework Pasal 50 plus Pasal 91 telah diimplementasikan per versi 1.9-pasal50-pasal91 (Mei 2026). Pasal 50 (Risiko Pasar) mensimulasikan penurunan harga volatile -25%/-50%/-80% dengan threshold ekuitas minimum Rp 50.000.000.000 sesuai Pasal 50(1)(o) POJK No. 27 Tahun 2024. Pasal 91 (Risiko Siber) mensimulasikan kehilangan AKD konsumen -23%/-50%/-100% dengan basis historis GDAC 2023, WazirX 2024, dan Mt Gox 2014.

---

## 5. Stablecoin Stress Threshold Tidak Configurable per PAKD

### Deskripsi

Stress test PRIMA menerapkan threshold yang sama untuk semua PAKD, tanpa mempertimbangkan profil risiko spesifik per PAKD seperti konsentrasi di stablecoin tertentu, leverage operasional, atau exposure ke off-chain assets.

### Tingkat Risiko

Rendah dalam konteks MVP. Threshold uniform memberikan baseline pengawasan yang konsisten lintas PAKD dan menghindari perdebatan kalibrasi per entitas pada tahap awal.

### Mitigasi Roadmap (v2.0)

Threshold per asset class dan per PAKD risk profile, di-configure oleh OJK supervisor berdasarkan hasil onsite audit dan profil portofolio. Threshold default tetap menjadi baseline minimum, dengan opsi tightening (tidak loosening) untuk PAKD dengan profil risiko tinggi.

---

## 6. Tata Kelola, Audit Trail, dan Authentication

### Deskripsi

PRIMA MVP tidak memiliki:

- Authentication mechanism. Tidak ada login, tidak ada session management, tidak ada user identity tracking.
- Role-based access control (RBAC). Tidak ada pembedaan akses antara OJK supervisor, OJK auditor, dan PAKD compliance officer.
- Cryptographic integrity untuk audit log. File `audit_log.json` adalah plain JSON yang dapat dimodifikasi tanpa meninggalkan jejak. Tidak ada hash chain atau tamper-evident structure.

Untuk konteks hackathon dengan data demonstrasi, ini aman. Untuk implementasi produksi dengan data regulasi nyata, ketiga komponen di atas bersifat mandatory.

### Tingkat Risiko

Tinggi untuk produksi. Rendah untuk MVP demo dengan data ilustratif.

### Mitigasi Roadmap (v2.0)

- v2.0: SSO integration dengan sistem identity OJK existing (LDAP, ADFS, atau equivalent yang dipakai internal OJK).
- v2.0: RBAC dengan minimum 3 role yaitu Supervisor (read-only akses ke dashboard pengawasan), Auditor (read plus sign-off pada hasil rekonsiliasi), Admin (full access termasuk schema migration dan PAKD onboarding).
- v2.0: Audit log hash chain. Setiap entri di-hash dengan SHA-256 termasuk hash entri sebelumnya, sehingga tampering apa pun di log akan terdeteksi via verification routine berkala.

---

## 7. Infrastruktur Hosting, Rate Limit, dan Persistence

### Deskripsi

Backend PRIMA di-deploy di Render free tier untuk demo hackathon. Konsekuensi arsitekturalnya:

- Filesystem ephemeral. Setelah instance restart, baik karena deploy push, Render maintenance, atau idle spin-down, file `pakd_data.json` revert ke seed dan verified status hilang. Mitigasi sementara: warm-up cron job (cron-job.org) ping setiap 10 menit, plus prosedur baseline reset 5 menit sebelum demo.
- Cold start latency. Instance idle lebih dari 15 menit di-spin-down, request pertama setelah idle butuh 30 sampai 60 detik untuk respawn.

Selain ephemeral filesystem, PRIMA bergantung pada API publik external:

- Etherscan V2 (free tier 5 request per detik)
- Blockstream Esplora (no formal limit publicly documented, rate-limit policies dapat berubah tanpa notice)
- CoinGecko Public API (free tier kurang lebih 10 sampai 30 request per menit, bervariasi)
- Solana JSON-RPC mainnet-beta (public RPC, throttling tidak deterministik)

Caching layer in-memory dengan TTL 60 detik untuk price dan 30 detik untuk balance mengurangi external API call selama window demo, tapi tidak menghilangkan dependency.

### Tingkat Risiko

Tinggi untuk produksi karena single point of failure di external API tanpa contracted SLA. Menengah untuk MVP karena caching plus warm-up procedure menjaga survivability dalam window demo.

### Mitigasi Roadmap (v2.0 sampai v2.5)

- v2.0: Migrasi backend ke Render paid tier dengan persistent disk, atau pindah ke external storage (PostgreSQL Supabase, atau OJK in-house infrastructure).
- v2.0: Multi-source RPC fallback untuk Solana via Helius dan QuickNode, plus contracted SLA dengan API providers tier-1 untuk produksi.
- v2.5: Internal price oracle yang aggregate beberapa sumber untuk reduce CoinGecko dependency.

---

## 8. Polish UI dan Edge Cases

### Deskripsi

Beberapa edge case dan polish item yang teridentifikasi dan dijadwalkan ke pasca-MVP:

- MetaMask installed-then-disabled mid-session. Object `window.ethereum` tetap ada (zombie reference) tetapi tidak responsif. Workaround current: refresh halaman setelah disable extension. Phase 2 fix: try-catch wrapper di `setupMetaMaskUI()` dengan timeout-based detection.
- Button disabled state belum punya visual differentiation CSS (cursor: not-allowed, opacity reduce). Cosmetic, tidak blocking happy path demo.

### Tingkat Risiko

Rendah. Tidak menghalangi happy path demo.

### Mitigasi Roadmap (v1.1)

Quick polish di pre-pitch window: CSS button disabled state plus zombie `window.ethereum` guard di `setupMetaMaskUI()`.

---

## Ringkasan Status Keterbatasan

| Keterbatasan | Tingkat Risiko | Target Mitigasi |
|--------------|----------------|-----------------|
| Window Dressing | Menengah | v2.0 |
| Cakupan Aset On-Chain | Menengah | v2.0 sampai v3.0 |
| Wallet Ownership Verification | Rendah ETH/SOL, Menengah BTC | v2.0 |
| Framework Stress Test Pasal 50 dan 91 | Rendah | v2.0 sampai v3.0 |
| Stablecoin Threshold Configurable | Rendah | v2.0 |
| Authentication, RBAC, Audit Log Integrity | Tinggi (produksi), Rendah (MVP) | v2.0 |
| Infrastruktur, Rate Limit, Persistence | Tinggi (produksi), Menengah (MVP) | v2.0 sampai v2.5 |
| Polish UI dan Edge Cases | Rendah | v1.1 |

---

*Dokumen ini adalah bagian dari komitmen PRIMA terhadap transparansi teknis. Versi dokumen diperbarui setiap kali arsitektur sistem mengalami perubahan material.*
