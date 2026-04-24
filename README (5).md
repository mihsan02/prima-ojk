# PRIMA
### Pemantauan Transparansi Aset Pedagang Aset Keuangan Digital Berbasis Blockchain

![Status](https://img.shields.io/badge/Status-MVP%20Minggu%201%20Selesai-0A7A4A?style=flat-square)
![Hackathon](https://img.shields.io/badge/DIGDAYA%20X%20Hackathon-2026-1B3A6B?style=flat-square)
![Regulator](https://img.shields.io/badge/Regulator-OJK-003087?style=flat-square)
![Chain](https://img.shields.io/badge/Chain-ETH-627EEA?style=flat-square)
![Backend](https://img.shields.io/badge/Backend-Flask%203.x-000000?style=flat-square)

> Prototype MVP · Dibangun untuk DIGDAYA X Hackathon 2026 · Pusat Inovasi Digital Indonesia

**[→ Lihat Landing Page](https://mihsan02.github.io/prima-ojk)** · **[→ Repositori](https://github.com/mihsan02/prima-ojk)**

> Dashboard monitoring memerlukan Flask backend. Lihat bagian [Cara Menjalankan](#cara-menjalankan) untuk instruksi lengkap.

---

## Apa itu PRIMA?

PRIMA adalah sistem pemantauan berbasis blockchain yang dirancang untuk membantu OJK mengawasi kecukupan aset Pedagang Aset Keuangan Digital (PAKD) secara otomatis.

Sistem ini melakukan rekonsiliasi antara saldo dompet on-chain yang diquery langsung dari jaringan Ethereum via Etherscan API dengan kewajiban yang dilaporkan PAKD kepada regulator. Harga ETH diambil live dari CoinGecko API untuk konversi ke IDR. Setiap selisih di atas ambang batas memicu klasifikasi alert berjenjang secara otomatis.

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

Referensi regulasi: POJK No. 27 Tahun 2024, POJK No. 27 Tahun 2021, OJK Peta Jalan IAKD 2024–2028, FSB (2023), IMF (2023).

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
Daftar alamat dompet ETH    →      Query Etherscan API            → Saldo ETH on-chain live
PAKD (terdaftar di sistem)         (GET /api/reconciliation)        per PAKD, dikonversi ke IDR

Laporan kewajiban PAKD      →      Harga ETH/IDR live             → Konversi nilai aset ke IDR
(input manual via form)            dari CoinGecko API               pada saat rekonsiliasi

Ambang batas deviasi        →      Rekonsiliasi otomatis          → Klasifikasi per PAKD:
  Surplus / defisit < 5%:          (Python · pandas)                Aman / Deviasi / Kritis
  Aman
  Defisit 5–15%: Deviasi                   ↓
  Defisit > 15%: Kritis           Stress test solvabilitas        → Laporan ketahanan per skenario:
                                  tiga skenario:                    Mild (-30%) · Moderate (-55%)
                                  lulus jika aset post-stress        · Severe (-80%)
                                  ≥ 80% aset dilaporkan

Setiap aksi sistem          →      Pencatatan ke audit log        → Riwayat aktivitas dengan
                                   (audit_log.json)                 timestamp per entri
```

---

## Tech Stack

| Kluster | Teknologi | Justifikasi |
|---------|-----------|-------------|
| Backend | Python 3.11, Flask 3.x, Flask-CORS | Flask ringan untuk API prototype; Flask-CORS menangani request dari frontend di port yang sama |
| Data Eksternal | Etherscan API v2, CoinGecko Public API | Etherscan: data ETH on-chain langsung dari node tanpa intermediari. CoinGecko: harga ETH/IDR live tanpa API key. Keduanya diverifikasi berfungsi untuk 25 PAKD dalam rate limit gratis |
| Pemrosesan | Python requests, pandas, NumPy | Cukup untuk rekonsiliasi tabular dan kalkulasi deviasi di MVP |
| Penyimpanan | JSON (pakd_data.json, audit_log.json) | Persistent storage tanpa dependensi database untuk tahap MVP; dapat diganti PostgreSQL di produksi |
| Antarmuka | HTML, CSS, JavaScript (vanilla) | Dashboard read-only tanpa framework berat; dapat dihosting dalam infrastruktur OJK tanpa dependensi eksternal |

---

## API Endpoints

| Endpoint | Method | Fungsi |
|----------|--------|--------|
| `/` | GET | Serve dashboard HTML |
| `/api/status` | GET | Health check |
| `/api/reconciliation` | GET | Rekonsiliasi live: query Etherscan + CoinGecko, hitung deviasi per PAKD |
| `/api/stress-test` | GET | Stress test tiga skenario, catat ke audit log |
| `/api/input-manual` | POST | Tambah atau perbarui data PAKD, validasi duplikat ID |
| `/api/audit-log` | GET | Kembalikan 50 entri terakhir audit log |

---

## Cara Menjalankan

```bash
# 1. Clone repo
git clone https://github.com/mihsan02/prima-ojk.git
cd prima-ojk

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set Etherscan API key (gratis di etherscan.io)
export ETHERSCAN_API_KEY="api_key_kamu"

# 4. Jalankan Flask
python prima-backend/app.py

# 5. Buka browser
# http://localhost:5000
```

CoinGecko API tidak memerlukan API key. Dashboard akan langsung menampilkan data ETH live setelah Flask berjalan.

---

## Struktur Repositori

```
prima-ojk/
├── README.md
├── index.html                      # Landing page statis (GitHub Pages)
├── requirements.txt                # flask, flask-cors, requests
├── prima-backend/
│   ├── app.py                      # Flask server — semua route API
│   ├── pakd_data.json              # Data PAKD (auto-generated saat pertama jalan)
│   └── audit_log.json              # Riwayat aktivitas (auto-generated)
├── prima-frontend/
│   └── index.html                  # Dashboard utama (4 halaman: Overview, Stress Test, Audit Log, Pengaturan)
└── docs/
    ├── arsitektur-sistem.md        # Desain arsitektur dan pseudocode lengkap
    └── keterbatasan-sistem.md      # Batasan MVP yang didokumentasikan
```

---

## Status Pengembangan

| Komponen | Status |
|----------|--------|
| Flask backend + semua route API | Selesai |
| Dashboard monitoring — live fetch dari Etherscan | Selesai |
| Harga ETH/IDR live dari CoinGecko | Selesai |
| Logika deviasi surplus/defisit yang benar | Selesai |
| Manual input form (tambah PAKD baru) | Selesai |
| Audit log (tulis + tampil) | Selesai |
| Stress test endpoint + panel (3 skenario) | Selesai |
| Navigasi multi-halaman (Stress Test, Audit Log, Pengaturan) | Selesai |
| Landing page statis untuk GitHub Pages | Selesai |
| Error handling dan timeout handling | Dalam pengerjaan |
| Integrasi BTC dan SOL | Belum — roadmap pasca-MVP |

---

## Keterbatasan yang Didokumentasikan

PRIMA dibangun dengan prinsip kejujuran teknis. Setiap keterbatasan disertai rencana mitigasi.

**Circular trust.**
Verifikasi dompet bergantung pada daftar alamat yang dideklarasikan PAKD ke OJK. Dompet yang tidak dideklarasikan tidak terdeteksi. Mitigasi roadmap: verifikasi on-site oleh OJK saat onboarding, wallet address dikunci setelah terdaftar dan tidak bisa diubah PAKD tanpa persetujuan regulator.

**Window dressing.**
Pemindahan aset sementara menjelang tanggal snapshot tidak tertangkap sistem satu titik. Mitigasi roadmap: rekonsiliasi multi-titik pada tanggal acak dalam satu periode untuk mengurangi prediktabilitas jadwal pemeriksaan.

**Cakupan aset MVP.**
Versi ini hanya mencakup Ethereum. Bitcoin dan Solana belum diintegrasikan meski arsitekturnya sudah dirancang dan endpoint Solana RPC sudah diverifikasi. Mitigasi roadmap: perluasan bertahap setelah pola integrasi API divalidasi.

**Konversi IDR hanya ETH.**
Aset kripto selain ETH belum memiliki konversi harga live. Mitigasi roadmap: tambah endpoint CoinGecko untuk BTC dan SOL bersamaan dengan perluasan integrasi chain.

**Tidak ada autentikasi.**
Dashboard tidak memiliki mekanisme login. Untuk konteks hackathon dengan data demonstrasi, ini aman. Untuk implementasi produksi dengan data regulasi nyata, RBAC dan autentikasi harus ditambahkan.

---

## Referensi

1. OJK. (2024). *POJK Nomor 27 Tahun 2024 tentang Perdagangan Aset Keuangan Digital*.
2. OJK. (2024). *Peta Jalan Inovasi Aset Keuangan Digital (IAKD) 2024–2028*.
3. OJK. (2024). *Statistik Pasar Modal — Nilai Transaksi Aset Kripto 2024*.
4. OJK. (2021). *POJK Nomor 27 Tahun 2021 tentang Penyelenggaraan Kegiatan di Bidang Pasar Modal*.
5. Financial Stability Board. (2023). *Regulation, Supervision and Oversight of Crypto-Asset Activities*.
6. International Monetary Fund. (2023). *Elements of Effective Policies for Crypto Assets*. IMF Policy Paper.
7. Chainalysis. (2024). *The Chainalysis 2024 Crypto Crime Report*.
8. IOSCO. (2023). *Policy Recommendations for Crypto and Digital Asset Markets*.
9. PwC Switzerland. (2022). *Proof of Reserves: Bridging the Trust Gap in Crypto Exchanges*.
10. Bisnis Indonesia. (2022, Juli). *Zipmex Bekukan Penarikan Dana Pengguna*. Bisnis.com.

---

*PRIMA v1.0 · Dibangun untuk DIGDAYA X Hackathon 2026 · Pusat Inovasi Digital Indonesia*
