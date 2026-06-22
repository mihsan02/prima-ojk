-- PRIMA Sprint 1: IAM Migration
-- Jalankan di Supabase SQL Editor (Dashboard > SQL Editor)
-- Urutan penting: enum dulu, lalu tabel, lalu RLS

-- 1. Enum types (skip jika sudah ada)
DO $$ BEGIN
  CREATE TYPE user_role AS ENUM ('pengawas', 'super_admin', 'pakd', 'kustodian');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE entity_type AS ENUM ('PAKD', 'KUSTODIAN');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 2. Tabel user_profiles
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    role user_role NOT NULL DEFAULT 'pengawas',
    entity_type entity_type,
    entity_id TEXT,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT valid_entity CHECK (
        (role IN ('pengawas', 'super_admin') AND entity_type IS NULL AND entity_id IS NULL)
        OR
        (role = 'pakd' AND entity_type = 'PAKD' AND entity_id IS NOT NULL)
        OR
        (role = 'kustodian' AND entity_type = 'KUSTODIAN' AND entity_id IS NOT NULL)
    )
);

-- 3. RLS: hanya service_role yang bisa akses (backend bypass RLS)
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_only" ON user_profiles;
CREATE POLICY "service_only" ON user_profiles
    USING (auth.role() = 'service_role');

-- 4. Verifikasi
SELECT 'user_profiles table ready' AS status;
SELECT COUNT(*) AS profile_count FROM user_profiles;

-- ============================================================
-- SEED USERS (jalankan SETELAH buat users via API)
-- Ganti UUID dengan ID aktual dari response API
-- ============================================================

-- Contoh INSERT (ganti UUID_xxx dengan ID aktual):
--
-- INSERT INTO user_profiles (id, role, entity_type, entity_id, display_name) VALUES
-- ('UUID_ADMIN',   'super_admin', NULL,   NULL,            'Super Admin PRIMA'),
-- ('UUID_PENGAWAS','pengawas',    NULL,   NULL,            'Pengawas IAKD'),
-- ('UUID_PAKD',    'pakd',        'PAKD', 'PAKD-DEMO-001', 'Alpha Kripto Compliance')
-- ON CONFLICT (id) DO NOTHING;
