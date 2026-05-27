# Keterbatasan Sistem PRIMA dan Rencana Mitigasi
### Dokumen Integritas Teknis, Versi 2.0

Terakhir diperbarui: 28 Mei 2026 (v1.9-pasal50-pasal91)

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

PRIMA v1.9 mendukung 3 chain native (BTC, ETH, SOL) dengan cakupan token sebagai berikut:

- Ethereum: ETH native plus curated top-50 ERC-20 (dipilih dari 821 aset ERC-20 terdaftar di bursa CFX per 19 Mei 2026, berdasarkan top market cap CoinGecko dan relevansi profil PAKD Indonesia
- Solana: SOL native plus seluruh SPL token yang muncul di wallet via Helius `getTokenAccountsByOwner`, difilter two-gate (Jupiter verified set ATAU has-price di Gate 1; has-price wajib di Gate 2 untuk masuk kalkulasi nilai).
- Bitcoin: UTXO via Blockstream Esplora. Saldo native only, tidak ada token layer di BTC.

Aset yang berada di luar cakupan saat ini:

- Token ERC-20 di luar 50 curated list (long-tail, token baru, token lokal). Dilaporkan UNVALUED.
- Token SPL Token-2022 (menggunakan extension program berbeda dari SPL standar). Tidak dienumerasi oleh `getTokenAccountsByOwner` pada program standar.
- Aset di L1 lain (Polygon, BNB Chain, Avalanche, Tron, dan lainnya).
- Aset yang disimpan di layanan kustodian pihak ketiga di luar wallet yang dideklarasikan PAKD.

Bitcoin proof-of-ownership belum diimplementasi (BIP-322 dijadwalkan Phase 2). Verifikasi kepemilikan dompet BTC saat ini hanya berdasarkan deklarasi PAKD tanpa cryptographic proof.

### Tingkat Risiko

Menengah, dan menurun seiring perluasan curated list. Untuk PAKD yang portofolionya didominasi token ERC-20 long-tail di luar 50 curated atau Token-2022, rekonsiliasi tidak menggambarkan posisi ekuitas yang sebenarnya. Untuk PAKD dengan portofolio SOL, cakupan sudah mendekati penuh (Jupiter two-gate filter mencakup token dengan harga terdaftar).

### Kondisi yang Memperburuk Risiko

Jika porsi aset nasabah di PAKD tertentu didominasi oleh token altcoin di luar cakupan, atau aset di jaringan selain tiga yang dicakup, rekonsiliasi MVP akan menunjukkan saldo on-chain yang jauh lebih rendah dari kewajiban yang dilaporkan. Bukan karena defisit nyata, melainkan karena aset tidak terlihat oleh sistem.

### Mitigasi Roadmap (v2.0 sampai v3.0)

Perluasan bertahap berdasarkan prioritas nilai aset:

- v2.0: Implementasi BIP-322 untuk Bitcoin signature verification
- v2.0: Tambah token ERC-20 dan SPL prioritas (WBTC, DAI, BUSD)
- v2.5: BNB Chain dan Polygon via BscScan dan Polygonscan API
- v3.0: Custodial reporting standard untuk aset off-chain dan evaluasi kebutuhan integrasi aset custodian berdasarkan regulasi OJK yang berkembang

### Status saat ini

Curated top-50 ERC-20 aktif di v1.9. SPL token enumeration via Helius aktif dengan two-gate filter Jupiter. BTC hanya native balance. Token-2022 dan ERC-20 di luar curated list dilaporkan UNVALUED. Chain L1 selain ETH, BTC, SOL belum didukung. Full enumeration ERC-20 dijadwalkan Phase 2 setelah infrastruktur API berbayar tersedia (lihat Section 9 untuk detail cacat teknis Reading C).

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

## 4. Framework Stress Test Ketahanan Ekuitas, Pasal 50 dan Pasal 91

### Deskripsi

PRIMA menjalankan satu stress test ketahanan ekuitas dengan dua sumber shock yang di-anchor ke pasal POJK 23/2025. Output keduanya adalah pertanyaan yang sama: apakah ekuitas pasca shock masih di atas ambang batas Rp 50 miliar yang diatur Pasal 50 ayat (1) huruf o.

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

Cakupan tanggung jawab: stress test cyber risk PRIMA hanya menghitung kewajiban penggantian atas Aset Kripto Konsumen yang berada di wallet yang dilaporkan PAKD. Tidak include Aset Konsumen yang ada di Pengelola Tempat Penyimpanan. Skema kustodi 70/30 (minimum 70% di Pengelola Tempat penyimpanan per regulasi POJK 23/2025) berarti PAKD dalam praktiknya hanya pegang maksimum 30% Aset Konsumen, dan stress test cyber risk PRIMA terbatas pada porsi tersebut.

Logic perhitungan per skenario:
liability_idr = customer_akd_idr × persentase_kehilangan
equity_post   = equity_idr − liability_idr
pass_flag     = (equity_post >= 50_000_000_000)

### Tingkat Risiko

Rendah dalam konteks MVP. Skenario historis konsisten dengan praktik stress test regulasi sektor keuangan konvensional, mengacu pada metodologi IMF Financial Sector Assessment Program yang juga menggunakan skenario historis sebagai baseline.

### Kondisi yang Memperburuk Risiko

- Kondisi pasar yang belum pernah terjadi sebelumnya, krisis sistemik dengan drawdown > 80%.
- Kehilangan custodial yang melibatkan Pengelola Tempat penyimpanan, di luar cakupan PRIMA MVP.

### Mitigasi Roadmap (v2.0 sampai v3.0)

- v2.0: Stablecoin stress scenario terpisah dari volatile assets, dengan threshold yang berbeda berdasarkan profil depeg historis (USDC pernah USD 0.87 saat SVB collapse 11 Maret 2023, Reuters reporting hari yang sama).
- v3.0: Implied volatility dari pasar opsi kripto (Deribit API) untuk skenario forward-looking sebagai layer tambahan di atas baseline historis.
- v3.0: Custodial scenario expansion mencakup Aset Konsumen di Pengelola Tempat penyimpanan berdasarkan regulasi yang berkembang.

### Status saat ini

Dual-test framework Pasal 50 plus Pasal 91 telah diimplementasikan per versi 1.9-pasal50-pasal91 (Mei 2026). Pasal 50 (Risiko Pasar) mensimulasikan penurunan harga volatile -25%/-50%/-80% dengan threshold ekuitas minimum Rp 50.000.000.000 sesuai Pasal 50(1)(o) POJK No. 23 Tahun 2025. Pasal 91 (Risiko Siber) mensimulasikan kehilangan AKD konsumen -23%/-45%/-100% dengan basis historis GDAC 2023, WazirX 2024, dan Mt Gox 2014. Parameter `pakd_id` wajib diisi pada endpoint `/api/stress-test` (return 400 jika kosong). Baseline aset diambil dari snapshot `reconciliation_snapshots` Supabase terbaru untuk menghindari OOM pada Render free tier 512MB yang terjadi saat live RPC fetch semua PAKD sekaligus.

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

PRIMA v1.9 memiliki lapisan autentikasi parsial yang sudah diimplementasikan:

**Sudah diimplementasikan:**
- Admin token via header `X-Admin-Token` pada seluruh endpoint write: `POST /api/input-manual`, `POST /api/pakd`, `PUT /api/pakd/<id>`, `DELETE /api/pakd/<id>`. Token dibandingkan menggunakan `hmac.compare_digest` (constant-time comparison per OWASP ASVS V2.10.3, mencegah timing attack).
- Token guard: jika `ADMIN_TOKEN` tidak di-set di environment, endpoint langsung return 401. Tidak ada fallback ke empty string.
- Internal token terpisah via `X-Internal-Token` untuk endpoint cron `POST /api/internal/refresh-all`. Digenerate via `openssl rand -hex 32`, disimpan di Render environment variable.
- Rate limiting: `GET /api/reconciliation` dibatasi satu call per 60 detik via `_last_rekon_time` global state. Bypass aktif saat `TESTING=True` untuk mencegah regresi test suite.
- Row Level Security (RLS) diaktifkan di seluruh tabel Supabase (`public.pakd`, `public.wallets`, `public.reconciliation_snapshots`) dengan policy `service_only` yang membatasi akses ke `service_role`.
- CORS origin restriction via `CORS(app, origins=ALLOWED_ORIGINS)`. Default: `prima-ojk.onrender.com`. Override via env `ALLOWED_ORIGINS` untuk staging atau custom domain.
- Connection pool: `psycopg2.pool.SimpleConnectionPool(minconn=1, maxconn=5)` menggantikan per-query `psycopg2.connect()`. Mengurangi koneksi TCP dari 2-4 per request ke reuse pool. `SimpleConnectionPool` bukan thread-safe, aman karena DB calls terjadi di main thread.
- Wallet uniqueness cross-PAKD: `_check_wallet_uniqueness()` mencegah satu alamat wallet terdaftar di lebih dari satu PAKD. Dipanggil di `create_pakd`, `update_pakd`, dan `input_manual`. Mencegah double-counting saldo on-chain.
- Unified error response: `_error_response(message, detail, status_code)` menstandarkan format error di seluruh endpoint. Menggantikan 4 format error yang sebelumnya tidak konsisten.

**Belum diimplementasikan:**
- Authentication mechanism untuk pengguna dashboard (tidak ada login, tidak ada session management, tidak ada user identity tracking).
- Role-based access control (RBAC). Tidak ada pembedaan akses antara OJK supervisor, OJK auditor, dan PAKD compliance officer.
- Cryptographic integrity untuk audit log. Audit log telah di-upgrade ke arsitektur dual-write (primary: tabel `audit_log` di Supabase, fallback: `audit_log.json` lokal), tetapi belum memiliki hash chain atau tamper-evident structure. Data audit persisten antar restart Render.

Untuk konteks hackathon dengan data demonstrasi, gap yang tersisa ini aman. Untuk implementasi produksi dengan data regulasi nyata, RBAC dan authentication pengguna bersifat mandatory.

## Keterbatasan Keamanan (Diketahui, Deferred Post-Demo)

| ID | Temuan | Status | Mitigation Plan |
|----|--------|--------|----------------|
| CRIT-1 | Wildcard CORS, endpoint publik | Sebagian -- `ALLOWED_ORIGINS` env-based restriction aktif, default `prima-ojk.onrender.com` | Produksi: restrict origin ke domain OJK + API key middleware |
| CRIT-2 | Tidak ada autentikasi endpoint write | Sebagian -- admin token aktif (lihat deskripsi di atas) | Produksi: Bearer token berbasis PKI OJK (POJK No. 23/2025 Pasal 50). Read endpoint masih terbuka. |
| CRIT-3 | CHALLENGE_STORE tidak dibatasi | Terbuka | Produksi: cachetools.TTLCache + flask-limiter |
| CRIT-4 | File locking pakd_data.json | Berkurang -- `pakd_data.json` hanya seed/fallback, primary storage di Supabase | Produksi: eliminasi file-based state sepenuhnya. `audit_log.json` juga sudah dual-write ke Supabase. |
| HIGH-1 | API key di URL query string | Terbuka | Produksi: pass via params dict, sanitize logs |
| HIGH-7 | PRICE_CACHE non-thread-safe | Terbuka | Produksi: threading.Lock atau Redis shared cache |

Catatan: PRIMA versi demo beroperasi sebagai single-worker instance (-w 1) untuk menghindari race condition cache. Skalabilitas multi-worker adalah item roadmap Phase 2.

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

- Filesystem ephemeral untuk file lokal (`pakd_data.json`, `audit_log.json`). Setelah instance restart, seed data direload dari kode. Untuk snapshot rekonsiliasi, Supabase (`reconciliation_snapshots`) sudah diintegrasikan sebagai persistent storage — data snapshot tidak hilang saat restart.
- Cold start latency. Instance idle lebih dari 15 menit di-spin-down, request pertama setelah idle butuh 30 sampai 60 detik untuk respawn. Mitigasi: cron-job.org ping setiap 5 menit (diubah dari 10 menit) via `POST /api/internal/refresh-all` yang sekaligus mengupdate snapshot Supabase.
- Page load dari snapshot. Frontend memanggil `GET /api/reconciliation/latest` (response <1 detik dari Supabase) bukan `GET /api/reconciliation` (live fetch yang cold-cache bisa 77 detik). Bottleneck cold start ETH terkonfirmasi via profiling empiris 20 Mei 2026: `fetch_eth_total` cold = 63.8 detik, warm = 0.01 detik (82.3% total waktu ada di ETH fetch).

Selain ephemeral filesystem, PRIMA bergantung pada API publik external:

- Etherscan V2 (free tier 5 request per detik, 100K request per hari). Mandatory param `chainid=1` sejak migrasi V1 ke V2.
- Blockstream Esplora (no formal rate limit publicly documented, rate-limit policies dapat berubah tanpa notice).
- CoinMarketCap v2 (15K credits per bulan, 50 req per menit). Primary price source. `PRICE_TTL=300` detik (bumped dari 60) untuk efisiensi credit budget.
- CoinGecko Demo API (30 contract address per call limit, 30 call per menit). Fallback price source untuk ERC-20 batch lookup. Base URL: `api.coingecko.com`, auth via header `x-cg-demo-api-key`.
- Helius RPC (Solana SPL token enumeration via `getTokenAccountsByOwner`; override via `SOLANA_RPC_URL` env var).
- Jupiter Tokens V2 (verified token set untuk SPL two-gate filter Gate 1).
- Jupiter Price V3 (harga SPL token untuk gate kedua two-gate filter; lite-api deprecation watch diperlukan).
- Solana JSON-RPC via Helius (SOL native balance via `getBalance`).

Price cascade empat tingkat aktif: CMC v2 (Tier 1) ke CoinGecko Demo (Tier 2) ke cache stale (Tier 3) ke hardcoded fallback (Tier 4). `harga_fallback=False` dikonfirmasi di production — CMC aktif.

### Tingkat Risiko

Tinggi untuk produksi karena single point of failure di external API tanpa contracted SLA. Menengah untuk MVP karena caching plus warm-up procedure menjaga survivability dalam window demo.

### Mitigasi Roadmap (v2.0 sampai v2.5)

- v1.9 (selesai): Supabase `reconciliation_snapshots` sebagai persistent storage untuk snapshot rekonsiliasi. Page load dari snapshot, bukan live fetch. Mengeliminasi cold start impact pada UX normal.
- v2.0: Multi-source RPC fallback untuk Solana via Helius dan QuickNode, plus contracted SLA dengan API providers tier-1 untuk produksi.
- v2.0: Backend ke Render paid tier dengan persistent disk untuk eliminasi ephemeral filesystem sepenuhnya.
- v2.5: Internal price oracle yang aggregate beberapa sumber untuk reduce dependency ke CMC dan CoinGecko.

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


## 9. ETH ERC-20 Enumeration: Pendekatan Curated dan Scope Phase 2

### Deskripsi

PRIMA v1.9 mengimplementasikan enumeration token ERC-20 di Ethereum menggunakan daftar curated 50 token, bukan enumeration penuh dari seluruh token yang dipegang wallet. Pendekatan ini dipilih karena lima keterbatasan teknis pada pendekatan full enumeration (Reading C):

1. Etherscan token transfer 10K cap. Endpoint `tokentx` Etherscan membatasi respons di 10.000 transaksi per query. Wallet dengan aktivitas tinggi tidak mendapat representasi lengkap token historis via endpoint ini.
2. CoinGecko Demo API 30-address limit. Endpoint `simple/token_price` pada Demo plan membatasi request ke 30 contract address per call. Full enumeration wallet dengan lebih dari 30 token unik membutuhkan N+1 call pattern yang tidak efisien.
3. N+1 call pattern. Full enumeration membutuhkan satu call per token untuk validasi harga, menghasilkan jumlah HTTP request yang tumbuh linear terhadap jumlah token unik per wallet per PAKD.
4. Render timeout 30 detik. Instance Render free tier membatasi response time. Full enumeration dengan banyak token dapat melampaui batas ini pada wallet aktif dengan portofolio besar.
5. Etherscan tokeninfo endpoint paid tier. Metadata token lengkap via endpoint `tokeninfo` membutuhkan Etherscan API paid plan. Demo plan tidak menyediakan akses ini secara reliable.

Solusi yang diimplementasikan: daftar curated 50 token dipilih berdasarkan tiga kriteria: (1) termasuk dalam 821 aset ERC-20 yang terdaftar di bursa PT Central Finansial X (CFX) per 19 Mei 2026 representasi terkini Daftar Aset Kripto yang berlaku di Indonesia. Angka 821 berasal dari analisis pemetaan jaringan blockchain terhadap 1.266 aset CFX, di mana 65,2% beroperasi di Ethereum atau EVM-compatible L2. (2) Termasuk dalam top market cap global per CoinGecko ranking memastikan token yang di-track memiliki likuiditas dan price feed yang reliabel. (3) Relevan untuk profil PAKD Indonesia berdasarkan data perdagangan historis token long-tail dengan volume minim diprioritaskan lebih rendah.

Token yang tidak teridentifikasi oleh curated list tetap dilaporkan sebagai `eth_other_token_idr` dengan label UNVALUED di frontend. Supervisor OJK mengetahui adanya token di luar cakupan tanpa nilai rupiah yang dapat direkonsiliasi, sehingga dapat memutuskan perlu tidaknya investigasi manual.

### Tingkat Risiko

Menengah. PAKD dengan portofolio ERC-20 yang didominasi token di luar 50 token curated akan menampilkan nilai UNVALUED yang besar, sehingga saldo on-chain ETH yang direkonsiliasi undercount nilai sebenarnya.

### Kondisi yang Memperburuk Risiko

PAKD yang secara sengaja memegang aset di token long-tail di luar curated list dapat memanfaatkan celah ini untuk menyembunyikan nilai aset dari rekonsiliasi otomatis PRIMA.

### Mitigasi Roadmap (v2.0)

1. Migrasi ke Etherscan paid tier untuk akses `tokeninfo` endpoint dan higher rate limit.
2. Upgrade CoinGecko ke paid plan untuk menghilangkan 30-address cap per call.
3. Implementasi batch price lookup dengan queue dan retry untuk mengeliminasi N+1 pattern.
4. Migrasi backend ke instance dengan response timeout lebih panjang.
5. Caching contract address metadata persisten via PostgreSQL untuk mengurangi API call berulang per rekonsiliasi.

### Status saat ini

Curated 50-token list aktif di v1.9. Token di luar list dilaporkan sebagai UNVALUED. Full enumeration dijadwalkan Phase 2 setelah infrastruktur API berbayar tersedia.

---

## 10. Fetch Performance dan Arsitektur Background Refresh

### Deskripsi

Profiling empiris pada 20 Mei 2026 mengukur latency rekonsiliasi live di production Render free tier untuk 4 PAKD aktif:

| Segmen | Cold cache | Warm cache |
|--------|-----------|-----------|
| fetch_eth_total | 63.8 detik | 0.01 detik |
| fetch_sol_total | 5.9 detik | 3.3 detik |
| db_write (sequential) | 5.5 detik | 5.5 detik |
| Total | 77.5 detik | 11.1 detik |

ETH cold cache adalah 82.3% total waktu karena sequential request ke Etherscan V2 free tier (5 req/detik untuk 53 request per wallet: 1 native + 2 stablecoin + 50 ERC-20 curated). Proyeksi 25 PAKD dengan 100 ETH wallet: cold start di atas 10 menit.

Solusi yang diimplementasikan adalah arsitektur hybrid dua lapis:

**Layer 1 — Background snapshot (sudah live):** `POST /api/internal/refresh-all` dipanggil cron-job.org tiap 5 menit. Hasil disimpan via `_save_snapshots_batch()` ke Supabase dalam satu `executemany()`. Page load memanggil `GET /api/reconciliation/latest` (response <1 detik dari `DISTINCT ON` query Supabase). Badge dan timestamp "Data terakhir diperbarui" ditampilkan di frontend.

**Layer 2 -- Manual refresh async (sudah live):** `POST /api/reconciliation/refresh` generate `job_id` dan submit task ke `ThreadPoolExecutor(max_workers=3)`. `GET /api/reconciliation/refresh/<job_id>` di-poll frontend tiap 2 detik. `REFRESH_LOCK` global mencegah concurrent run. `JOBS` dict in-memory tidak persist antar restart (acceptable untuk hackathon scope). Rekonsiliasi berjalan sequential per-PAKD dengan chain timeout graceful degradation (ETH 25 detik, BTC 15 detik, SOL 25 detik). Jika satu chain timeout, chain tersebut return empty result dengan nilai 0 tanpa menghentikan PAKD berikutnya. Executor digunakan tanpa `with` block untuk mencegah hang akibat `shutdown(wait=True)` yang menunggu thread lambat selesai meskipun timeout sudah tercapai.

### Keterbatasan yang Tersisa

- SOL warm cache masih 3.3 detik karena Jupiter `_get_jupiter_verified_set()` masih hit network tiap call (bukan `BALANCE_CACHE`). Acceptable untuk demo scope.
- `JOBS` dict hilang saat Render restart. User perlu retry manual refresh setelah restart.
- `[BATCH_SAVE]` debug log masih aktif di production (belum di-wrap `PRIMA_DEBUG`).

### Tingkat Risiko

Rendah untuk MVP. Live demo menggunakan snapshot dari Supabase, tidak tergantung cold start ETH.

### Mitigasi Roadmap (v2.0)

- Multicall3 via Etherscan V2 proxy `eth_call` untuk batch ETH native + ERC-20 dalam satu request.
- Multi-provider race untuk BTC (Blockstream + mempool.space + BlockCypher via ThreadPoolExecutor).
- Jupiter verified set caching ke `BALANCE_CACHE` untuk eliminasi SOL warm cache latency.
- Persistent job queue via Redis untuk replace in-memory `JOBS` dict.

---



| Keterbatasan | Tingkat Risiko | Status v1.9 | Target Mitigasi |
|--------------|----------------|-------------|-----------------|
| Window Dressing | Menengah | Terbuka | v2.0 |
| Cakupan Aset On-Chain | Menengah | ERC-20 curated 50, SPL full via Jupiter, BTC native only | v2.0 sampai v3.0 |
| Wallet Ownership Verification | Rendah ETH/SOL, Menengah BTC | ETH dan SOL: selesai. BTC: belum (BIP-322) | v2.0 |
| Framework Stress Test Pasal 50 dan 91 | Rendah | Selesai -- dual test live, pakd_id wajib, baseline dari Supabase snapshot | v2.0 sampai v3.0 |
| Stablecoin Threshold Configurable | Rendah | Terbuka | v2.0 |
| Authentication, RBAC, Audit Log Integrity | Tinggi (produksi) | Parsial -- admin token write, RLS Supabase, CORS restriction, connection pool, wallet uniqueness, unified error. RBAC dan user auth belum. Audit log dual-write Supabase. | v2.0 |
| Infrastruktur, Rate Limit, Persistence | Tinggi (produksi), Menengah (MVP) | Supabase live. Hybrid fetch (snapshot + async per-PAKD). Connection pool maxconn=5. Cache eviction aktif. N+1 query eliminated. | v2.0 sampai v2.5 |
| Polish UI dan Edge Cases | Rendah | Terbuka | v1.1 |
| ETH ERC-20 Curated Enumeration (Reading C) | Menengah | Curated 50 aktif. Full enumeration deferred. | v2.0 |
| Fetch Performance dan Arsitektur Background Refresh | Rendah (setelah hybrid arch) | Hybrid live. Manual refresh per-PAKD sequential dengan chain timeout graceful (ETH 25s/BTC 15s/SOL 25s). SOL warm cache masih 3.3 detik. | v2.0 |

---

*Dokumen ini adalah bagian dari komitmen PRIMA terhadap transparansi teknis. Versi dokumen diperbarui setiap kali arsitektur sistem mengalami perubahan material.*
