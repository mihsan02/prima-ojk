# PRIMA Sprint Semifinal — Progress Log

**Periode:** 22 Juni 2026 - 24 Juli 2026
**Repository:** github.com/mihsan02/prima-ojk

---

## Sprint 1: IAM dan Authentication (22 Jun - 1 Jul)

### 22 Juni 2026 — Day 1 + Day 2-9 (sesi pertama)

**Status:** IN PROGRESS

**Yang telah dikerjakan:**

#### auth.py (DONE)
- JWT validation via PyJWT + SUPABASE_JWT_SECRET
- `get_current_user()` - extract + validate Bearer token
- `_fetch_user_profile()` - query user_profiles DB dengan in-memory cache 5 menit
- `require_auth` decorator - inject `g.current_user`
- `require_role(*roles)` decorator - 403 jika role tidak sesuai
- `require_super_admin_or_token` decorator - dual-auth (JWT atau X-Admin-Token legacy)
- `require_entity_access` decorator - PAKD/Kustodian filter entity
- `login_user()` - call Supabase Auth REST API
- `create_supabase_user()` - Admin API create + insert user_profiles
- `delete_supabase_user()` - Admin API delete + invalidate cache

#### app.py (DONE)
- Import auth module setelah `app = Flask(__name__)`
- `POST /api/auth/login` - login endpoint
- `GET /api/auth/me` - current user info
- `GET /api/users` - list users (super_admin only)
- `POST /api/users` - create user (super_admin only)
- `DELETE /api/users/<user_id>` - delete user (super_admin only)
- `GET /api/pakd` - require_auth + entity filter untuk PAKD role
- `GET /api/reconciliation/latest` - require_auth + entity filter
- `GET /api/reconciliation-history` - require_auth + entity filter + 403 jika PAKD akses lain
- `GET /api/stress-test` - require_auth
- `GET /api/audit-log` - require_auth
- `POST /api/wallet-challenge` - require_auth
- `POST /api/wallet-verify` - require_auth
- `GET /api/export-csv` - require_auth
- `GET /api/export-csv-overview` - require_auth
- `POST /api/reconciliation/refresh` - require_role('super_admin')
- PAKD CRUD (POST/PUT/DELETE) - require_super_admin_or_token (dual-auth grace period)

#### requirements.txt (DONE)
- Tambah PyJWT>=2.8.0
- Tambah openpyxl (prep Sprint 3)

#### docs/sprint1_migration.sql (DONE)
- SQL untuk create enum user_role, entity_type
- CREATE TABLE user_profiles dengan CONSTRAINT valid_entity
- RLS policy service_only
- Template INSERT seed users

#### Frontend index.html (DONE)
- Login overlay page (full-screen, sebelum shell div)
- AUTH object: localStorage session management, headers(), authOnly()
- applyRoleUI(): toggle crud-action visibility berdasarkan role
- apiFetch() helper: auto-inject Bearer token + global 401 handler
- User badge + logout button di topbar
- Semua fetch calls ke protected endpoints diupdate ke apiFetch()
- Tombol "Tambah PAKD", Edit, Delete: class="crud-action" (hidden untuk non-super_admin)
- Field "Admin Token" disembunyikan di modal (diganti JWT session)

#### test_auth.py (DONE)
- TestAuthLogin: test login edge cases
- TestProtectedEndpoints: 401 tanpa token, token invalid, token expired, token valid
- TestRoleAuthorization: pengawas/pakd tidak bisa write, super_admin bisa
- TestEntityAccess: PAKD tidak bisa akses entitas lain
- TestBackwardCompat: X-Admin-Token masih diterima, /ping public
- TestUserManagement: user management requires super_admin

**TODO:**
- [ ] Jalankan SQL migration di Supabase dashboard
- [ ] Create 3 seed users via Supabase Auth REST API
- [ ] Set env vars di Render: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET
- [ ] Test login production: curl POST /api/auth/login
- [ ] Full pytest run setelah env vars diset

**Blockers:**
- Butuh Supabase project credentials (SUPABASE_URL, SUPABASE_JWT_SECRET)
- user_profiles table belum dibuat (butuh akses Supabase SQL Editor)

---

## Sprint 2: Kustodian Entity + 30/70 Model (2 Jul - 11 Jul)
*Belum dimulai*

## Sprint 3: E-Reporting Parser + BTC Verify (12 Jul - 18 Jul)
*Belum dimulai*

## Sprint 4: Integration + Polish + Demo (19 Jul - 24 Jul)
*Belum dimulai*
