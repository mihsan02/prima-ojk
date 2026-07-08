# PRIMA
### Multichain Transparency Monitoring for Digital Financial Assets

![Status](https://img.shields.io/badge/Status-v1.10--semifinal-0A7A4A?style=flat-square)
![Hackathon](https://img.shields.io/badge/DIGDAYA%20X%20Hackathon-2026-1B3A6B?style=flat-square)
![Regulator](https://img.shields.io/badge/Regulator-OJK-003087?style=flat-square)
![Chain](https://img.shields.io/badge/Chain-ETH%20%7C%20BTC%20%7C%20SOL-627EEA?style=flat-square)
![Auth](https://img.shields.io/badge/Auth-Supabase%20JWT-3ECF8E?style=flat-square)
![Backend](https://img.shields.io/badge/Backend-Flask%203.x-000000?style=flat-square)
![Tests](https://img.shields.io/badge/Tests-170%20passing-brightgreen?style=flat-square)

> Prototype MVP · Built for the DIGDAYA X Hackathon 2026 Semifinal · Pusat Inovasi Digital Indonesia (Indonesia Digital Innovation Center)

**[→ View Landing Page](https://prima-ojk.onrender.com/)** · **[→ Repository](https://github.com/mihsan02/prima-ojk)**

> The monitoring dashboard requires the Flask backend. See [Getting Started](#getting-started) for setup instructions.

---

## What Is PRIMA?

PRIMA (Platform Regulasi Inovasi dan Monitoring Aset) is a blockchain-based supervisory technology platform built to help OJK, Indonesia's Financial Services Authority, verify whether licensed digital financial asset traders (PAKD, Pedagang Aset Keuangan Digital) and their custodians (Kustodian) actually hold what they report to hold.

The system reconciles on-chain wallet balances, queried directly from three blockchain networks (Ethereum, Bitcoin, Solana), against the obligations that PAKD and Kustodian entities report to the regulator. Asset prices convert to IDR through a four-tier cascade (CoinMarketCap V2 → CoinGecko Demo → stale cache → hardcoded fallback). Deviations beyond a defined threshold trigger a tiered alert.

Since the DIGDAYA X semifinal build began in June 2026, PRIMA has grown from a single-entity reconciliation tool into a two-sided supervisory system. It now verifies not only what a PAKD holds directly, but also what portion of customer digital financial assets (AKD, Aset Keuangan Digital) sits with a licensed Kustodian, per the placement rule in POJK Nomor 23 Tahun 2025 Pasal 91. Access is role-gated: OJK supervisors, a super admin, and the regulated entities themselves (each scoped to their own data) authenticate through Supabase-backed JWT sessions rather than a single shared token.

PRIMA is positioned as a mandatory minimum baseline of oversight, not a replacement for audit. It fills a gap that periodic reporting cannot: detection lag, dependence on unverified self-reporting, and the absence of a standardized equity resilience stress test.

---

## The Problem

Since January 2025, OJK has supervised digital financial asset trading directly, following the transfer of authority from Bappebti under Law No. 4 of 2023 (UU P2SK). All 25 licensed PAKD, which handled Rp 556.53 trillion in industry transaction value through 2024 (OJK, 2024), are still supervised primarily through periodic, self-submitted reports.

Three structural weaknesses follow from a document-based reporting approach.

**Detection lag.** Monthly reports do not capture daily asset movement. The Zipmex case in July 2022 froze roughly $53 million in Indonesian user assets (Bisnis Indonesia, 2022) without any warning signal reaching the regulator beforehand. A report-based system is not built to catch a liquidity squeeze that develops over days.

**No independent verification.** The regulator has no mechanism to validate asset claims on its own. The entire verification process depends on the integrity of PAKD self-reporting, a structure the FSB (2023) categorizes as insufficient supervisory oversight.

**No standardized equity resilience stress test.** When Bitcoin fell 64% over 2022 (Chainalysis, 2024), OJK had no mechanism to determine how many PAKD were at risk of breaching the minimum equity threshold set by POJK Nomor 23 Tahun 2025.

Regulatory references: POJK Nomor 27 Tahun 2024, POJK Nomor 23 Tahun 2025, OJK's Digital Financial Asset Innovation Roadmap (Peta Jalan IAKD) 2024-2028, FSB (2023), IMF (2023).

---

## Why These Three Chains

PRIMA covers Ethereum, Bitcoin, and Solana natively. That choice is not arbitrary. It is grounded in a classification of every crypto asset registered on PT Central Finansial X (CFX), the exchange operator that maintains Indonesia's official list of tradeable crypto assets under OJK regulation.

The v2 corrected classification (CFX, 19 May 2026, 1,260 registered assets mapped across 44 blockchain networks by primary chain) shows:

| Network | Registered Assets | Share of Total | MVP Coverage |
|---|---|---|---|
| Ethereum | 988 | 78.4% | Yes |
| Solana | 105 | 8.3% | Yes |
| Bitcoin | 28 | 2.2% | Yes |
| BNB Chain | 24 | 1.9% | Phase 2 |
| Cosmos | 23 | 1.8% | Phase 2 |
| TON | 12 | 1.0% | Phase 3 |
| Polkadot | 10 | 0.8% | Phase 3 |
| Tron | 9 | 0.7% | Phase 3 |
| Sui | 7 | 0.6% | Phase 3 |
| 39 other networks | 55 | 4.4% | Not planned |

Three of 44 networks (6.8% of the networks CFX lists) account for 1,121 of 1,260 registered assets, an 89.0% coverage rate. Adding BNB Chain and Cosmos in Phase 2 would raise coverage to 92.7% (1,168 of 1,260). Adding TON and the remaining mid-tier networks in Phase 3 targets 95%+.

Each of the three networks also earns its place on a different dimension, not asset count alone:

| Dimension | Bitcoin | Ethereum | Solana |
|---|---|---|---|
| Global market cap dominance (Q1 2025) | 52-54% | 15-17% | 3-4% |
| Global DeFi TVL share | ~5% (via wrapped) | 55-60% | 4-5% |
| Indonesian trading volume rank (Bappebti, 2023) | #1 | #2 | Top 5 |
| Balance/history API | Blockstream Esplora | Etherscan V2 | Helius RPC |
| Wallet ownership proof | UTXO / P2PKH-P2WPKH signature | EIP-191 personal_sign | Ed25519 challenge |

Bitcoin anchors the coverage in assets under management. Ethereum anchors it in asset count and DeFi liquidity. Solana anchors it in tokenized-equity products (xStocks) that increasingly launch there first. All three appear in POJK Nomor 27 Tahun 2024's regulatory scope.

Source: PT Central Finansial X (CFX), Klasifikasi Aset Kripto Terdaftar per 19 Mei 2026 (internal network-mapping analysis, v2, corrected for 19 xStocks tokens reclassified from Ethereum to Solana).

---

## Why Not an Existing Solution?

Commercial blockchain analytics platforms such as Chainalysis and Nansen offer sophisticated on-chain monitoring. PRIMA does not compete with their technical depth. It solves a different problem.

- **No local regulatory integration.** Commercial platforms have no mapping to OJK's list of licensed PAKD, no POJK-based deviation thresholds, and no alert structure aligned to OJK's supervisory hierarchy.
- **Data sovereignty.** PAKD supervisory data is sensitive regulatory data. Relying on a foreign platform means the asset positions of Indonesia's entire licensed crypto industry sit outside the regulator's own jurisdiction.
- **Cost.** Chainalysis enterprise licensing runs into the hundreds of thousands of dollars per year, not a realistic figure for routine regulator tooling.

PRIMA is designed to run in-house at OJK, with data staying inside the regulator's own infrastructure.

---

## System Architecture

```
                    ┌─────────────────────────────────────┐
                    │        LOGIN (Supabase Auth)         │
                    │  Supervisor | Super Admin | PAKD/Kust │
                    └──────────────┬────────────────────────┘
                                   │ JWT Bearer (ES256)
                    ┌──────────────▼────────────────────────┐
                    │            Flask Backend               │
                    │   Auth middleware (JWT validate,       │
                    │   role + entity-scope injection)       │
                    │                                        │
                    │  ┌──────────┐   ┌───────────────────┐  │
                    │  │ PAKD API │   │  Kustodian API     │  │
                    │  └──────────┘   └───────────────────┘  │
                    │                                        │
                    │  ┌──────────┐   ┌───────────────────┐  │
                    │  │E-Report  │   │ Reconciliation      │  │
                    │  │ Parser   │   │ Engine (30/70)      │  │
                    │  └──────────┘   └───────────────────┘  │
                    │                                        │
                    │  ┌────────────────────────────────────┐│
                    │  │ Wallet Verify (ETH · SOL · BTC)     ││
                    │  └────────────────────────────────────┘│
                    └──────────────┬────────────────────────┘
                                   │
                    ┌──────────────▼────────────────────────┐
                    │        Supabase / PostgreSQL           │
                    │  auth.users + user_profiles            │
                    │  pakd + kustodian + kustodian_pakd      │
                    │  wallets (entity_type, entity_id)      │
                    │  reconciliation_snapshots               │
                    │  laporan_ereporting · audit_log         │
                    └─────────────────────────────────────────┘
```

Data moves through the system on a hybrid schedule. A background job runs every 5 minutes (triggered by cron-job.org against `POST /api/internal/refresh-all`), queries every declared wallet on all three chains, and writes a batch snapshot. Page loads read that snapshot (`GET /api/reconciliation/latest`, typically under one second). A supervisor can also trigger an on-demand recalculation (`POST /api/reconciliation/refresh`), which runs asynchronously and is polled for completion, so a live blockchain query never blocks the browser.

---

## Roles and Access Control

Authentication runs on Supabase Auth (JWT, ES256), validated against a public key supplied through the `SUPABASE_JWT_JWK` environment variable rather than a live JWKS fetch, since outbound calls to auth infrastructure from a cloud IP proved unreliable in testing. Sessions carry a 60-minute idle timeout with activity detection and silent token refresh for active users.

| Role | Scope | Can Write? |
|---|---|---|
| **Super Admin** | All PAKD, all Kustodian, all users | Yes: create/edit/delete PAKD and Kustodian, manage users, upload e-reporting filings, trigger manual reconciliation |
| **Supervisor (Pengawas)** | All PAKD, all Kustodian | No: read-only across the entire portfolio |
| **PAKD / Kustodian** | Own entity only | No: read-only, scoped to the entity's own data (a PAKD user cannot see another PAKD's holdings) |

A PAKD or Kustodian account requesting another entity's data receives a 403, enforced server-side, not just hidden in the interface. The cron-triggered refresh endpoint and one legacy write endpoint (`/api/input-manual`, kept for backward compatibility) still authenticate with a static internal token rather than a user JWT, since no human logs in to run a scheduled job.

---

## Custody Compliance: The 30/70 Placement Rule

POJK Nomor 23 Tahun 2025 Pasal 91 requires that a PAKD place no more than 30% of customer digital financial assets with itself, with at least 70% held at a licensed Kustodian (PTP, Pengelola Tempat Penyimpanan). PRIMA models the Kustodian as its own entity type, linked to one or more PAKD, and reconciles both sides of that split.

**Custody model.** Each Kustodian wallet is dedicated to exactly one PAKD. Balances are not pooled or prorated across every PAKD a Kustodian serves. This mirrors how custodial segregation actually works and replaced an earlier proportional-split model once real production data showed the shared-pool assumption produced misleading per-PAKD figures.

**Dual-track reconciliation.** For every PAKD, PRIMA computes:
1. On-chain balance at the PAKD's own declared wallets, against its 30%-cap obligation.
2. On-chain balance at its dedicated Kustodian wallet(s), against its 70%-floor obligation.
3. An aggregate deviation combining both tracks, plus a placement-ratio check.

A PAKD placing more than 30% of customer assets with itself trips a compliance flag. In the interface this is labeled **Status Penempatan AKD pada Kustodian** (AKD Placement Status at Custodian), matching the terminology used in the official e-reporting schema, rather than the shorthand "30/70."

**Kustodian monitoring dashboard.** Each Kustodian's page shows four summary indicators (Total AKD Under Custody, Expected Balance at PTP, Custodian Deviation, Wallet Verification rate), a compliance table listing every linked PAKD with its own on-chain-versus-reported comparison, a concentration-risk donut chart, and a wallet-level breakdown. A companion read-only script (`audit_wallets.py`) flags any registered wallet whose balance magnitude is inconsistent with demo scale (a Rp 100 billion threshold against a largest legitimate demo value of roughly Rp 8 billion), which is how two real exchange hot-wallet addresses were previously caught in seed data and replaced with placeholders.

**Regulatory anchors:**
- POJK Nomor 23 Tahun 2025, Pasal 91 (customer asset placement ratio).
- IOSCO, *Policy Recommendations for Crypto and Digital Asset Markets* (16 November 2023), Recommendations 12 through 16: Overarching Custody Recommendation, Segregation and Handling of Client Monies and Assets, Disclosure of Custody and Safekeeping Arrangements, Client Asset Reconciliation and Independent Assurance, and Securing Client Money and Assets.
- FSB, *High-Level Recommendations for the Regulation, Supervision and Oversight of Crypto-Asset Activities and Markets* (July 2023).
- FSB, *Thematic Peer Review on the FSB Global Regulatory Framework for Crypto-Asset Activities*, and IOSCO's parallel *Thematic Review on the Implementation of IOSCO's Crypto and Digital Asset Recommendations* (both 16 October 2025), which jointly assessed custody arrangements at crypto-asset service providers across member jurisdictions.

---

## E-Reporting Integration

PRIMA parses the actual government XLSX templates PAKD and Kustodian entities file under POJK Nomor 27 Tahun 2024, rather than a manual re-entry form.

- **PAKD filing:** sheet `LSTAKDKP` (monthly AKD recapitulation, including the split between assets held for customers versus the trader's own proprietary holdings), sheet `LBNP` (balance sheet figures, including total equity), and sheet `LRA` (administrative account, capturing what is held at the PAKD versus at the PTP).
- **Kustodian filing:** sheet `LPWAKD` (wallet register: address, network, and the reported IDR value custodied per wallet).

The flow is upload, parse, preview, and confirm. A super admin uploads the XLSX, the parser returns a structured preview for review, and only on confirmation does the filing become the system's source of "reported" values for reconciliation, replacing what was previously a hand-typed placeholder figure. Each uploaded file is hashed (SHA-256) at parse time.

---

## Wallet Ownership Verification

| Chain | Standard | Library | Coverage |
|---|---|---|---|
| Ethereum | EIP-191 `personal_sign` | `eth-account` | Full |
| Solana | Ed25519 challenge-response | `PyNaCl` + `base58` | Full |
| Bitcoin | BIP-322 (Level 2) | `ecdsa` | P2PKH (legacy) and P2WPKH (SegWit). P2SH and Taproot (P2TR) are not yet supported and return a descriptive error rather than a silent failure. |

Two operating modes exist. **Primary mode**, intended for production, has the PAKD or Kustodian generate a signature independently and submit it to OJK through an official channel, with the supervisor entering it into the dashboard for backend verification, matching the reality that the regulator and the regulated entity are separate parties on separate machines. **Convenience mode** offers in-browser MetaMask signing for ETH, useful for internal sandbox testing and onboarding sessions, but assumes the dashboard operator is the wallet owner, an assumption that does not hold in production.

A Dependabot advisory on the `ecdsa` package (a timing side-channel in `SigningKey.sign_digest()`) was reviewed and dismissed for this codebase: PRIMA only verifies Bitcoin signatures, and a grep of the signature-verification module confirms no call to `SigningKey`, `sign_digest`, or `.sign(` exists anywhere in it.

---

## Audit Trail and Access Logging

Every write action (creating, editing, or deleting a PAKD, a Kustodian, or a user, and every reconciliation run) is logged with the actor's identity, drawn automatically from the JWT rather than passed in by the caller.

Reads of sensitive reconciliation data are logged as well: viewing the latest snapshot or the reconciliation history now records who looked at what, and when. Because the dashboard polls these same endpoints repeatedly, read entries are throttled to one per user per resource per five minutes, so routine polling does not crowd out the audit log's limited entry count. CSV exports are never throttled. Each export is treated as a deliberate act of extracting data from the system, not passive viewing, so every export is logged individually.

The log writes to a Supabase table as the primary store, with a local JSON file as a fallback if the database is unreachable. It does not yet use hash chaining or another tamper-evident structure (see Known Limitations).

---

## Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend | Python 3.11, Flask 3.x, Flask-CORS | Lightweight for an API prototype. CORS is restricted to `ALLOWED_ORIGINS`. |
| Auth | Supabase Auth, PyJWT, `cryptography` | JWT (ES256) validated against a manually constructed EC public key from `SUPABASE_JWT_JWK`, avoiding a live JWKS fetch from a cloud IP |
| External Data | Etherscan API V2, Blockstream Esplora, CoinMarketCap API V2, CoinGecko Demo API, Helius RPC, Jupiter Tokens V2, Jupiter Price V3 | Etherscan: ETH native balance plus curated top-50 ERC-20. Blockstream: BTC UTXO balance. CMC: primary pricing with CoinGecko fallback. Helius: SPL token enumeration via `getTokenAccountsByOwner`. Jupiter: two-gate filter for verified tokens and SPL pricing. |
| Crypto Libraries | `eth-account`, `PyNaCl`, `base58`, `ecdsa` | EIP-191 (ETH), Ed25519 (SOL), and BIP-322 (BTC) signature verification, all without custodial key handling |
| E-Reporting | `openpyxl` | Parses the real POJK 27/2024 government XLSX templates (PAKD and Kustodian) |
| Processing | `requests`, `hmac`, `secrets`, `concurrent.futures` | Deviation calculation, constant-time token comparison (OWASP ASVS V2.10), parallel per-chain fetch with per-wallet timeout degradation |
| Storage | Supabase (`psycopg2`, pool size 1) | Auth, PAKD, Kustodian, reconciliation snapshots, e-reporting filings, and the audit log all persist here |
| Interface | HTML, CSS, JavaScript (vanilla) | A framework-free dashboard that can run inside OJK infrastructure without external build dependencies |
| Infrastructure | Render (Flask deployment, single Gunicorn worker), cron-job.org | cron-job.org triggers `POST /api/internal/refresh-all` every 5 minutes. A single worker keeps in-memory state (rate limiting, job tracking) consistent. |

---

## API Endpoints

### Authentication
| Endpoint | Method | Auth | Function |
|---|---|---|---|
| `/api/auth/login` | POST | - | Exchange email/password for a JWT and user profile |
| `/api/auth/me` | GET | JWT | Return the current authenticated user |
| `/api/auth/refresh` | POST | Refresh token | Rotate an access token without a fresh login |

### PAKD
| Endpoint | Method | Auth | Function |
|---|---|---|---|
| `/api/pakd` | GET | JWT (entity-scoped) | List PAKD entities |
| `/api/pakd` | POST | JWT (super_admin) | Create a PAKD |
| `/api/pakd/<pakd_id>` | PUT | JWT (super_admin) | Update a PAKD |
| `/api/pakd/<pakd_id>` | DELETE | JWT (super_admin) | Delete a PAKD |
| `/api/pakd/<pakd_id>/recalc-snapshot` | POST | JWT | Force a fresh reconciliation snapshot for one PAKD |
| `/api/input-manual` | POST | X-Admin-Token | Legacy manual PAKD entry, kept for backward compatibility |

### Kustodian
| Endpoint | Method | Auth | Function |
|---|---|---|---|
| `/api/kustodian` | GET | JWT (entity-scoped) | List Kustodian entities |
| `/api/kustodian` | POST | JWT (super_admin) | Create a Kustodian, link to PAKD, register wallets |
| `/api/kustodian/<kust_id>` | PUT | JWT (super_admin) | Update a Kustodian |
| `/api/kustodian/<kust_id>` | DELETE | JWT (super_admin) | Delete a Kustodian |
| `/api/kustodian/<kust_id>/monitoring` | GET | JWT (entity-scoped) | Full monitoring payload: KPIs, per-PAKD compliance, wallets |

### Reconciliation
| Endpoint | Method | Auth | Function |
|---|---|---|---|
| `/api/reconciliation` | GET | JWT | Live reconciliation: query every chain, compute deviation. Rate-limited to once per 60 seconds. |
| `/api/reconciliation/latest` | GET | JWT (entity-scoped) | Read the latest Supabase snapshot, typically under 1 second |
| `/api/reconciliation/refresh` | POST | JWT (super_admin) | Trigger an async reconciliation job, returns a `job_id` |
| `/api/reconciliation/refresh/<job_id>` | GET | JWT | Poll job status: done, running, or failed |
| `/api/reconciliation-history` | GET | JWT (entity-scoped) | Snapshot history, filterable by PAKD |

### E-Reporting
| Endpoint | Method | Auth | Function |
|---|---|---|---|
| `/api/upload-ereporting` | POST | JWT (super_admin) | Upload and parse a PAKD or Kustodian XLSX filing, return a preview |
| `/api/confirm-ereporting` | POST | JWT (super_admin) | Confirm and persist a previewed filing |

### Wallet Verification
| Endpoint | Method | Auth | Function |
|---|---|---|---|
| `/api/wallet-challenge` | POST | JWT | Issue a signing challenge (nonce) for a declared wallet |
| `/api/wallet-verify` | POST | JWT | Verify an EIP-191, Ed25519, or BIP-322 signature against the challenge |

### Stress Testing, Audit, and Export
| Endpoint | Method | Auth | Function |
|---|---|---|---|
| `/api/stress-test` | GET | JWT (entity-scoped) | Pasal 50 (market risk) and Pasal 91 (cyber risk) scenarios against a Rp 50 billion minimum equity threshold |
| `/api/audit-log` | GET | JWT | Return the most recent audit log entries, including actor identity |
| `/api/export-csv` | GET | JWT (entity-scoped) | Export reconciliation history for one PAKD |
| `/api/export-csv-overview` | GET | JWT (entity-scoped) | Export the latest snapshot across all PAKD |

### User Management and System
| Endpoint | Method | Auth | Function |
|---|---|---|---|
| `/api/users` | GET | JWT (super_admin) | List user accounts |
| `/api/users` | POST | JWT (super_admin) | Create a user with a role and entity binding |
| `/api/users/<user_id>` | DELETE | JWT (super_admin) | Delete a user |
| `/api/internal/refresh-all` | POST | X-Internal-Token | Cron-triggered batch reconciliation for every PAKD |
| `/` | GET | - | Serve the dashboard |
| `/ping` | GET | - | Health check |
| `/api/status` | GET | - | Service status |

---

## Getting Started

```bash
# 1. Clone the repository
git clone https://github.com/mihsan02/prima-ojk.git
cd prima-ojk/prima-backend

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables
export DATABASE_URL="..."            # Supabase connection string. Required: auth, Kustodian, and
                                      # e-reporting data all live here, not in a JSON fallback.
export SUPABASE_URL="..."            # Your project URL (https://xxxxx.supabase.co), NOT the anon key
export SUPABASE_ANON_KEY="..."
export SUPABASE_JWT_SECRET="..."
export SUPABASE_JWT_JWK="..."        # ES256 public key JSON, from Supabase JWKS
export SUPABASE_SERVICE_ROLE_KEY="..."  # Needed for the user-management admin API
export ETHERSCAN_API_KEY="..."       # Free tier at etherscan.io
export COINMARKETCAP_API_KEY="..."   # Free Basic plan
export SOLANA_RPC_URL="..."          # Helius RPC endpoint (falls back to public mainnet-beta, rate-limited)
export JUPITER_API_KEY="..."         # Optional, improves Jupiter rate limits
export ADMIN_TOKEN="..."             # Legacy write-endpoint token, kept for backward compatibility
export INTERNAL_TOKEN="..."          # Cron-only token for /api/internal/refresh-all
export ALLOWED_ORIGINS="..."         # CORS allowlist, defaults to prima-ojk.onrender.com

# 4. Run Flask
python app.py

# 5. Open the browser
# http://localhost:5000
```

---

## Repository Structure

```
prima-ojk/
├── README.md
├── index.html                       # Static landing page
├── requirements.txt
├── render.yaml                      # Render deployment config
├── prima-backend/
│   ├── app.py                       # Flask server, all 34 API routes
│   ├── auth.py                      # JWT validation, role and entity-scope decorators
│   ├── ereporting_parser.py         # POJK 27/2024 XLSX parser (PAKD + Kustodian)
│   ├── btc_verify.py                # BIP-322 Bitcoin signature verification
│   ├── audit_wallets.py             # Read-only wallet-balance anomaly audit
│   ├── scripts/
│   │   ├── verify_curated_list.py   # Verifies the curated top-50 ERC-20 list
│   │   └── calibrate_demo_data.py   # Derives demo reported values from live on-chain balances
│   ├── demo/
│   │   └── sign_cheatsheet.md       # Reference commands for generating test signatures
│   └── test_*.py                    # Test suite (170 passing, test_api.py needs live network)
├── prima-frontend/
│   └── index.html                   # Full dashboard: login, Overview, Kustodian Monitoring,
│                                     # Per-PAKD Detail, Stress Test, Audit Log, User Management
└── docs/
    ├── arsitektur-sistem.md         # Architecture reference
    ├── keterbatasan-sistem.md       # Documented limitations, updated per sprint
    └── SPRINT_SEMIFINAL_LOG.md      # Sprint-by-sprint build log
```

---

## Development Status

### Authentication and Access Control
| Component | Status |
|---|---|
| Supabase Auth (JWT, ES256) | Done |
| Three roles: Super Admin, Supervisor, PAKD/Kustodian | Done |
| Entity-scoped access on all data endpoints | Done |
| 60-minute idle timeout with token refresh | Done |
| User management UI (Super Admin only) | Done |

### Multichain Reconciliation
| Component | Status |
|---|---|
| ETH native + curated top-50 ERC-20 via Etherscan V2 | Done |
| BTC balance via Blockstream Esplora | Done |
| SOL native + SPL via Helius RPC and Jupiter two-gate filter | Done |
| Four-tier price cascade (CMC → CoinGecko → cache → hardcoded) | Done |
| Background snapshot every 5 minutes plus async manual refresh | Done |
| Partial-result preservation on per-chain timeout | Done |

### Custody Compliance (Kustodian, 30/70)
| Component | Status |
|---|---|
| Kustodian as a distinct entity, linked to PAKD | Done |
| Dedicated wallet-to-PAKD custody model | Done |
| Dual-track reconciliation and placement-ratio compliance badge | Done |
| Kustodian monitoring dashboard (KPIs, compliance table, donut, wallets) | Done |
| Read-only wallet anomaly audit script | Done |
| Demo data calibration against live on-chain balances | In progress |

### E-Reporting and Wallet Verification
| Component | Status |
|---|---|
| PAKD XLSX parser (LSTAKDKP, LBNP, LRA) | Done |
| Kustodian XLSX parser (LPWAKD) | Done |
| Upload, preview, confirm flow | Done |
| Wallet ownership proof: ETH (EIP-191), SOL (Ed25519) | Done |
| Wallet ownership proof: BTC (BIP-322, P2PKH + P2WPKH) | Done |
| Wallet ownership proof: BTC P2SH / Taproot | Not planned this round |

### Audit and Compliance Reporting
| Component | Status |
|---|---|
| Write-action audit log (dual-write, Supabase + JSON fallback) | Done |
| Read-access logging with throttling | Done |
| Untethered export logging | Done |
| Hash-chained, tamper-evident log structure | Open, see Known Limitations |
| Stress test: Pasal 50 (market) and Pasal 91 (cyber), both entity types | Done |
| CSV export (per-PAKD and portfolio overview) | Done |

### Known Open Items
| Item | Notes |
|---|---|
| Logout button and user badge occasionally stay hidden after login | Cosmetic, not root-caused, does not block the demo path |
| Multi-point reconciliation (anti-window-dressing) | Roadmap, post-semifinal |

---

## Known Limitations

PRIMA is built on the principle that a supervisory system that discloses its own limits is more trustworthy than one that claims unproven capabilities. Every limitation below carries a mitigation direction.

**Circular trust.** Wallet verification depends on the address list a PAKD or Kustodian declares to OJK. An undeclared wallet is invisible to the system. Ownership proof (EIP-191, Ed25519, BIP-322) verifies control of a declared wallet, not the completeness of the declared list. Mitigation roadmap: on-site verification at onboarding, with wallet addresses locked once registered.

**Window dressing.** Reconciliation runs on a single snapshot per period, which leaves room for a PAKD to move assets into declared wallets shortly before a scheduled check and move them out afterward. Mitigation roadmap: reconciliation at multiple, undisclosed points within a period.

**Curated ERC-20 coverage.** Ethereum ERC-20 tracking uses a curated list of roughly 50 tokens rather than full enumeration, chosen against CFX's registered asset list, global market cap, and relevance to Indonesian PAKD portfolios. Tokens outside that list are reported as `UNVALUED`, not silently dropped, so a supervisor can see that an unpriced position exists.

**SPL Token-2022 not enumerated.** Helius's `getTokenAccountsByOwner` covers the standard SPL token program only. Tokens issued under the Token-2022 extension program are not currently enumerated.

**Bitcoin signature coverage.** BIP-322 verification supports P2PKH and P2WPKH addresses. P2SH and Taproot (P2TR) addresses are not yet supported and return an explicit error rather than a false pass.

**Audit log integrity.** The audit log is dual-written (Supabase primary, JSON fallback) and now records both write actions and sensitive read access, but it does not yet use hash chaining or another tamper-evident structure.

---

## References

1. OJK. (2024). *POJK Nomor 27 Tahun 2024 tentang Perdagangan Aset Keuangan Digital*.
2. OJK. (2025). *POJK Nomor 23 Tahun 2025 tentang Penyelenggaraan Perdagangan Aset Keuangan Digital*.
3. OJK. (2024). *Peta Jalan Inovasi Aset Keuangan Digital (IAKD) 2024-2028*.
4. Financial Stability Board. (2023, July). *High-Level Recommendations for the Regulation, Supervision and Oversight of Crypto-Asset Activities and Markets*.
5. Financial Stability Board. (2025, October). *Thematic Peer Review on the FSB Global Regulatory Framework for Crypto-Asset Activities*.
6. International Organization of Securities Commissions. (2023, November). *Policy Recommendations for Crypto and Digital Asset Markets*.
7. International Organization of Securities Commissions. (2025, October). *Thematic Review on the Implementation of IOSCO's Crypto and Digital Asset Recommendations*.
8. International Monetary Fund. (2023). *Elements of Effective Policies for Crypto Assets*. IMF Policy Paper.
9. Chainalysis. (2024). *The Chainalysis 2024 Crypto Crime Report*.
10. PwC Switzerland. (2022). *Proof of Reserves: Bridging the Trust Gap in Crypto Exchanges*.
11. PT Central Finansial X. (2026, May 19). *Daftar Aset Kripto Terdaftar* (network classification analysis, v2).
12. Bisnis Indonesia. (2022, July). *Zipmex Bekukan Penarikan Dana Pengguna*. Bisnis.com.
13. OWASP. (2023). *Application Security Verification Standard (ASVS) v4.0.3*, V2.10 Service Authentication.

---

*PRIMA v1.10-semifinal · Built for the DIGDAYA X Hackathon 2026 Semifinal · Pusat Inovasi Digital Indonesia*
