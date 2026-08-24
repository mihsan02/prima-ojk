-- T2.4 Bagian A1. Dijalankan manual di Supabase SQL editor 23 Agu 2026,
-- dicommit retroaktif untuk reproduktifitas.
ALTER TABLE reconciliation_snapshots
  ADD COLUMN IF NOT EXISTS kelengkapan_status text,
  ADD COLUMN IF NOT EXISTS sumber_gagal jsonb,
  ADD COLUMN IF NOT EXISTS provenance_harga jsonb;
