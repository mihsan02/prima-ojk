-- PRIMA Sprint 3: E-Reporting Parser + BTC Verification
-- Run in Supabase SQL Editor
-- Date: 2 Jul 2026

-- Table: laporan_ereporting
-- Stores parsed e-reporting data (PAKD and Kustodian)
CREATE TABLE IF NOT EXISTS laporan_ereporting (
    id SERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('PAKD', 'KUSTODIAN')),
    entity_id TEXT NOT NULL,
    periode TEXT NOT NULL,                    -- '2026-06' format
    report_type TEXT NOT NULL,                -- 'pakd' or 'kustodian'
    file_hash TEXT,                           -- SHA-256 of uploaded file

    -- PAKD fields (from Sheet 2 + LBNP + LRA)
    aset_breakdown JSONB,                     -- array of per-asset records from Sheet 2
    balance_sheet JSONB,                      -- LBNP parsed fields
    rekening_administratif JSONB,             -- LRA parsed fields

    -- Kustodian fields (from LPWAKD)
    wallet_report JSONB,                      -- array of wallet records

    -- Derived values for reconciliation engine
    customer_at_pakd_idr NUMERIC DEFAULT 0,   -- sum AKD Konsumen penempatan di Pedagang
    customer_at_ptp_idr NUMERIC DEFAULT 0,    -- sum AKD Konsumen penempatan di PTP
    proprietary_idr NUMERIC DEFAULT 0,        -- sum AKD milik Pedagang
    ekuitas_idr NUMERIC DEFAULT 0,             -- from LBNP

    -- Metadata
    uploaded_by UUID,                          -- references auth.users
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ,                  -- NULL until confirmed
    status TEXT DEFAULT 'preview',             -- 'preview' or 'confirmed'
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(entity_id, periode, report_type)    -- one report per entity per period per type
);

ALTER TABLE laporan_ereporting ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only" ON laporan_ereporting
    USING (auth.role() = 'service_role');

-- Index for reconciliation engine lookups
CREATE INDEX IF NOT EXISTS idx_ereporting_entity_periode
    ON laporan_ereporting(entity_id, periode, status);
