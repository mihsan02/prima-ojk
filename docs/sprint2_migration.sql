-- PRIMA Sprint 2: Kustodian Entity + 30/70 Model
-- Run in Supabase SQL Editor
-- Date: 27 Jun 2026

-- 1. Tabel kustodian
CREATE TABLE IF NOT EXISTS kustodian (
    id TEXT PRIMARY KEY,
    nama TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE kustodian ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only" ON kustodian USING (auth.role() = 'service_role');

-- 2. Junction table kustodian <-> pakd (many-to-many)
CREATE TABLE IF NOT EXISTS kustodian_pakd (
    kustodian_id TEXT NOT NULL REFERENCES kustodian(id) ON DELETE CASCADE,
    pakd_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (kustodian_id, pakd_id)
);
ALTER TABLE kustodian_pakd ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only" ON kustodian_pakd USING (auth.role() = 'service_role');

-- 3. Extend wallets table
ALTER TABLE wallets ADD COLUMN IF NOT EXISTS entity_type TEXT DEFAULT 'PAKD';
ALTER TABLE wallets ADD COLUMN IF NOT EXISTS entity_id TEXT;

-- Backfill existing rows
UPDATE wallets SET entity_id = pakd_id, entity_type = 'PAKD' WHERE entity_id IS NULL;

-- 4. Extend reconciliation_snapshots for 30/70
ALTER TABLE reconciliation_snapshots ADD COLUMN IF NOT EXISTS pakd_onchain_idr NUMERIC;
ALTER TABLE reconciliation_snapshots ADD COLUMN IF NOT EXISTS kustodian_onchain_idr NUMERIC;
ALTER TABLE reconciliation_snapshots ADD COLUMN IF NOT EXISTS compliance_30_70 BOOLEAN;
ALTER TABLE reconciliation_snapshots ADD COLUMN IF NOT EXISTS ratio_at_pakd NUMERIC;
ALTER TABLE reconciliation_snapshots ADD COLUMN IF NOT EXISTS ratio_at_ptp NUMERIC;
