# Arsitektur Sistem PRIMA
### Pemantauan Transparansi Aset Pedagang Aset Keuangan Digital Berbasis Blockchain

Versi: 1.0 · Terakhir diperbarui: Maret 2026

---

## 1. Gambaran Umum

PRIMA beroperasi dalam tiga tahap utama: pengambilan data on-chain dari jaringan
blockchain, rekonsiliasi otomatis terhadap laporan kewajiban PAKD, dan distribusi
output kepada pengawas OJK. Seluruh proses dijalankan dalam infrastruktur yang
dioperasikan OJK secara in-house.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INFRASTRUKTUR OJK                            │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────────┐  │
│  │   INPUT      │    │    PROSES INTI   │    │     OUTPUT        │  │
│  │              │    │                  │    │                   │  │
│  │ · Dompet     │───▶│ · Query on-chain │───▶│ · Dashboard OJK   │  │
│  │   on-chain   │    │ · Rekonsiliasi   │    │ · Alert berjenjang│  │
│  │   PAKD       │    │ · Alert scoring  │    │ · Laporan periodik│  │
│  │              │    │ · Stress test    │    │ · Audit trail     │  │
│  │ · Laporan    │───▶│                  │───▶│                   │  │
│  │   kewajiban  │    │                  │    │                   │  │
│  │   PAKD       │    │                  │    │                   │  │
│  └──────────────┘    └──────────────────┘    └───────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
         ▲                      ▲
         │                      │
  Jaringan Blockchain    Database Laporan
  (BTC · ETH · SOL)     PAKD (PostgreSQL)
```

---

## 2. Komponen Input

### 2.1 Data On-Chain

PRIMA mengambil data saldo dompet langsung dari jaringan blockchain melalui
API publik tanpa biaya. Daftar alamat dompet diperoleh dari deklarasi resmi
PAKD kepada OJK.

| Jaringan | API | Endpoint Utama | Keandalan Data |
|----------|-----|----------------|----------------|
| Bitcoin | Blockstream API | `/api/address/{address}` | Finality setelah 6 konfirmasi blok |
| Ethereum | Etherscan API | `/api?module=account&action=balance` | Finality setelah ~15 detik (PoS) |
| Solana | Solscan API | `/account/{address}` | Finality setelah ~400ms |

**Catatan penting:** Data yang diambil adalah saldo dompet pada titik waktu
rekonsiliasi, bukan nilai pasar aset. Konversi ke Rupiah menggunakan harga
penutupan hari laporan dari sumber harga yang telah ditetapkan OJK.

### 2.2 Data Laporan Kewajiban PAKD

Laporan kewajiban PAKD diterima OJK dalam format terstandar (CSV/Excel) setiap
bulan, mencakup:
- Total kewajiban kepada nasabah per jenis aset
- Jumlah nasabah aktif
- Tanggal posisi laporan

Data ini dimasukkan ke PostgreSQL oleh petugas OJK yang berwenang sebelum
proses rekonsiliasi dijalankan.

---

## 3. Proses Inti

### 3.1 Pseudocode Rekonsiliasi

```python
UNTUK SETIAP pakd DALAM daftar_pakd_berizin:

    # Langkah 1: Ambil saldo on-chain
    saldo_onchain = 0
    UNTUK SETIAP alamat DALAM daftar_dompet[pakd]:
        saldo_onchain += query_blockchain(alamat, jaringan, tanggal_laporan)

    # Langkah 2: Ambil kewajiban yang dilaporkan
    kewajiban_dilaporkan = ambil_laporan_ojk(pakd, periode_laporan)

    # Langkah 3: Hitung deviasi
    selisih_absolut = saldo_onchain - kewajiban_dilaporkan
    deviasi_persen = (selisih_absolut / kewajiban_dilaporkan) * 100

    # Langkah 4: Klasifikasi status
    JIKA ABS(deviasi_persen) < 5:
        status = "AMAN"
        tier_alert = TIDAK_ADA
    JIKA 5 <= ABS(deviasi_persen) < 20:
        status = "DEVIASI"
        tier_alert = TIER_1
    JIKA ABS(deviasi_persen) >= 20:
        status = "KRITIS"
        tier_alert = TIER_2

    # Langkah 5: Simpan hasil dan kirim alert
    simpan_hasil_rekonsiliasi(pakd, saldo_onchain, kewajiban_dilaporkan,
                               deviasi_persen, status, tanggal_laporan)
    JIKA tier_alert != TIDAK_ADA:
        kirim_notifikasi(pakd, tier_alert, deviasi_persen)
```

### 3.2 Justifikasi Ambang Batas Deviasi

Threshold <5% / 5–20% / >20% ditetapkan berdasarkan dua pertimbangan:

Pertama, praktik industri Proof-of-Reserves (PoR) yang digunakan oleh exchange
kripto besar pasca-kolaps FTX menerima toleransi deviasi kecil akibat perbedaan
waktu pelaporan dan pembulatan nilai. PwC Switzerland (2022) dalam panduan
PoR mereka menetapkan bahwa deviasi di bawah 5% masih dalam batas akurasi
operasional normal.

Kedua, threshold >20% digunakan sebagai batas kritis karena pada angka tersebut
selisih tidak lagi dapat dijelaskan oleh perbedaan teknis pelaporan dan mengindikasikan
kemungkinan kekurangan aset yang material. Threshold ini bersifat dapat dikonfigurasi
dan dimaksudkan untuk difinalisasi bersama OJK berdasarkan asesmen risiko aktual
industri PAKD Indonesia.

### 3.3 Pseudocode Stress Test Solvabilitas

```python
SKENARIO = {
    "mild":     {"penurunan": -0.30, "label": "Mild (-30%)"},
    "moderate": {"penurunan": -0.55, "label": "Moderate (-55%)"},
    "severe":   {"penurunan": -0.80, "label": "Severe (-80%)"}
}

UNTUK SETIAP skenario DALAM SKENARIO:
    hasil_skenario = []

    UNTUK SETIAP pakd DALAM daftar_pakd_berizin:
        # Terapkan penurunan harga pada aset on-chain
        nilai_aset_terstres = saldo_onchain[pakd] * (1 + skenario["penurunan"])

        # Bandingkan dengan kewajiban yang dilaporkan
        JIKA nilai_aset_terstres >= kewajiban_dilaporkan[pakd]:
            hasil = "LULUS"
        LAINNYA:
            hasil = "GAGAL"
            kekurangan = kewajiban_dilaporkan[pakd] - nilai_aset_terstres

        hasil_skenario.append({
            "pakd": pakd,
            "hasil": hasil,
            "kekurangan_estimasi": kekurangan JIKA hasil == "GAGAL" LAINNYA 0
        })

    # Agregasi hasil per skenario
    jumlah_lulus = HITUNG(p UNTUK p DALAM hasil_skenario JIKA p["hasil"] == "LULUS")
    total_kekurangan_industri = JUMLAH(p["kekurangan_estimasi"] UNTUK p DALAM hasil_skenario)

    simpan_hasil_stress_test(skenario, jumlah_lulus, total_kekurangan_industri)
```

**Justifikasi skenario:**
- **Mild -30%:** Mengacu pada koreksi pasar Bitcoin Q2 2021 dari ATH $64.000 ke $29.000
- **Moderate -55%:** Mendekati rata-rata bear market kripto 2022 (Bitcoin -64%, dibulatkan konservatif)
- **Severe -80%:** Mengacu pada bear market kripto 2018 yang merupakan penurunan terdalam yang terdokumentasi dalam sejarah Bitcoin (Chainalysis, 2024)

---

## 4. Komponen Output

### 4.1 Sistem Alert Berjenjang

| Tier | Pemicu | Tindakan |
|------|--------|----------|
| Tidak ada | Deviasi < 5% | Tidak ada notifikasi; tercatat dalam audit trail |
| Tier 1 | Deviasi 5–20% | Notifikasi kepada supervisor OJK; PAKD diminta penjelasan tertulis dalam 3 hari kerja |
| Tier 2 | Deviasi > 20% | Notifikasi kepada pimpinan unit IAKD OJK; permintaan dokumen aset tambahan; pertimbangan tindak lanjut pengawasan |

### 4.2 Dashboard Monitoring

Dashboard berbasis web yang dapat diakses oleh pengawas OJK yang berwenang.
Menampilkan status rekonsiliasi seluruh PAKD, tren historis 6 bulan, dan
hasil stress test terkini. Tidak dapat diakses publik pada tahap MVP.

Lihat: `demo/PRIMA_Dashboard_Integrated.html`

### 4.3 Audit Trail

Setiap operasi rekonsiliasi menghasilkan entri audit yang tidak dapat dimodifikasi
(append-only) di PostgreSQL, mencakup: timestamp operasi, hash data input, hasil
rekonsiliasi, dan identitas pengguna yang menjalankan proses. Entri audit dienkripsi
dengan AES-256 dan disimpan selama minimum 5 tahun sesuai ketentuan OJK.

---

## 5. Jadwal Operasi

| Operasi | Frekuensi | Pemicu |
|---------|-----------|--------|
| Rekonsiliasi rutin | Bulanan | Otomatis setelah batas waktu pelaporan PAKD |
| Rekonsiliasi manual | Ad-hoc | Dipicu oleh pengawas OJK |
| Stress test | Bulanan | Bersamaan dengan rekonsiliasi rutin |
| Pembaruan harga aset | Harian | Otomatis dari sumber harga yang ditetapkan |

---

## 6. Keterbatasan Arsitektur (Ringkasan)

Deskripsi lengkap beserta rencana mitigasi ada di `docs/keterbatasan-sistem.md`.

| Keterbatasan | Dampak | Tingkat Risiko |
|-------------|--------|----------------|
| Circular trust (dompet dideklarasikan sendiri) | Dompet tidak terdaftar tidak terdeteksi | Tinggi |
| Snapshot tunggal per periode | Rentan window dressing | Menengah |
| Cakupan tiga chain saja | Aset di jaringan lain tidak dimonitor | Menengah |
| Data harga historis untuk stress test | Tidak forward-looking | Rendah |

---

## Referensi Teknis

- Blockstream API Documentation: https://github.com/Blockstream/esplora/blob/master/API.md
- Etherscan API Documentation: https://docs.etherscan.io
- Solscan API Documentation: https://pro-api.solscan.io/pro-api-docs
- PwC Switzerland. (2022). *Proof of Reserves: Bridging the Trust Gap in Crypto Exchanges*.
- Chainalysis. (2024). *The Chainalysis 2024 Crypto Crime Report*.
