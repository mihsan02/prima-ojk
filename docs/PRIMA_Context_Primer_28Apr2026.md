# PRIMA Context Primer
**Tanggal dokumen:** 28 April 2026
**Periode aktif:** 28 April 2026 sampai 1 Juni 2026
**Repository:** https://github.com/mihsan02/prima-ojk
**Submission deadline:** 1 Juni 2026 (geser dari deadline awal 24 Mei)
**Author context:** Ihsan, mhusername mihsan02, peserta DIGDAYA X 2026

Dokumen ini menggantikan PRIMA_Context_Primer.md sebelumnya sebagai single source of truth untuk konteks chat baru. Berisi keputusan arsitektur, schema reporting yang baru ditemukan, timeline revisi, dan hard rules yang harus dipegang sampai submission.

---

## 1. Ringkasan Sesi 28 April 2026

Sesi ini menghasilkan empat keputusan struktural yang mengubah arah PRIMA dari versi MVP awal.

Pertama, deadline submission geser dari 24 Mei ke 1 Juni 2026. Total tambahan 8 hari kalender. Realokasi: 6 hari coding extension, 8 hari polish dan rehearsal yang lebih panjang.

Kedua, pendekatan rekonsiliasi historis ditetapkan snapshot-based, bukan delta arithmetic. Ide awal "ambil saldo sekarang lalu kurangi inflow tambah outflow ke tanggal target" ditolak dengan alasan teknis: edge case smart contract interaction (gas, internal tx, swap atomik, staking, MEV) membuat reconstruction rapuh, archive node berbayar dibutuhkan untuk historical state query lebih dari 27 jam, dan delta arithmetic reinvent kapabilitas eth_getBalance dengan blockNumber parameter yang sudah ada di level protocol.

Ketiga, schema pelaporan PAKD sesuai POJK 27/2024 ditemukan jauh lebih kompleks dari asumsi awal PRIMA. PAKD lapor dua komponen: Form Rincian Keuangan Bulanan (balance sheet plus laba rugi plus rekening administratif) dan Rekapitulasi Aset Keuangan Digital Konsumen dan Pedagang Bulanan (breakdown per-aset dengan dimensi kepemilikan dan kustodi). Single-number reconciliation di MVP sekarang tidak cukup untuk schema ini.

Keempat, Pengelola Tempat Penyimpanan (PTP) dikonfirmasi sebagai entitas teregulasi terpisah dengan izin sendiri dari OJK. Regulasi mensyaratkan minimal 70 persen aset Konsumen wajib di PTP, maksimal 30 persen di Pedagang. PRIMA versi sekarang belum cover PTP wallet sama sekali, dan ini gap material yang harus minimum di-acknowledge di sprint extension.

---

## 2. Konteks Proyek (Update)

PRIMA (Pemantauan Transparansi Aset Pedagang Aset Keuangan Digital Berbasis Blockchain) adalah sistem pemantauan regulasi yang dibangun untuk OJK, ditujukan mengawasi Pedagang Aset Keuangan Digital (PAKD) yang sebelumnya diatur Bappebti. Kewenangan pengawasan berpindah ke OJK efektif 10 Januari 2025 berdasarkan UU P2SK.

Anchor regulasi yang dipakai dan sudah dipublikasikan resmi:
- POJK No. 27 Tahun 2021
- POJK No. 27 Tahun 2024 (mengatur cadence pelaporan bulanan, deadline tanggal 10 bulan berikutnya)
- UU P2SK (Undang-Undang Nomor 4 Tahun 2023)
- Peta Jalan IAKD OJK 2024 sampai 2028
- Schema laporan: Form Rincian Keuangan Bulanan Pedagang dan Rekapitulasi Aset Keuangan Digital Konsumen dan Pedagang Bulanan

PRIMA bukan replacement audit. PRIMA adalah baseline regulatory monitoring tool yang melakukan rekonsiliasi otomatis antara aset on-chain yang dideklarasikan PAKD versus aset yang dilaporkan ke OJK, ditambah stress test solvabilitas pada beberapa skenario harga.

Differentiator versus tools sejenis:
- Regulator-operated, bukan exchange self-reporting (kontras versus Chainlink Proof of Reserve)
- Indonesia-specific dengan integrasi ekosistem regulasi OJK
- Cost-accessible (open source, infrastruktur publik di MVP)
- Monitoring on-chain yang verify movements (penambahan/pengurangan) per aset, kapabilitas yang tidak ada di alat regulator TradFi

---

## 3. Schema Pelaporan PAKD (Discovery Sesi Ini)

### 3.1 Form Rincian Keuangan Bulanan Pedagang

Komponen pertama. Berisi balance sheet lengkap, laporan laba rugi, dan rekening administratif. Pos yang relevan untuk PRIMA:

Aset:
- Persediaan Aset Keuangan Digital (AKD untuk dijual ke konsumen)
- Aset Tidak Berwujud > Aset Keuangan Digital:
  - Simpanan milik Pedagang (PAKD-owned, non-trading)
  - Dalam protokol staking: milik Pedagang dan milik Konsumen (dipisah)
  - Dalam protokol lainnya: milik Pedagang dan milik Konsumen (dipisah)

Liabilitas:
- Liabilitas kepada Konsumen termasuk kewajiban penggantian AKD milik Konsumen, AKD dalam protokol staking milik Konsumen, AKD dalam protokol lain milik Konsumen

Rekening Administratif (off-balance sheet):
- Titipan Aset Keuangan Digital Milik Konsumen pada Pedagang
- Titipan Aset Keuangan Digital Milik Konsumen pada Pengelola Tempat Penyimpanan
- Titipan Margin derivatif (dana di Lembaga Kliring Penjaminan dan Penyelesaian, AKD di PTP)

Valuasi: harga penutupan acuan Bursa pukul 23:59 WIB tanggal cut-off (akhir bulan).

### 3.2 Rekapitulasi Aset Keuangan Digital Konsumen dan Pedagang Bulanan

Komponen kedua. Per-asset breakdown dengan kolom:
- Kode Aset Keuangan Digital, Nama AKD
- Posisi Awal Bulan: jumlah unit, dipecah AKD milik Konsumen vs Pedagang, lalu Konsumen dipecah lagi penempatan di Pedagang vs di PTP
- Nilai Penambahan: dimensi sama
- Nilai Pengurangan: dimensi sama
- Posisi Akhir Bulan: autofilled dari rumus (Awal + Penambahan - Pengurangan)
- Harga Penutupan Akhir Bulan Per Unit dalam Rupiah

Constraint kustodi (hardcoded di schema):
- Maksimal 30 persen aset Konsumen di Pedagang
- Minimal 70 persen aset Konsumen di Pengelola Tempat Penyimpanan

PTP adalah entitas teregulasi terpisah dengan izin sendiri dari OJK. Bukan PAKD, bukan custodian arbitrer.

### 3.3 Implikasi untuk PRIMA

Single-number reconciliation di MVP saat ini secara struktural tidak bisa serve schema ini. Yang sebenarnya harus dicocokkan adalah total balance on-chain di semua wallet (PAKD plus PTP) per aset cocok dengan jumlah komponen rekapitulasi yaitu Persediaan plus Simpanan Pedagang plus Staking (Pedagang dan Konsumen) plus Protokol Lain (Pedagang dan Konsumen) plus Titipan Konsumen.

Realistis untuk hackathon: implementasi penuh schema butuh database, schema migration kompleks, dan reconciliation logic per asset class. Minimum 8 sampai 10 hari kerja, terlalu mahal untuk benefit yang masih bisa dinarasikan sebagai Phase 2 di pitch. Yang masuk sprint extension hanya minimum data model awareness dan documentation hooks.

---

## 4. Arsitektur Snapshot-Based (Keputusan Sesi)

### 4.1 Kenapa Snapshot, Bukan Delta Arithmetic

Pendekatan rollback live (ambil saldo sekarang, kurangi inflow tambah outflow) ditolak karena:

Pertama, transfer bukan satu-satunya cara saldo berubah. Gas fees, internal transactions di smart contract, failed transactions yang konsumsi gas, token swap atomik yang ubah aset A jadi aset B dalam satu transaksi, staking dan lending dan airdrop dan MEV. Setiap edge case yang lewat menghasilkan saldo historis yang salah.

Kedua, secara komputasional mahal. Backfill historis multiply API calls dengan faktor 10 sampai 100 per query. Sprint sudah perlu caching layer untuk survive rate limit di mode real-time saja.

Ketiga, full node Ethereum hanya simpan 128 block terakhir (sekitar 26 menit) atau setelah upgrade Pectra sekitar 8.192 block (sekitar 27 jam). State lebih lama dipangkas. eth_getBalance dengan block parameter historis akan return error "required historical state unavailable" pada full node tanpa archive data. Public RPC dan Etherscan free tier umumnya full node, bukan archive. Untuk historical query yang lebih dari sehari ke belakang butuh provider archive berbayar (Alchemy, Infura, Helius archive tier). Tidak konsisten dengan pitch cost-accessible.

Sumber teknis: dokumentasi JSON-RPC ethereum.org, dokumentasi QuickNode, blog Dwellir tentang archive node retention windows.

### 4.2 Bagaimana Snapshot-Based Bekerja

POJK 27/2024 cadence bulanan deadline tanggal 10 bulan berikutnya menciptakan window 10 hari yang sempurna untuk snapshot architecture.

Flow operasional:
- Hari 1 sampai akhir bulan: PRIMA capture daily snapshot otomatis di background. Capture pada block height yang difinalkan paling dekat dengan 23:59:59 WIB tanggal target setiap harinya.
- Akhir bulan: snapshot pada block cut-off bulan ditandai sebagai official month-end snapshot untuk reporting cycle.
- Hari 1 sampai 10 bulan berikutnya: PAKD prepare dan submit laporan ke OJK.
- Saat submit: PRIMA auto-reconcile laporan PAKD versus official month-end snapshot tersimpan.
- Output: deviation report, status (Aman, Deviasi, Kritis), audit trail dari capture sampai reconciliation.

PRIMA tidak perlu archive RPC. Tidak perlu reconstruction. Tidak perlu rollback. Yang dibutuhkan: cron daily di waktu fixed UTC untuk capture, storage time-series ringan, endpoint reconciliation yang menerima parameter cut-off date.

### 4.3 Cut-Off Adalah Block Height, Bukan Tanggal Kalender

Blockchain tidak punya boundary tanggal. Yang ada adalah block height. "Data blockchain pada 30 April" sebenarnya berarti state pada block yang difinalkan paling dekat dengan 30 April 23:59 WIB untuk Ethereum, block height yang setara di Bitcoin, dan slot yang setara di Solana.

Cut-off operasional PRIMA harus didefinisikan eksplisit di config:
- Block Ethereum yang difinalkan terakhir sebelum 17:00:00 UTC tanggal terakhir bulan lapor (artinya 00:00:00 WIB tanggal 1 bulan baru)
- Block Bitcoin setara
- Slot Solana setara

Tanpa definisi ini, PAKD bisa cherry-pick block dan dispute soal kapan persisnya cut-off. Ini governance issue, bukan detail teknis.

### 4.4 Continuous Monitoring versus Reactive Verification

Posture yang harus PRIMA ambil adalah continuous monitoring, bukan passive verification. PRIMA capture snapshot di jadwalnya sendiri terlepas dari kapan PAKD lapor. Hasilnya time series lengkap milik regulator, bukan event-driven verification yang trigger oleh PAKD.

Saat PAKD submit laporan, laporan jadi checkpoint dalam time series PRIMA, bukan trigger reconciliation. Ini exactly differentiator regulator-operated tool versus self-reported Proof of Reserve. Chainlink PoR capture saat exchange yang trigger. PRIMA capture berdasarkan jadwal regulator.

---

## 5. Schema Data PAKD (Update Sesi Ini)

### 5.1 Schema Lama (Sebelum Update)

```json
{
  "id": "PAKD-001",
  "nama": "PT Indodax Nasional Indonesia",
  "wallets": [
    {"network": "ethereum", "address": "0x...", "verified": false}
  ],
  "aset_dilaporkan": 50000000000,
  "last_reconciled": "2026-05-10T08:35:00Z"
}
```

### 5.2 Schema Baru (Target Sprint Extension)

```json
{
  "id": "PAKD-001",
  "nama": "PT Indodax Nasional Indonesia",
  "wallets": [
    {
      "network": "ethereum",
      "address": "0x...",
      "verified": false,
      "verified_at": null,
      "wallet_class": "pakd"
    }
  ],
  "ptp_wallets": [
    {
      "network": "bitcoin",
      "address": "bc1q...",
      "verified": false,
      "verified_at": null,
      "ptp_entity_name": "PT Pengelola Penyimpanan ABC"
    }
  ],
  "aset_dilaporkan": {
    "aset_pedagang_idr": 30000000000,
    "aset_konsumen_titipan_pedagang_idr": 6000000000,
    "aset_konsumen_titipan_ptp_idr": 14000000000,
    "total_idr": 50000000000
  },
  "last_reconciled": "2026-05-10T08:35:00Z"
}
```

Migration handler wajib backward-compatible. Existing record dengan single-number aset_dilaporkan harus diparse ulang ke struct dengan total_idr field saja, dan field ownership-class lainnya null sampai PAKD update laporannya.

### 5.3 Compliance Check 70/30

Implementasi cheap, satu rasio aritmatika dari struct baru:

```
total_titipan_konsumen = aset_konsumen_titipan_pedagang_idr + aset_konsumen_titipan_ptp_idr
ratio_pedagang = aset_konsumen_titipan_pedagang_idr / total_titipan_konsumen
ratio_ptp = aset_konsumen_titipan_ptp_idr / total_titipan_konsumen

flag_violation = (ratio_pedagang > 0.30) OR (ratio_ptp < 0.70)
```

Tampilkan flag di detail page per PAKD. Heavy secara pitch impact karena PRIMA enforce ketentuan POJK secara mekanis, immediately recognizable oleh juri yang baca regulasi.

---

## 6. Timeline Revisi (28 April sampai 1 Juni)

### 6.1 Status Hari 1 sampai 16 (Plan Awal)

Hari 1 sampai 16 (27 April sampai 12 Mei) jalan sesuai PRIMA_Sprint_Plan_27Apr_18Mei2026.md yang sudah di-commit. Goal Hari 16 adalah v1.0-multichain-rc1 yang ship multi-chain ETH BTC SOL native plus ERC-20 USDT USDC plus SPL USDT USDC, wallet ownership proof ETH dan SOL, caching layer, stress test refactor per asset class.

### 6.2 Hari 17 sampai 22 (13 sampai 18 Mei) Coding Extension

Hari 17 dan 18 (13 sampai 14 Mei): Schema-aware data model dan PTP support
- Refactor pakd_data.json: aset_dilaporkan jadi struct tiga field plus total_idr
- Tambah array ptp_wallets dengan struktur sama wallets plus field ptp_entity_name
- Update endpoint reconciliation untuk consume schema baru, tampilkan deviation per kelas kepemilikan
- Frontend update minimal untuk display struct baru
- Migration handler legacy single-number tetap perlu agar existing data tidak corrupt
- Backup pakd_data.json ke .bak.20260513 sebelum migration jalan

Hari 19 dan 20 (15 sampai 16 Mei): Detail per PAKD page dan compliance check 70/30
- Halaman drill-down per PAKD: list wallet PAKD dan list wallet PTP, breakdown per aset di setiap wallet, total per kelas kepemilikan
- Flag merah otomatis kalau persentase aset Konsumen di PAKD wallet melebihi 30 persen total titipan Konsumen
- Compliance status (Sesuai 70/30, Pelanggaran Ringan, Pelanggaran Berat) ditampilkan prominent

Hari 21 dan 22 (17 sampai 18 Mei): Snapshot persistence layer ringan
- Endpoint POST /api/snapshot/capture (manual trigger di MVP, cron tetap Phase 2)
- Storage /data/snapshots/PAKD-XXX_YYYY-MM-DD.json dengan atomic write pattern
- Endpoint GET /api/snapshot/list?pakd_id=X untuk browse history
- Endpoint GET /api/reconcile-historical?pakd_id=X&date=YYYY-MM-DD untuk reconcile laporan vs snapshot tersimpan
- Demo flow: capture snapshot di tanggal X, list snapshot, user pilih, sistem reconcile, output deviation

Code freeze 18 Mei pukul 23:59 WIB. Tidak ada fitur baru setelah ini. Hard rule.

### 6.3 Hari 23 sampai 35 (19 Mei sampai 31 Mei) Polish dan Rehearsal

19 sampai 20 Mei: Finalize pitch deck, integrate screenshot schema rekapitulasi POJK 27/2024 sebagai appendix slide.

21 sampai 22 Mei: Record video demo versi 1, identify gap dan bug yang muncul saat rehearsal demo.

23 sampai 25 Mei: Bug fix only (no new features) di code, record video demo versi 2 final, plus backup video version (slide-based annotated walkthrough sebagai fallback kalau live demo crash).

26 sampai 30 Mei: Rehearsal pitch live minimum 10 kali. Simulate Q&A dengan minimum 10 pertanyaan keras yang harus disiapkan duluan plus jawaban. Prepare backup plan kalau live demo crash di submission.

31 Mei: Final review semua deliverable, push final commit dengan tag v1.0-prima-final, verify GitHub Pages live, verify video accessible.

1 Juni: Submit dengan deck final, video demo final, repository tagged, dokumentasi update.

### 6.4 Pertanyaan Q&A Keras yang Harus Disiapkan

Daftar minimum 10 pertanyaan yang harus dijawab confidently:

1. Bagaimana PRIMA verifikasi 70 persen aset Konsumen di Pengelola Tempat Penyimpanan?
2. Apa beda PRIMA dengan Chainlink Proof of Reserve?
3. Kenapa pakai CoinGecko bukan harga acuan Bursa?
4. Apa yang terjadi kalau PAKD pakai DeFi staking di Lido atau Aave?
5. Bagaimana PRIMA tahu wallet yang dideklarasikan PAKD itu benar miliknya?
6. Apa proses kalau PAKD bantah hasil rekonsiliasi PRIMA?
7. Berapa biaya operasional PRIMA dalam production?
8. Bagaimana PRIMA scale ke 50 PAKD plus PTP?
9. Kenapa MVP hanya cover ETH BTC SOL, bagaimana dengan TRON BSC POLYGON?
10. Apakah PRIMA sudah berkoordinasi dengan tim OJK secara formal?
11. Apa yang terjadi kalau RPC public down saat reconciliation cycle?
12. Bagaimana PRIMA handle stablecoin depeg seperti USDC SVB Maret 2023?

---

## 7. Pitch Positioning (Update Sesi)

### 7.1 Roadmap Phase Framing

Phase 1 (MVP saat ini, demonstrate di pitch): Total balance reconciliation multi-chain (ETH BTC SOL plus ERC-20 USDT USDC plus SPL USDT USDC), wallet ownership proof ETH dan SOL, stress test per asset class, snapshot persistence dasar, detail per PAKD view dengan compliance check 70/30.

Phase 2 (post-hackathon, 6 sampai 12 bulan): Per-asset breakdown reconciliation full schema POJK 27/2024, integrasi wallet PTP via koordinasi inter-entitas teregulasi OJK, integrasi Bursa reference price feed (butuh formal partnership dengan Bursa), scheduled background cron capture, database migration dari JSON file, RBAC dan authentication, hash chain integrity di audit log, integrasi dengan sistem pelaporan OJK eksisting (PAKD upload sekali, PRIMA otomatis pull data laporan).

Phase 3 (long-term, 12 sampai 24 bulan): Staking dan DeFi position tracking via contract-specific oracles atau subgraph queries, multi-chain expansion (TRON BSC POLYGON), Bitcoin BIP-322 signature verification, ML anomaly detection untuk pattern deviation lintas waktu.

### 7.2 Slide yang Wajib Ada di Deck

Problem statement (1 slide): kewenangan transfer Bappebti ke OJK 10 Januari 2025, tantangan pengawasan PAKD, gap di self-reported Proof of Reserve.

Schema regulasi (1 slide): screenshot Form Rincian dan Rekapitulasi dari POJK 27/2024 dengan caption "schema pelaporan PAKD penuh yang PRIMA Phase 2 akan dukung". Ini slide kritis yang menunjukkan kamu paham regulasi di level operasional.

Differentiator (1 slide): regulator-operated, Indonesia-specific, cost-accessible, on-chain movement verification (kapabilitas yang tidak ada di alat regulator TradFi).

Architecture (1 slide): diagram tiga stage Input dari blockchain dan input PAKD, Process di PRIMA core, Output ke OJK dashboard.

Demo (3 sampai 5 slide atau 90 sampai 120 detik live demo): happy path yang sudah di-rehearse minimum 10 kali.

Phase roadmap (1 slide): tiga fase dengan timeline indikatif.

Limitasi yang diakui (1 slide): circular trust gap PTP wallet di Phase 1, valuasi pakai CoinGecko placeholder, staking dan DeFi out of scope MVP. Ini slide yang counter-intuitively menambah credibility.

Closing (1 slide): regulatory baseline, bukan replacement audit. Cost-accessible. Open source. Siap untuk pilot bersama OJK.

### 7.3 Ucapan Pembuka Pitch (Hook 20 Detik)

Draft sample yang bisa di-adapt:

"Per 10 Januari 2025, kewenangan pengawasan Pedagang Aset Keuangan Digital berpindah dari Bappebti ke OJK. Per POJK 27/2024, PAKD wajib lapor aset bulanan ke OJK paling lambat tanggal 10. Pertanyaan: bagaimana OJK verifikasi laporan tersebut benar di chain, di tengah 50-an PAKD aktif dan miliaran rupiah aset terpencar di banyak wallet? Saat ini, OJK mengandalkan self-reporting. Kami bangun PRIMA, sistem pemantauan otomatis berbasis blockchain yang OJK sendiri operasikan, untuk menutup gap itu."

20 detik tepat. Tidak ada kata berlebih.

---

## 8. Hard Rules Sampai 1 Juni

Aturan non-negotiable yang harus dipegang:

Tidak ada fitur baru setelah Hari 22 (18 Mei pukul 23:59 WIB). Tidak peduli sebagus apa idenya. Ide brilian post-freeze masuk docs/post-hackathon-roadmap.md. Code freeze yang dilanggar adalah cara hackathon submission paling sering kalah. Bug muncul di rehearsal Hari 28 yang root cause-nya fitur ditambah Hari 25 tidak akan sempat diperbaiki.

Tidak claim kapabilitas yang belum diimplementasi. Phase 2 dan Phase 3 di-frame sebagai roadmap, bukan sebagai "akan kami tambahkan minggu depan". Juri yang paham crypto akan probe klaim agresif dan tegas.

Tidak skip rehearsal. 10 ronde minimum untuk live pitch. Q&A simulation dengan 10 hard questions plus jawaban yang dirancang. Video demo 2 versi minimum (live screen recording plus annotated walkthrough fallback).

Tidak abaikan limitasi di slide. Slide limitasi yang diakui justru menambah credibility. Hide limitasi adalah red flag bagi juri berpengalaman.

Tidak modifikasi pitch deck atau video demo setelah 31 Mei. Submit window 1 Juni harus cuma click submit, bukan finalize file.

---

## 9. File dan Dokumen Acuan

Repository: https://github.com/mihsan02/prima-ojk

File acuan yang sudah ada di repository dan project knowledge:
- README.md (perlu update reflect schema awareness dan Phase 2 framing setelah sprint extension)
- docs/arsitektur-sistem.md (perlu update tambah PTP wallet concept dan snapshot architecture)
- docs/keterbatasan-sistem.md (perlu update tambah PTP gap, Bursa price gap, staking gap, single-number reconciliation gap)
- PRIMA_Sprint_Plan_27Apr_18Mei2026.md (plan asli Hari 1-16, masih valid sebagai daily plan untuk fase coding awal)
- PRIMA_Progress_Tracker.md
- PRIMA_Context_Primer.md (versi lama, di-supersede oleh dokumen ini)

Dokumen schema regulasi (sudah dipublikasikan resmi):
- POJK No. 27 Tahun 2024
- Form Rincian Keuangan Bulanan Pedagang dan Rekapitulasi Aset Keuangan Digital Konsumen dan Pedagang Bulanan (turunan SEOJK)
- Cantumkan dokumen asli sebagai appendix mandatory di pitch deck

Sumber teknis untuk justifikasi pitch:
- IOSCO Crypto and Digital Asset Recommendations final November 2023
- Dokumentasi JSON-RPC ethereum.org untuk eth_getBalance dengan blockNumber parameter
- Blog Dwellir "The Hidden Costs of Archive Nodes" untuk justifikasi snapshot-based architecture

---

## 10. Cara Memulai Sesi Chat Baru

Buka chat baru di project. Paste prompt awal:

```
Lanjut PRIMA. Submission deadline 1 Juni 2026.
Status: [Hari N dari 22 coding extension] atau [Fase polish dan rehearsal Hari X].
Task hari ini: [copy dari section Timeline Revisi di PRIMA_Context_Primer_28Apr2026.md].
Status sebelumnya: [hari sebelumnya selesai dengan hasil Y].
Mulai dengan eksekusi task hari ini.
```

Claude akan punya context project knowledge plus user memories. Tidak perlu mengulang dari awal. File ini adalah single source of truth untuk arsitektur revisi pasca-28 April.

Kalau ada pertanyaan arsitektur baru yang muncul di chat, cek dulu apakah jawabannya sudah di Section 1 sampai 7 di file ini. Kalau iya, paste reference. Kalau tidak ada, putuskan sebagai keputusan baru, dokumentasikan di file successor jika substansial.

---

## 11. Pertanyaan Terbuka yang Belum Terjawab

Daftar item yang masih perlu klarifikasi sebelum atau saat sprint extension. Tidak blocking untuk Hari 17-22, tapi harus dipikirkan menjelang pitch:

Apakah POJK 27/2024 atau SEOJK turunannya mengatur penalty untuk late submission setelah tanggal 10? Grace period? Auto-flag deviasi? Penting untuk narasi enforcement di pitch.

Bagaimana mekanisme amendment laporan kalau PAKD submit ulang di tanggal 12 untuk cycle yang sama? Apakah PRIMA reconcile ulang dan overwrite, atau record amendment sebagai entry baru? Affects audit trail design.

Bagaimana dispute mechanism antara PRIMA finding versus PAKD bantahan? Berapa lama review window? Siapa final arbiter? Sistem regulator tanpa dispute mechanism rawan overturn.

Apakah PAKD post-transfer dari Bappebti sekarang submit laporan via sistem OJK eksisting apa? PRIMA integrate atau parallel? Integrate berarti satu upload, parallel berarti dua upload yang akan resistance dari industri.

Apakah Bursa Berjangka punya API publik untuk reference price, atau itu institusional access only? Status ini menentukan seberapa aman Phase 2 framing valuasi.

Apakah ada requirement audit independen di POJK 27/2024 yang positioning PRIMA bisa overlap atau complementary? Kalau ada, framing PRIMA versus auditor harus jelas di pitch.

---

*Dokumen ini dibuat 28 April 2026 sebagai context primer pasca diskusi arsitektur revisi. Commit ke /docs/PRIMA_Context_Primer_28Apr2026.md di repository agar accessible dari mana saja dan dipakai sebagai context starter di sesi chat berikutnya. File ini supersede PRIMA_Context_Primer.md versi sebelumnya untuk semua keputusan post-28 April 2026.*
