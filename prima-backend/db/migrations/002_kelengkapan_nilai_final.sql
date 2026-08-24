-- T2.4 Bagian A1 lanjutan (Opsi 2). aset_onchain_idr_final adalah nilai
-- autoritatif T2.2: NULL saat kelengkapan_status != LENGKAP, berbeda
-- semantik dari aset_onchain_idr lama yang bisa membawa kontribusi
-- tidak lengkap. subtotal_diketahui_idr adalah subtotal dari sumber
-- yang berhasil diambil, terlepas status kelengkapan.
ALTER TABLE reconciliation_snapshots
  ADD COLUMN IF NOT EXISTS aset_onchain_idr_final bigint,
  ADD COLUMN IF NOT EXISTS subtotal_diketahui_idr bigint;
