# PRIMA
### Pemantauan Transparansi Aset Pedagang Aset Keuangan Digital Berbasis Blockchain

![Status](https://img.shields.io/badge/Status-Prototype%20MVP-0A7A4A?style=flat-square)
![Hackathon](https://img.shields.io/badge/DIGDAYA%20X%20Hackathon-2026-1B3A6B?style=flat-square)
![Regulator](https://img.shields.io/badge/Regulator-OJK-003087?style=flat-square)
![Chain](https://img.shields.io/badge/Chain-BTC%20%7C%20ETH%20%7C%20SOL-F7931A?style=flat-square)

> Prototype MVP · Dibangun untuk DIGDAYA X Hackathon 2026 · Pusat Inovasi Digital Indonesia

**[→ Lihat Live Demo Dashboard](https://ihsanudin.github.io/prima-ojk/demo/PRIMA_Dashboard_Integrated.html)**

---

## Apa itu PRIMA?

PRIMA adalah sistem pemantauan berbasis blockchain yang dirancang untuk membantu OJK mengawasi kecukupan aset Pedagang Aset Keuangan Digital (PAKD) secara otomatis dan real-time.

Sistem ini melakukan rekonsiliasi antara saldo dompet on-chain yang terverifikasi di jaringan blockchain dengan kewajiban yang dilaporkan PAKD kepada regulator. Setiap selisih di atas ambang batas yang ditetapkan memicu alert berjenjang secara otomatis.

PRIMA diposisikan sebagai **baseline pengawasan minimum yang wajib**, bukan pengganti audit. Sistem ini mengisi celah yang tidak bisa diisi oleh laporan periodik biasa: keterlambatan deteksi, ketergantungan pada laporan yang tidak terverifikasi, dan absennya stress test solvabilitas terstandar.

---

## Masalah yang Diselesaikan

Per Januari 2025, OJK mengambil alih pengawasan aset keuangan digital dari Bappebti berdasarkan UU Nomor 4 Tahun 2023 (UU P2SK). Seluruh 25 PAKD berizin — yang mengelola nilai transaksi industri sebesar Rp 556,53 triliun sepanjang 2024 (OJK, 2024) — masih diawasi melalui laporan berkala yang diserahkan sendiri oleh pelaku usaha.

Tiga kelemahan struktural dari pendekatan pelaporan berbasis dokumen:

**1. Keterlambatan deteksi.**
Laporan bulanan tidak menangkap pergerakan aset harian. Kasus Zipmex pada Juli 2022 membekukan aset pengguna Indonesia senilai sekitar $53 juta (Bisnis Indonesia, 2022) tanpa sinyal peringatan yang terdeteksi regulator sebelumnya. Sistem berbasis laporan tidak dirancang untuk mendeteksi tekanan likuiditas yang berkembang dalam hitungan hari.

**2. Tidak ada verifikasi independen.**
Regulator tidak memiliki mekanisme untuk memvalidasi klaim aset secara mandiri. Seluruh proses verifikasi bergantung pada kejujuran pelaporan PAKD — struktur yang oleh FSB (2023) dikategorikan sebagai *insufficient supervisory oversight*.

**3. Tidak ada stress test solvabilitas terstandar.**
Ketika Bitcoin turun 64% sepanjang 2022 (Chainalysis, 2024), tidak ada mekanisme yang memungkinkan OJK mengetahui berapa PAKD yang berisiko gagal bayar kewajiban nasabah sebelum krisis terjadi.

Referensi regulasi: POJK No. 27 Tahun 2024, POJK No. 27 Tahun 2021, OJK Peta Jalan IAKD 2024–2028, FSB (2023), IMF (2023).

---

## Mengapa Bukan Solusi yang Sudah Ada?

Platform analitik blockchain komersial seperti Chainalysis dan Nansen menyediakan kemampuan on-chain monitoring yang canggih. PRIMA tidak bersaing dengan kecanggihan teknis mereka. PRIMA menyelesaikan masalah yang berbeda:

- **Tidak ada integrasi regulasi lokal.** Platform komersial tidak memiliki pemetaan ke daftar PAKD berizin OJK, threshold deviasi berdasarkan POJK, atau struktur alert yang sesuai dengan hierarki pengawasan OJK.
- **Kedaulatan data.** Data pengawasan PAKD adalah data sensitif regulasi. Mengandalkan platform asing berarti posisi aset seluruh industri kripto Indonesia berada di luar yurisdiksi regulator.
- **Biaya.** Lisensi enterprise Chainalysis berkisar ratusan ribu dolar per tahun — tidak realistis sebagai alat pengawasan rutin regulator.

PRIMA dirancang untuk dioperasikan OJK secara in-house, dengan data yang tetap berada dalam infrastruktur regulator.

---

## Cara Kerja Sistem

```
INPUT                         PROSES                        OUTPUT
────────────────────────      ──────────────────────────    ─────────────────────────
Daftar alamat dompet    →     Query blockchain explorer  →  Saldo on-chain terverifikasi
PAKD (dideklarasikan          (Blockstream API · BTC)       per PAKD per tanggal laporan
ke OJK)                       (Etherscan API · ETH)
                              (Solscan API · SOL)
                                        ↓
Laporan kewajiban PAKD  →     Rekonsiliasi otomatis      →  Selisih absolut dan persentase
(diserahkan ke OJK            (Python · pandas)              per entitas
setiap bulan)
                                        ↓
Ambang batas deviasi    →     Klasifikasi dan             →  Notifikasi Tier 1 (>5%)
(<5%: aman                    alert scoring berjenjang       Notifikasi Tier 2 (>20%)
 5–20%: deviasi               per PAKD                       Laporan agregat industri
 >20%: kritis) ¹
                                        ↓
Data historis harga     →     Stress test solvabilitas    →  Laporan ketahanan industri
kripto 36 bulan               tiga skenario:                 per skenario per periode
                              Mild (-30%) · Moderate
                              (-55%) · Severe (-80%) ²
```

> ¹ Ambang batas deviasi mengacu pada praktik Proof-of-Reserves industri (PwC Switzerland, 2022) dan disesuaikan untuk konteks pengawasan OJK. Threshold ini bersifat dapat dikonfigurasi dan dimaksudkan untuk difinalisasi bersama OJK sebelum implementasi penuh.

> ² Skenario stress test mengacu pada drawdown historis Bitcoin: koreksi 2021 (-30%), bear market 2022 (-64%, dibulatkan ke -55% untuk skenario moderat), dan krisis ekstrem historis 2018 (-80%).

---

## Tech Stack

| Kluster | Teknologi | Justifikasi Pemilihan |
|---------|-----------|----------------------|
| Blockchain | Blockstream API, Etherscan API, Solscan API | API publik tanpa biaya dengan rate limit yang cukup untuk 25 PAKD; data bersumber langsung dari node full validator |
| Integrasi | Python 3.11, Requests, APScheduler | Python dominan untuk otomasi data keuangan; APScheduler memungkinkan penjadwalan rekonsiliasi terkonfigurasi tanpa infrastruktur tambahan |
| Analitik | pandas, NumPy | Cukup untuk operasi rekonsiliasi tabular dan kalkulasi deviasi yang dibutuhkan MVP |
| Penyimpanan | PostgreSQL, AES-256, TLS 1.3, RBAC | Keandalan audit trail dan dukungan query historis; enkripsi dan kontrol akses berbasis peran untuk memenuhi standar keamanan data regulasi |
| Antarmuka | HTML, CSS, JavaScript, Chart.js | Tidak memerlukan framework berat untuk dashboard read-only; dapat dihosting dalam infrastruktur OJK tanpa dependensi eksternal |

---

## Status Pengembangan

| Komponen | Status | Lokasi di Repo |
|----------|--------|----------------|
| Dashboard monitoring — mockup | Selesai | `demo/PRIMA_Dashboard_Mockup.html` |
| Dashboard monitoring — integrated | Selesai | `demo/PRIMA_Dashboard_Integrated.html` |
| Desain arsitektur sistem | Selesai | `docs/arsitektur-sistem.md` |
| Logika rekonsiliasi (pseudocode) | Selesai | `docs/arsitektur-sistem.md` |
| Stress test scoring logic | Selesai | `docs/arsitektur-sistem.md` |
| Keterbatasan dan rencana mitigasi | Selesai | `docs/keterbatasan-sistem.md` |
| Backend Python — POC | Dalam pengembangan | — |
| Koneksi API blockchain live | Dalam pengembangan | — |

---

## Struktur Repositori

```
prima-ojk/
├── README.md
├── demo/
│   ├── PRIMA_Dashboard_Integrated.html   ← versi terbaru, multi-halaman
│   └── PRIMA_Dashboard_Mockup.html       ← versi awal
├── docs/
│   ├── arsitektur-sistem.md              ← desain arsitektur lengkap
│   └── keterbatasan-sistem.md            ← batasan MVP yang didokumentasikan
└── assets/
    └── screenshot-dashboard.png
```

---

## Keterbatasan yang Didokumentasikan

PRIMA dibangun dengan prinsip kejujuran teknis. Setiap keterbatasan disertai rencana mitigasi untuk versi berikutnya.

**Circular trust.**
Verifikasi dompet bergantung pada daftar alamat yang dideklarasikan PAKD ke OJK. Dompet yang tidak dideklarasikan tidak terdeteksi. Mitigasi roadmap: mekanisme random sampling audit dompet on-chain oleh OJK secara mandiri, dipicu setelah alert Tier 2.

**Window dressing.**
Pemindahan aset sementara menjelang tanggal snapshot rekonsiliasi tidak tertangkap sistem satu titik. Mitigasi roadmap: rekonsiliasi multi-titik dalam satu periode — empat kali per bulan pada tanggal acak — untuk mengurangi prediktabilitas jadwal pemeriksaan.

**Cakupan aset MVP.**
Versi ini hanya mencakup Bitcoin, Ethereum, dan Solana. Aset ERC-20, token SPL, dan jaringan lain di luar cakupan. Mitigasi roadmap: perluasan bertahap setelah pola integrasi API divalidasi pada tiga chain pertama.

**Sumber data stress test.**
Skenario menggunakan data historis harga, bukan model proyeksi forward-looking. Mitigasi roadmap: integrasi data volatilitas implied dari pasar derivatif kripto untuk skenario yang lebih prospektif.

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
