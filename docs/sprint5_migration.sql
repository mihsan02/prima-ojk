-- Sprint 5: Enhanced Audit Log — access tracking
-- Audit log sebelumnya hanya mencatat operasi write (insert/update/delete).
-- Migrasi ini menambahkan kolom aktor sehingga sistem dapat mencatat
-- SIAPA yang mengakses data rekonsiliasi dan KAPAN (read-access audit).
--
-- Jalankan di Supabase SQL Editor. Idempotent (aman dijalankan ulang).

ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS actor_email TEXT;
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS actor_role  TEXT;

-- Audit log dibaca ORDER BY created_at DESC LIMIT 50; index mempercepat
-- query saat tabel membesar karena entri akses data bertambah.
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log (created_at DESC);
