# Sprint 2: Kustodian Entity + 30/70 Compliance Model

**Date:** 27 Jun 2026  
**Branch:** `claude/new-session-ljm4ek`  
**PR:** https://github.com/mihsan02/prima-ojk/pull/8 (draft)

## Steps Completed

| Step | Description | Status |
|------|-------------|--------|
| 1 | Schema migration SQL (kustodian, kustodian_pakd, wallets extension) | Done |
| 2 | Backend seed data (KUSTODIAN_DEFAULT, REPORTED_VALUES_DEFAULT, init_kustodian_data) | Done |
| 3 | Kustodian CRUD API + 15 tests | Done |
| 4 | Frontend Kustodian page (table, detail, CRUD modal) | Done |
| 5 | Reconciliation engine rewrite (30/70 dual-track) | Done |
| 6 | Dashboard 30/70 compliance badges + detail dual-track panel | Done |
| 7 | Stress test 30/70 cyber risk scenarios (PAKD-only, Kustodian-only, Both) | Done |
| 8 | Tests + regression (36/36 passing) | Done |

## Key Files Modified

- `docs/sprint2_migration.sql` — Schema migration
- `prima-backend/app.py` — Kustodian CRUD, 30/70 engine, stress test update
- `prima-backend/test_kustodian.py` — 15 new tests
- `prima-frontend/index.html` — Kustodian page, badges, detail 30/70 panel, stress test section

## Test Results

```
36 passed in 0.41s
- test_auth.py: 21 tests
- test_kustodian.py: 15 tests
```

## Manual Testing Checklist

- [ ] Kustodian page CRUD (add, edit, delete)
- [ ] 30/70 badges on dashboard overview (COMPLIANT / VIOLATION / N/A)
- [ ] Detail page dual-track panel with donut chart
- [ ] Stress test 30/70 section (3 scenarios)
- [ ] CSV export includes 30/70 columns
- [ ] Gamma (PAKD-OJK-002) shows VIOLATION badge (62.5% at PAKD > 30%)
