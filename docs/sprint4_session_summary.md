# Sprint 4 Session Summary — Kustodian Monitoring Dashboard

**Date:** 6 Juli 2026
**Branch:** `claude/enhanced-sidebar-kustodian-i3e3km` (merged via PR #18, #19, #20, #21)
**Baseline at session start:** post-Sprint-3.5, `a37121e` · 147 tests passing (2 known network-dependent failures: `test_day7_spl_integration.py` test_I3/test_I8)
**Baseline at session end:** `827d114` · 154 tests passing (same 2 known failures)

---

## Deliverables

### 1. Kustodian Monitoring Dashboard (PR #18)

Transformed the Kustodian page from a CRUD management tool into a regulatory
monitoring dashboard answering: *is this Kustodian actually holding what it
should, for whom, and is it verifiable?*

**Backend — `GET /api/kustodian/<kust_id>/monitoring`** (`prima-backend/app.py`)

- Single response containing `kustodian`, `summary`, `pakd_compliance[]`, `wallets[]`.
- Auth scoping: `super_admin`/`pengawas` → any kustodian; `pakd` → only linked
  kustodian (403 otherwise); `kustodian` → only own entity.
- Reported values resolved via the existing `_get_reported_values()`
  (`laporan_ereporting` → `REPORTED_VALUES_DEFAULT` fallback) — no duplicated logic.
- `kustodian_onchain_idr` is taken (not summed) from the latest reconciliation
  snapshot — it is the kustodian's total wallet balance, identical across
  linked PAKDs in the same run.
- `deviation_pct = (total_onchain − Σ customer_at_ptp) / Σ customer_at_ptp × 100`.
- `conn=` passed through to all helpers (pool-size-1 deadlock guard).
- No schema changes; all data from existing tables.

**Frontend** (`prima-frontend/index.html`)

- 4 KPI summary cards (existing `kpi-card` styles): Total AKD Under Custody,
  Ekspektasi di PTP, Deviasi Kustodian (green −10%..+50% / amber −20%..−10%
  or +50%..+100% / red beyond), Verifikasi Wallet (n/total, %).
- "Status Penempatan AKD pada Kustodian · POJK 23/2025 Pasal 91" table with
  `badge-compliant`/`badge-violation` badges per linked PAKD.
- SVG donut: AKD distribution per PAKD (concentration risk), with legend and
  total-di-PTP center label.
- Wallet table (network, address, verified status).
- Client-side CSV export (`kustodian_<id>_monitoring.csv`).
- Kustodian selector dropdown, shown for `super_admin`/`pengawas` when ≥2
  kustodian exist.
- CRUD (Tambah/Edit/Hapus) untouched — monitoring is a read overlay.

**Regulatory anchors:** POJK 23/2025 Pasal 91 (30/70 placement), IOSCO
Recommendation 12 (custody records: nature/amount/location/ownership), FSB
safeguarding recommendations, FSB & IOSCO Thematic Reviews Oct 2025
(third-party custody concentration gap).

### 2. Wallet Address Audit Script (PR #19)

`prima-backend/audit_wallets.py` — **read-only, flag only**. Motivated by two
real Binance hot wallets found registered under KUST-001/KUST-002 earlier.

- Confirms `wallets` schema via `information_schema` before querying; one
  enumeration query covers both linkage patterns
  (`COALESCE(entity_id, pakd_id::text)`).
- Live balances via the existing `get_total_balance_idr()`, one wallet at a
  time, 1.5 s sleep between calls (free-tier rate limits).
- Flags by **magnitude** (> Rp 100 miliar), not an address blocklist — the
  largest legitimate demo value is Rp 8 miliar.
- Duplicate-row check across every entity type.
- One pooled connection for the whole run; per-wallet fetch errors printed
  inline and skipped; every line `flush=True`.
- **Run it where the app runs** (needs `DATABASE_URL` + chain-API access):
  `DATABASE_URL=... python prima-backend/audit_wallets.py`
- Remediation: flagged ethereum rows get the established placeholder
  (`UPDATE wallets SET address = '0x' || lpad('deadN', 40, '0') WHERE id = <id>;`);
  flagged bitcoin/solana rows need a chain-appropriate placeholder agreed first.

### 3. On-Chain vs Reported Comparison (PR #20 + #21)

Feedback: the Kustodian table (reported values) could not be reconciled by eye
against the Overview (on-chain values).

- Backend: `pakd_compliance[]` rows now carry `pakd_onchain_idr` (that PAKD's
  own on-chain balance, latest snapshot) and `kustodian_onchain_idr`
  (kustodian total, repeated per row — the chain cannot attribute the custody
  pool per PAKD).
- Frontend: each comparison cell stacks two equal-size values with small
  uppercase labels — **DILAPORKAN** above, **ON-CHAIN** below. The on-chain
  line is red **only on negative deviation** (on-chain < reported).
- CSV export includes both on-chain columns.

---

## Key data-semantics note (why the numbers "don't tally")

- Overview *Aset On-Chain PAKD* / *On-Chain Kustodian* = **live blockchain
  balances** (the kustodian figure is one aggregate repeated on every linked
  PAKD's row).
- Kustodian table *AKD Konsumen di PAKD / di PTP* = **self-reported filings**
  (e-reporting or defaults).
- The gap between them is the reconciliation signal, surfaced as the Deviasi
  Kustodian card and the red on-chain lines. With current demo data the gaps
  are extreme because reported values were never calibrated against actual
  wallet balances (known issue, out of scope this session).

## Tests

- +7 tests in `test_kustodian.py` (`TestKustodianMonitoring`): payload
  contract, all four auth-scoping cases, 404, 401. Total: **154 passing**.
- `test_api.py` performs a live Etherscan call at import time — it cannot run
  in sandboxed environments with blocked egress; exclude with
  `--ignore=test_api.py` there.

## Open items / roadmap

1. **Demo data recalibration** — align `REPORTED_VALUES_DEFAULT` /
   e-reporting rows with actual on-chain balances so demo deviations look
   plausible.
2. **Live run of `audit_wallets.py`** against production DB; remediate any
   WARNING rows (ask before inventing BTC/SOL placeholder formats).
3. **`btn-logout` / `user-badge`** stay hidden after login — not root-caused.
4. **Trend chart / historical time series** for kustodian monitoring — Tier 3,
   cut for semifinal.
5. Dependabot reports 1 high-severity vulnerability on the default branch.

## Pull requests

| PR | Content | Status |
|----|---------|--------|
| #18 | Monitoring endpoint + dashboard UI + 7 tests | Merged |
| #19 | `audit_wallets.py` read-only audit script | Merged |
| #20 | On-chain vs reported comparison in table + CSV | Merged |
| #21 | Equal-size comparison lines, red only on negative deviation | Merged |
