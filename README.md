# PRIMA
### Pemantauan Transparansi Aset Pedagang Aset Keuangan Digital Berbasis Blockchain

![Status](https://img.shields.io/badge/Status-v1.9--pasal50--pasal91-0A7A4A?style=flat-square)
![Hackathon](https://img.shields.io/badge/DIGDAYA%20X%20Hackathon-2026-1B3A6B?style=flat-square)
![Regulator](https://img.shields.io/badge/Regulator-OJK-003087?style=flat-square)
![Chain](https://img.shields.io/badge/Chain-ETH%20%7C%20BTC%20%7C%20SOL-627EEA?style=flat-square)
![Backend](https://img.shields.io/badge/Backend-Flask%203.x-000000?style=flat-square)

> Prototype MVP · Dibangun untuk DIGDAYA X Hackathon 2026 · Pusat Inovasi Digital Indonesia

**[→ Lihat Landing Page](https://prima-ojk.onrender.com/)** · **[→ Repositori](https://github.com/mihsan02/prima-ojk)**

> Dashboard monitoring memerlukan Flask backend. Lihat bagian [Cara Menjalankan](#cara-menjalankan) untuk instruksi lengkap.

---

## Apa itu PRIMA?

PRIMA adalah sistem pemantauan berbasis blockchain yang dirancang untuk membantu OJK mengawasi kecukupan aset Pedagang Aset Keuangan Digital (PAKD) secara otomatis.

Sistem ini melakukan rekonsiliasi antara saldo dompet on-chain yang diquery langsung dari tiga jaringan blockchain (Ethereum, Bitcoin, Solana) dengan kewajiban yang dilaporkan PAKD kepada regulator. Harga aset diambil secara live dengan cascade empat tingkat (CoinMarketCap v2 → CoinGecko Demo → cache stale → hardcoded fallback) untuk konversi ke IDR. Setiap selisih di atas ambang batas memicu klasifikasi alert berjenjang secara otomatis.

PRIMA diposisikan sebagai baseline pengawasan minimum yang wajib, bukan pengganti audit. Sistem ini mengisi celah yang tidak bisa diisi oleh laporan periodik: keterlambatan deteksi, ketergantungan pada laporan yang tidak terverifikasi, dan absennya stress test solvabilitas terstandar.

---

## Masalah yang Diselesaikan

Per Januari 2025, OJK mengambil alih pengawasan aset keuangan digital dari Bappebti berdasarkan UU Nomor 4 Tahun 2023 (UU P2SK). Seluruh 25 PAKD berizin, yang mengelola nilai transaksi industri sebesar Rp 556,53 triliun sepanjang 2024 (OJK, 2024), masih diawasi melalui laporan berkala yang diserahkan sendiri oleh pelaku usaha.

Tiga kelemahan struktural dari pendekatan pelaporan berbasis dokumen:

**1. Keterlambatan deteksi.**
Laporan bulanan tidak menangkap pergerakan aset harian. Kasus Zipmex pada Juli 2022 membekukan aset pengguna Indonesia senilai sekitar $53 juta (Bisnis Indonesia, 2022) tanpa sinyal peringatan yang terdeteksi regulator sebelumnya. Sistem berbasis laporan tidak dirancang untuk mendeteksi tekanan likuiditas yang berkembang dalam hitungan hari.

**2. Tidak ada verifikasi independen.**
Regulator tidak memiliki mekanisme untuk memvalidasi klaim aset secara mandiri. Seluruh proses verifikasi bergantung pada kejujuran pelaporan PAKD, struktur yang oleh FSB (2023) dikategorikan sebagai *insufficient supervisory oversight*.

**3. Tidak ada stress test solvabilitas terstandar.**
Ketika Bitcoin turun 64% sepanjang 2022 (Chainalysis, 2024), tidak ada mekanisme yang memungkinkan OJK mengetahui berapa PAKD yang berisiko gagal bayar kewajiban nasabah sebelum krisis terjadi.

Referensi regulasi: POJK No. 27 Tahun 2024, POJK No. 23 Tahun 2025, OJK Peta Jalan IAKD 2024–2028, FSB (2023), IMF (2023).

---

## Mengapa Bukan Solusi yang Sudah Ada?

Platform analitik blockchain komersial seperti Chainalysis dan Nansen menyediakan kemampuan on-chain monitoring yang canggih. PRIMA tidak bersaing dengan kecanggihan teknis mereka. PRIMA menyelesaikan masalah yang berbeda:

- **Tidak ada integrasi regulasi lokal.** Platform komersial tidak memiliki pemetaan ke daftar PAKD berizin OJK, threshold deviasi berdasarkan POJK, atau struktur alert yang sesuai dengan hierarki pengawasan OJK.
- **Kedaulatan data.** Data pengawasan PAKD adalah data sensitif regulasi. Mengandalkan platform asing berarti posisi aset seluruh industri kripto Indonesia berada di luar yurisdiksi regulator.
- **Biaya.** Lisensi enterprise Chainalysis berkisar ratusan ribu dolar per tahun, tidak realistis sebagai alat pengawasan rutin regulator.

PRIMA dirancang untuk dioperasikan OJK secara in-house, dengan data yang tetap berada dalam infrastruktur regulator.

---

## Cara Kerja Sistem

```
INPUT                              PROSES                           OUTPUT
─────────────────────────────      ──────────────────────────────   ──────────────────────────
Daftar alamat dompet per chain     Background cron tiap 5 menit    Snapshot Supabase terakhir
(ETH, BTC, SOL) per PAKD    →     query semua chain, simpan ke → dirender <1 detik saat
                                   reconciliation_snapshots          halaman dibuka

Laporan kewajiban PAKD      →      Harga aset live:               → Konversi nilai aset ke IDR
(input manual via form)             CMC v2 (Tier 1)                  pada saat rekonsiliasi
                                    CoinGecko Demo (Tier 2)
                                    Cache stale (Tier 3)
                                    Hardcoded fallback (Tier 4)

Ambang batas deviasi        →      Rekonsiliasi otomatis          → Klasifikasi per PAKD:
  Surplus / defisit <= 5%:          (Python · pandas)                Aman / Deviasi / Kritis
  Aman
  Deviasi 5–20%: Deviasi                    ↓
  Defisit > 20%: Kritis           Stress test solvabilitas        → Laporan ketahanan per skenario:
                                  Pasal 50 (Mild -30%)              Mild / Moderate / Severe
                                  Pasal 91 (Moderate -55%,
                                  Severe -80%): lulus jika aset
                                  post-stress >= 80% dilaporkan

Dompet per PAKD             →      Wallet proof EIP-191 (ETH)     → Badge verified / unverified
                                   Ed25519 (SOL)                    per dompet di tabel PAKD
                                   via MetaMask / phantom

Setiap aksi sistem          →      Pencatatan ke Supabase         → Riwayat rekonsiliasi,
                                   + audit_log.json                 export CSV, donut chart
```

---

## Tech Stack

| Kluster | Teknologi | Justifikasi |
|---------|-----------|-------------|
| Backend | Python 3.11, Flask 3.x, Flask-CORS | Flask ringan untuk API prototype; Flask-CORS menangani request dari frontend |
| Data Eksternal | Etherscan API v2, Blockstream Esplora, CoinMarketCap API v2, CoinGecko Demo API, Helius RPC, Jupiter Tokens V2, Jupiter Price V3, Solana JSON-RPC | Etherscan: saldo ETH native + curated top-50 ERC-20. Blockstream: saldo BTC (UTXO). CMC: harga tier-1 dengan cascade fallback ke CoinGecko. Helius: SPL token enumeration via getTokenAccountsByOwner. Jupiter: two-gate filter token terverifikasi + harga SPL. |
| Crypto Libraries | eth-account, PyNaCl, base58 | EIP-191 personal_sign verification (ETH) dan Ed25519 signature verification (SOL). Wallet ownership proof tanpa custodial dependency. |
| Pemrosesan | Python requests, pandas, NumPy, hmac, secrets | Rekonsiliasi tabular, kalkulasi deviasi, constant-time token comparison (OWASP ASVS V2.10) |
| Penyimpanan | Supabase (psycopg2), JSON (pakd_data.json, audit_log.json) | Supabase: snapshot rekonsiliasi persisten, riwayat per-PAKD, query DISTINCT ON untuk latest snapshot. JSON: audit log lokal dan PAKD state. |
| Antarmuka | HTML, CSS, JavaScript (vanilla) | Dashboard read-only tanpa framework berat; dapat dihosting dalam infrastruktur OJK tanpa dependensi eksternal |
| Infrastruktur | Render (Flask deployment), cron-job.org (background refresh) | Cron-job.org trigger POST /api/internal/refresh-all tiap 5 menit. Render single worker memastikan in-memory state konsisten. |

---

## API Endpoints

| Endpoint | Method | Auth | Fungsi |
|----------|--------|------|--------|
| `/` | GET | - | Serve dashboard HTML |
| `/api/status` | GET | - | Health check |
| `/api/reconciliation` | GET | - | Rekonsiliasi live: query semua chain + CMC/CoinGecko, hitung deviasi per PAKD. Rate limit: 60 detik. |
| `/api/reconciliation/latest` | GET | - | Baca snapshot terakhir dari Supabase. Response <1 detik. |
| `/api/reconciliation/refresh` | POST | - | Trigger background job rekonsiliasi. Return job_id instan. |
| `/api/reconciliation/refresh/<job_id>` | GET | - | Poll status job. Return done/running/failed + result. |
| `/api/reconciliation-history` | GET | - | Riwayat snapshot per PAKD dengan filter pakd_id dan limit. |
| `/api/internal/refresh-all` | POST | X-Internal-Token | Cron-triggered: rekonsiliasi semua PAKD, simpan batch ke Supabase. REFRESH_LOCK mencegah concurrent run. |
| `/api/stress-test` | GET | - | Stress test Pasal 50 (Mild) + Pasal 91 (Moderate/Severe). Catat ke audit log. |
| `/api/pakd` | GET | - | Ambil semua PAKD |
| `/api/pakd` | POST | X-Admin-Token | Tambah PAKD baru |
| `/api/pakd/<pakd_id>` | PUT | X-Admin-Token | Perbarui data PAKD |
| `/api/pakd/<pakd_id>` | DELETE | X-Admin-Token | Hapus PAKD |
| `/api/input-manual` | POST | X-Admin-Token | Tambah atau perbarui data PAKD (legacy endpoint, tetap aktif) |
| `/api/audit-log` | GET | - | Kembalikan 50 entri terakhir audit log |
| `/api/export-csv` | GET | - | Export riwayat rekonsiliasi per PAKD (max 200 baris) |
| `/api/export-csv-overview` | GET | - | Export snapshot terbaru per PAKD via DISTINCT ON |
| `/api/wallet-proof/challenge` | POST | - | Generate challenge string untuk verifikasi kepemilikan dompet |
| `/api/wallet-proof/verify` | POST | - | Verifikasi signature EIP-191 (ETH) atau Ed25519 (SOL) |

---

## Cara Menjalankan

```bash
# 1. Clone repo
git clone https://github.com/mihsan02/prima-ojk.git
cd prima-ojk

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables
export ETHERSCAN_API_KEY="..."       # Etherscan V2 (gratis di etherscan.io)
export CMC_API_KEY="..."             # CoinMarketCap (gratis plan Basic)
export COINGECKO_API_KEY="..."       # CoinGecko Demo (gratis)
export HELIUS_API_KEY="..."          # Helius RPC untuk Solana SPL
export DATABASE_URL="..."            # Supabase connection string (opsional — fallback ke JSON)
export ADMIN_TOKEN="..."             # Token untuk endpoint write PAKD
export INTERNAL_TOKEN="..."          # Token untuk cron internal refresh

# 4. Jalankan Flask
python prima-backend/app.py

# 5. Buka browser
# http://localhost:5000
```

Database Supabase opsional untuk pengembangan lokal. Tanpa `DATABASE_URL`, sistem menggunakan `pakd_data.json` sebagai storage. Snapshot dan riwayat rekonsiliasi hanya tersedia bila Supabase dikonfigurasi.

---

## Struktur Repositori

```
prima-ojk/
├── README.md
├── index.html                      # Landing page statis (GitHub Pages)
├── requirements.txt
├── prima-backend/
│   ├── app.py                      # Flask server — semua route API
│   ├── pakd_data.json              # Data PAKD (auto-generated saat pertama jalan)
│   └── audit_log.json              # Riwayat aktivitas (auto-generated)
├── prima-frontend/
│   └── index.html                  # Dashboard utama (Overview, Detail Per-PAKD, Stress Test, Audit Log, Pengaturan)
├── scripts/
│   └── verify_curated_list.py      # Verifikasi Etherscan V2 tokenbalance + CoinGecko price untuk curated top-50 ERC-20
└── docs/
    ├── arsitektur-sistem.md        # Desain arsitektur dan pseudocode lengkap
    └── keterbatasan-sistem.md      # Batasan MVP yang didokumentasikan per seksi
```

---

## Status Pengembangan

| Komponen | Status |
|----------|--------|
| Flask backend + semua route API | Selesai |
| Dashboard monitoring — multi-chain live fetch | Selesai |
| ETH native balance via Etherscan V2 | Selesai |
| ERC-20 curated top-50 via Etherscan V2 + CoinGecko batch | Selesai |
| BTC balance via Blockstream Esplora | Selesai |
| SOL native + SPL token via Helius RPC + Jupiter two-gate filter | Selesai |
| Harga multi-aset: CMC v2 → CoinGecko → cache → hardcoded | Selesai |
| Logika deviasi surplus/defisit yang benar | Selesai |
| Stress test Pasal 50 + Pasal 91 (3 skenario) | Selesai |
| Multi-wallet per PAKD (wallets array) | Selesai |
| Wallet ownership proof EIP-191 (ETH) via MetaMask | Selesai |
| Wallet ownership proof Ed25519 (SOL) via PyNaCl | Selesai |
| Supabase: reconciliation_snapshots table | Selesai |
| Background refresh via /api/internal/refresh-all | Selesai |
| Page load dari snapshot Supabase (<1 detik) | Selesai |
| Async manual refresh dengan job polling | Selesai |
| Riwayat rekonsiliasi per-PAKD dengan donut chart | Selesai |
| Export CSV per-PAKD dan overview (DISTINCT ON) | Selesai |
| Admin token auth pada endpoint write (hmac.compare_digest) | Selesai |
| Rate limiting rekonsiliasi (60 detik cooldown) | Selesai |
| RLS di seluruh tabel Supabase | Selesai |
| Manual input form (tambah PAKD baru) | Selesai |
| Audit log (tulis + tampil) | Selesai |
| Navigasi multi-halaman dashboard | Selesai |
| Landing page statis untuk GitHub Pages | Selesai |
| Error handling dan timeout handling | Selesai |
| Format IDR full nominal (tanpa pembulatan M/T) | Selesai |
| RBAC dan autentikasi pengguna | Belum — roadmap pasca-MVP |
| Multi-point reconciliation (anti-window-dressing) | Belum — roadmap pasca-MVP |

---

## Keterbatasan yang Didokumentasikan

PRIMA dibangun dengan prinsip kejujuran teknis. Setiap keterbatasan disertai rencana mitigasi.

**Circular trust.**
Verifikasi dompet bergantung pada daftar alamat yang dideklarasikan PAKD ke OJK. Dompet yang tidak dideklarasikan tidak terdeteksi. Wallet proof (EIP-191 dan Ed25519) memverifikasi kepemilikan dompet yang sudah dideklarasikan, bukan completeness daftar. Mitigasi roadmap: verifikasi on-site oleh OJK saat onboarding, wallet address dikunci setelah terdaftar.

**Window dressing.**
Rekonsiliasi berbasis snapshot memungkinkan pemindahan aset sementara menjelang tanggal pemeriksaan. Mitigasi roadmap: rekonsiliasi multi-titik pada tanggal acak dalam satu periode.

**Cakupan ERC-20 dibatasi curated 50 token.**
Etherscan full enumeration via tokentx memiliki lima cacat teknikal yang didokumentasikan (Section 9 keterbatasan-sistem.md): hasil tidak deterministik untuk transfer besar, data inkonsisten untuk token dengan custom transfer logic, tidak menangkap mint/burn, potensi duplikasi record, dan ketergantungan pada indexer Etherscan bukan on-chain state langsung. Pendekatan curated 50 token di-verifikasi via scripts/verify_curated_list.py.

**SPL Token-2022 tidak dienumerasi.**
Helius getTokenAccountsByOwner hanya mengembalikan token program standar. Token yang menggunakan Token-2022 program (extensions) tidak ter-cover.

**Tidak ada RBAC.**
Dashboard memiliki admin token untuk endpoint write, tetapi tidak ada sistem login berbasis role untuk pengawas OJK. Untuk implementasi produksi dengan data regulasi nyata, RBAC dan autentikasi pengguna harus ditambahkan.

---

## Referensi

1. OJK. (2024). *POJK Nomor 27 Tahun 2024 tentang Perdagangan Aset Keuangan Digital*.
2. OJK. (2025). *POJK Nomor 23 Tahun 2025 tentang Penyelenggaraan Perdagangan Aset Keuangan Digital*.
3. OJK. (2024). *Peta Jalan Inovasi Aset Keuangan Digital (IAKD) 2024–2028*.
4. Financial Stability Board. (2023). *Regulation, Supervision and Oversight of Crypto-Asset Activities*.
5. International Monetary Fund. (2023). *Elements of Effective Policies for Crypto Assets*. IMF Policy Paper.
6. Chainalysis. (2024). *The Chainalysis 2024 Crypto Crime Report*.
7. IOSCO. (2023). *Policy Recommendations for Crypto and Digital Asset Markets*.
8. PwC Switzerland. (2022). *Proof of Reserves: Bridging the Trust Gap in Crypto Exchanges*.
9. Bisnis Indonesia. (2022, Juli). *Zipmex Bekukan Penarikan Dana Pengguna*. Bisnis.com.
10. OWASP. (2023). *Application Security Verification Standard (ASVS) v4.0.3 — V2.10 Service Authentication*.

---

*PRIMA v1.9-pasal50-pasal91 · Dibangun untuk DIGDAYA X Hackathon 2026 · Pusat Inovasi Digital Indonesia*
