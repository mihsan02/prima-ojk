# Sprint 5 Session Summary — Enhanced Audit Log (Access Tracking)

**Date:** 7 Juli 2026
**Branch:** `claude/audit-log-access-tracking-ws8lco` (merged via PR #32)
**Baseline at session start:** post-Sprint-4, `6a14d17` · 162 tests passing (`test_api.py` excluded — needs live network)
**Baseline at session end:** `8d71dc2` (merge commit on `main`) · 170 tests passing

---

## Problem

Audit log PRIMA sebelumnya hanya mencatat operasi **write** (insert/update/
delete): `CREATE_PAKD`, `UPDATE_KUSTODIAN`, `DELETE_USER`, `REKONSILIASI`,
dan lain-lain. Tidak ada jejak siapa yang **membaca** data rekonsiliasi
sensitif (snapshot terbaru, riwayat, ekspor CSV) dan kapan — celah yang
relevan untuk pengawasan OJK atas siapa yang mengakses data solvabilitas
PAKD/Kustodian.

## Deliverable

Read-access audit trail: setiap akses ke data rekonsiliasi kini dicatat
dengan identitas aktor (email + role dari JWT) dan waktu, tanpa mengubah
skema audit log secara breaking dan tanpa membanjiri log akibat polling
dashboard.

### 1. Actor identity di seluruh audit trail (`prima-backend/app.py`)

- `write_audit(action, detail, actor=None)` — parameter `actor` baru,
  opsional. Bila tidak diberikan, otomatis diambil dari `g.current_user`
  via helper `_current_actor()`. Efeknya: **seluruh call site lama**
  (`CREATE_PAKD`, `UPDATE_KUSTODIAN`, `WALLET VERIFIED`, dst.) langsung
  mendapat kolom aktor tanpa perlu diubah satu per satu.
- Kolom baru `actor_email`, `actor_role` pada tabel `audit_log`. Insert
  mencoba skema baru dulu; jika kolom belum ada (migrasi belum jalan),
  `rollback()` lalu insert ulang dengan skema lama — jadi kode aman
  di-deploy sebelum *maupun* sesudah migrasi dijalankan.
- Fallback file (`audit_log.json`) juga menyertakan `aktor` / `aktor_role`.

### 2. Pencatatan akses read (`log_data_access()`)

- Dipanggil dari:
  - `GET /api/reconciliation/latest`
  - `GET /api/reconciliation-history`
- Entri beraksi `AKSES DATA`, detail mencantumkan email, role, resource,
  dan konteks (mis. jumlah PAKD atau `pakd_id` yang diminta).
- **Throttle 5 menit per (user, resource)** (`_ACCESS_LOG_SEEN`,
  in-memory) — dashboard melakukan polling berkala, jadi akses berulang
  oleh user yang sama ke resource yang sama dalam window tersebut hanya
  dicatat sekali agar 50-entri audit log tidak habis oleh noise polling.
- No-op otomatis di luar request context (mis. dipanggil dari background
  job) — tidak ada `g.current_user` untuk diacu.

### 3. Ekspor data selalu dicatat (tanpa throttle)

- `GET /api/export-csv` dan `GET /api/export-csv-overview` menulis entri
  `EKSPOR DATA` pada **setiap** panggilan (ekstraksi data ke luar sistem
  dianggap tindakan deliberate, bukan polling), termasuk jumlah baris dan
  cakupan (`pakd_id` tertentu vs semua PAKD).

### 4. Rekonsiliasi live menyebut pemicu

- Entri `REKONSILIASI` yang sudah ada di `GET /api/reconciliation` kini
  menyertakan siapa yang memicu proses (email + role).

### 5. Endpoint & UI

- `GET /api/audit-log` — response menambahkan field `aktor` dan
  `aktor_role` per entri, dengan query fallback bila kolom belum ada di DB.
- `prima-frontend/index.html` — halaman Audit Log mendapat kolom baru
  **Pengguna** (email + badge role); entri lama tanpa aktor tampil `—`.

### 6. Migrasi database

`docs/sprint5_migration.sql` (idempotent, jalankan manual di Supabase SQL
Editor):

```sql
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS actor_email TEXT;
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS actor_role  TEXT;
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log (created_at DESC);
```

## Tests

- `prima-backend/test_audit_access.py` (baru, 8 test):
  - `log_data_access` mencatat aktor + resource dengan benar.
  - Akses berulang oleh user yang sama di-throttle (hanya 1 entri).
  - User berbeda dicatat terpisah (tidak saling men-throttle).
  - No-op di luar request context.
  - `write_audit` file-fallback menyertakan aktor eksplisit.
  - `write_audit` auto-detect aktor dari `g.current_user` saat `actor`
    tidak diberikan.
  - `GET /api/reconciliation-history` benar-benar memanggil audit akses.
  - `GET /api/audit-log` mengembalikan field `aktor` / `aktor_role`.
- Total: **170 passing** (`test_api.py` tetap di-exclude di lingkungan
  sandbox — perlu panggilan jaringan live ke Etherscan saat import,
  bukan terkait perubahan ini).

## Design notes / trade-offs

- **In-memory throttle, bukan DB-backed.** Sederhana dan cukup untuk
  tujuan "jangan banjiri log akibat polling"; konsekuensinya throttle
  window reset saat proses restart (dianggap dapat diterima — regulator
  tetap mendapat entri baru setelah restart, bukan kebocoran audit).
- **Dual-schema insert/select (try new columns, fallback legacy)**
  dipilih agar deploy kode dan migrasi SQL bisa dipisah tanpa downtime
  atau urutan wajib, konsisten dengan pola dual-write Supabase/file yang
  sudah ada di `write_audit`.
- **Ekspor tidak di-throttle** karena secara semantik berbeda dari
  polling — setiap klik ekspor adalah tindakan operator yang harus
  100% tertelusuri.

## Open items / roadmap

1. Migrasi `docs/sprint5_migration.sql` masih perlu dijalankan manual di
   Supabase production — sebelum itu, aktor tersimpan tapi tidak di
   kolom terstruktur (fallback legacy insert, aktor hanya ada di
   response saat request context aktif, tidak persisten di kolom baru).
2. Audit log 50-entri masih belum punya hash chain / tamper-evident
   structure (catatan lama, lihat `docs/keterbatasan-sistem.md` Section 6).
3. Throttle window (5 menit) di-hardcode; bisa dijadikan env var bila
   pola polling dashboard berubah.

## Pull requests

| PR | Content | Status |
|----|---------|--------|
| #32 | Enhanced audit log: read-access tracking (siapa & kapan) untuk data rekonsiliasi | Merged |
