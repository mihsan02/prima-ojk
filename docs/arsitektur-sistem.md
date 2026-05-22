# Arsitektur Sistem PRIMA
### Pemantauan Transparansi Multichain Aset Keuangan Digital 
Versi: 1.9-pasal50-pasal91 · Terakhir diperbarui: 22 Mei 2026

---

## 1. Gambaran Umum

PRIMA beroperasi dalam empat tahap: pengambilan data on-chain dari tiga jaringan blockchain, rekonsiliasi otomatis terhadap laporan kewajiban PAKD, penyimpanan snapshot ke database, dan distribusi output kepada pengawas OJK via dashboard berbasis snapshot.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          INFRASTRUKTUR OJK                                  │
│                                                                             │
│  ┌──────────────┐    ┌────────────────────┐    ┌────────────┐    ┌───────┐  │
│  │   INPUT      │    │    PROSES INTI     │    │  STORAGE   │    │OUTPUT │  │
│  │              │    │                    │    │            │    │       │  │
│  │ Multi-wallet │───▶│ Query on-chain     │───▶│ Supabase   │───▶│Dashbd │  │
│  │ per PAKD     │    │ ETH + BTC + SOL    │    │ snapshots  │    │<1 dtk │  │
│  │ (array)      │    │                    │    │            │    │       │  │
│  │              │    │ Harga: CMC v2      │    │ audit_log  │    │Export │  │
│  │ Laporan      │───▶│ → CoinGecko        │───▶│ .json      │───▶│CSV    │  │
│  │ kewajiban    │    │ → cache stale      │    │            │    │       │  │
│  │ PAKD         │    │ → hardcoded        │    │            │    │Alert  │  │
│  │              │    │                    │    │            │    │berjenjang│
│  │ Wallet proof │───▶│ Stress test        │    │            │    │       │  │
│  │ EIP-191      │    │ Pasal 50 + 91      │    │            │    │       │  │
│  │ Ed25519      │    │                    │    │            │    │       │  │
│  └──────────────┘    └────────────────────┘    └────────────┘    └───────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
         ▲                      ▲                     ▲
         │                      │                     │
  Jaringan Blockchain     Price APIs              cron-job.org
  ETH: Etherscan V2       CMC v2, CoinGecko       (5 menit interval)
  BTC: Blockstream        Demo, Jupiter Price V3
  SOL: Helius RPC
       Jupiter Tokens V2
```

---

## 2. Komponen Input

### 2.1 Data On-Chain

PRIMA mengambil data saldo dompet langsung dari jaringan blockchain melalui API publik. Satu PAKD dapat memiliki banyak alamat dompet per chain (array), bukan satu alamat tunggal. Daftar alamat diperoleh dari deklarasi resmi PAKD kepada OJK dan dikunci setelah terdaftar.

| Jaringan | API | Data yang Diambil | Catatan |
|----------|-----|-------------------|---------|
| Bitcoin | Blockstream Esplora | `/api/address/{address}` — `chain_stats` only | Mempool (unconfirmed) dikecualikan untuk konsistensi. |
| Ethereum | Etherscan V2 | `chainid=1&action=balance` (native) + `action=tokenbalance` × 50 token (ERC-20) | Mandatory param `chainid=1` sejak migrasi V1 ke V2. Sequential 5 req/dtk. |
| Solana (native) | Solana JSON-RPC via Helius | `getBalance` per alamat | SOL dalam lamports, dibagi 10^9. |
| Solana (SPL) | Helius RPC | `getTokenAccountsByOwner` + `jsonParsed` | Semua token account per wallet dalam satu call. |
| Harga SPL | Jupiter Price V3 | `https://lite.jupag.ag/v3/price` | two-gate filter. Lite-api deprecation watch. |
| Token set terverifikasi | Jupiter Tokens V2 | `https://tokens.jup.ag/tokens?tags=verified` | Gate 1 SPL filter: Jupiter verified OR has-price. |

**Cakupan ERC-20:** Curated 50 token dipilih berdasarkan tiga kriteria: (1) termasuk dalam 821 aset ERC-20 yang terdaftar di Bursa Aset Keuangan Digital per 19 Mei 2026 representasi terkini dari aset kripto yang diizinkan beredar di Indonesia di bawah rezim OJK. Angka 821 berasal dari analisis pemetaan jaringan blockchain terhadap 1.266 aset CFX, di mana 65,2% beroperasi di Ethereum atau EVM-compatible L2 (analisis PRIMA, 19 Mei 2026). Di bawah POJK No. 27 Tahun 2024, penetapan Daftar Aset Kripto berpindah dari Bappebti ke Bursa (CFX), sehingga daftar CFX adalah referensi. (2) Termasuk dalam top market cap global per CoinGecko ranking memastikan token yang di-track memiliki likuiditas dan price feed yang reliabel untuk konversi IDR. (3) Relevan untuk profil PAKD Indonesia berdasarkan data perdagangan historis token long-tail dengan volume minim di pasar Indonesia diprioritaskan lebih rendah. Seluruh 50 contract diverifikasi via `scripts/verify_curated_list.py`. Token di luar 50 yang terdeteksi di wallet PAKD dilaporkan sebagai `eth_other_token_idr` dengan label `UNVALUED` di frontend.

**SPL two-gate filter:** Gate 1 menerima token yang masuk Jupiter verified set ATAU memiliki harga di Jupiter Price V3. Gate 2 wajib has-price untuk masuk kalkulasi nilai IDR. Token yang lolos Gate 1 tapi gagal Gate 2 tetap dilaporkan sebagai `sol_other_token_idr` dengan label `UNVALUED`.

### 2.2 Sumber Harga (Price Cascade)

Harga diambil dengan cascade empat tingkat. Tingkat berikutnya hanya digunakan jika tingkat sebelumnya gagal.

| Tingkat | Sumber | Plan | Catatan |
|---------|--------|------|---------|
| Tier 1 | CoinMarketCap v2 | Basic (15K credit/bulan, 50 req/menit) | Primary. `PRICE_TTL=300` detik. `harga_fallback=False` di production. |
| Tier 2 | CoinGecko Demo | Demo (30 call/menit, 30 address/call) | Fallback. Header `x-cg-demo-api-key`. Base URL `api.coingecko.com`. Batch 25 contract per request. |
| Tier 3 | Cache stale | In-memory | Digunakan jika kedua API gagal dan cache belum expired sepenuhnya. |
| Tier 4 | Hardcoded fallback | - | Last resort. Field `harga_fallback=True` dikirim ke frontend sebagai indikator data stale. |

### 2.3 Data Laporan Kewajiban PAKD

Laporan kewajiban diinput oleh petugas OJK yang berwenang via form dashboard atau API endpoint `/api/input-manual` (POST, auth required). Field wajib: `pakd_id`, `nama_pakd`, `aset_dilaporkan` (total kewajiban ke nasabah dalam IDR), `wallets` (array per chain).

Field opsional untuk stress test: `ekuitas`, `persediaan_akd`, `simpanan_pedagang_akd`, `akd_konsumen`.

---

## 3. Proses Inti

### 3.1 Arsitektur Fetch: Hybrid Snapshot + Live

Berdasarkan profiling empiris 20 Mei 2026 (4 PAKD aktif di production Render):

| Segmen | Cold cache | Warm cache |
|--------|-----------|-----------|
| fetch_eth_total | 63.775 detik | 0.010 detik |
| fetch_sol_total | 5.897 detik | 3.645 detik |
| db_write (sequential, sebelum batch) | 5.523 detik | 5.523 detik |
| fetch_btc_total | 0.0 detik | 0.0 detik |
| pricing_eth_fallback | 0.0 detik | 0.0 detik |
| Total | 77.453 detik | 11.128 detik |

Kondisi profiling: 4 PAKD aktif, wallet distribusi ETH-heavy, 0 BTC wallet aktif, commit `99de842`. Run 3 (mixed, jeda ~4 menit) menunjukkan total 10.808 detik — konfirmasi bahwa BALANCE_TTL=300 detik efektif mempertahankan ETH warm cache.

ETH cold cache adalah 82.3% total waktu karena 53 sequential request per wallet ke Etherscan V2 free tier (1 native + 2 stablecoin + 50 curated ERC-20). SOL warm cache 3.3–3.6 detik karena Jupiter `_get_jupiter_verified_set()` masih hit network tiap call (bukan BALANCE_CACHE) — acceptable untuk demo scope. db_write flat 5.5 detik tidak terpengaruh cache status; proyeksi 25 PAKD dengan sequential insert = ~34 detik, wajib di-batch.

Keputusan arsitektur berdasarkan profiling:
- Path A (background snapshot): prioritas utama — solve cold start tanpa perlu Multicall3.
- Batch db_write: wajib sebelum Path A, mengeliminasi proyeksi 34 detik untuk 25 PAKD.
- Path B (Multicall3 untuk refresh manual <30 detik): dijadwalkan Phase 2 post-hackathon.

Solusi yang diimplementasikan: arsitektur hybrid dua lapis.

**Layer 1 — Background snapshot:**
cron-job.org memanggil `POST /api/internal/refresh-all` tiap 5 menit. Endpoint ini menjalankan rekonsiliasi penuh semua PAKD dan menyimpan hasilnya ke Supabase via `_save_snapshots_batch()` (satu koneksi, satu `executemany()` — menggantikan sequential per-PAKD yang proyeksi 25 PAKD menghasilkan 34 detik hanya untuk DB write). Page load frontend memanggil `GET /api/reconciliation/latest` (DISTINCT ON query Supabase, response <1 detik).

**Layer 2 — Manual refresh async:**
Tombol "Rekonsiliasi Manual" memanggil `POST /api/reconciliation/refresh`, mendapat `job_id` instan, dan polling `GET /api/reconciliation/refresh/<job_id>` tiap 2 detik. `REFRESH_LOCK` global mencegah concurrent run. `JOBS` dict in-memory tidak persist antar restart.

### 3.2 Pseudocode Rekonsiliasi

```python
# Layer 1: background cron (dipanggil tiap 5 menit oleh cron-job.org)
FUNGSI internal_refresh_all():
    VALIDASI X-Internal-Token via hmac.compare_digest
    JIKA REFRESH_LOCK aktif: return 409 Conflict
    SET REFRESH_LOCK = True

    semua_pakd = load_pakd()
    hasil_list = []

    UNTUK SETIAP pakd DALAM semua_pakd:
        wallets = pakd.get("wallets", [])
        hasil = get_total_balance_idr(wallets)
        # hasil adalah dict 18 key: total_idr, breakdown per chain, network_breakdown
        
        aset_onchain_idr = hasil["total_idr"]
        aset_dilaporkan   = pakd["aset_dilaporkan"]
        deviasi_pct       = (aset_onchain_idr - aset_dilaporkan) / aset_dilaporkan * 100
        deviasi_pct       = clamp(deviasi_pct, -9999.9999, 9999.9999)  # NUMERIC(8,4) ceiling
        
        JIKA surplus = aset_onchain_idr >= aset_dilaporkan
        JIKA surplus:                          status = "Aman"
        JIKA NOT surplus AND deficit < 0.01:   status = "Aman"   # noise guard
        JIKA NOT surplus AND deficit <= 10:    status = "Deviasi"
        JIKA NOT surplus AND deficit > 10:     status = "Kritis"
        
        hasil_list.append({pakd_id, aset_onchain_idr, aset_dilaporkan, deviasi_pct,
                           status, network_breakdown, captured_at: now()})

    _save_snapshots_batch(hasil_list)  # satu executemany() ke Supabase
    SET REFRESH_LOCK = False

# Layer 2: page load (response <1 detik dari Supabase snapshot)
FUNGSI reconciliation_latest():
    QUERY Supabase:
        SELECT DISTINCT ON (pakd_id) *
        FROM reconciliation_snapshots
        ORDER BY pakd_id, captured_at DESC
    RETURN JSON dengan field as_of (timestamp snapshot terbaru)

# Layer 3: manual refresh async (dipicu tombol di frontend)
FUNGSI reconciliation_refresh():
    job_id = UUID()
    JOBS[job_id] = {status: "pending", created_at: now()}
    SUBMIT _run_refresh_job(job_id) ke ThreadPoolExecutor
    RETURN {job_id, status: "pending"}

FUNGSI reconciliation_refresh_status(job_id):
    RETURN JOBS[job_id]  # status: pending/running/done/failed + result
```

### 3.3 Justifikasi Ambang Batas Deviasi

Sistem menggunakan logika surplus/deficit, bukan deviasi absolut simetris. Surplus (aset on-chain >= dilaporkan) selalu Aman karena tidak menunjukkan kekurangan aset. Threshold hanya berlaku untuk sisi deficit.

| Kondisi | Status | Justifikasi |
|---------|--------|-------------|
| Surplus (on-chain >= dilaporkan) | Aman | Tidak ada kekurangan aset. |
| Deficit < 0.01% | Aman | Noise guard untuk floating point rounding dan timing difference antar API call. Bukan threshold regulasi. |
| Deficit 0.01–10% | Deviasi | Selisih material yang memerlukan penjelasan dari PAKD tetapi belum mengindikasikan kekurangan kritis. |
| Deficit > 10% | Kritis | Selisih signifikan yang tidak dapat dijelaskan oleh perbedaan teknis pelaporan. Mengindikasikan kemungkinan kekurangan aset material. |

Threshold 10% lebih konservatif dari praktik industri Proof-of-Reserves pasca-kolaps FTX. PwC Switzerland (2022) menetapkan batas akurasi operasional normal di bawah 5%, dan threshold Kritis lazimnya di 20%. PRIMA menggunakan threshold yang lebih ketat karena PAKD memegang aset konsumen langsung tanpa capital buffer tebal seperti bank konvensional.

Threshold ini bersifat dapat dikonfigurasi dan dimaksudkan untuk difinalisasi bersama OJK berdasarkan asesmen risiko aktual industri PAKD Indonesia.

**Catatan inkonsistensi:** Background batch refresh (endpoint `/api/internal/refresh-all`) saat ini masih menggunakan threshold lama (5%/20%) di dua lokasi kode. Snapshot Supabase yang dihasilkan dapat memiliki klasifikasi status berbeda dari live endpoint untuk deviasi di rentang 5–10%. Homogenisasi dijadwalkan sebelum code freeze 24 Mei 2026.

### 3.4 Pseudocode Stress Test: Pasal 50 dan Pasal 91

PRIMA menjalankan dua test solvabilitas yang di-anchor ke POJK No. 27 Tahun 2024. Threshold pass: ekuitas pasca-shock >= Rp 50.000.000.000 (Pasal 50 ayat (1) huruf o).

```python
# Test 1: Risiko Pasar (Pasal 50)
# Aset terdampak: proprietary PAKD saja (Persediaan AKD + Simpanan Pedagang)
# Aset Konsumen tidak termasuk — per regulasi, PAKD kembalikan unit kripto bukan nilai rupiah
SKENARIO_PASAL_50 = [
    {"label": "Mild",     "shock": -0.25},  # koreksi pasar normal
    {"label": "Moderate", "shock": -0.50},  # bear market tahunan (BTC 2022: -64%)
    {"label": "Severe",   "shock": -0.80},  # peak-to-trough historis (BTC 2017-2018)
]

UNTUK SETIAP skenario DALAM SKENARIO_PASAL_50:
    UNTUK SETIAP pakd:
        dampak_idr  = (persediaan_akd_idr + simpanan_pedagang_akd_idr) * ABS(skenario["shock"])
        equity_post = ekuitas_idr - dampak_idr
        pass_flag   = (equity_post >= 50_000_000_000)

# Test 2: Risiko Siber dan Operasional (Pasal 91)
# Kewajiban: kehilangan AKD Konsumen menjadi tanggungan PAKD (Pasal 91 ayat (1))
# Hanya mencakup AKD Konsumen di wallet PAKD yang dilaporkan (bukan porsi di PTP)
SKENARIO_PASAL_91 = [
    {"label": "Mild",     "shock": 0.23},   # benchmark GDAC April 2023 (CoinDesk, 10 Apr 2023)
    {"label": "Moderate", "shock": 0.45},   # benchmark WazirX Juli 2024 (Decrypt, Jan 2025)
    {"label": "Severe",   "shock": 1.00},   # benchmark Mt Gox Feb 2014
]

UNTUK SETIAP skenario DALAM SKENARIO_PASAL_91:
    UNTUK SETIAP pakd:
        liability_idr = customer_akd_idr * skenario["shock"]
        equity_post   = ekuitas_idr - liability_idr
        pass_flag     = (equity_post >= 50_000_000_000)
```

---

## 4. Verifikasi Kepemilikan Dompet

### 4.1 Flow Verifikasi

PRIMA mengimplementasikan cryptographic proof-of-ownership untuk Ethereum dan Solana. Bitcoin (BIP-322) dijadwalkan Phase 2.

```
PAKD                            PRIMA Backend
  │                                   │
  │──── POST /api/wallet-proof/challenge ──▶│
  │     {wallet_address, chain}        │
  │                                   │ generate challenge string
  │                                   │ simpan ke CHALLENGE_STORE
  │◀─── {challenge, expires_in} ──────│
  │                                   │
  │ (sign challenge dengan private key)│
  │                                   │
  │──── POST /api/wallet-proof/verify ─▶│
  │     {wallet_address, chain,        │
  │      signature}                    │
  │                                   │ verifikasi signature
  │◀─── {verified: true/false} ────────│
```

### 4.2 Implementasi per Chain

| Chain | Standard | Library | Catatan |
|-------|----------|---------|---------|
| Ethereum | EIP-191 personal_sign | eth-account | `encode_defunct` + `recover_message`. Address recovery dan comparison (case-insensitive). |
| Solana | Ed25519 | PyNaCl, base58 | Decode public key dari base58, decode signature dari base58, verify via `nacl.signing.VerifyKey`. |
| Bitcoin | BIP-322 | Belum diimplementasikan | Roadmap Phase 2. |

### 4.3 Mode Operasi

**Primary mode (production):** PAKD generate signature menggunakan signing tool di environment masing-masing, submit signature blob ke OJK via channel resmi. Supervisor OJK input signature ke dashboard untuk diverifikasi backend. Mode ini sesuai dengan production reality: OJK dan PAKD adalah entitas terpisah di perangkat berbeda.

**Convenience mode (sandbox/workshop):** MetaMask integration in-browser via `personal_sign`. Berguna untuk OJK internal testing dan onboarding session PAKD di laptop netral. Mode ini mengasumsikan operator dashboard adalah pemilik wallet — asumsi yang tidak valid di production.

---

## 5. Keamanan dan Autentikasi

### 5.1 Lapisan Autentikasi yang Sudah Diimplementasikan

| Komponen | Implementasi | Referensi |
|----------|-------------|-----------|
| Admin token pada endpoint write | Header `X-Admin-Token`, dibandingkan via `hmac.compare_digest` (constant-time) | OWASP ASVS V2.10.3 |
| Token guard | Jika `ADMIN_TOKEN` env var tidak di-set, endpoint return 401 langsung. Tidak ada fallback ke empty string. | — |
| Internal token untuk cron | Header `X-Internal-Token`, sama mekanisme hmac.compare_digest. Digenerate via `openssl rand -hex 32`. | — |
| Rate limiting rekonsiliasi | 60 detik cooldown via `_last_rekon_time` global state. Bypass aktif saat `TESTING=True`. | — |
| Row Level Security Supabase | RLS diaktifkan di tiga tabel: `public.pakd`, `public.wallets`, `public.reconciliation_snapshots`. Policy `service_only` membatasi ke `service_role`. | — |
| SQL injection | Seluruh query parameterized via psycopg2. Zero f-string atau `.format()` interpolation. Diverifikasi via grep audit. | — |

### 5.2 Keterbatasan Keamanan yang Masih Terbuka

Lihat `docs/keterbatasan-sistem.md` Section 6 untuk tabel lengkap dengan status per temuan. Yang masih terbuka: wildcard CORS, tidak ada authentication untuk pengguna dashboard (read endpoints terbuka), CHALLENGE_STORE tidak dibatasi, PRICE_CACHE non-thread-safe.

---

## 6. Komponen Output

### 6.1 Dashboard Monitoring

Dashboard berbasis web, load dari snapshot Supabase (<1 detik response). Halaman-halaman yang tersedia:

- **Overview PAKD:** Tabel seluruh PAKD dengan status, deviasi, chain coverage, dan timestamp rekonsiliasi terakhir. Filter chip per status. Tombol "Rekonsiliasi Manual" dengan async job polling.
- **Detail Per-PAKD:** Breakdown per aset kripto (saldo on-chain vs dilaporkan per token), profil PAKD, daftar wallet per chain dengan badge verified/unverified, donut chart distribusi aset.
- **Stress Test:** Pasal 50 (market risk) dan Pasal 91 (cyber risk), tiga skenario masing-masing, pass/fail per PAKD per skenario, metodologi lengkap per skenario.
- **Audit Log:** 50 entri terakhir aktivitas sistem.
- **Pengaturan:** Manajemen data PAKD (tambah, edit, hapus) dengan admin token gate.

Export: `GET /api/export-csv` (riwayat per-PAKD, max 200 baris) dan `GET /api/export-csv-overview` (snapshot terbaru per PAKD via DISTINCT ON).

### 6.2 Audit Trail

Setiap operasi rekonsiliasi menghasilkan entri di `audit_log.json` (append-only, plain JSON) dan snapshot di tabel Supabase `reconciliation_snapshots`. Catatan: audit_log.json tidak memiliki hash chain atau tamper-evident structure pada versi MVP. Lihat `docs/keterbatasan-sistem.md` Section 6 untuk rencana mitigasi.

---

## 7. Jadwal Operasi

| Operasi | Frekuensi | Pemicu |
|---------|-----------|--------|
| Background snapshot | Setiap 5 menit | cron-job.org → `POST /api/internal/refresh-all` |
| Warm-up instance | Setiap 5 menit | Sekaligus dengan background snapshot |
| Manual refresh | Ad-hoc | Supervisor OJK klik tombol di dashboard → async job polling |
| Stress test | Ad-hoc | Supervisor OJK request `GET /api/stress-test` |
| Rekonsiliasi live (legacy) | Ad-hoc | `GET /api/reconciliation` — rate limit 60 detik |

---

## 8. Keterbatasan Arsitektur (Ringkasan)

Deskripsi lengkap beserta rencana mitigasi ada di `docs/keterbatasan-sistem.md`.

| Keterbatasan | Dampak | Tingkat Risiko | Status v1.9 |
|-------------|--------|----------------|-------------|
| Circular trust (dompet dideklarasikan sendiri) | Dompet tidak terdaftar tidak terdeteksi | Tinggi | Wallet proof parsial mitigasi (ETH + SOL terverifikasi kriptografis) |
| Snapshot tunggal per periode | Rentan window dressing | Menengah | Terbuka — roadmap v2.0 multi-titik acak |
| ERC-20 curated 50 token | Token long-tail UNVALUED | Menengah | Terbuka — full enum Phase 2 setelah API berbayar |
| SPL Token-2022 tidak dienumerasi | Token extension program tidak tercakup | Rendah | Terbuka |
| BTC tanpa proof-of-ownership | Kepemilikan BTC hanya berdasarkan deklarasi | Menengah | Terbuka — BIP-322 Phase 2 |
| Fetch cold start ETH 64 detik | UX terganggu jika live fetch tanpa cache | Menengah | Dimitigasi via snapshot architecture |
| Tidak ada RBAC dan user auth | Read endpoint terbuka, tidak ada role separation | Tinggi (produksi) | Terbuka — admin token hanya untuk write |

---

## Referensi Teknis

- Etherscan V2 API: https://docs.etherscan.io/etherscan-v2
- Blockstream Esplora API: https://github.com/Blockstream/esplora/blob/master/API.md
- Helius RPC Documentation: https://docs.helius.dev
- Jupiter Tokens V2: https://tokens.jup.ag/tokens?tags=verified
- Jupiter Price V3: https://lite.jupag.ag/v3/price
- Solana JSON-RPC: https://solana.com/docs/rpc
- CoinMarketCap API v2: https://coinmarketcap.com/api/documentation/v2
- CoinGecko Demo API: https://docs.coingecko.com/reference/introduction
- PwC Switzerland. (2022). *Proof of Reserves: Bridging the Trust Gap in Crypto Exchanges*.
- Chainalysis. (2024). *The Chainalysis 2024 Crypto Crime Report*.
- OWASP ASVS V4.0.3 — V2.10.3 Service Authentication.
- POJK No. 23 Tahun 2025, Pasal 50 ayat (1) huruf o, Pasal 91 ayat (1).
- PT Central Finansial X (CFX). Daftar Aset Kripto Terdaftar, 19 Mei 2026. Total 1.266 aset; analisis jaringan PRIMA: 821 ERC-20/Ethereum (65,2%), 93 Solana (7,4%), 28 Bitcoin (2,2%). https://www.cfx.co.id/

