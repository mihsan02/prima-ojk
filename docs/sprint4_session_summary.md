# Sprint 4 Session Summary — Kustodian Monitoring Dashboard

**Date:** 6–7 Juli 2026
**Branch:** `claude/enhanced-sidebar-kustodian-i3e3km` (merged via PR #18–#30)
**Baseline at session start:** post-Sprint-3.5, `a37121e` · 147 tests passing (2 known network-dependent failures: `test_day7_spl_integration.py` test_I3/test_I8)
**Baseline at session end:** `6a14d17` · 162 tests passing (same 2 known failures, network-blocked in sandbox)

This session ran in two phases. **Phase 1** (PR #18–#21) built the Kustodian
monitoring dashboard from the sprint spec. **Phase 2** (PR #22–#30) was a long
iterative debugging arc, driven entirely by the user testing the deployed
dashboard against real Etherscan/Solscan data and reporting mismatches —
each fix uncovered the next layer of the problem.

---

## Phase 1: Kustodian Monitoring Dashboard (PR #18–#21)

Transformed the Kustodian page from a CRUD management tool into a regulatory
monitoring dashboard answering: *is this Kustodian actually holding what it
should, for whom, and is it verifiable?*

### PR #18 — Monitoring endpoint + dashboard UI

**Backend — `GET /api/kustodian/<kust_id>/monitoring`** (`prima-backend/app.py`)
- Single response containing `kustodian`, `summary`, `pakd_compliance[]`, `wallets[]`.
- Auth scoping: `super_admin`/`pengawas` → any kustodian; `pakd` → only linked
  kustodian (403 otherwise); `kustodian` → only own entity.
- Reported values resolved via the existing `_get_reported_values()`
  (`laporan_ereporting` → `REPORTED_VALUES_DEFAULT` fallback) — no duplicated logic.
- `conn=` passed through to all helpers (pool-size-1 deadlock guard).
- No schema changes; all data from existing tables.

**Frontend** (`prima-frontend/index.html`)
- 4 KPI summary cards: Total AKD Under Custody, Ekspektasi di PTP, Deviasi
  Kustodian (color-coded), Verifikasi Wallet.
- "Status Penempatan AKD pada Kustodian · POJK 23/2025 Pasal 91" compliance
  table with COMPLIANT/VIOLATION badges.
- SVG donut: AKD distribution per PAKD (concentration risk).
- Wallet table, client-side CSV export, kustodian selector dropdown.
- CRUD (Tambah/Edit/Hapus) untouched — monitoring is a read overlay.

**Regulatory anchors:** POJK 23/2025 Pasal 91 (30/70 placement), IOSCO
Recommendation 12 (custody records), FSB safeguarding recommendations, FSB &
IOSCO Thematic Reviews Oct 2025 (third-party custody concentration gap).

### PR #19 — Wallet address audit script

`prima-backend/audit_wallets.py` — **read-only, flag only**. Motivated by two
real Binance hot wallets found registered under KUST-001/KUST-002.
- Confirms `wallets` schema via `information_schema` before querying.
- Live balances via the existing `get_total_balance_idr()`, 1.5s sleep between wallets.
- Flags by **magnitude** (> Rp 100 miliar), not an address blocklist.
- Duplicate-row check across every entity type.
- Run where the app runs: `DATABASE_URL=... python prima-backend/audit_wallets.py`

### PR #20 + #21 — On-chain vs reported comparison

The Kustodian table (reported values) couldn't be reconciled by eye against
the Overview (on-chain values).
- `pakd_compliance[]` rows gained `pakd_onchain_idr` and `kustodian_onchain_idr`.
- Comparison cells stack DILAPORKAN above / ON-CHAIN below, equal size, red
  only on negative deviation (PR #21 polish after initial full-red styling).

---

## Phase 2: The custody-model correction arc (PR #22–#30)

Phase 1 shipped with a **shared-pool proration model**: a kustodian's total
wallet balance was split across all linked PAKDs by their reported placement
ratio. Real-world testing against production data invalidated this model and
then surfaced a chain of balance-fetching bugs underneath it.

### PR #22 — Prorate shared kustodian custody (superseded by #26)

First attempt at "one kustodian, many PAKDs" correctness: distribute a
kustodian's on-chain balance across linked PAKDs proportionally to each
PAKD's reported `customer_at_ptp_idr`, instead of mirroring the full balance
onto every row. Also folded in this session's earlier documentation commit
and a `deviasi_with_custody()` helper so deviasi counts the custody share as
part of a PAKD's on-chain assets (previously a compliant 30/70 PAKD always
showed ≈ −70% deviasi).

### PR #23 — Full-consistency deviasi + demo data calibration script

Extended `deviasi_with_custody()` to all four reconciliation code paths
(manual refresh, recalc endpoint, internal refresh, background job), and
added `scripts/calibrate_demo_data.py`: derives `laporan_ereporting` values
from live on-chain balances instead of static guesses. Dry-run by default,
`--apply` to write.

### PR #24 — Wallet edit/remove/add + bubble map + on-chain donut

UI response to "I can't fix a bad wallet without SQL": per-wallet edit/remove
on the Kustodian page, a wallet→PAKD "bubble map" visualization, and the
donut re-based on on-chain distribution.

### PR #25 — Unify donut/bubble distribution source + resilient balance fetch

The donut and bubble map disagreed because they read different data (one
on-chain, one reported). Unified into one `custodyDistribution()` helper.
Root-caused via direct DB queries with the user: **one PAKD's on-chain porsi
snapshotted as 0 while siblings in the same refresh run got real values**,
because a rate-limited chain call silently returns 0 and the kustodian pool
is re-fetched per PAKD. Added `_get_kustodian_onchain_resilient()`: retry
once, then fall back to a 15-minute last-known-good cache.

### PR #26 — Dedicated wallet model (the actual fix)

**User corrected the custody model entirely**: per supervisor guidance, one
kustodian wallet serves **exactly one PAKD** — no sharing, no proration. This
made the proration work in #22/#23/#25 obsolete.
- Implemented via the pre-existing `wallets.pakd_id` column on KUSTODIAN rows
  (no schema change) — previously unused for this entity type.
- `_get_kustodian_data_for_pakd()` now fetches only wallets dedicated to that
  PAKD; the proration helper is deleted.
- Bubble map became a true 1:1 mapping (wallet → its one PAKD at 100%, or
  UNASSIGNED); wallet table gained a "PAKD (Dedicated)" column with a 🔗
  assign action.
- `calibrate_demo_data.py` updated to sum dedicated-wallet balances.

### PR #27 — Isolate dedicated kustodian wallets from PAKD wallet queries

Reusing `pakd_id` for dedication broke two PAKD-side queries that matched on
`pakd_id` alone:
- `load_pakd()` leaked kustodian-dedicated wallets into the PAKD's own wallet
  list (visible as extra chips in Overview — risk of double-counting custody).
- `save_pakd()` ran `DELETE FROM wallets WHERE pakd_id = %s`, which **silently
  destroyed the kustodian's dedication** on any PAKD save.
Both now filter `entity_type = 'KUSTODIAN'` out of PAKD-side queries.

### PR #28, #29, #30 — Three-bug chain behind "funded wallets read Rp 0"

After dedication was wired correctly, two of three dedicated wallets still
read 0 despite the user confirming real balances on Etherscan/Solscan. Three
independent root causes, found one at a time as each fix exposed the next:

1. **PR #28** — a wallet holding *only OKB* valued to 0 because OKB wasn't in
   `ETH_CURATED_TOKENS` (the list of ~50 ERC-20s priced beyond ETH/USDT/USDC).
   Added OKB. Also hardened the Solana SPL pricing block: it ran inside the
   wallet's outer `try`, so an API failure while pricing hundreds of token
   accounts discarded the already-fetched native SOL balance. Pricing now
   degrades to native+tier1 on failure instead of zeroing the wallet.

2. **PR #29** — OKB's *balance* fetch worked but its *price* didn't: curated
   tokens are priced only via CoinGecko's contract-price endpoint, which is
   Cloudflare-throttled from Render's shared IP pool (the documented reason
   BTC/ETH/SOL/USDT/USDC were migrated to CoinMarketCap in an earlier
   sprint). Added a CMC single-asset quote fallback for curated tokens
   (starting with OKB, id 3897).

3. **PR #30** — the remaining zero (Gamma's SOL wallet: 11k native SOL + 406
   SPL token accounts) traced to the chain-harvest **timeout**, not an
   exception: `_proc_sol` appended each wallet's result entry to the shared
   list only *after* token pricing finished, and pricing 290+ mints reliably
   exceeds the ~25s harvest timeout. On timeout, `_harvest_partial()` only
   keeps entries already in the list — so the abandoned worker thread's
   already-fetched native balance was lost entirely. Fixed by appending the
   entry *before* fetching and committing native/USDT/USDC values into it
   immediately after each fetch, so a timeout mid-pricing now degrades to
   native+tier1 instead of discarding everything.

---

## Key data-semantics notes

**Custody model (final, post PR #26):** one kustodian wallet is dedicated to
exactly one PAKD via `wallets.pakd_id` on KUSTODIAN-typed rows. A PAKD's
custody at a kustodian = the full balance of its dedicated wallet(s), no
splitting. Wallets with `pakd_id IS NULL` are unassigned and count toward no
PAKD.

**Why "on-chain" and "dilaporkan" differ by design:** Overview's on-chain
columns are live blockchain balances; the Kustodian table's DILAPORKAN values
are self-reported filings (e-reporting or `REPORTED_VALUES_DEFAULT`). The gap
between them **is** the reconciliation signal (Deviasi cards, red comparison
lines) — not a bug. `calibrate_demo_data.py` exists to make demo data's
reported values track real balances so the gaps look intentional rather than
broken.

**Why a "funded" wallet can still read 0 in this app**, in order of what to
check: (1) is the balance in a token PRIMA doesn't have priced — check
`ETH_CURATED_TOKENS` / SPL unvalued-mint lists; (2) is the price source
reachable from Render — CoinGecko's contract endpoint is CF-throttled there,
CMC is not; (3) does the wallet have so many token accounts that pricing
blows the ~25s chain-harvest timeout — check for `[CHAIN_FETCH] ... timeout`
or `[SPL_PRICE]` lines in the logs.

## Tests

- Regression grew from 147 → 162 passing tests across the session (new
  `TestKustodianMonitoring`, `TestDeviasiWithCustody`, resilience, and
  curated-token-count tests; obsolete proration tests removed in #26).
- `test_api.py` performs a live Etherscan call at import time — cannot run in
  sandboxed environments with blocked egress; excluded with
  `--ignore=test_api.py` there. Not a regression; matches the pre-existing
  2-known-failure baseline in spirit.

## Open items / roadmap

1. **Demo wallet cleanup** — Beta's and Gamma's *own* PAKD wallets (not the
   kustodian-dedicated ones) still hold real third-party balances in the
   tens of trillions of Rupiah (a real exchange hot wallet on ETH, a real
   whale wallet on BTC) — same category as the Binance addresses replaced
   earlier. `audit_wallets.py` will flag them; replace before any public demo.
2. **Run `calibrate_demo_data.py --apply` + a reconciliation refresh** so
   reported values track the now-correct on-chain dedicated-wallet balances.
3. **`btn-logout` / `user-badge`** stay hidden after login — not root-caused,
   out of scope this session.
4. **Trend chart / historical time series** for kustodian monitoring — Tier 3,
   cut for semifinal.
5. Dependabot reports 1 high-severity vulnerability on the default branch.
6. Gamma's dedicated SOL wallet (406 token accounts) will make every
   reconciliation refresh slow and usually land on the timeout-degraded
   native-only value — swap for a quieter address if demo speed matters.

## Pull requests

| PR | Content | Status |
|----|---------|--------|
| #18 | Monitoring endpoint + dashboard UI + 7 tests | Merged |
| #19 | `audit_wallets.py` read-only audit script | Merged |
| #20 | On-chain vs reported comparison in table + CSV | Merged |
| #21 | Equal-size comparison lines, red only on negative deviation | Merged |
| #22 | Prorate shared kustodian custody (superseded by #26) | Merged |
| #23 | Full-consistency deviasi + demo data calibration script | Merged |
| #24 | Wallet edit/remove/add + bubble map + on-chain donut | Merged |
| #25 | Unify donut/bubble distribution source + resilient balance fetch | Merged |
| #26 | Dedicated wallet model (1 kustodian wallet = 1 PAKD) | Merged |
| #27 | Isolate dedicated kustodian wallets from PAKD wallet queries | Merged |
| #28 | OKB curated-token coverage + SPL pricing exception guard | Merged |
| #29 | CMC price fallback for curated OKB (CoinGecko CF-throttled) | Merged |
| #30 | Preserve SOL native+tier1 across harvest timeout | Merged |
