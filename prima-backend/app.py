from flask import Flask, jsonify, request, send_from_directory, make_response, g
from flask_cors import CORS
import requests
import os
import json
import tempfile
import uuid
from datetime import datetime
import re
import time
import functools
import secrets
import hmac
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct

import base58
import nacl.signing
import nacl.exceptions

from ereporting_parser import parse_pakd_ereporting, parse_kustodian_wallet_report

app = Flask(__name__)

# Auth module - import lazy to avoid circular at module level
# (auth.py imports _get_db_conn from app, so we import auth after app is defined)
from auth import (
    require_auth, require_role, require_entity_access,
    require_super_admin_or_token, login_user,
    create_supabase_user, delete_supabase_user, invalidate_user_cache
)

def _error_response(message, detail=None, status_code=400):
    """Format error response yang konsisten di seluruh endpoint."""
    body = {"status": "error", "message": message}
    if detail is not None:
        body["detail"] = str(detail)
    return jsonify(body), status_code

def _safe_uuid(val):
    """Return val if it's a valid UUID string, else None (for UUID columns)."""
    try:
        return str(uuid.UUID(str(val)))
    except (ValueError, AttributeError, TypeError):
        return None
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', 'https://prima-ojk.onrender.com').split(',')
CORS(app, origins=ALLOWED_ORIGINS)

SATOSHI_PER_BTC    = 100_000_000
_last_rekon_time = 0
REKON_COOLDOWN   = 60
LAMPORTS_PER_SOL   = 1_000_000_000
BALANCE_CACHE      = {}
REFRESH_LOCK       = {"running": False, "started_at": None}
JOBS               = {}  # {job_id: {"status": "pending|running|done|failed", "result": None, "created_at": float}}
BALANCE_TTL        = 300  # bumped: cache outlives request duration
_SERVER_START_TIME = time.time()

MAX_BALANCE_CACHE       = 500
MAX_JUPITER_PRICE_CACHE = 300


# ---- Jupiter API constants (Day 16) ----
JUPITER_API_BASE      = "https://api.jup.ag"
JUPITER_API_KEY       = os.environ.get("JUPITER_API_KEY", "")
JUPITER_STRICT_CACHE  = {}     # {"verified_set": (cached_at, set_of_mints)}
JUPITER_PRICE_CACHE   = {}     # {mint: (cached_at, usd_price_or_None)}
JUPITER_STRICT_TTL    = 86_400 # 24h cache for verified token list
JUPITER_PRICE_TTL     = 300    # 5m cache aligned with PRICE_TTL
CHALLENGE_STORE = {}
CHALLENGE_TTL   = 300

SOLANA_RPC_URL = os.environ.get(
    "SOLANA_RPC_URL",
    "https://api.mainnet-beta.solana.com"   # public fallback, rate-limited on cloud IPs
)

ETHERSCAN_API_KEY  = os.environ.get("ETHERSCAN_API_KEY", "")

# T2.5: flag demo, konjungsi wajib -- FLASK_ENV kosong di Render berarti
# disjungsi bersenjata secara default di produksi. Diekstrak jadi fungsi
# supaya test bisa memanggilnya ulang tanpa importlib.reload(app).
def _resolve_demo_force_provider_failure():
    demo_mode = os.environ.get("DEMO_MODE", "").strip().lower() == "true"
    flask_env = os.environ.get("FLASK_ENV", "")
    if demo_mode and flask_env != "production":
        return [
            p.strip() for p in os.environ.get("DEMO_FORCE_PROVIDER_FAILURE", "").split(",")
            if p.strip()
        ]
    return []

# Dibaca sekali ke konstanta modul saat boot, tidak per-request.
DEMO_FORCE_PROVIDER_FAILURE = _resolve_demo_force_provider_failure()

# T1.1 (D1): get_eth_balance dipindah ke core/acquisition.py. Di-import
# sebagai nama global supaya pemanggil lama tetap bekerja tanpa diubah.
from core.acquisition import (  # noqa: E402
    get_eth_balance, fetch_erc20_balance, STABLECOIN_DECIMALS,
)

# T1.2 (D3/D4): kaskade harga pindah ke core/pricing.py. Di-import balik
# sebagai nama global supaya seluruh pemanggil lama -- termasuk tes yang
# mengakses app.PRICE_CACHE -- tetap bekerja tanpa diubah.
from core.pricing import (  # noqa: E402
    PRICE_CACHE, PRICE_TTL, MAX_PRICE_CACHE, FALLBACK_STABLECOIN_IDR,
    CMC_ID_TO_CGKEY, _evict_stale_entries, get_cached_price,
    _refresh_price_cache_from_cmc, get_eth_price_idr,
    get_eth_price_with_provenance, get_price_with_provenance,
    fetch_stablecoin_prices_idr, _get_stablecoin_prices_idr,
    fetch_btc_price_idr, fetch_sol_price_idr, _get_usd_idr_rate,
)
from core.completeness import hitung_kelengkapan  # noqa: E402
from core.verdict import tetapkan_verdict_ternary, tetapkan_verdict_surplus  # noqa: E402

DATA_FILE          = os.path.join(os.path.dirname(__file__), "pakd_data.json")
# T3.1: write_audit, verify_chain, VERSI_PERHITUNGAN pindah ke audit.py.
# AUDIT_FILE TETAP di sini (bukan impor) -- test_audit_access.py mem-patch
# app.AUDIT_FILE langsung, dan write_audit membaca lewat deferred import
# supaya patch itu benar-benar terlihat, bukan ikatan beku dari re-export.
AUDIT_FILE = os.path.join(os.path.dirname(__file__), "audit_log.json")
from audit import write_audit, verify_chain, VERSI_PERHITUNGAN  # noqa: E402,F401

# ---------------------------------------------------------------------------
# ERC-20 contract constants (Day 4)
# USDT: Tether USD — 6 decimals
# USDC: USD Coin   — 6 decimals
# Source: Etherscan token tracker, verified contracts on Ethereum mainnet
# ---------------------------------------------------------------------------
USDT_CONTRACT      = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
USDC_CONTRACT      = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

# ---------------------------------------------------------------------------
# Day 17: Curated ETH ERC-20 enumeration list (top-50)
# ---------------------------------------------------------------------------
# Verified 12 Mei 2026 via scripts/verify_curated_list.py:
#   All 50 contracts return valid Etherscan V2 tokenbalance + active
#   CoinGecko price feed (platform=ethereum).
# Excluded:
#   - MATIC (migrated to POL Sep 2024, see POL slot 7)
#   - ARB (tracked primarily on arbitrum-one CG platform)
#   - OP (Optimism L2 native, no canonical mainnet contract)
# ---------------------------------------------------------------------------

ETH_CURATED_TOKENS = [
    {"symbol": "OKB",    "contract": "0x75231F58b43240C9718Dd58B4967c5114342a86c", "decimals": 18},
    {"symbol": "WBTC",   "contract": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "decimals": 8},
    {"symbol": "LINK",   "contract": "0x514910771AF9Ca656af840dff83E8264EcF986CA", "decimals": 18},
    {"symbol": "UNI",    "contract": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984", "decimals": 18},
    {"symbol": "AAVE",   "contract": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9", "decimals": 18},
    {"symbol": "SHIB",   "contract": "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE", "decimals": 18},
    {"symbol": "PEPE",   "contract": "0x6982508145454Ce325dDbE47a25d4ec3d2311933", "decimals": 18},
    {"symbol": "POL",    "contract": "0x455e53CBB86018Ac2B8092FdCd39d8444aFFC3F6", "decimals": 18},
    {"symbol": "BLUR",   "contract": "0x5283D291DBCF85356A21bA090E6db59121208b44", "decimals": 18},
    {"symbol": "MKR",    "contract": "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2", "decimals": 18},
    {"symbol": "LDO",    "contract": "0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32", "decimals": 18},
    {"symbol": "CRV",    "contract": "0xD533a949740bb3306d119CC777fa900bA034cd52", "decimals": 18},
    {"symbol": "SAND",   "contract": "0x3845badAde8e6dFF049820680d1F14bD3903a5d0", "decimals": 18},
    {"symbol": "MANA",   "contract": "0x0F5D2fB29fb7d3CFeE444a200298f468908cC942", "decimals": 18},
    {"symbol": "APE",    "contract": "0x4d224452801ACEd8B2F0aebE155379bb5D594381", "decimals": 18},
    {"symbol": "GRT",    "contract": "0xc944E90C64B2c07662A292be6244BDf05Cda44a7", "decimals": 18},
    {"symbol": "LRC",    "contract": "0xBBbbCA6A901c926F240b89EacB641d8Aec7AEafD", "decimals": 18},
    {"symbol": "1INCH",  "contract": "0x111111111117dC0aa78b770fA6A738034120C302", "decimals": 18},
    {"symbol": "COMP",   "contract": "0xc00e94Cb662C3520282E6f5717214004A7f26888", "decimals": 18},
    {"symbol": "SNX",    "contract": "0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6F", "decimals": 18},
    {"symbol": "RNDR",   "contract": "0x6De037ef9aD2725EB40118Bb1702EBb27e4Aeb24", "decimals": 18},
    {"symbol": "FLOKI",  "contract": "0xcf0C122c6b73ff809C693DB761e7BaeBe62b6a2E", "decimals": 9},
    {"symbol": "INJ",    "contract": "0xe28b3B32B6c345A34Ff64674606124Dd5Aceca30", "decimals": 18},
    {"symbol": "IMX",    "contract": "0xF57e7e7C23978C3cAEC3C3548E3D615c346e79fF", "decimals": 18},
    {"symbol": "AXS",    "contract": "0xBB0E17EF65F82Ab018d8EDd776e8DD940327B28b", "decimals": 18},
    {"symbol": "CHZ",    "contract": "0x3506424F91fD33084466F402d5D97f05F8e3b4AF", "decimals": 18},
    {"symbol": "GALA",   "contract": "0xd1d2Eb1B1e90B638588728b4130137D262C87cae", "decimals": 8},
    {"symbol": "ENS",    "contract": "0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72", "decimals": 18},
    {"symbol": "DYDX",   "contract": "0x92D6C1e31e14520e676a687F0a93788B716BEff5", "decimals": 18},
    {"symbol": "BAT",    "contract": "0x0D8775F648430679A709E98d2b0Cb6250d2887EF", "decimals": 18},
    {"symbol": "ZRX",    "contract": "0xE41d2489571d322189246DaFA5ebDe1F4699F498", "decimals": 18},
    {"symbol": "ENJ",    "contract": "0xF629cBd94d3791C9250152BD8dfBDF380E2a3B9c", "decimals": 18},
    {"symbol": "YFI",    "contract": "0x0bc529c00C6401aEF6D220BE8C6Ea1667F6Ad93e", "decimals": 18},
    {"symbol": "BAL",    "contract": "0xba100000625a3754423978a60c9317c58a424e3D", "decimals": 18},
    {"symbol": "SUSHI",  "contract": "0x6B3595068778DD592e39A122f4f5a5cF09C90fE2", "decimals": 18},
    {"symbol": "OCEAN",  "contract": "0x967da4048cD07aB37855c090aAF366e4ce1b9F48", "decimals": 18},
    {"symbol": "FET",    "contract": "0xaea46A60368A7bD060eec7DF8CBa43b7EF41Ad85", "decimals": 18},
    {"symbol": "RPL",    "contract": "0xD33526068D116cE69F19A9ee46F0bd304F21A51f", "decimals": 18},
    {"symbol": "FXS",    "contract": "0x3432B6A60D23Ca0dFCa7761B7ab56459D9C964D0", "decimals": 18},
    {"symbol": "STG",    "contract": "0xAf5191B0De278C7286d6C7CC6ab6BB8A73bA2Cd6", "decimals": 18},
    {"symbol": "PENDLE", "contract": "0x808507121B80c02388fAd14726482e061B8da827", "decimals": 18},
    {"symbol": "METIS",  "contract": "0x9E32b13ce7f2E80A01932B42553652E053D6ed8e", "decimals": 18},
    {"symbol": "BNT",    "contract": "0x1F573D6Fb3F13d689FF844B4cE37794d79a7FF1C", "decimals": 18},
    {"symbol": "RLB",    "contract": "0x046EeE2cc3188071C02BfC1745A6b17c656e3f3d", "decimals": 18},
    {"symbol": "TUSD",   "contract": "0x0000000000085d4780B73119b644AE5ecd22b376", "decimals": 18},
    {"symbol": "DAI",    "contract": "0x6B175474E89094C44Da98b954EedeAC495271d0F", "decimals": 18},
    {"symbol": "LUSD",   "contract": "0x5f98805A4E8be255a32880FDeC7F6728C6568bA0", "decimals": 18},
    {"symbol": "FRAX",   "contract": "0x853d955aCEf822Db058eb8505911ED77F175b99e", "decimals": 18},
    {"symbol": "ONDO",   "contract": "0xfAbA6f8e4a5E8Ab82F62fe7C39859FA577269BE3", "decimals": 18},
    {"symbol": "LPT",    "contract": "0x58b6A8A3302369DAEc383334672404Ee733aB239", "decimals": 18},
    {"symbol": "NMR",    "contract": "0x1776e1F26f98b1A5dF9cD347953a26dd3Cb46671", "decimals": 18},
]

COINGECKO_TOKEN_CACHE = {}
COINGECKO_TOKEN_CACHE_TS = 0
COINGECKO_TOKEN_CACHE_TTL = 300

USDT_MINT_SOL = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
USDC_MINT_SOL = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_NATIVE_SENTINEL  = "So11111111111111111111111111111111111111112"  # wrapped SOL mint
SPL_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"  # standard SPL, NOT Token-2022


# ---------------------------------------------------------------------------
# Regulatory thresholds and stress test scenarios
# ---------------------------------------------------------------------------

# Source: POJK No. 27 Tahun 2024, Pasal 50 ayat (1) huruf o
# "mempertahankan ekuitas paling sedikit Rp50.000.000.000,00"
EQUITY_MINIMUM_IDR = 50_000_000_000

# Pasal 50 (Risiko Pasar) — price drop applied to volatile and stable assets.
# Volatile basis: BTC -64% in 2022 (Chainalysis Crypto Crime Report 2024);
#                 BTC -84% from Nov 2017 ATH to Dec 2018 (CoinMarketCap historical).
# Stablecoin basis: USDC depeg to USD 0.87 on 11 Mar 2023 / SVB collapse (Reuters).
SKENARIO_PASAL50 = {
    "mild":     {"label": "Mild (-25%)",     "volatile_drop": 0.25, "stable_drop": 0.03},
    "moderate": {"label": "Moderate (-50%)", "volatile_drop": 0.50, "stable_drop": 0.08},
    "severe":   {"label": "Severe (-80%)",   "volatile_drop": 0.80, "stable_drop": 0.13},
}

# Pasal 91 (Risiko Siber) — % of AKD lost to cyber incident.
# Source: GDAC Apr 2023 -23% (BeInCrypto / Chainalysis 2024);
#         WazirX Jul 2024 -50% (Elliptic / Reuters Jul 2024);
#         Mt Gox 2014 -100% customer AKD (public record).
SKENARIO_PASAL91 = {
    "mild":     {"label": "Mild (-23%)",     "loss": 0.23},
    "moderate": {"label": "Moderate (-50%)", "loss": 0.50},
    "severe":   {"label": "Severe (-100%)",  "loss": 1.00},
}

WALLET_RE = {
    "ethereum": re.compile(r"^0x[0-9a-fA-F]{40}$"),
    "bitcoin":  re.compile(r"^(bc1[a-zA-Z0-9]{6,87}|[13][a-km-zA-HJ-NP-Z0-9]{25,34})$"),
    "solana":   re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$"),
}
SUPPORTED_NETWORKS = set(WALLET_RE.keys())

PAKD_DEFAULT = [
    {
        "id":   "PAKD-DEMO-001",
        "nama": "Alpha Kripto Nusantara",
        "wallets": [
            {"network": "ethereum", "address": "0xB6da511B4550B440415f8c640E986Ec41d9020C0", "verified": True,  "verified_at": "2026-05-21T06:00:00Z"},
            {"network": "bitcoin",  "address": "bc1pcjpx4xd6lje4drllupg54tmzetvth48gwvwarzk939hlw229xzyqtmn33q",         "verified": False, "verified_at": None},
            {"network": "solana",   "address": "H13V5d2YdEvL9172K4jH5xfD7tGJN7UqEBR8y5Tb15B1", "verified": False, "verified_at": None},
        ],
        "aset_dilaporkan": 70_000_000,
        "equity_idr": None,
        "persediaan_akd_idr": None,
        "simpanan_pedagang_akd_idr": None,
        "customer_akd_idr": None,
    },
    {
        "id":   "PAKD-OJK-001",
        "nama": "Beta Aset Digital",
        "wallets": [
            {"network": "ethereum", "address": "0x28C6c06298d514Db089934071355E5743bf21d60", "verified": False, "verified_at": None},
            {"network": "bitcoin",  "address": "bc1qy3dvzw3rm9zxyzdhfjh6auv833gu4y4pahcanf",        "verified": False, "verified_at": None},
            {"network": "solana",   "address": "H13V5d2YdEvL9172K4jH5xfD7tGJN7UqEBR8y5Tb15B1", "verified": False, "verified_at": None},
        ],
        "aset_dilaporkan": 4_500_000_000_000,
        "equity_idr": None,
        "persediaan_akd_idr": None,
        "simpanan_pedagang_akd_idr": None,
        "customer_akd_idr": None,
    },
    {
        "id":   "PAKD-OJK-002",
        "nama": "Gamma Perdagangan Kripto",
        "wallets": [
            {"network": "ethereum", "address": "0x71660c4005BA85c37ccec55d0C4493E66Fe775d3", "verified": False, "verified_at": None},
            {"network": "bitcoin",  "address": "bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h",        "verified": False, "verified_at": None},
            {"network": "solana",   "address": "H13V5d2YdEvL9172K4jH5xfD7tGJN7UqEBR8y5Tb15B1", "verified": False, "verified_at": None},
        ],
        "aset_dilaporkan": 1_200_000_000_000,
        "equity_idr": None,
        "persediaan_akd_idr": None,
        "simpanan_pedagang_akd_idr": None,
        "customer_akd_idr": None,
    },
    {
        "id":   "PAKD-OJK-003",
        "nama": "Delta Exchange Digital",
        "wallets": [
            {"network": "ethereum", "address": "0x2910543Af39abA0CD09dBb2D50200b3E800A63D2", "verified": False, "verified_at": None},
            {"network": "bitcoin",  "address": "bc1qewn3pue4jjryur6wmwj7vmcajj0vcexdahgsr0",        "verified": False, "verified_at": None},
            {"network": "solana",   "address": "H13V5d2YdEvL9172K4jH5xfD7tGJN7UqEBR8y5Tb15B1", "verified": False, "verified_at": None},
        ],
        "aset_dilaporkan": 99_000_000,
        "equity_idr": None,
        "persediaan_akd_idr": None,
        "simpanan_pedagang_akd_idr": None,
        "customer_akd_idr": None,
    },
    {
        "id":   "PAKD-OJK-004",
        "nama": "Epsilon Kripto Nusantara",
        "wallets": [
            {"network": "ethereum", "address": "0x71660c4005BA85c37ccec55d0C4493E66Fe775d3", "verified": True,  "verified_at": "2026-05-20T10:00:00Z"},
            {"network": "bitcoin",  "address": "1K5WjXwZY8Mn58EpFJewGL17Dj7QXyTzJQ",        "verified": False, "verified_at": None},
            {"network": "solana",   "address": "H13V5d2YdEvL9172K4jH5xfD7tGJN7UqEBR8y5Tb15B1", "verified": True,  "verified_at": "2026-05-20T10:05:00Z"},
        ],
        "aset_dilaporkan": 400_000_000,
        "equity_idr": None,
        "persediaan_akd_idr": None,
        "simpanan_pedagang_akd_idr": None,
        "customer_akd_idr": None,
    },
]

KUSTODIAN_DEFAULT = [
    {
        "id": "KUST-001",
        "nama": "PT Kustodian Aset Prima",
        "pakd_ids": ["PAKD-DEMO-001", "PAKD-OJK-001", "PAKD-OJK-002"],
        "wallets": [
            {"network": "ethereum", "address": "0xDFd5293D8e347dFe59E90eFd55b2956a1343963d", "verified": False, "verified_at": None},
            {"network": "solana",   "address": "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", "verified": False, "verified_at": None},
        ]
    },
    {
        "id": "KUST-002",
        "nama": "PT Simpan Digital Nusantara",
        "pakd_ids": ["PAKD-OJK-003", "PAKD-OJK-004"],
        "wallets": [
            {"network": "ethereum", "address": "0x5a52E96BAcdaBb82fd05763E25335261B270Efcb", "verified": False, "verified_at": None},
            {"network": "bitcoin",  "address": "bc1q0cgwerdvvnxnwlpzmfet2gq80flrsdnkhqhp6e", "verified": False, "verified_at": None},
        ]
    }
]

REPORTED_VALUES_DEFAULT = {
    "PAKD-DEMO-001": {"customer_at_pakd_idr": 3_000_000_000, "customer_at_ptp_idr": 7_000_000_000, "proprietary_idr": 1_000_000_000},
    "PAKD-OJK-001":  {"customer_at_pakd_idr": 2_000_000_000, "customer_at_ptp_idr": 8_000_000_000, "proprietary_idr": 500_000_000},
    "PAKD-OJK-002":  {"customer_at_pakd_idr": 5_000_000_000, "customer_at_ptp_idr": 3_000_000_000, "proprietary_idr": 400_000_000},
    "PAKD-OJK-003":  {"customer_at_pakd_idr": 1_500_000_000, "customer_at_ptp_idr": 6_000_000_000, "proprietary_idr": 300_000_000},
    "PAKD-OJK-004":  {"customer_at_pakd_idr": 1_000_000_000, "customer_at_ptp_idr": 4_000_000_000, "proprietary_idr": 200_000_000},
}


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _normalize_wallet_entry(w, default_network="ethereum"):
    if isinstance(w, str):
        return {"network": default_network, "address": w, "verified": False, "verified_at": None}
    if isinstance(w, dict):
        return {
            "network":     w.get("network", default_network),
            "address":     w.get("address", ""),
            "verified":    w.get("verified", False),
            "verified_at": w.get("verified_at", None),
        }
    return None


def _migrate_record(p):
    p = dict(p)
    if "pakd_id" in p and "id" not in p:
        p["id"] = p.pop("pakd_id")
    if "nama_pakd" in p and "nama" not in p:
        p["nama"] = p.pop("nama_pakd")
    if "aset_dilaporkan_idr" in p and "aset_dilaporkan" not in p:
        p["aset_dilaporkan"] = p.pop("aset_dilaporkan_idr")
    if "eth_wallet" in p and "wallets" not in p:
        eth_addr = p.pop("eth_wallet")
        p["wallets"] = [{"network": "ethereum", "address": eth_addr, "verified": False, "verified_at": None}]
        return p
    if "wallets" in p and isinstance(p["wallets"], list):
        normalized = []
        for w in p["wallets"]:
            entry = _normalize_wallet_entry(w, default_network="ethereum")
            if entry:
                normalized.append(entry)
        p["wallets"] = normalized
    p.setdefault("equity_idr", None)
    p.setdefault("persediaan_akd_idr", None)
    p.setdefault("simpanan_pedagang_akd_idr", None)
    p.setdefault("customer_akd_idr", None)
    return p

_DB_POOL = None

def _init_db_pool():
    global _DB_POOL
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return None
    try:
        import psycopg2.pool
        _DB_POOL = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=5, dsn=db_url, connect_timeout=5
        )
        return _DB_POOL
    except Exception as e:
        print(f"[DB_POOL] init failed: {type(e).__name__}: {e}", flush=True)
        return None

def _get_db_conn():
    global _DB_POOL
    pool = _DB_POOL or _init_db_pool()
    if not pool:
        return None
    try:
        return pool.getconn()
    except Exception as e:
        print(f"[DB_POOL] getconn failed: {type(e).__name__}: {e}", flush=True)
        return None

def _return_db_conn(conn):
    global _DB_POOL
    if _DB_POOL and conn:
        try:
            _DB_POOL.putconn(conn)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass


def _row_for_snapshot(h, harga_fallback):
    return (h["id"], h["nama"], int(h["aset_dilaporkan_idr"]), int(h["aset_onchain_idr"]),
            (None if h["deviasi_pct"] is None else max(-9999.9999, min(9999.9999, float(h["deviasi_pct"])))), h["status"], harga_fallback, json.dumps(h["breakdown"]),
            h.get("pakd_onchain_idr"), h.get("kustodian_onchain_idr"),
            h.get("compliance_30_70"), h.get("ratio_at_pakd"), h.get("ratio_at_ptp"),
            h.get("kelengkapan_status"),
            json.dumps(h["sumber_gagal"]) if h.get("sumber_gagal") is not None else None,
            json.dumps(h["provenance_harga"]) if h.get("provenance_harga") is not None else None,
            h.get("aset_onchain_idr_final"), h.get("subtotal_diketahui_idr"))


_SNAPSHOT_INSERT_SQL = """INSERT INTO reconciliation_snapshots
       (pakd_id, pakd_nama, aset_dilaporkan_idr, aset_onchain_idr,
        deviasi_persen, status, harga_fallback, network_breakdown,
        pakd_onchain_idr, kustodian_onchain_idr, compliance_30_70, ratio_at_pakd, ratio_at_ptp,
        kelengkapan_status, sumber_gagal, provenance_harga,
        aset_onchain_idr_final, subtotal_diketahui_idr)
       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""


def _save_snapshots_batch(hasil_list, harga_fallback):
    """D53 (Opsi C): coba batch dulu (jalur cepat, satu round-trip).
    Kalau gagal, fallback per-baris -- commit tiap baris sukses, rollback
    SETELAH baris gagal (wajib: transaksi Postgres aborted tanpa rollback
    akan menjatuhkan baris berikutnya juga meski datanya benar).
    Mengembalikan {"saved": [pakd_id,...], "failed": [{"pakd_id","error"},...]}
    supaya kegagalan terlihat eksplisit, bukan cuma print ke log Render.
    """
    conn = _get_db_conn()
    if not conn:
        return {"saved": [], "failed": [
            {"pakd_id": h["id"], "error": "no_db_connection"} for h in hasil_list
        ]}
    result = {"saved": [], "failed": []}
    try:
        cur = conn.cursor()
        rows = [_row_for_snapshot(h, harga_fallback) for h in hasil_list]
        try:
            cur.executemany(_SNAPSHOT_INSERT_SQL, rows)
            conn.commit()
            result["saved"] = [h["id"] for h in hasil_list]
            print(f"[BATCH_SAVE] saved {len(rows)} snapshots", flush=True)
        except Exception as _batch_e:
            print(f'[BATCH_SAVE] batch failed, falling back per-row: '
                  f'{type(_batch_e).__name__}: {_batch_e}', flush=True)
            for h, row in zip(hasil_list, rows):
                try:
                    cur.execute(_SNAPSHOT_INSERT_SQL, row)
                    conn.commit()
                    result["saved"].append(h["id"])
                except Exception as _row_e:
                    conn.rollback()
                    result["failed"].append({
                        "pakd_id": h["id"],
                        "error": f"{type(_row_e).__name__}: {_row_e}",
                    })
                    print(f'[BATCH_SAVE] ERROR pakd_id={h["id"]}: '
                          f'{type(_row_e).__name__}: {_row_e}', flush=True)
    finally:
        _return_db_conn(conn)
    return result


def load_pakd():
    conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, nama, aset_dilaporkan, equity_idr, persediaan_akd_idr, simpanan_pedagang_akd_idr, customer_akd_idr FROM pakd ORDER BY id")
            pakd_rows = cur.fetchall()
            if not pakd_rows:
                cur.close()
                _return_db_conn(conn)
                return []
            pakd_ids = [row[0] for row in pakd_rows]
            # Exclude KUSTODIAN rows: dedicated kustodian wallets carry pakd_id
            # but belong to the kustodian, not the PAKD's own wallet list.
            cur.execute("""SELECT pakd_id, network, address, verified, verified_at FROM wallets
                           WHERE pakd_id = ANY(%s) AND (entity_type IS NULL OR entity_type = 'PAKD')
                           ORDER BY pakd_id""", (pakd_ids,))
            wallet_rows = cur.fetchall()
            cur.close()
            _return_db_conn(conn)
            from collections import defaultdict
            wallets_by_pakd = defaultdict(list)
            for w in wallet_rows:
                wallets_by_pakd[w[0]].append({
                    "network": w[1], "address": w[2],
                    "verified": w[3],
                    "verified_at": str(w[4]) if w[4] else None
                })
            result = []
            for row in pakd_rows:
                result.append({
                    "id": row[0], "nama": row[1],
                    "aset_dilaporkan": row[2] or 0,
                    "equity_idr": row[3], "persediaan_akd_idr": row[4],
                    "simpanan_pedagang_akd_idr": row[5], "customer_akd_idr": row[6],
                    "wallets": wallets_by_pakd.get(row[0], [])
                })
            if result:
                return result
        except Exception as e:
            print(f"[DB] load_pakd failed: {e}", flush=True)
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
            if data:
                return [_migrate_record(p) for p in data]
    except Exception as e:
        print(f"[AUDIT] failed: {type(e).__name__}: {e}", flush=True)
    print("[DB] load_pakd: all sources failed, returning empty list", flush=True)
    return []


def save_pakd(data):
    conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            for pakd in data:
                cur.execute("""
                    INSERT INTO pakd (id, nama, aset_dilaporkan, equity_idr, persediaan_akd_idr, simpanan_pedagang_akd_idr, customer_akd_idr)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        nama = EXCLUDED.nama,
                        aset_dilaporkan = EXCLUDED.aset_dilaporkan,
                        equity_idr = EXCLUDED.equity_idr,
                        persediaan_akd_idr = EXCLUDED.persediaan_akd_idr,
                        simpanan_pedagang_akd_idr = EXCLUDED.simpanan_pedagang_akd_idr,
                        customer_akd_idr = EXCLUDED.customer_akd_idr
                """, (pakd["id"], pakd["nama"], pakd.get("aset_dilaporkan", 0),
                      pakd.get("equity_idr"), pakd.get("persediaan_akd_idr"),
                      pakd.get("simpanan_pedagang_akd_idr"), pakd.get("customer_akd_idr")))
                # Never touch KUSTODIAN rows: dedicated kustodian wallets share
                # pakd_id but are owned by the kustodian entity.
                cur.execute("DELETE FROM wallets WHERE pakd_id = %s AND (entity_type IS NULL OR entity_type = 'PAKD')", (pakd["id"],))
                for w in pakd.get("wallets", []):
                    cur.execute("""
                        INSERT INTO wallets (pakd_id, network, address, verified, verified_at)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (pakd["id"], w["network"], w["address"], w.get("verified", False), w.get("verified_at")))
            conn.commit()
            cur.close()
            _return_db_conn(conn)
            return
        except Exception as e:
            print(f"[DB] save_pakd failed: {e}", flush=True)
    dir_ = os.path.dirname(DATA_FILE) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, DATA_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

def _current_actor():
    """Ambil identitas user dari request context (jika ada) untuk audit trail.
    Return {"email": ..., "role": ...} atau None (mis. dipanggil dari background job).
    """
    try:
        user = getattr(g, "current_user", None)
    except RuntimeError:
        return None
    if not user:
        return None
    return {
        "email": user.get("email") or user.get("id") or "",
        "role": user.get("role") or "",
    }


# T3.1: write_audit dipindah ke audit.py (diimpor di atas). Lihat audit.py untuk implementasi rantai hash.
_ACCESS_LOG_SEEN  = {}    # {(user_id, resource): last_logged_epoch}
ACCESS_LOG_WINDOW = 300   # detik — akses berulang oleh user yang sama dalam window ini tidak dicatat ulang


def log_data_access(resource, extra=""):
    """Catat siapa mengakses data rekonsiliasi dan kapan (audit read-access).

    Dashboard melakukan polling, jadi akses berulang oleh user yang sama ke
    resource yang sama dalam ACCESS_LOG_WINDOW hanya dicatat sekali agar
    audit log tidak banjir.
    """
    actor = _current_actor()
    if not actor:
        return
    try:
        user_id = g.current_user.get("id")
    except RuntimeError:
        return
    key = (user_id, resource)
    now = time.time()
    if now - _ACCESS_LOG_SEEN.get(key, 0) < ACCESS_LOG_WINDOW:
        return
    _ACCESS_LOG_SEEN[key] = now
    who = actor["email"]
    role = actor["role"]
    detail = f"{who} ({role}) mengakses {resource}"
    if extra:
        detail += f" — {extra}"
    write_audit("AKSES DATA", detail, actor=actor)


def _check_wallet_uniqueness(wallets, pakd_id, existing_pakd_list):
    """Periksa apakah wallet address sudah terdaftar di PAKD lain."""
    for w in wallets:
        addr_lc = w.get("address", "").lower()
        net = w.get("network", "")
        if not addr_lc:
            continue
        for other in existing_pakd_list:
            if other["id"] == pakd_id:
                continue
            for ow in other.get("wallets", []):
                if ow.get("address", "").lower() == addr_lc and ow.get("network") == net:
                    return False, (
                        f"Wallet {w['address']} ({net}) sudah terdaftar "
                        f"pada PAKD {other['id']} ({other['nama']}). "
                        f"Satu wallet hanya boleh dimiliki satu PAKD."
                    )
    return True, None

def validate_wallet_address(network, address):
    if network not in SUPPORTED_NETWORKS:
        return False, f"Network '{network}' tidak didukung. Pilih: {', '.join(sorted(SUPPORTED_NETWORKS))}"
    if not WALLET_RE[network].match(address):
        return False, f"Alamat '{address}' tidak valid untuk network {network}"
    return True, None


# ---------------------------------------------------------------------------
# 30/70 Kustodian reconciliation helpers
# ---------------------------------------------------------------------------

def _get_kustodian_data_for_pakd(pakd_id, conn=None):
    """Fetch linked kustodian IDs and the wallets DEDICATED to this PAKD.

    Custody model (supervisor guidance): one kustodian wallet serves exactly
    one PAKD (wallets.pakd_id on the KUSTODIAN row). Wallets with pakd_id
    NULL are unassigned and count toward no PAKD.
    """
    own_conn = conn is None
    if own_conn:
        conn = _get_db_conn()
    if not conn:
        return [], []
    try:
        cur = conn.cursor()
        cur.execute("SELECT kustodian_id FROM kustodian_pakd WHERE pakd_id = %s", (pakd_id,))
        kust_ids = [r[0] for r in cur.fetchall()]
        if not kust_ids:
            cur.close()
            if own_conn:
                _return_db_conn(conn)
            return [], []
        cur.execute("""
            SELECT entity_id, network, address, verified, verified_at
            FROM wallets
            WHERE entity_type = 'KUSTODIAN' AND entity_id = ANY(%s) AND pakd_id = %s
        """, (kust_ids, pakd_id))
        wallet_rows = cur.fetchall()
        cur.close()
        if own_conn:
            _return_db_conn(conn)
        from collections import defaultdict
        wallets_by_kust = defaultdict(list)
        for w in wallet_rows:
            wallets_by_kust[w[0]].append({
                "network": w[1], "address": w[2],
                "verified": w[3], "verified_at": str(w[4]) if w[4] else None
            })
        return kust_ids, wallets_by_kust
    except Exception as e:
        print(f"[30/70] _get_kustodian_data_for_pakd failed: {e}", flush=True)
        if own_conn:
            _return_db_conn(conn)
        return [], []


def _get_reported_values(pakd_id, conn=None):
    """Get reported values for a PAKD from confirmed e-reporting data.
    Falls back to REPORTED_VALUES_DEFAULT when no confirmed report exists.
    """
    own_conn = conn is None
    if own_conn:
        conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT customer_at_pakd_idr, customer_at_ptp_idr, proprietary_idr
                FROM laporan_ereporting
                WHERE entity_id = %s AND report_type = 'pakd' AND status = 'confirmed'
                ORDER BY periode DESC
                LIMIT 1
            """, (pakd_id,))
            row = cur.fetchone()
            cur.close()
            if row:
                return {
                    'customer_at_pakd_idr': float(row[0] or 0),
                    'customer_at_ptp_idr': float(row[1] or 0),
                    'proprietary_idr': float(row[2] or 0),
                }
        except Exception as e:
            print(f"[EREPORTING] _get_reported_values query failed: {e}", flush=True)
        finally:
            if own_conn:
                _return_db_conn(conn)
    # FALLBACK: used when no confirmed e-reporting exists for a PAKD.
    # Sprint 3 goal: all entities should have e-reporting data.
    # This dict will be removed in Sprint 4 after demo data is calibrated.
    return REPORTED_VALUES_DEFAULT.get(pakd_id, {})


def _get_aset_dilaporkan(pakd_id, fallback=0, conn=None):
    """Resolve aset_dilaporkan for a PAKD.

    Priority: latest confirmed e-reporting (customer_at_pakd_idr +
    customer_at_ptp_idr + proprietary_idr) -> pakd.aset_dilaporkan -> fallback.
    Accepts conn= pass-through (pool size 1: never grab a second connection
    while the caller holds one).
    """
    own_conn = conn is None
    if own_conn:
        conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT customer_at_pakd_idr, customer_at_ptp_idr, proprietary_idr
                FROM laporan_ereporting
                WHERE entity_id = %s AND report_type = 'pakd' AND status = 'confirmed'
                ORDER BY periode DESC
                LIMIT 1
            """, (pakd_id,))
            row = cur.fetchone()
            if row:
                cur.close()
                return float(row[0] or 0) + float(row[1] or 0) + float(row[2] or 0)
            default = REPORTED_VALUES_DEFAULT.get(pakd_id)
            if default:
                cur.close()
                return (default.get("customer_at_pakd_idr", 0)
                        + default.get("customer_at_ptp_idr", 0)
                        + default.get("proprietary_idr", 0))
            cur.execute("SELECT aset_dilaporkan FROM pakd WHERE id = %s", (pakd_id,))
            pakd_row = cur.fetchone()
            cur.close()
            if pakd_row and pakd_row[0]:
                return pakd_row[0]
        except Exception as e:
            print(f"[EREPORTING] _get_aset_dilaporkan({pakd_id}) query failed: {e}", flush=True)
        finally:
            if own_conn:
                _return_db_conn(conn)
    return fallback


# Last-known-good kustodian custody balance: kust_id -> (timestamp, dict).
# D30: nilai tersimpan kini dict {total_idr, entries, provenance_harga}.
# Indeks 0 tetap timestamp, jadi pemeriksaan TTL tidak berubah.
# Chain fetchers swallow errors and yield 0, which poisoned one PAKD's
# snapshot with porsi 0 while siblings in the same run got real values.
_KUST_ONCHAIN_LKG = {}
_KUST_ONCHAIN_LKG_TTL = 900  # 15 minutes


def _get_kustodian_onchain_resilient(kust_id, kust_wallets):
    """Fetch a kustodian's total custody balance with retry + last-known-good.

    A transient rate-limit turns into a silent 0 in get_total_balance_idr.
    Retry once, then fall back to a recent successful value so a single
    failed fetch can't zero one PAKD's porsi mid-refresh.

    D30: kembaliannya dict, bukan int. Total telanjang membuat kustodian
    yang salah satu harganya gagal tidak terbedakan dari kustodian yang
    asetnya terbaca lengkap -- keduanya menerbitkan angka yang sama.
    """
    if not kust_wallets:
        return {"total_idr": 0, "entries": [], "provenance_harga": {},
                "sumber_total": "tanpa_wallet", "lkg_umur_detik": None}
    result = get_total_balance_idr(kust_wallets)
    kust_onchain = result["total_idr"]
    if kust_onchain <= 0:
        print(f"[30/70] kustodian {kust_id} balance fetched as 0 — retrying once", flush=True)
        time.sleep(2)
        result = get_total_balance_idr(kust_wallets)
        kust_onchain = result["total_idr"]
    # Pola toleran: kunci yang absen dan kunci bernilai None diperlakukan sama.
    entries = result.get("entries") or []
    provenance_harga = result.get("provenance_harga") or {}
    if kust_onchain > 0:
        _KUST_ONCHAIN_LKG[kust_id] = (time.time(), {
            "total_idr": kust_onchain,
            "entries": entries,
            "provenance_harga": provenance_harga,
        })
        return {"total_idr": kust_onchain, "entries": entries,
                "provenance_harga": provenance_harga,
                "sumber_total": "live", "lkg_umur_detik": None}
    cached = _KUST_ONCHAIN_LKG.get(kust_id)
    if cached and time.time() - cached[0] < _KUST_ONCHAIN_LKG_TTL:
        umur = time.time() - cached[0]
        tersimpan = cached[1]
        print(f"[30/70] kustodian {kust_id} fetch still 0 — using last-known-good "
              f"Rp {tersimpan['total_idr']:,.0f} from {umur:.0f}s ago", flush=True)
        # Provenance yang disajikan adalah milik nilai yang dipakai, bukan
        # milik percobaan yang baru saja gagal. Dict baru: entri cache
        # tidak boleh termutasi oleh pemanggil.
        return {"total_idr": tersimpan["total_idr"],
                "entries": list(tersimpan["entries"]),
                "provenance_harga": dict(tersimpan["provenance_harga"]),
                "sumber_total": "lkg", "lkg_umur_detik": umur}
    return {"total_idr": 0, "entries": entries,
            "provenance_harga": provenance_harga,
            "sumber_total": "gagal", "lkg_umur_detik": None}


def deviasi_with_custody(pakd_onchain_idr, kustodian_share_idr, aset_dilaporkan):
    """Deviasi counting the PAKD's dedicated custody balance as its on-chain assets.

    Reported totals include AKD placed at the PTP, so the on-chain side must
    include the balance of the kustodian wallets dedicated to this PAKD --
    otherwise a perfectly compliant 30/70 PAKD always shows ~-70% deviasi.
    Returns (total_attributable_idr, deviasi_pct).
    """
    total = (pakd_onchain_idr or 0) + (kustodian_share_idr or 0)
    if aset_dilaporkan and aset_dilaporkan > 0:
        deviasi_pct = (total - aset_dilaporkan) / aset_dilaporkan * 100
    else:
        deviasi_pct = 0
    return total, deviasi_pct


def compute_30_70_compliance(pakd_id, pakd_onchain_idr, conn=None, as_of=None):
    """Compute 30/70 compliance for a PAKD with linked kustodian(s).
    Returns dict with kustodian_onchain_idr, compliance_30_70, ratio_at_pakd, ratio_at_ptp, kustodian_details.
    """
    kust_ids, wallets_by_kust = _get_kustodian_data_for_pakd(pakd_id, conn=conn)

    # D30: as_of disuntikkan supaya keluarannya deterministik saat diuji.
    if as_of is None:
        as_of = datetime.now(timezone.utc).isoformat()

    if not kust_ids:
        return {
            # D34/D35: tanpa kustodian sama sekali, porsi PTP tidak
            # pernah diukur. None berarti "tidak terukur"; 0 akan berarti
            # "diukur dan hasilnya nol", dua keadaan yang berbeda.
            "kustodian_onchain_idr": None,
            "compliance_30_70": False,
            "ratio_at_pakd": 1.0,
            "ratio_at_ptp": 0.0,
            "kustodian_details": [],
            "has_kustodian": False,
            "kustodian_kelengkapan": hitung_kelengkapan([], {}, as_of),
        }

    kustodian_onchain_total = 0
    kustodian_details = []
    # D34/D35: dikumpulkan per kontributor, bukan satu nilai skalar.
    # Loop di bawah berjalan sekali per 18 Agustus 2026 karena satu PAKD
    # tertaut ke satu Kustodian, tapi begitu ada PAKD dengan lebih dari
    # satu Kustodian, satu kontributor yang gagal sudah cukup membuat
    # totalnya tidak terukur -- yang paling buruk menang, sama seperti
    # aturan provenance_harga di bawah.
    sumber_per_kontributor = []
    entries_gabungan = []
    provenance_gabungan = {}
    for kust_id in kust_ids:
        # Wallets here are already DEDICATED to this PAKD (1 wallet = 1 PAKD),
        # so the balance is attributed in full — no proration.
        kust_wallets = wallets_by_kust.get(kust_id, [])
        kust_onchain = _get_kustodian_onchain_resilient(f"{kust_id}:{pakd_id}", kust_wallets)
        kustodian_onchain_total += kust_onchain["total_idr"]
        sumber_per_kontributor.append(kust_onchain["sumber_total"])
        kustodian_details.append({
            "kustodian_id": kust_id,
            "onchain_idr": round(kust_onchain["total_idr"]),
            "wallet_count": len(kust_wallets),
        })
        entries_gabungan.extend(kust_onchain["entries"])
        # D30: yang paling buruk menang. Satu jaringan hanya sah kalau
        # SETIAP kustodian penyumbangnya punya provenance sah untuknya;
        # satu None saja membuat gabungannya None.
        #
        # Penyumbang di sini didefinisikan lewat kehadiran kunci di dict
        # provenance, sementara completeness.py menurunkan relevansi
        # jaringan dari entries yang balance_native-nya di atas nol. Dua
        # definisi, dan keduanya sepakat hanya karena
        # get_total_balance_idr menginisialisasi ketiga kunci jaringan
        # sekaligus, sehingga kunci yang absen tidak pernah lahir dari
        # jalur produksi. Kesetaraan itu juga bergantung pada loop ini
        # yang selalu berjalan satu putaran: satu PAKD tertaut ke satu
        # Kustodian per 18 Agustus 2026.
        #
        # Bila salah satu dari dua syarat itu berubah, yaitu ada PAKD
        # dengan lebih dari satu Kustodian atau ada jalur yang
        # menghasilkan provenance tanpa kunci jaringan, samakan definisi
        # penyumbang dengan yang dipakai completeness.py: turunkan dari
        # entries, dan perlakukan kunci provenance yang absen pada
        # penyumbang sebagai None, bukan sebagai bukan penyumbang.
        for _net, _prov in kust_onchain["provenance_harga"].items():
            if _net not in provenance_gabungan or _prov is None:
                provenance_gabungan[_net] = _prov

    reported = _get_reported_values(pakd_id, conn=conn)
    customer_at_pakd = reported.get("customer_at_pakd_idr", 0)
    customer_at_ptp = reported.get("customer_at_ptp_idr", 0)
    total_customer = customer_at_pakd + customer_at_ptp

    if total_customer > 0:
        ratio_at_pakd = customer_at_pakd / total_customer
        ratio_at_ptp = customer_at_ptp / total_customer
    else:
        ratio_at_pakd = 0.0
        ratio_at_ptp = 0.0

    compliance = ratio_at_pakd <= 0.30

    # D34/D35: hanya NILAI YANG DIKEMBALIKAN yang bercabang.
    # kustodian_onchain_total tetap numerik dan perhitungan ratio serta
    # compliance di atas tidak tersentuh.
    total_tidak_terukur = any(
        s in ("gagal", "tanpa_wallet") for s in sumber_per_kontributor)

    return {
        "kustodian_onchain_idr": (None if total_tidak_terukur
                                  else round(kustodian_onchain_total)),
        "compliance_30_70": compliance,
        "ratio_at_pakd": round(ratio_at_pakd, 4),
        "ratio_at_ptp": round(ratio_at_ptp, 4),
        "kustodian_details": kustodian_details,
        "has_kustodian": True,
        "reported_customer_at_pakd_idr": customer_at_pakd,
        "reported_customer_at_ptp_idr": customer_at_ptp,
        "reported_proprietary_idr": reported.get("proprietary_idr", 0),
        # D30: total kustodian kini datang bersama asal-usulnya.
        "kustodian_kelengkapan": hitung_kelengkapan(
            entries_gabungan, provenance_gabungan, as_of),
    }


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------



def get_cached_balance(cache_key, address, fetch_fn):
    """
    Return cached balance for (cache_key, address). cache_key is the
    network identifier — for ERC-20 tokens, pass a namespaced key like
    "usdt_erc20" or "usdc_erc20" to avoid collisions with native ETH
    balances on the same address.

    Calls fetch_fn only when cache is cold or older than BALANCE_TTL seconds.
    """
    now = time.time()
    key = (cache_key, address)
    if key in BALANCE_CACHE:
        cached_at, balance = BALANCE_CACHE[key]
        if now - cached_at < BALANCE_TTL:
            return balance
    balance = fetch_fn()
    BALANCE_CACHE[key] = (now, balance)
    return balance


# ---------------------------------------------------------------------------
# Ethereum — native ETH fetchers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# CoinMarketCap primary price source (Day 15 cascade)
# Rationale: Render shared IP-pool throttled by CoinGecko Cloudflare edge.
# CMC authenticated requests bypass IP-based throttle.
# Plan: 15K credits/month, 50 req/min. Single batched call covers all 5
# assets at 1 credit per call.
# ---------------------------------------------------------------------------


# Curated ERC-20 symbols priced via a dedicated CMC call (IDR) when the
# CoinGecko contract-price endpoint fails/throttles (CF-throttled from Render).
CURATED_CMC_FALLBACK = {"OKB": "3897"}


def _curated_idr_price_fallback(symbol):
    """IDR price for a curated token via a single-asset CMC quote, or None."""
    cmc_id = CURATED_CMC_FALLBACK.get(symbol)
    if not cmc_id:
        return None
    cache_key = f"cmc_curated_{cmc_id}"
    cached = PRICE_CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < PRICE_TTL and cached[1] > 0:
        return cached[1]
    api_key = os.environ.get("COINMARKETCAP_API_KEY", "")
    if not api_key:
        return None
    try:
        resp = requests.get(
            "https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest",
            headers={"X-CMC_PRO_API_KEY": api_key, "Accept": "application/json"},
            params={"id": cmc_id, "convert": "IDR", "aux": ""},
            timeout=10,
        )
        resp.raise_for_status()
        entry = resp.json().get("data", {}).get(cmc_id)
        if isinstance(entry, list):
            entry = entry[0] if entry else None
        price = (entry or {}).get("quote", {}).get("IDR", {}).get("price")
        if price and price > 0:
            PRICE_CACHE[cache_key] = (time.time(), float(price))
            return float(price)
    except Exception as e:
        print(f"[CMC] curated fallback price ({symbol}/{cmc_id}) failed: {e}", flush=True)
    return None








# ---------------------------------------------------------------------------
# ERC-20 token fetchers (Day 4)
# ---------------------------------------------------------------------------







# ---------------------------------------------------------------------------
# Bitcoin fetchers
# ---------------------------------------------------------------------------

def fetch_btc_balance(address):
    """
    Fetch confirmed BTC balance via race between Blockstream and mempool.space.
    Returns float in BTC. Uses chain_stats only (confirmed txos).
    First provider to return HTTP 200 wins.
    """
    from concurrent.futures import ThreadPoolExecutor as _BTCTPE, as_completed as _ac
    providers = [
        f"https://blockstream.info/api/address/{address}",
        f"https://mempool.space/api/address/{address}",
    ]
    def _fetch(url):
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        return r.json()
    with _BTCTPE(max_workers=2) as _ex:
        futures = {_ex.submit(_fetch, url): url for url in providers}
        for f in _ac(futures):
            try:
                data   = f.result()
                funded = data["chain_stats"]["funded_txo_sum"]
                spent  = data["chain_stats"]["spent_txo_sum"]
                return (funded - spent) / SATOSHI_PER_BTC
            except Exception:
                continue
    raise RuntimeError(f"All BTC providers failed for {address}")




# ---------------------------------------------------------------------------
# Solana fetchers
# ---------------------------------------------------------------------------

def fetch_sol_balance(address):
    """
    Fetch confirmed SOL balance via Solana JSON-RPC getBalance.
    Returns float in SOL.

    Uses commitment='confirmed' — finalized would add ~30s latency and is
    unnecessary for regulatory monitoring snapshots. Unconfirmed (processed)
    is explicitly excluded: unsettled transactions must not count toward
    regulatory reserve.

    Source: https://solana.com/docs/rpc/http/getbalance
    """
    payload = {
        "jsonrpc": "2.0",
        "id":      1,
        "method":  "getBalance",
        "params":  [address, {"commitment": "confirmed"}],
    }
    resp = requests.post(
        SOLANA_RPC_URL,
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise ValueError(f"Solana RPC error: {data['error']}")
    lamports = data["result"]["value"]
    return lamports / LAMPORTS_PER_SOL



def fetch_spl_token_balance(address, mint_address):
    """
    Fetch SPL token balance for a given mint via Solana JSON-RPC
    getTokenAccountsByOwner.

    Uses jsonParsed encoding so uiAmount is already in human-readable
    units (e.g. 1000.50 USDC, not raw integer). Sums across all token
    accounts for the same mint — a wallet can technically have multiple
    accounts for the same mint, though uncommon for exchange wallets.

    Uses commitment='confirmed' for consistency with fetch_sol_balance().

    Source: https://solana.com/docs/rpc/http/gettokenaccountsbyowner
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            address,
            {"mint": mint_address},
            {"encoding": "jsonParsed", "commitment": "confirmed"}
        ]
    }
    resp = requests.post(
        SOLANA_RPC_URL,
        json=payload,
        timeout=10
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise ValueError(f"Solana RPC error: {data['error']}")

    total = 0.0
    for account in data["result"]["value"]:
        ui_amount = (
            account["account"]["data"]["parsed"]
            ["info"]["tokenAmount"]["uiAmount"]
        )
        if ui_amount:
            total += ui_amount
    return total

def fetch_all_spl_balances(address):
    """
    Enumerate ALL non-zero SPL token accounts owned by `address` via Solana
    JSON-RPC getTokenAccountsByOwner filtered by standard SPL program.

    Limitation (Day 16 scope):
        Token-2022 mints (program TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb)
        are NOT enumerated by this call. Documented in keterbatasan-sistem.md.

    Returns:
        list of {"mint": str, "ui_amount": float} with ui_amount > 0 only.

    Source: https://solana.com/docs/rpc/http/gettokenaccountsbyowner
    """
    payload = {
        "jsonrpc": "2.0",
        "id":      1,
        "method":  "getTokenAccountsByOwner",
        "params": [
            address,
            {"programId": SPL_TOKEN_PROGRAM_ID},
            {"encoding": "jsonParsed", "commitment": "confirmed"},
        ],
    }
    resp = requests.post(
        SOLANA_RPC_URL,
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise ValueError(f"Solana RPC error: {data['error']}")

    holdings = []
    for account in data["result"]["value"]:
        info      = account["account"]["data"]["parsed"]["info"]
        mint      = info["mint"]
        ui_amount = info["tokenAmount"].get("uiAmount")
        if ui_amount and ui_amount > 0:
            holdings.append({"mint": mint, "ui_amount": float(ui_amount)})
    return holdings


def _get_jupiter_verified_set():
    """
    Return set of mint addresses tagged "verified" in Jupiter Tokens V2.

    V1 tag "strict" was deprecated. V2 equivalent (per dev.jup.ag/docs/tokens/v2)
    is "verified" plus "lst" only. "verified" carries the curatorship intent
    that PRIMA needs as Gate 1 legitimacy proxy under POJK 23/2025 DAKD spirit.

    Cache TTL 24h. On fetch failure returns last cached set (even stale)
    to keep reconciliation operational; empty set only on cold start failure.
    """
    now = time.time()
    cached = JUPITER_STRICT_CACHE.get("verified_set")
    if cached and (now - cached[0]) < JUPITER_STRICT_TTL:
        return cached[1]

    headers = {}
    base    = JUPITER_API_BASE
    if JUPITER_API_KEY:
        headers["x-api-key"] = JUPITER_API_KEY
    else:
        base = "https://lite-api.jup.ag"   # graceful fallback when key absent

    try:
        resp = requests.get(
            f"{base}/tokens/v2/tag",
            params={"query": "verified"},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        verified_set = {
            item["id"] for item in data
            if isinstance(item, dict) and item.get("id")
        }
        JUPITER_STRICT_CACHE["verified_set"] = (now, verified_set)
        return verified_set
    except Exception as e:
        if os.environ.get('PRIMA_DEBUG'):
            print(f"[JUPITER] verified_set fetch failed: {type(e).__name__}: {e}", flush=True)
        return cached[1] if cached else set()


def _get_jupiter_prices(mints):
    """
    Return {mint: usd_price} for requested mints via Jupiter Price V3.

    Per-mint cache TTL 300s. Only uncached mints trigger network call,
    batched into one comma-separated GET. Mints with null/zero/missing
    price are negative-cached (entry = None) so they are not re-fetched
    every reconciliation cycle.

    V3 response: {mint: {usdPrice: float, blockId, decimals, ...}}
    Source: https://dev.jup.ag/docs/price/v3
    """
    now      = time.time()
    result   = {}
    to_fetch = []

    for mint in mints:
        cached = JUPITER_PRICE_CACHE.get(mint)
        if cached and (now - cached[0]) < JUPITER_PRICE_TTL:
            if cached[1] is not None and cached[1] > 0:
                result[mint] = cached[1]
        else:
            to_fetch.append(mint)

    if not to_fetch:
        return result

    headers = {}
    base    = JUPITER_API_BASE
    if JUPITER_API_KEY:
        headers["x-api-key"] = JUPITER_API_KEY
    else:
        base = "https://lite-api.jup.ag"

    try:
        resp = requests.get(
            f"{base}/price/v3",
            params={"ids": ",".join(to_fetch)},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        for mint in to_fetch:
            entry = data.get(mint)
            if entry and isinstance(entry, dict):
                usd_price = entry.get("usdPrice")
                if usd_price is not None and usd_price > 0:
                    JUPITER_PRICE_CACHE[mint] = (now, float(usd_price))
                    result[mint] = float(usd_price)
                else:
                    JUPITER_PRICE_CACHE[mint] = (now, None)
            else:
                JUPITER_PRICE_CACHE[mint] = (now, None)
    except Exception as e:
        if os.environ.get('PRIMA_DEBUG'):
            print(f"[JUPITER] price fetch failed: {type(e).__name__}: {e}", flush=True)
    _evict_stale_entries(JUPITER_PRICE_CACHE, MAX_JUPITER_PRICE_CACHE)
    return result
def _get_dexscreener_price(mint: str):
    """
    Fallback price source for SPL tokens not priced by Jupiter Price V3.
    Uses DexScreener public API — no API key required.
    Returns usdPrice (float) or None.
    Selects highest-liquidity pair to minimise price manipulation risk.
    """
    try:
        resp = requests.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{mint}",
            timeout=5
        )
        if resp.status_code != 200:
            return None
        pairs = resp.json().get("pairs") or []
        priced = [p for p in pairs if p.get("priceUsd")]
        if not priced:
            return None
        best = max(priced, key=lambda p: float((p.get("liquidity") or {}).get("usd", 0) or 0))
        return float(best["priceUsd"])
    except Exception as e:
        if os.environ.get('PRIMA_DEBUG'):
            print(f"[DEXSCREENER] price fetch failed for {mint}: "
                  f"{type(e).__name__}: {e}", flush=True)
        return None


# ---------------------------------------------------------------------------
# Unified multi-network balance fetcher (updated Day 4)
# ---------------------------------------------------------------------------



def _get_coingecko_eth_token_prices(contracts):
    """
    Fetch USD prices for ERC-20 contracts via CoinGecko Demo API.

    Chunked 25 contracts/request (Demo plan caps at 30). Cache TTL 300s.
    Defensive: any exception returns partial dict, never crashes recon.

    Args:
        contracts: list of contract address strings (any case).

    Returns:
        dict mapping lowercase contract -> USD price (float).
        Contracts without active CoinGecko entry omitted.
    """
    global COINGECKO_TOKEN_CACHE, COINGECKO_TOKEN_CACHE_TS

    if not contracts:
        return {}

    now = time.time()
    if COINGECKO_TOKEN_CACHE and (now - COINGECKO_TOKEN_CACHE_TS) < COINGECKO_TOKEN_CACHE_TTL:
        requested_lc = {c.lower() for c in contracts}
        return {k: v for k, v in COINGECKO_TOKEN_CACHE.items() if k in requested_lc}

    cg_key  = os.getenv("COINGECKO_API_KEY")
    headers = {"x-cg-demo-api-key": cg_key} if cg_key else {}
    result  = {}

    for i in range(0, len(contracts), 25):
        batch = contracts[i:i+25]
        csv   = ",".join(batch)
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/simple/token_price/ethereum",
                params={"contract_addresses": csv, "vs_currencies": "usd"},
                headers=headers,
                timeout=10,
            )
            if r.status_code != 200:
                if os.environ.get('PRIMA_DEBUG'):
                    print(f"[CG_TOKEN] batch {i//25 + 1} HTTP {r.status_code}", flush=True)
                continue
            data = r.json()
            for contract_lc, price_obj in data.items():
                usd = price_obj.get("usd") if isinstance(price_obj, dict) else None
                if usd is not None:
                    result[contract_lc.lower()] = float(usd)
        except Exception as e:
            if os.environ.get('PRIMA_DEBUG'):
                print(f"[CG_TOKEN] batch {i//25 + 1} exception: {e}", flush=True)
            continue

    if result:
        COINGECKO_TOKEN_CACHE    = result.copy()
        COINGECKO_TOKEN_CACHE_TS = now

    return result


def fetch_curated_erc20_balances(address):
    """
    Enumerate non-zero balances across ETH_CURATED_TOKENS for `address`.

    Uses ThreadPoolExecutor with max_workers=5 (Etherscan 5 req/sec ceiling).
    Cache key namespace: 'erc20_curated_<contract>' via get_cached_balance.

    Returns:
        list of {"symbol", "contract", "balance", "decimals"} non-zero only.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _fetch_one(token):
        symbol   = token["symbol"]
        contract = token["contract"]
        decimals = token["decimals"]
        try:
            bal = get_cached_balance(
                f"erc20_curated_{contract.lower()}",
                address,
                lambda a=address, c=contract, d=decimals: fetch_erc20_balance(a, c, d),
            )
            if bal and bal > 0:
                return {
                    "symbol":   symbol,
                    "contract": contract,
                    "balance":  bal,
                    "decimals": decimals,
                }
        except Exception as e:
            print(f"[ERC20_CURATED] {symbol} {address[:8]} error: {e}", flush=True)
        return None

    holdings = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_fetch_one, t) for t in ETH_CURATED_TOKENS]
        for future in as_completed(futures):
            res = future.result()
            if res:
                holdings.append(res)

    return holdings


def get_total_balance_idr(wallets, eth_price_idr=None, btc_price_idr=None, sol_price_idr=None,
                           usdt_price_idr=None, usdc_price_idr=None):
    """
    Fetch on-chain balance for all wallets across Ethereum (native ETH
    + USDT + USDC), Bitcoin, and Solana.

    Ethereum wallet breakdown now includes:
      eth_native_idr : IDR value of native ETH
      usdt_balance   : USDT balance in token units
      usdt_idr       : IDR value of USDT
      usdc_balance   : USDC balance in token units
      usdc_idr       : IDR value of USDC

    Returns dict:
      total_idr          : float  — combined IDR value, all networks and tokens
      eth_balance_idr    : float  — ETH wallets subtotal (native + ERC-20) in IDR
      eth_native_idr     : float  — native ETH subtotal only
      eth_usdt_idr       : float  — USDT subtotal across ETH wallets
      eth_usdc_idr       : float  — USDC subtotal across ETH wallets
      btc_balance_idr    : float  — BTC wallets subtotal in IDR
      sol_balance_idr    : float  — SOL wallets subtotal in IDR
      breakdown          : list   — per-wallet detail
    """
    # --- Resolve prices (use provided values or fetch/cache) ---
    # T1.2 (D3/D4): chain yang harganya gagal diambil masuk ke himpunan ini.
    # Chain tersebut TIDAK dinilai dan TIDAK muncul di breakdown -- hilang,
    # bukan nol. Menilainya nol rupiah membuat verdict tetap keluar seolah
    # kepemilikannya memang kosong.
    harga_tidak_tersedia = set()

    # D25: provenance tiap harga native dikumpulkan di sini dan ikut
    # dilaporkan pada kembalian. Tanpa ini pemanggil tidak punya bahan
    # untuk menilai kelengkapan data -- lihat core/completeness.py.
    provenance_harga = {"ethereum": None, "bitcoin": None, "solana": None}

    if eth_price_idr is None:
        # D24: samakan ETH dengan BTC/SOL. Tier hardcoded pada kaskade
        # bukan harga pasar, jadi ia diperlakukan sebagai harga yang
        # tidak tersedia -- kepemilikan ETH hilang dari breakdown alih-alih
        # dinilai memakai konstanta. Lapisan get_cached_price("ethereum")
        # dilepas: kaskade ETH sudah punya cache dan provenance sendiri,
        # dan menumpuknya membuat provenance yang dilaporkan bisa
        # menggambarkan nilai yang berbeda dari yang dipakai.
        try:
            prov_eth = get_eth_price_with_provenance()
            # D25: provenance dilaporkan apa adanya, termasuk pada cabang
            # hardcoded di bawah. Nilainya tetap ditolak (D24), tapi
            # sebab penolakannya harus terbaca sebagai "hardcoded", bukan
            # sebagai provenance yang tidak tersedia.
            provenance_harga["ethereum"] = prov_eth
            if prov_eth["sumber"] == "hardcoded":
                eth_price_idr = None
                harga_tidak_tersedia.add("eth_native")
            else:
                eth_price_idr = prov_eth["nilai"]
        except Exception:
            eth_price_idr = None
            harga_tidak_tersedia.add("eth_native")

    if btc_price_idr is None:
        try:
            _prov_btc = get_price_with_provenance("bitcoin", fetch_btc_price_idr)
            provenance_harga["bitcoin"] = _prov_btc
            btc_price_idr = _prov_btc["nilai"]
        except Exception:
            btc_price_idr = None
            harga_tidak_tersedia.add("btc_native")

    if sol_price_idr is None:
        try:
            _prov_sol = get_price_with_provenance("solana", fetch_sol_price_idr)
            provenance_harga["solana"] = _prov_sol
            sol_price_idr = _prov_sol["nilai"]
        except Exception:
            sol_price_idr = None
            harga_tidak_tersedia.add("sol_native")

    # Stablecoins: always batch in one call via _get_stablecoin_prices_idr().
    if usdt_price_idr is None or usdc_price_idr is None:
        try:
            _usdt, _usdc = _get_stablecoin_prices_idr()
            if usdt_price_idr is None:
                usdt_price_idr = _usdt
            if usdc_price_idr is None:
                usdc_price_idr = _usdc
        except Exception:
            usdt_price_idr = usdt_price_idr or FALLBACK_STABLECOIN_IDR
            usdc_price_idr = usdc_price_idr or FALLBACK_STABLECOIN_IDR

    # --- Accumulate across wallets (parallel per chain) ---
    eth_wallets = [w for w in wallets if w.get("network", "ethereum") == "ethereum"]
    btc_wallets = [w for w in wallets if w.get("network") == "bitcoin"]
    sol_wallets = [w for w in wallets if w.get("network") == "solana"]
    other_wallets = [w for w in wallets if w.get("network") not in ("ethereum", "bitcoin", "solana")]

    def _proc_eth(eth_w, shared_entries):
        _entries = shared_entries  # append-per-wallet so caller can harvest partial results on timeout
        _eth_total = _eth_native = _eth_usdt = _eth_usdc = _eth_other = 0.0
        _eth_unvalued_count = 0
        _eth_unvalued_contracts = []
        _t = 0.0
        for wallet in eth_w:
            address  = wallet.get("address", "")
            verified = wallet.get("verified", False)
            entry = {
                "network": "ethereum", "address": address,
                "balance_native": 0.0, "native_unit": "ETH", "balance_idr": 0.0,
                "eth_native_idr": None, "usdt_balance": None, "usdt_idr": None,
                "usdc_balance": None, "usdc_idr": None,
                "sol_native_idr": None, "sol_usdt_balance": None, "sol_usdt_idr": None,
                "sol_usdc_balance": None, "sol_usdc_idr": None,
                "sol_other_token_idr": None, "sol_unvalued_count": None, "sol_unvalued_mints": None,
                "eth_other_token_idr": None, "eth_unvalued_count": None, "eth_unvalued_contracts": None,
                "verified": verified, "error": None, "fetch_status": "sukses",
            }
            _tw = time.perf_counter()
            try:
                if "ethereum" in DEMO_FORCE_PROVIDER_FAILURE:
                    write_audit("DEMO_FAILURE_TRIGGERED", "Simulated ethereum provider failure (DEMO_MODE)")
                    raise RuntimeError("DEMO_FORCE_PROVIDER_FAILURE: ethereum")
                eth_bal = get_cached_balance("ethereum", address, lambda a=address: get_eth_balance(a))
                # D24: tanpa penjaga ini, eth_price_idr None melempar
                # TypeError yang tertangkap blok except di bawah dan
                # dilaporkan sebagai "ETH fetch error" -- kegagalan harga
                # menyamar sebagai kegagalan fetch saldo. Polanya mengikuti
                # Solana (_sol_native_dinilai), bukan Bitcoin: USDT dan USDC
                # di wallet ini dihargai lewat kaskade stablecoin terpisah
                # yang tetap sahih, jadi hanya komponen native yang gugur.
                _eth_native_dinilai = eth_price_idr is not None
                eth_native_idr_val = (eth_bal * eth_price_idr) if _eth_native_dinilai else 0.0
                usdt_bal = get_cached_balance("usdt_erc20", address, lambda a=address: fetch_erc20_balance(a, USDT_CONTRACT))
                usdt_idr_val = usdt_bal * usdt_price_idr
                usdc_bal = get_cached_balance("usdc_erc20", address, lambda a=address: fetch_erc20_balance(a, USDC_CONTRACT))
                usdc_idr_val = usdc_bal * usdc_price_idr
                wallet_total_idr = eth_native_idr_val + usdt_idr_val + usdc_idr_val
                entry["balance_native"] = eth_bal
                entry["balance_idr"]    = wallet_total_idr
                entry["eth_native_idr"] = round(eth_native_idr_val) if _eth_native_dinilai else None
                entry["usdt_balance"]   = round(usdt_bal, 6)
                entry["usdt_idr"]       = round(usdt_idr_val)
                entry["usdc_balance"]   = round(usdc_bal, 6)
                entry["usdc_idr"]       = round(usdc_idr_val)
                _eth_total  += wallet_total_idr
                _eth_native += eth_native_idr_val
                _eth_usdt   += usdt_idr_val
                _eth_usdc   += usdc_idr_val
                try:
                    curated_balances = fetch_curated_erc20_balances(address)
                    if curated_balances:
                        contracts_to_price = [t["contract"] for t in curated_balances]
                        curated_prices     = _get_coingecko_eth_token_prices(contracts_to_price)
                        usd_idr_rate       = _get_usd_idr_rate(usdt_price_idr)
                        eth_other_idr_val           = 0.0
                        unvalued_contracts_per_addr = []
                        for token in curated_balances:
                            contract_lc = token["contract"].lower()
                            usd_price   = curated_prices.get(contract_lc)
                            if usd_price and usd_price > 0:
                                eth_other_idr_val += token["balance"] * usd_price * usd_idr_rate
                            else:
                                idr_price = _curated_idr_price_fallback(token["symbol"])
                                if idr_price:
                                    eth_other_idr_val += token["balance"] * idr_price
                                else:
                                    unvalued_contracts_per_addr.append(token["contract"])
                        entry["eth_other_token_idr"]    = round(eth_other_idr_val)
                        entry["eth_unvalued_count"]     = len(unvalued_contracts_per_addr)
                        entry["eth_unvalued_contracts"] = unvalued_contracts_per_addr
                        wallet_total_idr               += eth_other_idr_val
                        _eth_total                     += eth_other_idr_val
                        _eth_other                     += eth_other_idr_val
                        _eth_unvalued_count            += len(unvalued_contracts_per_addr)
                        _eth_unvalued_contracts.extend(unvalued_contracts_per_addr)
                        entry["balance_idr"] = wallet_total_idr
                    else:
                        entry["eth_other_token_idr"]    = 0
                        entry["eth_unvalued_count"]     = 0
                        entry["eth_unvalued_contracts"] = []
                except Exception as curated_err:
                    entry["fetch_status"] = "partial"
                    if os.environ.get("PRIMA_DEBUG"):
                        print(f"[ETH_CURATED] {address[:8]} error: {curated_err}", flush=True)
                    entry["eth_other_token_idr"]    = 0
                    entry["eth_unvalued_count"]     = 0
                    entry["eth_unvalued_contracts"] = []
            except Exception as e:
                entry["fetch_status"] = "gagal"
                entry["error"] = f"ETH fetch error: {e}"
            _t += time.perf_counter() - _tw
            _entries.append(entry)
        return {"entries": _entries, "eth_total": _eth_total, "eth_native": _eth_native,
                "eth_usdt": _eth_usdt, "eth_usdc": _eth_usdc, "eth_other": _eth_other,
                "eth_unvalued_count": _eth_unvalued_count, "eth_unvalued_contracts": _eth_unvalued_contracts,
                "t": _t}

    def _proc_btc(btc_w, shared_entries):
        _entries = shared_entries  # append-per-wallet so caller can harvest partial results on timeout
        _btc_total = 0.0
        _t = 0.0
        for wallet in btc_w:
            address  = wallet.get("address", "")
            verified = wallet.get("verified", False)
            entry = {
                "network": "bitcoin", "address": address,
                "balance_native": 0.0, "native_unit": "BTC", "balance_idr": 0.0,
                "eth_native_idr": None, "usdt_balance": None, "usdt_idr": None,
                "usdc_balance": None, "usdc_idr": None,
                "sol_native_idr": None, "sol_usdt_balance": None, "sol_usdt_idr": None,
                "sol_usdc_balance": None, "sol_usdc_idr": None,
                "sol_other_token_idr": None, "sol_unvalued_count": None, "sol_unvalued_mints": None,
                "eth_other_token_idr": None, "eth_unvalued_count": None, "eth_unvalued_contracts": None,
                "verified": verified, "error": None, "fetch_status": "sukses",
            }
            _tw = time.perf_counter()
            try:
                if "bitcoin" in DEMO_FORCE_PROVIDER_FAILURE:
                    write_audit("DEMO_FAILURE_TRIGGERED", "Simulated bitcoin provider failure (DEMO_MODE)")
                    raise RuntimeError("DEMO_FORCE_PROVIDER_FAILURE: bitcoin")
                bal = get_cached_balance("bitcoin", address, lambda a=address: fetch_btc_balance(a))
                entry["balance_native"] = round(bal, 8)
                entry["balance_idr"]    = bal * btc_price_idr
                _btc_total             += entry["balance_idr"]
            except Exception as e:
                entry["fetch_status"] = "gagal"
                entry["error"] = f"BTC fetch error: {e}"
            _t += time.perf_counter() - _tw
            _entries.append(entry)
        return {"entries": _entries, "btc_total": _btc_total, "t": _t}

    def _proc_sol(sol_w, shared_entries):
        _entries = shared_entries  # append-per-wallet so caller can harvest partial results on timeout
        _sol_total = _sol_native = _sol_usdt = _sol_usdc = _sol_other = 0.0
        _sol_unvalued_count = 0
        _sol_unvalued_mints = []
        _t = 0.0
        for wallet in sol_w:
            address  = wallet.get("address", "")
            verified = wallet.get("verified", False)
            entry = {
                "network": "solana", "address": address,
                "balance_native": 0.0, "native_unit": "SOL", "balance_idr": 0.0,
                "eth_native_idr": None, "usdt_balance": None, "usdt_idr": None,
                "usdc_balance": None, "usdc_idr": None,
                "sol_native_idr": None, "sol_usdt_balance": None, "sol_usdt_idr": None,
                "sol_usdc_balance": None, "sol_usdc_idr": None,
                "sol_other_token_idr": None, "sol_unvalued_count": None, "sol_unvalued_mints": None,
                "eth_other_token_idr": None, "eth_unvalued_count": None, "eth_unvalued_contracts": None,
                "verified": verified, "error": None, "fetch_status": "sukses",
            }
            _tw = time.perf_counter()
            # Early append: on harvest timeout the caller keeps this dict with
            # whatever has been committed into it so far.
            _entries.append(entry)
            try:
                if "solana" in DEMO_FORCE_PROVIDER_FAILURE:
                    write_audit("DEMO_FAILURE_TRIGGERED", "Simulated solana provider failure (DEMO_MODE)")
                    raise RuntimeError("DEMO_FORCE_PROVIDER_FAILURE: solana")
                sol_bal = get_cached_balance("solana", address, lambda a=address: fetch_sol_balance(a))
                # T1.2 (D3/D4) Opsi A: harga SOL native tidak tersedia berarti
                # native TIDAK dinilai. SPL di bawah tetap dinilai karena harga
                # stablecoin datang dari kaskade yang lain.
                _sol_native_dinilai = sol_price_idr is not None
                sol_native_idr_val = (sol_bal * sol_price_idr) if _sol_native_dinilai else 0.0
                sol_usdt_bal = get_cached_balance("sol_usdt_spl", address, lambda a=address: fetch_spl_token_balance(a, USDT_MINT_SOL))
                sol_usdt_idr_val = sol_usdt_bal * usdt_price_idr
                sol_usdc_bal = get_cached_balance("sol_usdc_spl", address, lambda a=address: fetch_spl_token_balance(a, USDC_MINT_SOL))
                sol_usdc_idr_val = sol_usdc_bal * usdc_price_idr
                # Commit native+tier1 NOW: a harvest timeout during slow token
                # pricing must not discard the already-fetched balances.
                entry["balance_native"]   = round(sol_bal, 9)
                entry["sol_native_idr"]   = round(sol_native_idr_val) if _sol_native_dinilai else None
                entry["sol_usdt_balance"] = round(sol_usdt_bal, 6)
                entry["sol_usdt_idr"]     = round(sol_usdt_idr_val)
                entry["sol_usdc_balance"] = round(sol_usdc_bal, 6)
                entry["sol_usdc_idr"]     = round(sol_usdc_idr_val)
                entry["balance_idr"]      = sol_native_idr_val + sol_usdt_idr_val + sol_usdc_idr_val
                other_token_idr_val  = 0.0
                unvalued_mints_local = []
                try:
                    _spl_key = ("spl_enum", address)
                    _now = time.time()
                    if _spl_key in BALANCE_CACHE and (_now - BALANCE_CACHE[_spl_key][0]) < BALANCE_TTL:
                        all_holdings = BALANCE_CACHE[_spl_key][1]
                    else:
                        all_holdings = fetch_all_spl_balances(address)
                        BALANCE_CACHE[_spl_key] = (_now, all_holdings)
                except Exception as enum_err:
                    entry["fetch_status"] = "partial"
                    all_holdings = []
                    if os.environ.get("PRIMA_DEBUG"):
                        print(f"[SPL_ENUM] fetch_all_spl_balances({address}) failed: {type(enum_err).__name__}: {enum_err}", flush=True)
                tier1_mints     = {USDT_MINT_SOL, USDC_MINT_SOL, SOL_NATIVE_SENTINEL}
                candidate_mints = [h["mint"] for h in all_holdings if h["mint"] not in tier1_mints]
                if candidate_mints:
                    # Pricing failures must degrade to native+tier1, never zero
                    # the whole wallet (a 400-token wallet WILL hit API limits).
                    try:
                        verified_set = _get_jupiter_verified_set()
                        prices       = _get_jupiter_prices(candidate_mints)
                        usd_idr_rate = _get_usd_idr_rate(usdt_price_idr)
                        for holding in all_holdings:
                            mint = holding["mint"]
                            if mint in tier1_mints:
                                continue
                            in_verified = mint in verified_set
                            usd_price   = prices.get(mint)
                            has_price   = usd_price is not None and usd_price > 0
                            if not has_price:
                                try:
                                    usd_price = _get_dexscreener_price(mint)
                                except Exception:
                                    usd_price = None
                                has_price = usd_price is not None and usd_price > 0
                            pass_gate1 = in_verified or has_price
                            pass_gate2 = has_price
                            if pass_gate1 and pass_gate2:
                                token_idr = holding["ui_amount"] * usd_price * usd_idr_rate
                                other_token_idr_val += token_idr
                                BALANCE_CACHE[(f"sol_other_token:{mint}", address)] = (time.time(), holding["ui_amount"])
                            else:
                                unvalued_mints_local.append(mint)
                    except Exception as price_err:
                        entry["fetch_status"] = "partial"
                        print(f"[SPL_PRICE] token pricing for {address[:8]} failed, "
                              f"keeping native+tier1 only: {type(price_err).__name__}: {price_err}", flush=True)
                        unvalued_mints_local = [h["mint"] for h in all_holdings if h["mint"] not in tier1_mints]
                wallet_total_idr = sol_native_idr_val + sol_usdt_idr_val + sol_usdc_idr_val + other_token_idr_val
                entry["balance_native"]      = round(sol_bal, 9)
                entry["balance_idr"]         = wallet_total_idr
                entry["sol_native_idr"]      = round(sol_native_idr_val) if _sol_native_dinilai else None
                entry["sol_usdt_balance"]    = round(sol_usdt_bal, 6)
                entry["sol_usdt_idr"]        = round(sol_usdt_idr_val)
                entry["sol_usdc_balance"]    = round(sol_usdc_bal, 6)
                entry["sol_usdc_idr"]        = round(sol_usdc_idr_val)
                entry["sol_other_token_idr"] = round(other_token_idr_val)
                entry["sol_unvalued_count"]  = len(unvalued_mints_local)
                entry["sol_unvalued_mints"]  = unvalued_mints_local
                _sol_total          += wallet_total_idr
                _sol_native         += sol_native_idr_val
                _sol_usdt           += sol_usdt_idr_val
                _sol_usdc           += sol_usdc_idr_val
                _sol_other          += other_token_idr_val
                _sol_unvalued_count += len(unvalued_mints_local)
                _sol_unvalued_mints.extend(unvalued_mints_local)
            except Exception as e:
                entry["fetch_status"] = "gagal"
                entry["error"] = f"SOL fetch error: {e}"
            _t += time.perf_counter() - _tw
        return {"entries": _entries, "sol_total": _sol_total, "sol_native": _sol_native,
                "sol_usdt": _sol_usdt, "sol_usdc": _sol_usdc, "sol_other": _sol_other,
                "sol_unvalued_count": _sol_unvalued_count, "sol_unvalued_mints": _sol_unvalued_mints,
                "t": _t}

    def _harvest_partial(shared_entries, chain_wallets, network, native_unit, label, timeout):
        """On chain timeout/error, keep entries already appended by the worker thread
        and add explicit error entries for wallets not yet processed."""
        harvested = list(shared_entries)  # snapshot: worker thread may still append
        processed_addrs = {e["address"] for e in harvested}
        for wallet in chain_wallets:
            addr = wallet.get("address", "")
            if addr in processed_addrs:
                continue
            harvested.append({
                "network": network, "address": addr,
                "balance_native": 0.0, "native_unit": native_unit, "balance_idr": None,
                "eth_native_idr": None, "usdt_balance": None, "usdt_idr": None,
                "usdc_balance": None, "usdc_idr": None,
                "sol_native_idr": None, "sol_usdt_balance": None, "sol_usdt_idr": None,
                "sol_usdc_balance": None, "sol_usdc_idr": None,
                "sol_other_token_idr": None, "sol_unvalued_count": None, "sol_unvalued_mints": None,
                "eth_other_token_idr": None, "eth_unvalued_count": None, "eth_unvalued_contracts": None,
                "verified": wallet.get("verified", False),
                "error": f"Chain fetch timeout after {timeout}s",
            })
        print(f"[CHAIN_FETCH] {label} timeout: {len(processed_addrs)}/{len(chain_wallets)} wallets preserved", flush=True)
        return harvested

    from concurrent.futures import ThreadPoolExecutor as _ChainTPE
    _ex = _ChainTPE(max_workers=3)
    _eth_entries, _btc_entries, _sol_entries = [], [], []
    _f_eth = _ex.submit(_proc_eth, eth_wallets, _eth_entries)
    # BTC native adalah satu-satunya aset di chain bitcoin, jadi tanpa
    # harganya tidak ada apa pun yang bisa dinilai di sana.
    _f_btc = (None if "btc_native" in harga_tidak_tersedia
              else _ex.submit(_proc_btc, btc_wallets, _btc_entries))
    # Solana TIDAK di-skip walau harga SOL native gagal: SPL USDT/USDC
    # dihargai lewat kaskade stablecoin yang terpisah dan tetap sahih.
    _f_sol = _ex.submit(_proc_sol, sol_wallets, _sol_entries)
    from concurrent.futures import TimeoutError as FuturesTimeout
    try:
            _r_eth = _f_eth.result(timeout=25)
    except (FuturesTimeout, Exception) as e:
            print(f"[CHAIN_FETCH] ETH timeout/error: {e}", flush=True)
            _partial = _harvest_partial(_eth_entries, eth_wallets, "ethereum", "ETH", "ETH", 25)
            _r_eth = {"entries": _partial,
                      "eth_total": sum(en["balance_idr"] or 0 for en in _partial),
                      "eth_native": sum(en["eth_native_idr"] or 0 for en in _partial),
                      "eth_usdt": sum(en["usdt_idr"] or 0 for en in _partial),
                      "eth_usdc": sum(en["usdc_idr"] or 0 for en in _partial),
                      "eth_other": sum(en["eth_other_token_idr"] or 0 for en in _partial),
                      "eth_unvalued_count": sum(en["eth_unvalued_count"] or 0 for en in _partial),
                      "eth_unvalued_contracts": [c for en in _partial for c in (en["eth_unvalued_contracts"] or [])],
                      "t": 0}
    if _f_btc is None:
        # Harga BTC tidak tersedia: chain ini tidak dinilai sama sekali dan
        # tidak menyumbang baris apa pun ke breakdown.
        _r_btc = {"entries": [], "btc_total": 0.0, "t": 0.0}
    else:
        try:
            _r_btc = _f_btc.result(timeout=15)
        except (FuturesTimeout, Exception) as e:
            print(f"[CHAIN_FETCH] BTC timeout/error: {e}", flush=True)
            _partial = _harvest_partial(_btc_entries, btc_wallets, "bitcoin", "BTC", "BTC", 15)
            _r_btc = {"entries": _partial,
                      "btc_total": sum(en["balance_idr"] or 0 for en in _partial),
                      "t": 0}
    try:
        _r_sol = _f_sol.result(timeout=25)
    except (FuturesTimeout, Exception) as e:
        print(f"[CHAIN_FETCH] SOL timeout/error: {e}", flush=True)
        _partial = _harvest_partial(_sol_entries, sol_wallets, "solana", "SOL", "SOL", 25)
        _r_sol = {"entries": _partial,
                  "sol_total": sum(en["balance_idr"] or 0 for en in _partial),
                  "sol_native": sum(en["sol_native_idr"] or 0 for en in _partial),
                  "sol_usdt": sum(en["sol_usdt_idr"] or 0 for en in _partial),
                  "sol_usdc": sum(en["sol_usdc_idr"] or 0 for en in _partial),
                  "sol_other": sum(en["sol_other_token_idr"] or 0 for en in _partial),
                  "sol_unvalued_count": sum(en["sol_unvalued_count"] or 0 for en in _partial),
                  "sol_unvalued_mints": [m for en in _partial for m in (en["sol_unvalued_mints"] or [])],
                  "t": 0}

    # --- Merge results ---
    other_entries = []
    for wallet in other_wallets:
        other_entries.append({
            "network": wallet.get("network", ""), "address": wallet.get("address", ""),
            "balance_native": 0.0, "native_unit": wallet.get("network", "").upper(),
            "balance_idr": 0.0, "verified": wallet.get("verified", False),
            "error": f"Network '{wallet.get('network')}' belum didukung",
            "fetch_status": "gagal",
            "eth_native_idr": None, "usdt_balance": None, "usdt_idr": None,
            "usdc_balance": None, "usdc_idr": None,
            "sol_native_idr": None, "sol_usdt_balance": None, "sol_usdt_idr": None,
            "sol_usdc_balance": None, "sol_usdc_idr": None,
            "sol_other_token_idr": None, "sol_unvalued_count": None, "sol_unvalued_mints": None,
            "eth_other_token_idr": None, "eth_unvalued_count": None, "eth_unvalued_contracts": None,
        })

    breakdown          = _r_eth["entries"] + _r_btc["entries"] + _r_sol["entries"] + other_entries
    eth_total_idr      = _r_eth["eth_total"]
    eth_native_sum     = _r_eth["eth_native"]
    eth_usdt_sum       = _r_eth["eth_usdt"]
    eth_usdc_sum       = _r_eth["eth_usdc"]
    eth_other_token_sum          = _r_eth["eth_other"]
    eth_unvalued_count_total     = _r_eth["eth_unvalued_count"]
    eth_unvalued_contracts_global = _r_eth["eth_unvalued_contracts"]
    btc_total_idr      = _r_btc["btc_total"]
    sol_total_idr      = _r_sol["sol_total"]
    sol_native_sum     = _r_sol["sol_native"]
    sol_usdt_sum       = _r_sol["sol_usdt"]
    sol_usdc_sum       = _r_sol["sol_usdc"]
    sol_other_token_sum          = _r_sol["sol_other"]
    sol_unvalued_count_total     = _r_sol["sol_unvalued_count"]
    sol_unvalued_mints_global    = _r_sol["sol_unvalued_mints"]
    total_idr          = sum(e["balance_idr"] or 0 for e in breakdown)
    _t_eth = _r_eth["t"]
    _t_btc = _r_btc["t"]
    _t_sol = _r_sol["t"]


    _chain_timings = {
        "fetch_eth_total": round(_t_eth, 3),
        "fetch_btc_total": round(_t_btc, 3),
        "fetch_sol_total": round(_t_sol, 3),
    }
    if os.environ.get("PRIMA_DEBUG"):
        print(f"[PROFILING] chain timings: {_chain_timings}", flush=True)
    _evict_stale_entries(BALANCE_CACHE, MAX_BALANCE_CACHE)
    return {
        "total_idr":       total_idr,
        "_chain_timings":  _chain_timings,
        "eth_balance_idr": eth_total_idr,
        "eth_native_idr":  eth_native_sum,
        "eth_usdt_idr":    eth_usdt_sum,
        "eth_usdc_idr":    eth_usdc_sum,
        "btc_balance_idr": btc_total_idr,
        "sol_balance_idr": sol_total_idr,
        "sol_native_idr":  sol_native_sum,
        "sol_usdt_idr":    sol_usdt_sum,
        "sol_usdc_idr":    sol_usdc_sum,
        "sol_other_token_idr": sol_other_token_sum,
        "sol_unvalued_count":  sol_unvalued_count_total,
        "sol_unvalued_mints":  sol_unvalued_mints_global,
        "eth_other_token_idr":      eth_other_token_sum,
        "eth_unvalued_count":       eth_unvalued_count_total,
        "eth_unvalued_contracts":   eth_unvalued_contracts_global,
        "breakdown":       breakdown,
        # D25: "entries" adalah daftar yang sama dengan "breakdown".
        # "breakdown" dipertahankan apa adanya karena frontend membacanya;
        # "entries" adalah nama yang dibaca core/completeness.py.
        "entries":         breakdown,
        "provenance_harga": provenance_harga,
        # T1.2 (D3/D4): chain yang harganya gagal diambil. Kepemilikan di
        # chain ini TIDAK ikut total_idr dan tidak ada di breakdown.
        "harga_tidak_tersedia": sorted(harga_tidak_tersedia),
    }


# ---------------------------------------------------------------------------
# Data init
# ---------------------------------------------------------------------------

def init_data():
    conn = _get_db_conn()
    if not conn:
        print("[DB] init_data: no DB connection, skipping seed", flush=True)
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM pakd")
        count = cur.fetchone()[0]
        cur.close()
        _return_db_conn(conn)
        if count == 0:
            print("[DB] init_data: empty table, seeding PAKD_DEFAULT", flush=True)
            save_pakd([dict(p) for p in PAKD_DEFAULT])
        else:
            print(f"[DB] init_data: {count} PAKD exist, skipping seed", flush=True)
    except Exception as e:
        print(f"[DB] init_data check failed: {e}, skipping seed", flush=True)


def init_kustodian_data():
    conn = _get_db_conn()
    if not conn:
        print("[DB] init_kustodian_data: no DB connection, skipping seed", flush=True)
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM kustodian")
        count = cur.fetchone()[0]
        if count > 0:
            print(f"[DB] init_kustodian_data: {count} kustodian exist, skipping seed", flush=True)
            cur.close()
            _return_db_conn(conn)
            return

        print("[DB] init_kustodian_data: empty table, seeding KUSTODIAN_DEFAULT", flush=True)
        for kust in KUSTODIAN_DEFAULT:
            cur.execute("""
                INSERT INTO kustodian (id, nama) VALUES (%s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (kust["id"], kust["nama"]))

            for pakd_id in kust.get("pakd_ids", []):
                cur.execute("""
                    INSERT INTO kustodian_pakd (kustodian_id, pakd_id) VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, (kust["id"], pakd_id))

            for w in kust.get("wallets", []):
                cur.execute("""
                    INSERT INTO wallets (pakd_id, network, address, verified, verified_at, entity_type, entity_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (None, w["network"], w["address"], w.get("verified", False),
                      w.get("verified_at"), "KUSTODIAN", kust["id"]))

        conn.commit()
        cur.close()
        _return_db_conn(conn)
        print("[DB] init_kustodian_data: seeded successfully", flush=True)
    except Exception as e:
        print(f"[DB] init_kustodian_data failed: {e}", flush=True)
        try:
            conn.rollback()
            _return_db_conn(conn)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    resp = send_from_directory("../prima-frontend", "index.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/js/<path:filename>")
def frontend_js(filename):
    resp = send_from_directory("../prima-frontend/js", filename)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/api/status")
def status():
    return jsonify({"status": "ok", "sistem": "PRIMA", "versi": VERSI_PERHITUNGAN,
                    "commit": os.environ.get("RENDER_GIT_COMMIT", "unknown")[:7]})

def require_admin_token(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        expected = os.environ.get('ADMIN_TOKEN')
        if not expected:
            return jsonify({'error': 'Unauthorized'}), 401
        token = request.headers.get('X-Admin-Token', '')
        if not hmac.compare_digest(token, expected):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """Login endpoint. Return JWT + user profile."""
    data = request.get_json(silent=True)
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Email dan password wajib diisi'}), 400
    result = login_user(data['email'], data['password'])
    if 'error' in result:
        return jsonify(result), 401
    return jsonify(result)


@app.route('/api/auth/me', methods=['GET'])
@require_auth
def api_auth_me():
    """Return current user info dari JWT."""
    return jsonify(g.current_user)

@app.route('/api/auth/refresh', methods=['POST'])
def api_auth_refresh():
    """Refresh JWT token via Supabase."""
    import requests as _req
    data = request.get_json(silent=True) or {}
    rt = data.get('refresh_token')
    if not rt:
        return jsonify({'error': 'refresh_token wajib diisi'}), 400
    try:
        from auth import _supabase_url, _anon_key
        resp = _req.post(
            _supabase_url() + '/auth/v1/token?grant_type=refresh_token',
            json={'refresh_token': rt},
            headers={'Content-Type': 'application/json', 'apikey': _anon_key()},
            timeout=10
        )
        if resp.status_code != 200:
            return jsonify({'error': 'Refresh failed'}), 401
        result = resp.json()
        return jsonify({
            'access_token': result.get('access_token'),
            'refresh_token': result.get('refresh_token'),
            'expires_in': result.get('expires_in', 3600)
        })
    except Exception as e:
        print(f'[AUTH] Refresh error: {e}', flush=True)
        return jsonify({'error': 'Refresh failed'}), 500


@app.route('/api/users', methods=['GET'])
@require_role('super_admin')
def api_list_users():
    """List semua user profiles."""
    conn = _get_db_conn()
    if not conn:
        return _error_response("Database tidak tersedia", status_code=503)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, role, entity_type, entity_id, display_name, created_at "
            "FROM user_profiles ORDER BY created_at"
        )
        rows = cur.fetchall()
        cur.close()
        users = [{
            'id': str(r[0]),
            'role': r[1],
            'entity_type': r[2],
            'entity_id': r[3],
            'display_name': r[4],
            'created_at': str(r[5]) if r[5] else None
        } for r in rows]
        return jsonify(users)
    except Exception as e:
        return _error_response("Gagal fetch users", detail=e, status_code=500)
    finally:
        _return_db_conn(conn)


@app.route('/api/users', methods=['POST'])
@require_role('super_admin')
def api_create_user():
    """Create user via Supabase Auth Admin API + insert profile."""
    data = request.get_json(silent=True)
    if not data:
        return _error_response("Request body wajib diisi")
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', '').strip()
    display_name = data.get('display_name', '').strip()
    entity_type = data.get('entity_type') or None
    entity_id = data.get('entity_id') or None

    if not email or not password or not role or not display_name:
        return _error_response("email, password, role, display_name wajib diisi")
    if role not in ('pengawas', 'super_admin', 'pakd', 'kustodian'):
        return _error_response(f"Role tidak valid: {role}")

    result = create_supabase_user(email, password, display_name, role, entity_type, entity_id)
    if 'error' in result:
        return jsonify(result), 400
    write_audit("CREATE_USER", f"Buat user {email} role={role}")
    return jsonify(result), 201


@app.route('/api/users/<user_id>', methods=['DELETE'])
@require_role('super_admin')
def api_delete_user(user_id):
    """Delete user via Supabase Auth Admin API + cascade profile."""
    result = delete_supabase_user(user_id)
    if 'error' in result:
        return jsonify(result), 400
    write_audit("DELETE_USER", f"Hapus user {user_id}")
    return jsonify(result)


@app.route("/api/pakd", methods=["GET"])
@require_auth
def get_pakd():
    user = g.current_user
    pakd_list = load_pakd()
    if user['role'] in ('pakd', 'kustodian') and user.get('entity_id'):
        pakd_list = [p for p in pakd_list if p['id'] == user['entity_id']]
    return jsonify(pakd_list)

@app.route("/api/pakd", methods=["POST"])
@require_super_admin_or_token
def create_pakd():
    body = request.get_json(force=True)
    if not body.get("id") or not body.get("nama"):
        return _error_response("id dan nama wajib diisi")
    data = load_pakd()
    if any(p["id"] == body["id"] for p in data):
        return _error_response(f"PAKD {body['id']} sudah ada", status_code=409)
    incoming_wallets = body.get("wallets", [])
    ok, conflict_msg = _check_wallet_uniqueness(incoming_wallets, body["id"], data)
    if not ok:
        return _error_response(conflict_msg, status_code=409)
    new_pakd = {
        "id": body["id"],
        "nama": body["nama"],
        "aset_dilaporkan": body.get("aset_dilaporkan", 0),
        "equity_idr": body.get("equity_idr"),
        "persediaan_akd_idr": body.get("persediaan_akd_idr"),
        "simpanan_pedagang_akd_idr": body.get("simpanan_pedagang_akd_idr"),
        "customer_akd_idr": body.get("customer_akd_idr"),
        "wallets": body.get("wallets", []),
    }
    data.append(new_pakd)
    save_pakd(data)
    write_audit("CREATE_PAKD", f"Tambah {body['id']} - {body['nama']}")
    return jsonify(new_pakd), 201

@app.route("/api/pakd/<pakd_id>/recalc-snapshot", methods=["POST"])
@require_super_admin_or_token
def recalc_snapshot(pakd_id):
    """Recalculate snapshot deviasi from existing on-chain data without blockchain re-fetch.

    Tidak menghasilkan kelengkapan_status/sumber_gagal/provenance_harga/
    aset_onchain_idr_final/subtotal_diketahui_idr: fungsi ini tidak fetch
    on-chain baru dan tidak memanggil hitung_kelengkapan(). Kolom tersebut
    NULL by design (Opsi A, lihat core/verdict.py), bukan gap sementara.
    """
    conn = _get_db_conn()
    if not conn:
        return jsonify({"error": "DB unavailable"}), 503
    try:
        cur = conn.cursor()
        # Get latest on-chain data from snapshot
        cur.execute(
            "SELECT aset_onchain_idr, network_breakdown, harga_fallback "
            "FROM reconciliation_snapshots WHERE pakd_id = %s ORDER BY created_at DESC LIMIT 1",
            (pakd_id,)
        )
        snap = cur.fetchone()
        if not snap:
            cur.close()
            _return_db_conn(conn)
            return jsonify({"error": "Tidak ada snapshot sebelumnya untuk PAKD ini"}), 404
        aset_onchain = snap[0]
        breakdown = snap[1]
        harga_fallback = snap[2]
        # Get aset_dilaporkan: prefer e-reporting, fallback to pakd table
        cur.execute("SELECT nama, aset_dilaporkan FROM pakd WHERE id = %s", (pakd_id,))
        pakd = cur.fetchone()
        if not pakd:
            cur.close()
            _return_db_conn(conn)
            return jsonify({"error": "PAKD tidak ditemukan"}), 404
        pakd_nama = pakd[0]
        aset_dilaporkan = _get_aset_dilaporkan(pakd_id, fallback=pakd[1] or 0, conn=conn)
        # Recalculate deviasi (includes prorated custody share)
        _c3070_pre = compute_30_70_compliance(pakd_id, int(aset_onchain), conn=conn)
        _total_attr, deviasi = deviasi_with_custody(
            aset_onchain, (_c3070_pre.get("kustodian_onchain_idr") or 0), aset_dilaporkan)
        if aset_dilaporkan == 0:
            deviasi = 0.0 if _total_attr == 0 else 9999.9999
        deviasi_clamped = max(-9999.9999, min(9999.9999, deviasi))
        surplus = _total_attr >= aset_dilaporkan
        if surplus:
            status = "Aman"
        else:
            deficit_pct = abs(deviasi_clamped)
            if deficit_pct < 0.01:
                status = "Aman"
            elif deficit_pct <= 10:
                status = "Deviasi"
            else:
                status = "Kritis"
        # Insert new snapshot with 30/70 compliance (computed above for deviasi)
        c3070 = _c3070_pre

        cur.execute(
            """INSERT INTO reconciliation_snapshots
               (pakd_id, pakd_nama, aset_dilaporkan_idr, aset_onchain_idr,
                deviasi_persen, status, harga_fallback, network_breakdown,
                pakd_onchain_idr, kustodian_onchain_idr, compliance_30_70, ratio_at_pakd, ratio_at_ptp,
                kelengkapan_status, sumber_gagal, provenance_harga,
                aset_onchain_idr_final, subtotal_diketahui_idr)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (pakd_id, pakd_nama, int(aset_dilaporkan), int(aset_onchain),
             deviasi_clamped, status, harga_fallback, json.dumps(breakdown) if isinstance(breakdown, (list, dict)) else breakdown,
             int(aset_onchain), c3070.get("kustodian_onchain_idr"),
             c3070.get("compliance_30_70", False), c3070.get("ratio_at_pakd"), c3070.get("ratio_at_ptp"),
             None, None, None, None, None)
        )
        conn.commit()
        cur.close()
        _return_db_conn(conn)
        write_audit("RECALC_SNAPSHOT", f"PAKD {pakd_id}: dilaporkan={aset_dilaporkan}, onchain={aset_onchain}, deviasi={deviasi_clamped:.2f}%")
        return jsonify({"status": "ok", "pakd_id": pakd_id, "aset_dilaporkan": aset_dilaporkan, "aset_onchain": aset_onchain, "deviasi_pct": round(deviasi_clamped, 4), "status_rekonsiliasi": status})
    except Exception as e:
        print(f"[RECALC] failed: {type(e).__name__}: {e}", flush=True)
        _return_db_conn(conn)
        return jsonify({"error": str(e)}), 500

@app.route("/api/pakd/<pakd_id>", methods=["PUT"])
@require_super_admin_or_token
def update_pakd(pakd_id):
    body = request.get_json(force=True)
    data = load_pakd()
    for i, p in enumerate(data):
        if p["id"] == pakd_id:
            data[i]["nama"] = body.get("nama", p["nama"])
            data[i]["aset_dilaporkan"] = body.get("aset_dilaporkan", p["aset_dilaporkan"])
            data[i]["equity_idr"] = body.get("equity_idr", p.get("equity_idr"))
            data[i]["persediaan_akd_idr"] = body.get("persediaan_akd_idr", p.get("persediaan_akd_idr"))
            data[i]["simpanan_pedagang_akd_idr"] = body.get("simpanan_pedagang_akd_idr", p.get("simpanan_pedagang_akd_idr"))
            data[i]["customer_akd_idr"] = body.get("customer_akd_idr", p.get("customer_akd_idr"))
            if "wallets" in body:
                ok, conflict_msg = _check_wallet_uniqueness(body["wallets"], pakd_id, data)
                if not ok:
                    return _error_response(conflict_msg, status_code=409)
                data[i]["wallets"] = body["wallets"]
            save_pakd(data)
            write_audit("UPDATE_PAKD", f"Edit {pakd_id}")
            return jsonify(data[i])
    return _error_response(f"PAKD {pakd_id} tidak ditemukan", status_code=404)

@app.route("/api/pakd/<pakd_id>", methods=["DELETE"])
@require_super_admin_or_token
def delete_pakd(pakd_id):
    data = load_pakd()
    new_data = [p for p in data if p["id"] != pakd_id]
    if len(new_data) == len(data):
        return _error_response(f"PAKD {pakd_id} tidak ditemukan", status_code=404)
    conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM pakd WHERE id = %s", (pakd_id,))
            cur.execute("DELETE FROM reconciliation_snapshots WHERE pakd_id = %s", (pakd_id,))
            conn.commit()
            cur.close()
            _return_db_conn(conn)
        except Exception as e:
            print(f"[DB] delete_pakd failed: {e}", flush=True)
    save_pakd(new_data)
    write_audit("DELETE_PAKD", f"Hapus {pakd_id}")
    return jsonify({"deleted": pakd_id})


# ---------------------------------------------------------------------------
# Kustodian CRUD
# ---------------------------------------------------------------------------

@app.route("/api/kustodian", methods=["GET"])
@require_auth
def api_list_kustodian():
    conn = _get_db_conn()
    if not conn:
        return _error_response("DB unavailable", status_code=503)
    try:
        cur = conn.cursor()
        user = g.current_user

        if user['role'] == 'kustodian' and user.get('entity_id'):
            cur.execute("SELECT id, nama, created_at, updated_at FROM kustodian WHERE id = %s", (user['entity_id'],))
        elif user['role'] == 'pakd' and user.get('entity_id'):
            cur.execute("""
                SELECT k.id, k.nama, k.created_at, k.updated_at
                FROM kustodian k
                JOIN kustodian_pakd kp ON k.id = kp.kustodian_id
                WHERE kp.pakd_id = %s
            """, (user['entity_id'],))
        else:
            cur.execute("SELECT id, nama, created_at, updated_at FROM kustodian ORDER BY id")

        rows = cur.fetchall()
        result = []
        for r in rows:
            kust_id = r[0]
            cur.execute("SELECT pakd_id FROM kustodian_pakd WHERE kustodian_id = %s", (kust_id,))
            pakd_ids = [row[0] for row in cur.fetchall()]
            cur.execute("SELECT network, address, verified, verified_at, pakd_id FROM wallets WHERE entity_type = 'KUSTODIAN' AND entity_id = %s", (kust_id,))
            wallets = [{"network": w[0], "address": w[1], "verified": w[2], "verified_at": str(w[3]) if w[3] else None, "pakd_id": w[4]} for w in cur.fetchall()]
            result.append({
                "id": kust_id,
                "nama": r[1],
                "pakd_ids": pakd_ids,
                "wallets": wallets,
                "created_at": str(r[2]) if r[2] else None,
                "updated_at": str(r[3]) if r[3] else None,
            })
        cur.close()
        _return_db_conn(conn)
        return jsonify(result)
    except Exception as e:
        print(f"[KUSTODIAN] list failed: {e}", flush=True)
        _return_db_conn(conn)
        return _error_response(str(e), status_code=500)


@app.route("/api/kustodian", methods=["POST"])
@require_super_admin_or_token
def api_create_kustodian():
    body = request.get_json(force=True)
    if not body.get("id") or not body.get("nama"):
        return _error_response("id dan nama wajib diisi")

    conn = _get_db_conn()
    if not conn:
        return _error_response("DB unavailable", status_code=503)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM kustodian WHERE id = %s", (body["id"],))
        if cur.fetchone():
            cur.close()
            _return_db_conn(conn)
            return _error_response(f"Kustodian {body['id']} sudah ada", status_code=409)

        incoming_wallets = body.get("wallets", [])
        for w in incoming_wallets:
            valid, msg = validate_wallet_address(w.get("network", ""), w.get("address", ""))
            if not valid:
                cur.close()
                _return_db_conn(conn)
                return _error_response(msg)
            cur.execute("SELECT pakd_id, entity_type, entity_id FROM wallets WHERE network = %s AND LOWER(address) = LOWER(%s)",
                        (w["network"], w["address"]))
            dup = cur.fetchone()
            if dup:
                cur.close()
                _return_db_conn(conn)
                return _error_response(
                    f"Wallet {w['address']} ({w['network']}) sudah terdaftar pada {dup[1]} {dup[2]}.",
                    status_code=409)

        cur.execute("INSERT INTO kustodian (id, nama) VALUES (%s, %s)", (body["id"], body["nama"]))
        for pakd_id in body.get("pakd_ids", []):
            cur.execute("INSERT INTO kustodian_pakd (kustodian_id, pakd_id) VALUES (%s, %s)", (body["id"], pakd_id))
        for w in incoming_wallets:
            cur.execute("""
                INSERT INTO wallets (pakd_id, network, address, verified, verified_at, entity_type, entity_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (w.get("pakd_id") or None, w["network"], w["address"], w.get("verified", False), w.get("verified_at"), "KUSTODIAN", body["id"]))

        conn.commit()
        cur.close()
        _return_db_conn(conn)
        write_audit("CREATE_KUSTODIAN", f"Tambah {body['id']} - {body['nama']}")
        return jsonify({"id": body["id"], "nama": body["nama"], "pakd_ids": body.get("pakd_ids", []), "wallets": incoming_wallets}), 201
    except Exception as e:
        print(f"[KUSTODIAN] create failed: {e}", flush=True)
        try:
            conn.rollback()
            _return_db_conn(conn)
        except Exception:
            pass
        return _error_response(str(e), status_code=500)


@app.route("/api/kustodian/<kust_id>", methods=["PUT"])
@require_super_admin_or_token
def api_update_kustodian(kust_id):
    body = request.get_json(force=True)
    conn = _get_db_conn()
    if not conn:
        return _error_response("DB unavailable", status_code=503)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM kustodian WHERE id = %s", (kust_id,))
        if not cur.fetchone():
            cur.close()
            _return_db_conn(conn)
            return _error_response(f"Kustodian {kust_id} tidak ditemukan", status_code=404)

        if "nama" in body:
            cur.execute("UPDATE kustodian SET nama = %s, updated_at = NOW() WHERE id = %s", (body["nama"], kust_id))

        if "pakd_ids" in body:
            cur.execute("DELETE FROM kustodian_pakd WHERE kustodian_id = %s", (kust_id,))
            for pakd_id in body["pakd_ids"]:
                cur.execute("INSERT INTO kustodian_pakd (kustodian_id, pakd_id) VALUES (%s, %s)", (kust_id, pakd_id))

        if "wallets" in body:
            for w in body["wallets"]:
                valid, msg = validate_wallet_address(w.get("network", ""), w.get("address", ""))
                if not valid:
                    conn.rollback()
                    cur.close()
                    _return_db_conn(conn)
                    return _error_response(msg)
                cur.execute("""
                    SELECT pakd_id, entity_type, entity_id FROM wallets
                    WHERE network = %s AND LOWER(address) = LOWER(%s) AND entity_id != %s
                """, (w["network"], w["address"], kust_id))
                dup = cur.fetchone()
                if dup:
                    conn.rollback()
                    cur.close()
                    _return_db_conn(conn)
                    return _error_response(
                        f"Wallet {w['address']} ({w['network']}) sudah terdaftar pada {dup[1]} {dup[2]}.",
                        status_code=409)

            cur.execute("DELETE FROM wallets WHERE entity_type = 'KUSTODIAN' AND entity_id = %s", (kust_id,))
            for w in body["wallets"]:
                cur.execute("""
                    INSERT INTO wallets (pakd_id, network, address, verified, verified_at, entity_type, entity_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (w.get("pakd_id") or None, w["network"], w["address"], w.get("verified", False), w.get("verified_at"), "KUSTODIAN", kust_id))

        conn.commit()
        cur.close()
        _return_db_conn(conn)
        write_audit("UPDATE_KUSTODIAN", f"Edit {kust_id}")
        return jsonify({"id": kust_id, "updated": True})
    except Exception as e:
        print(f"[KUSTODIAN] update failed: {e}", flush=True)
        try:
            conn.rollback()
            _return_db_conn(conn)
        except Exception:
            pass
        return _error_response(str(e), status_code=500)


@app.route("/api/kustodian/<kust_id>", methods=["DELETE"])
@require_super_admin_or_token
def api_delete_kustodian(kust_id):
    conn = _get_db_conn()
    if not conn:
        return _error_response("DB unavailable", status_code=503)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM kustodian WHERE id = %s", (kust_id,))
        if not cur.fetchone():
            cur.close()
            _return_db_conn(conn)
            return _error_response(f"Kustodian {kust_id} tidak ditemukan", status_code=404)

        cur.execute("DELETE FROM wallets WHERE entity_type = 'KUSTODIAN' AND entity_id = %s", (kust_id,))
        cur.execute("DELETE FROM kustodian_pakd WHERE kustodian_id = %s", (kust_id,))
        cur.execute("DELETE FROM kustodian WHERE id = %s", (kust_id,))
        conn.commit()
        cur.close()
        _return_db_conn(conn)
        write_audit("DELETE_KUSTODIAN", f"Hapus {kust_id}")
        return jsonify({"deleted": kust_id})
    except Exception as e:
        print(f"[KUSTODIAN] delete failed: {e}", flush=True)
        try:
            conn.rollback()
            _return_db_conn(conn)
        except Exception:
            pass
        return _error_response(str(e), status_code=500)


def _get_kustodian_monitoring_data(kust_id, conn):
    """Aggregate monitoring dashboard data for one Kustodian.

    conn is REQUIRED (pool size 1 on Supabase free tier: caller holds the
    connection, helper must never open its own). Returns None when the
    kustodian does not exist.
    """
    cur = conn.cursor()

    cur.execute("SELECT id, nama FROM kustodian WHERE id = %s", (kust_id,))
    kust_row = cur.fetchone()
    if not kust_row:
        cur.close()
        return None

    cur.execute("""
        SELECT kp.pakd_id, p.nama
        FROM kustodian_pakd kp
        JOIN pakd p ON p.id = kp.pakd_id
        WHERE kp.kustodian_id = %s
        ORDER BY kp.pakd_id
    """, (kust_id,))
    linked_pakds = cur.fetchall()

    pakd_ids = [r[0] for r in linked_pakds]
    snapshots = {}
    if pakd_ids:
        cur.execute("""
            SELECT DISTINCT ON (pakd_id)
                pakd_id, kustodian_onchain_idr, compliance_30_70,
                ratio_at_pakd, ratio_at_ptp, captured_at, pakd_onchain_idr
            FROM reconciliation_snapshots
            WHERE pakd_id = ANY(%s)
            ORDER BY pakd_id, captured_at DESC
        """, (pakd_ids,))
        for r in cur.fetchall():
            snapshots[r[0]] = {
                "kustodian_onchain_idr": r[1],
                "compliance_30_70": r[2],
                "ratio_at_pakd": r[3],
                "ratio_at_ptp": r[4],
                "captured_at": r[5],
                "pakd_onchain_idr": r[6],
            }

    pakd_compliance = []
    total_expected_at_ptp = 0
    kustodian_onchain = 0

    for pid, nama in linked_pakds:
        reported = _get_reported_values(pid, conn=conn)
        # T2.4/D33: dihitung SEBELUM .get(pid, {}), karena sesudahnya
        # informasi ini hilang -- PAKD tanpa baris dan PAKD dengan baris
        # berkolom NULL sama-sama menghasilkan None di tiap titik pakai.
        punya_snapshot = pid in snapshots
        snap = snapshots.get(pid, {})

        customer_at_pakd = reported.get("customer_at_pakd_idr", 0) or 0
        customer_at_ptp = reported.get("customer_at_ptp_idr", 0) or 0
        total_expected_at_ptp += customer_at_ptp

        # kustodian_onchain_idr in snapshots is this PAKD's PRORATED share of
        # the kustodian's custody pool (split by reported placement), so the
        # kustodian total is the SUM of shares across linked PAKDs.
        snap_kust_onchain = snap.get("kustodian_onchain_idr")
        if snap_kust_onchain is not None:
            kustodian_onchain += float(snap_kust_onchain)

        captured_at = snap.get("captured_at")
        compliance = bool(snap.get("compliance_30_70")) if snap.get("compliance_30_70") is not None else False
        pakd_compliance.append({
            "pakd_id": pid,
            "nama": nama,
            "customer_at_pakd_idr": customer_at_pakd,
            "customer_at_ptp_idr": customer_at_ptp,
            "pakd_onchain_idr": float(snap.get("pakd_onchain_idr") or 0),
            # D34/D35: float(None) melempar TypeError, jadi cabangnya
            # eksplisit. "or 0" dilepas karena ia meratakan NULL dan nol.
            "kustodian_onchain_idr": (None if snap_kust_onchain is None
                                      else float(snap_kust_onchain)),
            # Presedensi mengikat: belum direkonsiliasi mendahului tidak
            # terukur. PAKD tanpa baris snapshot juga punya
            # snap_kust_onchain None, tapi sebabnya berbeda -- belum
            # pernah diukur, bukan diukur lalu gagal.
            "kustodian_onchain_status": (
                "belum_direkonsiliasi" if not punya_snapshot
                else "tidak_terukur" if snap_kust_onchain is None
                else "terukur"),
            "ratio_at_pakd": float(snap.get("ratio_at_pakd") or 0),
            "compliance_30_70": compliance,
            "status": "COMPLIANT" if compliance else "VIOLATION",
            "latest_snapshot_at": captured_at.isoformat() if captured_at else None,
            # D33: punya_snapshot diturunkan dari keanggotaan pid di dict
            # snapshots, bukan dari captured_at. captured_at bisa NULL pada
            # baris yang ADA, dan baris yang ada berarti rekonsiliasi pernah
            # berjalan -- dua kondisi itu berhimpitan hari ini tapi artinya
            # berbeda.
            "verdict_status": ("COMPLIANT" if compliance else "VIOLATION")
                              if punya_snapshot else "BELUM_DIREKONSILIASI",
            # D16: bernilai "declared" karena ratio_at_pakd dihitung dari
            # customer_at_pakd_idr dan customer_at_ptp_idr, keduanya nilai
            # yang dilaporkan sendiri; tidak ada angka on-chain yang masuk
            # ke perhitungannya.
            "ratio_provenance": "declared" if punya_snapshot else None,
        })

    cur.execute("""
        SELECT network, address, verified, verified_at, pakd_id
        FROM wallets
        WHERE entity_type = 'KUSTODIAN' AND entity_id = %s
        ORDER BY network, address
    """, (kust_id,))
    wallets = []
    for w in cur.fetchall():
        wallets.append({
            "network": w[0],
            "address": w[1],
            "verified": bool(w[2]),
            "verified_at": w[3].isoformat() if hasattr(w[3], "isoformat") else (str(w[3]) if w[3] else None),
            "pakd_id": w[4],
        })
    cur.close()

    verified_count = sum(1 for w in wallets if w["verified"])
    deviation_pct = 0
    if total_expected_at_ptp > 0:
        deviation_pct = round((kustodian_onchain - total_expected_at_ptp) / total_expected_at_ptp * 100, 2)

    return {
        "kustodian": {"id": kust_row[0], "nama": kust_row[1]},
        "summary": {
            "total_onchain_idr": kustodian_onchain,
            "total_expected_at_ptp_idr": total_expected_at_ptp,
            "deviation_pct": deviation_pct,
            "jumlah_pakd": len(linked_pakds),
            "wallet_verified_count": verified_count,
            "wallet_total_count": len(wallets),
            "verification_rate_pct": round(verified_count / len(wallets) * 100, 1) if wallets else 0,
        },
        "pakd_compliance": pakd_compliance,
        "wallets": wallets,
    }


@app.route("/api/kustodian/<kust_id>/monitoring", methods=["GET"])
@require_auth
def api_kustodian_monitoring(kust_id):
    """Kustodian monitoring dashboard (POJK 23/2025 Pasal 91, IOSCO Rec 12).

    Auth scoping:
      - super_admin/pengawas: any kustodian
      - pakd: only kustodian linked to their entity
      - kustodian: only own entity
    """
    user = g.current_user
    if user["role"] == "kustodian":
        if user.get("entity_id") != kust_id:
            return _error_response("forbidden", status_code=403)

    conn = _get_db_conn()
    if not conn:
        return _error_response("DB unavailable", status_code=503)
    try:
        if user["role"] == "pakd":
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM kustodian_pakd WHERE kustodian_id = %s AND pakd_id = %s",
                        (kust_id, user.get("entity_id")))
            linked = cur.fetchone()
            cur.close()
            if not linked:
                _return_db_conn(conn)
                return _error_response("forbidden", status_code=403)

        result = _get_kustodian_monitoring_data(kust_id, conn)
        _return_db_conn(conn)
        if result is None:
            return _error_response(f"Kustodian {kust_id} tidak ditemukan", status_code=404)
        return jsonify(result)
    except Exception as e:
        print(f"[KUSTODIAN] monitoring failed: {type(e).__name__}: {e}", flush=True)
        _return_db_conn(conn)
        return _error_response(str(e), status_code=500)


@app.route("/api/upload-ereporting", methods=["POST"])
@require_super_admin_or_token
def api_upload_ereporting():
    if 'file' not in request.files:
        return _error_response("File wajib disertakan")
    f = request.files['file']
    if not f.filename or not f.filename.lower().endswith('.xlsx'):
        return _error_response("Hanya file .xlsx yang diterima")

    report_type = request.form.get('type', '')
    entity_id = request.form.get('entity_id', '')
    periode = request.form.get('periode', '')

    if report_type not in ('pakd', 'kustodian'):
        return _error_response(f"Tipe laporan tidak valid: {report_type}")
    if not entity_id or not periode:
        return _error_response("entity_id dan periode wajib diisi")

    conn = _get_db_conn()
    if not conn:
        return _error_response("DB unavailable", status_code=503)
    try:
        cur = conn.cursor()
        table = "pakd" if report_type == "pakd" else "kustodian"
        cur.execute(f"SELECT id FROM {table} WHERE id = %s", (entity_id,))
        if not cur.fetchone():
            return _error_response(f"Entity {entity_id} tidak ditemukan", status_code=404)
    finally:
        cur.close()
        _return_db_conn(conn)

    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    tmp_path = tmp.name
    try:
        f.save(tmp_path)
        tmp.close()
        if report_type == 'pakd':
            parsed = parse_pakd_ereporting(tmp_path)
        else:
            parsed = parse_kustodian_wallet_report(tmp_path)
        parsed['entity_id'] = entity_id
        parsed['periode'] = periode
        parsed['report_type'] = report_type
        return jsonify({'status': 'preview', 'data': parsed})
    except Exception as e:
        return _error_response("Gagal parse file", detail=e, status_code=500)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.route("/api/confirm-ereporting", methods=["POST"])
@require_super_admin_or_token
def api_confirm_ereporting():
    data = request.get_json(force=True, silent=True)
    if not data:
        return _error_response("Request body kosong")

    entity_id = data.get('entity_id', '')
    periode = data.get('periode', '')
    report_type = data.get('report_type', '')
    if not all([entity_id, periode, report_type]):
        return _error_response("entity_id, periode, dan report_type wajib diisi")
    if report_type not in ('pakd', 'kustodian'):
        return _error_response(f"Tipe laporan tidak valid: {report_type}")

    uploaded_by = _safe_uuid(g.current_user.get('id'))

    conn = _get_db_conn()
    if not conn:
        return _error_response("DB unavailable", status_code=503)
    try:
        cur = conn.cursor()
        if report_type == 'pakd':
            breakdown = data.get('aset_breakdown', [])
            customer_at_pakd = sum(
                float(r.get('konsumen_di_pedagang_unit', 0) or 0) * float(r.get('harga_per_unit_idr', 0) or 0)
                for r in breakdown
            )
            customer_at_ptp = sum(
                float(r.get('konsumen_di_ptp_unit', 0) or 0) * float(r.get('harga_per_unit_idr', 0) or 0)
                for r in breakdown
            )
            proprietary = sum(
                float(r.get('pedagang_unit', 0) or 0) * float(r.get('harga_per_unit_idr', 0) or 0)
                for r in breakdown
            )
            ekuitas = float(data.get('balance_sheet', {}).get('ekuitas_idr', 0) or 0)
            cur.execute("""
                INSERT INTO laporan_ereporting
                    (entity_type, entity_id, periode, report_type, file_hash,
                     aset_breakdown, balance_sheet, rekening_administratif,
                     customer_at_pakd_idr, customer_at_ptp_idr, proprietary_idr, ekuitas_idr,
                     uploaded_by, status, confirmed_at)
                VALUES ('PAKD', %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        %s, %s, %s, %s,
                        %s, 'confirmed', NOW())
                ON CONFLICT (entity_id, periode, report_type)
                DO UPDATE SET
                    file_hash = EXCLUDED.file_hash,
                    aset_breakdown = EXCLUDED.aset_breakdown,
                    balance_sheet = EXCLUDED.balance_sheet,
                    rekening_administratif = EXCLUDED.rekening_administratif,
                    customer_at_pakd_idr = EXCLUDED.customer_at_pakd_idr,
                    customer_at_ptp_idr = EXCLUDED.customer_at_ptp_idr,
                    proprietary_idr = EXCLUDED.proprietary_idr,
                    ekuitas_idr = EXCLUDED.ekuitas_idr,
                    uploaded_by = EXCLUDED.uploaded_by,
                    status = 'confirmed',
                    confirmed_at = NOW()
            """, (
                entity_id, periode, report_type, data.get('file_hash'),
                json.dumps(breakdown),
                json.dumps(data.get('balance_sheet', {})),
                json.dumps(data.get('rekening_administratif', {})),
                customer_at_pakd, customer_at_ptp, proprietary, ekuitas,
                uploaded_by,
            ))
        else:
            cur.execute("""
                INSERT INTO laporan_ereporting
                    (entity_type, entity_id, periode, report_type, file_hash,
                     wallet_report, uploaded_by, status, confirmed_at)
                VALUES ('KUSTODIAN', %s, %s, %s, %s,
                        %s::jsonb, %s, 'confirmed', NOW())
                ON CONFLICT (entity_id, periode, report_type)
                DO UPDATE SET
                    file_hash = EXCLUDED.file_hash,
                    wallet_report = EXCLUDED.wallet_report,
                    uploaded_by = EXCLUDED.uploaded_by,
                    status = 'confirmed',
                    confirmed_at = NOW()
            """, (
                entity_id, periode, report_type, data.get('file_hash'),
                json.dumps(data.get('wallets', [])),
                uploaded_by,
            ))
        conn.commit()
        cur.close()
        _return_db_conn(conn)
        write_audit("CONFIRM_EREPORTING", f"{report_type} entity={entity_id} periode={periode}")
        return jsonify({'status': 'confirmed', 'entity_id': entity_id, 'periode': periode})
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        _return_db_conn(conn)
        return _error_response("Gagal menyimpan", detail=e, status_code=500)


@app.route("/api/reconciliation")
@require_auth
def reconciliation():
    global _last_rekon_time
    _now = time.time()
    if not app.config.get('TESTING') and _now - _last_rekon_time < REKON_COOLDOWN:
        _sisa = int(REKON_COOLDOWN - (_now - _last_rekon_time))
        return jsonify({'error': f'Cooldown aktif. Tunggu {_sisa} detik.'}), 429
    _last_rekon_time = _now
    try:
        _t_total = time.perf_counter()
        _timings = {}
        pakd_list = load_pakd()
        user = g.current_user
        if user['role'] in ('pakd', 'kustodian') and user.get('entity_id'):
            pakd_list = [p for p in pakd_list if p['id'] == user['entity_id']]
        hasil = []
        _t_fetch = time.perf_counter()

        for pakd in pakd_list:
            wallets = pakd["wallets"]

            balance_result   = get_total_balance_idr(wallets)
            aset_onchain_idr = balance_result["total_idr"]
            _ct = balance_result.get("_chain_timings", {})
            _timings["fetch_eth_total"] = round(_timings.get("fetch_eth_total", 0) + _ct.get("fetch_eth_total", 0), 3)
            _timings["fetch_btc_total"] = round(_timings.get("fetch_btc_total", 0) + _ct.get("fetch_btc_total", 0), 3)
            _timings["fetch_sol_total"] = round(_timings.get("fetch_sol_total", 0) + _ct.get("fetch_sol_total", 0), 3)
            aset_dilaporkan  = _get_aset_dilaporkan(pakd["id"], fallback=pakd.get("aset_dilaporkan", 0))

            compliance_data = compute_30_70_compliance(pakd["id"], aset_onchain_idr)

            # Deviasi counts the PAKD's prorated custody share (reported totals
            # include AKD placed at the PTP, so the on-chain side must too).
            total_attributable, deviasi_pct = deviasi_with_custody(
                aset_onchain_idr, (compliance_data.get("kustodian_onchain_idr") or 0), aset_dilaporkan)
            selisih = total_attributable - aset_dilaporkan if aset_dilaporkan > 0 else 0

            _as_of = datetime.now(timezone.utc).isoformat()
            _kelengkapan = hitung_kelengkapan(
                balance_result["entries"], balance_result["provenance_harga"], _as_of)
            _verdict = tetapkan_verdict_surplus(
                _kelengkapan["status"], total_attributable, aset_dilaporkan, deviasi_pct)
            surplus = _verdict["surplus"]
            status_rec = _verdict["status"]
            _kelengkapan_status_out = _kelengkapan["status"]
            _sumber_gagal_out = _kelengkapan["sumber_gagal"]
            _aset_onchain_idr_final = (
                aset_onchain_idr if _kelengkapan_status_out == "LENGKAP" else None)
            _subtotal_diketahui_idr = aset_onchain_idr


            hasil.append({
                "id":                  pakd["id"],
                "nama":                pakd["nama"],
                "wallets":             wallets,
                "wallet_count":        len(wallets),
                "aset_onchain_idr":    round(aset_onchain_idr),
                "eth_balance_idr":     round(balance_result["eth_balance_idr"]),
                "eth_native_idr":      round(balance_result["eth_native_idr"]),
                "eth_usdt_idr":        round(balance_result["eth_usdt_idr"]),
                "eth_usdc_idr":        round(balance_result["eth_usdc_idr"]),
                "btc_balance_idr":     round(balance_result["btc_balance_idr"]),
                "sol_balance_idr":     round(balance_result["sol_balance_idr"]),
                "sol_native_idr":      round(balance_result["sol_native_idr"]),
                "sol_usdt_idr":        round(balance_result["sol_usdt_idr"]),
                "sol_usdc_idr":        round(balance_result["sol_usdc_idr"]),
                "sol_other_token_idr": round(balance_result.get("sol_other_token_idr", 0)),
                "sol_unvalued_count":  balance_result.get("sol_unvalued_count", 0),
                "sol_unvalued_mints":  balance_result.get("sol_unvalued_mints", []),
                "eth_other_token_idr":    balance_result.get("eth_other_token_idr", 0),
                "eth_unvalued_count":     balance_result.get("eth_unvalued_count", 0),
                "eth_unvalued_contracts": balance_result.get("eth_unvalued_contracts", []),
                "aset_dilaporkan_idr": aset_dilaporkan,
                "deviasi_pct":         _verdict["deviasi_pct"],
                "surplus":             surplus,
                "kelengkapan_status":     _kelengkapan_status_out,
                "sumber_gagal":           _sumber_gagal_out,
                "aset_onchain_idr_final": _aset_onchain_idr_final,
                "subtotal_diketahui_idr": _subtotal_diketahui_idr,
                "status":              status_rec,
                "breakdown":           balance_result["breakdown"],
                "pakd_onchain_idr":           round(aset_onchain_idr),
                "kustodian_onchain_idr":      compliance_data["kustodian_onchain_idr"],
                "compliance_30_70":           compliance_data["compliance_30_70"],
                "ratio_at_pakd":              compliance_data["ratio_at_pakd"],
                "ratio_at_ptp":               compliance_data["ratio_at_ptp"],
                "kustodian_details":          compliance_data["kustodian_details"],
                "has_kustodian":              compliance_data["has_kustodian"],
            })

        _timings["fetch_all_pakd"] = round(time.perf_counter() - _t_fetch, 3)
        write_audit("REKONSILIASI",
                    f"{len(hasil)} PAKD direkonsiliasi (ETH native+USDT+USDC, BTC, SOL) — "
                    f"dipicu oleh {user.get('email') or user.get('id')} ({user.get('role')})")
        # Resolve harga_fallback flag from ETH price fetch
        _t0 = time.perf_counter()
        _, eth_fallback = get_eth_price_idr()
        _timings["pricing_eth_fallback"] = round(time.perf_counter() - _t0, 3)
        # Save snapshot to Supabase (non-blocking)
        _t0 = time.perf_counter()
        _save_snapshots_batch(hasil, eth_fallback)
        _timings["db_write"] = round(time.perf_counter() - _t0, 3)
        _timings["total"] = round(time.perf_counter() - _t_total, 3)
        resp = {
            "data":          hasil,
            "total_pakd":    len(hasil),
            "harga_fallback": eth_fallback,
        }
        if os.environ.get("PRIMA_DEBUG"):
            resp["_timings"] = _timings
        return jsonify(resp)

    except Exception as e:
        return _error_response("Rekonsiliasi gagal", detail=e, status_code=500)


@app.route("/api/internal/refresh-all", methods=["POST"])
def internal_refresh_all():
    import time as _time
    token = request.headers.get("X-Internal-Token", "")
    _expected_internal = os.environ.get("INTERNAL_TOKEN")
    if not _expected_internal or not hmac.compare_digest(token, _expected_internal):
        return jsonify({"status": "unauthorized"}), 401
    if REFRESH_LOCK["running"]:
        return jsonify({"status": "skipped", "reason": "previous run still active",
                        "started_at": REFRESH_LOCK["started_at"]}), 409
    REFRESH_LOCK["running"] = True
    REFRESH_LOCK["started_at"] = _time.time()
    try:
        pakd_list = load_pakd()
        hasil = []
        for pakd in pakd_list:
            result_bal = get_total_balance_idr(pakd.get("wallets", []))
            total = result_bal["total_idr"]
            breakdown = result_bal["breakdown"]
            dilaporkan = _get_aset_dilaporkan(pakd["id"], fallback=pakd.get("aset_dilaporkan", 0))
            compliance_data = compute_30_70_compliance(pakd["id"], int(total))
            total_attributable, deviasi = deviasi_with_custody(
                total, (compliance_data.get("kustodian_onchain_idr") or 0), dilaporkan)
            _as_of = datetime.now(timezone.utc).isoformat()
            _kelengkapan = hitung_kelengkapan(
                result_bal["entries"], result_bal["provenance_harga"], _as_of)
            # D49: disatukan ke ambang surplus/defisit (0.01%/10%), lebih ketat
            # dari ternary lama (5%/20%) -- keputusan mentor 24 Agustus 2026.
            # Lihat core/verdict.py untuk detail keputusan dan alasan.
            _verdict = tetapkan_verdict_surplus(
                _kelengkapan["status"], total_attributable, dilaporkan, deviasi)
            status = _verdict["status"]
            _kelengkapan_status_out = _kelengkapan["status"]
            _sumber_gagal_out = _kelengkapan["sumber_gagal"]
            _aset_onchain_idr_final = (
                total if _kelengkapan_status_out == "LENGKAP" else None)
            _subtotal_diketahui_idr = total
            hasil.append({
                "id": pakd["id"], "nama": pakd["nama"],
                "aset_dilaporkan_idr": dilaporkan,
                "aset_onchain_idr": total,
                "deviasi_pct": _verdict["deviasi_pct"],
                "status": status,
                "kelengkapan_status":     _kelengkapan_status_out,
                "sumber_gagal":           _sumber_gagal_out,
                "aset_onchain_idr_final": _aset_onchain_idr_final,
                "subtotal_diketahui_idr": _subtotal_diketahui_idr,
                "breakdown": breakdown,
                "pakd_onchain_idr": int(total),
                "kustodian_onchain_idr": compliance_data["kustodian_onchain_idr"],
                "compliance_30_70": compliance_data["compliance_30_70"],
                "ratio_at_pakd": compliance_data["ratio_at_pakd"],
                "ratio_at_ptp": compliance_data["ratio_at_ptp"],
            })
        _, eth_fallback = get_eth_price_idr()
        _save_snapshots_batch(hasil, eth_fallback)
        return jsonify({"status": "ok", "pakd_refreshed": len(hasil),
                        "timestamp": _time.time()})
    except Exception as e:
        return _error_response("Internal refresh gagal", detail=e, status_code=500)
    finally:
        REFRESH_LOCK["running"] = False
        REFRESH_LOCK["started_at"] = None

@app.route("/api/reconciliation/latest")
@require_auth
def reconciliation_latest():
    conn = _get_db_conn()
    if not conn:
        return _error_response("Database tidak tersedia", status_code=503)
    try:
        import psycopg2.extras
        cur = conn.cursor()
        user = g.current_user
        _snap_cols = """s.pakd_id, s.pakd_nama, s.aset_dilaporkan_idr, s.aset_onchain_idr,
                    s.deviasi_persen, s.status, s.harga_fallback, s.network_breakdown, s.captured_at, s.created_at,
                    s.pakd_onchain_idr, s.kustodian_onchain_idr, s.compliance_30_70, s.ratio_at_pakd, s.ratio_at_ptp,
                    s.kelengkapan_status, s.sumber_gagal, s.provenance_harga,
                    s.aset_onchain_idr_final, s.subtotal_diketahui_idr"""
        if user['role'] in ('pakd', 'kustodian') and user.get('entity_id'):
            cur.execute(f"""
                SELECT DISTINCT ON (s.pakd_id) {_snap_cols}
                FROM reconciliation_snapshots s
                INNER JOIN pakd p ON p.id = s.pakd_id
                WHERE s.pakd_id = %s
                ORDER BY s.pakd_id, s.captured_at DESC
            """, (user['entity_id'],))
        else:
            cur.execute(f"""
                SELECT DISTINCT ON (s.pakd_id) {_snap_cols}
                FROM reconciliation_snapshots s
                INNER JOIN pakd p ON p.id = s.pakd_id
                ORDER BY s.pakd_id, s.captured_at DESC
            """)
        rows = cur.fetchall()
        # Build set of pakd_ids that have linked kustodian
        pakd_ids = [r[0] for r in rows]
        pakd_with_kustodian = set()
        if pakd_ids:
            cur.execute("SELECT DISTINCT pakd_id FROM kustodian_pakd WHERE pakd_id = ANY(%s)", (pakd_ids,))
            pakd_with_kustodian = {r2[0] for r2 in cur.fetchall()}
        hasil = []
        as_of = None
        for r in rows:
            captured_at = r[8]
            if as_of is None or captured_at > as_of:
                as_of = captured_at
            network_breakdown = r[7] if isinstance(r[7], list) else []
            eth_idr = sum((w.get("balance_idr") or 0) for w in network_breakdown if w.get("network") == "ethereum")
            btc_idr = sum((w.get("balance_idr") or 0) for w in network_breakdown if w.get("network") == "bitcoin")
            sol_idr = sum((w.get("balance_idr") or 0) for w in network_breakdown if w.get("network") == "solana")
            has_kustodian = r[0] in pakd_with_kustodian
            compliance_30_70 = r[12] if r[12] is not None else False
            ratio_at_pakd = float(r[13]) if r[13] is not None else (1.0 if not has_kustodian else 0.0)
            ratio_at_ptp = float(r[14]) if r[14] is not None else 0.0

            hasil.append({
                "id":                   r[0],
                "nama":                 r[1],
                "aset_dilaporkan_idr":  r[2],
                "aset_onchain_idr":     r[3],
                "deviasi_pct":          r[4],
                "status":               r[5],
                "harga_fallback":       r[6],
                "eth_balance_idr":      round(eth_idr),
                "btc_balance_idr":      round(btc_idr),
                "sol_balance_idr":      round(sol_idr),
                "captured_at":          captured_at.isoformat() if captured_at else None,
                "network_breakdown":    network_breakdown,
                "pakd_onchain_idr":     r[10],
                "kustodian_onchain_idr": r[11],
                # D34/D35: baris di sini selalu berasal dari snapshot,
                # jadi "belum_direkonsiliasi" tidak berlaku.
                "kustodian_onchain_status": ("tidak_terukur" if r[11] is None
                                             else "terukur"),
                "compliance_30_70":     compliance_30_70,
                "ratio_at_pakd":        ratio_at_pakd,
                "ratio_at_ptp":         ratio_at_ptp,
                "has_kustodian":        has_kustodian,
                "kelengkapan_status":     r[15],
                "sumber_gagal":           r[16],
                "provenance_harga":       r[17],
                "aset_onchain_idr_final": r[18],
                "subtotal_diketahui_idr": r[19],
            })
            # Item 2 (Opsi 1, kompromi sesi 23 Agu 2026): verdict indikatif dari
            # data yang diketahui, TANPA porsi kustodian (D49 rumus resmi pakai
            # deviasi_with_custody -- ini sengaja lebih sederhana, dilabeli
            # eksplisit di UI, bukan pengganti verdict resmi). Properti aman:
            # subtotal_diketahui_idr adalah worst-case (wallet gagal = 0), jadi
            # kalau indikatif sudah Aman, verdict sungguhan tidak mungkin lebih
            # buruk -- hanya bisa membaik saat data yang hilang ditemukan.
            _kel = r[15]
            if _kel is not None and _kel != "LENGKAP" and r[2]:
                _subtotal = r[19] if r[19] is not None else 0
                _dilaporkan = r[2]
                _dev_ind = ((_subtotal - _dilaporkan) / _dilaporkan) * 100
                if _dev_ind >= -0.0001:
                    _status_ind = "Aman"
                elif abs(_dev_ind) <= 20:
                    _status_ind = "Deviasi"
                else:
                    _status_ind = "Kritis"
                hasil[-1]["status_indikatif"] = _status_ind
                hasil[-1]["deviasi_pct_indikatif"] = round(_dev_ind, 2)
        cur.close()
        _return_db_conn(conn)
        log_data_access("snapshot rekonsiliasi terbaru (/api/reconciliation/latest)",
                        f"{len(hasil)} PAKD")
        return jsonify({
            "data":       hasil,
            "total_pakd": len(hasil),
            "as_of":      as_of.isoformat() if as_of else None,
            "source":     "snapshot",
        })
    except Exception as e:
        return _error_response(str(e), status_code=500)


@app.route("/api/reconciliation-history")
@require_auth
def reconciliation_history():
    # Entity access check sebelum DB (agar 403 tidak tertutup 503)
    user = g.current_user
    pakd_id = request.args.get("pakd_id")
    if user['role'] in ('pakd', 'kustodian') and user.get('entity_id'):
        if pakd_id and pakd_id != user['entity_id']:
            return jsonify({'error': 'Forbidden', 'message': 'Anda hanya dapat mengakses data entity sendiri'}), 403
        pakd_id = user['entity_id']

    conn = _get_db_conn()
    if not conn:
        return _error_response("Database tidak tersedia", status_code=503)
    try:
        limit = min(int(request.args.get("limit", 30)), 100)
        cur = conn.cursor()
        if pakd_id:
            cur.execute(
                """SELECT id, captured_at, pakd_id, pakd_nama,
                          aset_dilaporkan_idr, aset_onchain_idr,
                          deviasi_persen, status, harga_fallback, network_breakdown,
                          kelengkapan_status, sumber_gagal,
                          aset_onchain_idr_final, subtotal_diketahui_idr
                   FROM reconciliation_snapshots
                   WHERE pakd_id = %s
                   ORDER BY captured_at DESC LIMIT %s""",
                (pakd_id, limit)
            )
        else:
            cur.execute(
                """SELECT id, captured_at, pakd_id, pakd_nama,
                          aset_dilaporkan_idr, aset_onchain_idr,
                          deviasi_persen, status, harga_fallback, network_breakdown,
                          kelengkapan_status, sumber_gagal,
                          aset_onchain_idr_final, subtotal_diketahui_idr
                   FROM reconciliation_snapshots
                   ORDER BY captured_at DESC LIMIT %s""",
                (limit,)
            )
        rows = cur.fetchall()
        hasil = []
        for r in rows:
            _kel_h = r[10]
            _subtotal_h = r[13]
            entry = {
                "id":                  r[0],
                "captured_at":         r[1].isoformat() if r[1] else None,
                "pakd_id":             r[2],
                "pakd_nama":           r[3],
                "aset_dilaporkan_idr": r[4],
                "aset_onchain_idr":    r[5],
                "deviasi_persen":      float(r[6]) if r[6] is not None else None,
                "status":              r[7],
                "harga_fallback":      r[8],
                "network_breakdown":   r[9] if r[9] is not None else [],
                "kelengkapan_status":     _kel_h,
                "sumber_gagal":           r[11],
                "aset_onchain_idr_final": r[12],
                "subtotal_diketahui_idr": _subtotal_h,
            }
            # Item 2 (Opsi 1): sama seperti /api/reconciliation/latest, indikatif
            # sederhana tanpa porsi kustodian, worst-case-safe.
            if _kel_h is not None and _kel_h != "LENGKAP" and r[4]:
                _subtotal_val = _subtotal_h if _subtotal_h is not None else 0
                _dilaporkan_h = r[4]
                _dev_ind_h = ((_subtotal_val - _dilaporkan_h) / _dilaporkan_h) * 100
                if _dev_ind_h >= -0.0001:
                    _status_ind_h = "Aman"
                elif abs(_dev_ind_h) <= 20:
                    _status_ind_h = "Deviasi"
                else:
                    _status_ind_h = "Kritis"
                entry["status_indikatif"] = _status_ind_h
                entry["deviasi_pct_indikatif"] = round(_dev_ind_h, 2)
            hasil.append(entry)
        log_data_access("riwayat rekonsiliasi (/api/reconciliation-history)",
                        f"pakd_id={pakd_id}" if pakd_id else "semua PAKD")
        return jsonify({"data": hasil, "total": len(hasil)})
    except Exception as e:
        return _error_response(str(e), status_code=500)
    finally:
        _return_db_conn(conn)


@app.route("/api/stress-test")
@require_auth
def stress_test():
    user = g.current_user
    pakd_id = request.args.get("pakd_id")
    if user['role'] in ('pakd', 'kustodian') and user.get('entity_id'):
        if pakd_id and pakd_id != user['entity_id']:
            return jsonify({'error': 'Forbidden'}), 403
        pakd_id = user['entity_id']

    pakd_list = [p for p in load_pakd() if p["id"] == pakd_id] if pakd_id else load_pakd()
    if not pakd_list:
        return jsonify({"error": f"PAKD {pakd_id} tidak ditemukan"}), 404
    """
    Dual stress test: Pasal 50 (Risiko Pasar) + Pasal 91 (Risiko Siber).

    Pasal 50 (Risiko Pasar) — POJK No. 27 Tahun 2024, Pasal 50(1)(o):
      Threshold: equity_post >= EQUITY_MINIMUM_IDR (Rp 50.000.000.000)
      Volatile drop: mild -25%, moderate -50%, severe -80%
      Stablecoin drop: mild -3%, moderate -8%, severe -13%
      Historical basis:
        BTC -64% in 2022 (Chainalysis Crypto Crime Report 2024)
        BTC -84% Nov 2017 ATH to Dec 2018 bottom (CoinMarketCap historical)
        USDC depeg to USD 0.87 on 11 Mar 2023 / SVB collapse (Reuters)

    Pasal 91 (Risiko Siber) — POJK No. 27 Tahun 2024, Pasal 91(1):
      Threshold: equity_post >= EQUITY_MINIMUM_IDR (Rp 50.000.000.000)
      Loss base: customer_akd_idr if available, else aset_onchain_idr (proxy)
      Historical basis:
        mild  -23%: GDAC April 2023, $13M of $57M lost (Chainalysis 2024)
        mod   -50%: WazirX July 2024, $235M of ~$500M lost (Elliptic/Reuters)
        severe -100%: Mt Gox 2014, 850,000 BTC, 100% customer AKD (public record)
    """
    try:
        eth_price, harga_fallback = get_eth_price_idr()
        try:
            btc_price = get_cached_price("bitcoin", fetch_btc_price_idr)
        except Exception:
            btc_price = 0.0
        try:
            sol_price = get_cached_price("solana", fetch_sol_price_idr)
        except Exception:
            sol_price = 0.0
        try:
            usdt_price, usdc_price = _get_stablecoin_prices_idr()
        except Exception:
            usdt_price = FALLBACK_STABLECOIN_IDR
            usdc_price = FALLBACK_STABLECOIN_IDR

        # Baseline: Supabase snapshot (production) atau get_total_balance_idr (testing)
        baseline_result = {}
        if app.config.get("TESTING"):
            for pakd in pakd_list:
                result = get_total_balance_idr(
                    pakd["wallets"],
                    eth_price_idr=eth_price,
                    btc_price_idr=btc_price,
                    sol_price_idr=sol_price,
                    usdt_price_idr=usdt_price,
                    usdc_price_idr=usdc_price,
                )
                baseline_result[pakd["id"]] = result
        else:
            import psycopg2, json as _json
            _db = psycopg2.connect(os.environ["DATABASE_URL"])
            _cur = _db.cursor()
            for pakd in pakd_list:
                _cur.execute(
                    "SELECT aset_onchain_idr, network_breakdown FROM reconciliation_snapshots "
                    "WHERE pakd_id = %s ORDER BY created_at DESC LIMIT 1",
                    (pakd["id"],)
                )
                row = _cur.fetchone()
                if row:
                    total_idr = float(row[0] or 0)
                    nb = row[1] if isinstance(row[1], list) else []
                    eth_native   = sum(w.get("eth_native_idr", 0) or 0 for w in nb if w.get("network") == "ethereum")
                    eth_usdt     = sum(w.get("usdt_idr", 0) or 0 for w in nb if w.get("network") == "ethereum")
                    eth_usdc     = sum(w.get("usdc_idr", 0) or 0 for w in nb if w.get("network") == "ethereum")
                    eth_other    = sum(w.get("eth_other_token_idr", 0) or 0 for w in nb if w.get("network") == "ethereum")
                    btc_idr      = sum(w.get("balance_idr", 0) or 0 for w in nb if w.get("network") == "bitcoin")
                    sol_native   = sum(w.get("sol_native_idr", 0) or 0 for w in nb if w.get("network") == "solana")
                    sol_usdt     = sum(w.get("sol_usdt_idr", 0) or 0 for w in nb if w.get("network") == "solana")
                    sol_usdc     = sum(w.get("sol_usdc_idr", 0) or 0 for w in nb if w.get("network") == "solana")
                    sol_other    = sum(w.get("sol_other_token_idr", 0) or 0 for w in nb if w.get("network") == "solana")
                    baseline_result[pakd["id"]] = {
                        "total_idr": total_idr,
                        "eth_native_idr": eth_native,
                        "eth_usdt_idr": eth_usdt,
                        "eth_usdc_idr": eth_usdc,
                        "eth_other_token_idr": eth_other,
                        "btc_balance_idr": btc_idr,
                        "sol_native_idr": sol_native,
                        "sol_usdt_idr": sol_usdt,
                        "sol_usdc_idr": sol_usdc,
                        "sol_other_token_idr": sol_other,
                    }
                else:
                    baseline_result[pakd["id"]] = {"total_idr": 0, "eth_native_idr": 0,
                        "eth_usdt_idr": 0, "eth_usdc_idr": 0, "eth_other_token_idr": 0,
                        "btc_balance_idr": 0, "sol_native_idr": 0, "sol_usdt_idr": 0,
                        "sol_usdc_idr": 0, "sol_other_token_idr": 0}
            _cur.close()
            _db.close()

        # ----------------------------------------------------------------
        # Pasal 50: Risiko Pasar
        # ----------------------------------------------------------------
        hasil_pasal50 = {}
        for key, s in SKENARIO_PASAL50.items():
            v_drop = s["volatile_drop"]
            s_drop = s["stable_drop"]
            eth_stressed  = eth_price  * (1 - v_drop)
            btc_stressed  = btc_price  * (1 - v_drop)
            sol_stressed  = sol_price  * (1 - v_drop)
            usdt_stressed = usdt_price * (1 - s_drop)
            usdc_stressed = usdc_price * (1 - s_drop)

            lulus = gagal = 0
            per_pakd = []

            for pakd in pakd_list:
                b = baseline_result[pakd["id"]]
                aset_stressed = (
                    b.get("eth_native_idr", 0)      * (1 - v_drop)
                    + b.get("eth_usdt_idr", 0)      * (1 - s_drop)
                    + b.get("eth_usdc_idr", 0)      * (1 - s_drop)
                    + b.get("eth_other_token_idr", 0)
                    + b.get("btc_balance_idr", 0)   * (1 - v_drop)
                    + b.get("sol_native_idr", 0)    * (1 - v_drop)
                    + b.get("sol_usdt_idr", 0)      * (1 - s_drop)
                    + b.get("sol_usdc_idr", 0)      * (1 - s_drop)
                    + b.get("sol_other_token_idr", 0)
                )
                aset_baseline = b["total_idr"]

                equity_idr = pakd.get("equity_idr")
                if equity_idr is not None:
                    # equity_post = equity + perubahan nilai aset kripto
                    equity_post  = equity_idr + (aset_stressed - aset_baseline)
                    equity_sumber = "dilaporkan"
                else:
                    # Proxy konservatif: treat aset_onchain sebagai equity
                    equity_post  = aset_stressed
                    equity_sumber = "proxy_onchain"

                lulus_flag = equity_post >= EQUITY_MINIMUM_IDR
                lulus += 1 if lulus_flag else 0
                gagal += 0 if lulus_flag else 1

                per_pakd.append({
                    "id":               pakd["id"],
                    "nama":             pakd["nama"],
                    "aset_onchain_idr": round(aset_baseline),
                    "aset_stressed":    round(aset_stressed),
                    "equity_post":      round(equity_post),
                    "equity_sumber":    equity_sumber,
                    "threshold":        EQUITY_MINIMUM_IDR,
                    "lulus":            lulus_flag,
                })

            hasil_pasal50[key] = {
                "label":         s["label"],
                "volatile_drop": v_drop,
                "stable_drop":   s_drop,
                "lulus":         lulus,
                "gagal":         gagal,
                "total":         len(pakd_list),
                "eth_stressed":  round(eth_stressed),
                "btc_stressed":  round(btc_stressed),
                "sol_stressed":  round(sol_stressed),
                "usdt_stressed": round(usdt_stressed, 2),
                "usdc_stressed": round(usdc_stressed, 2),
                "per_pakd":      per_pakd,
            }

        # ----------------------------------------------------------------
        # Pasal 91: Risiko Siber
        # ----------------------------------------------------------------
        hasil_pasal91 = {}
        for key, s in SKENARIO_PASAL91.items():
            loss_pct = s["loss"]
            lulus = gagal = 0
            per_pakd = []

            for pakd in pakd_list:
                aset_onchain = baseline_result[pakd["id"]]["total_idr"]

                customer_akd = pakd.get("customer_akd_idr")
                if customer_akd is not None:
                    loss_idr   = customer_akd * loss_pct
                    loss_sumber = "customer_akd"
                else:
                    loss_idr   = aset_onchain * loss_pct
                    loss_sumber = "proxy_onchain"

                equity_idr = pakd.get("equity_idr")
                if equity_idr is not None:
                    equity_post   = equity_idr - loss_idr
                    equity_sumber = "dilaporkan"
                else:
                    equity_post   = aset_onchain - loss_idr
                    equity_sumber = "proxy_onchain"

                lulus_flag = equity_post >= EQUITY_MINIMUM_IDR
                lulus += 1 if lulus_flag else 0
                gagal += 0 if lulus_flag else 1

                per_pakd.append({
                    "id":                pakd["id"],
                    "nama":              pakd["nama"],
                    "aset_onchain_idr":  round(aset_onchain),
                    "customer_akd_idr":  round(customer_akd) if customer_akd is not None else None,
                    "loss_idr":          round(loss_idr),
                    "loss_sumber":       loss_sumber,
                    "equity_post":       round(equity_post),
                    "equity_sumber":     equity_sumber,
                    "threshold":         EQUITY_MINIMUM_IDR,
                    "lulus":             lulus_flag,
                })

            hasil_pasal91[key] = {
                "label":    s["label"],
                "loss_pct": loss_pct,
                "lulus":    lulus,
                "gagal":    gagal,
                "total":    len(pakd_list),
                "per_pakd": per_pakd,
            }

        # ----------------------------------------------------------------
        # Risiko Siber 30/70: Attack vector scenarios
        # PAKD-only breach, Kustodian-only breach, Both breached
        # ----------------------------------------------------------------
        hasil_cyber_3070 = {}
        attack_vectors = {
            "pakd_only":      {"label": "Breach di PAKD saja",      "pakd_loss": 1.0, "kust_loss": 0.0},
            "kustodian_only": {"label": "Breach di Kustodian saja", "pakd_loss": 0.0, "kust_loss": 1.0},
            "both":           {"label": "Breach di PAKD + Kustodian","pakd_loss": 1.0, "kust_loss": 1.0},
        }
        kust_onchain_map = {}
        if not app.config.get("TESTING"):
            import psycopg2 as _pg2
            _db2 = _pg2.connect(os.environ["DATABASE_URL"])
            _cur2 = _db2.cursor()
            for pakd in pakd_list:
                _cur2.execute(
                    "SELECT kustodian_onchain_idr FROM reconciliation_snapshots "
                    "WHERE pakd_id = %s ORDER BY created_at DESC LIMIT 1",
                    (pakd["id"],)
                )
                row = _cur2.fetchone()
                kust_onchain_map[pakd["id"]] = float(row[0] or 0) if row else 0.0
            _cur2.close()
            _db2.close()

        for vec_key, vec in attack_vectors.items():
            per_pakd = []
            lulus = gagal = 0
            for pakd in pakd_list:
                b = baseline_result[pakd["id"]]
                pakd_onchain = b["total_idr"]

                if app.config.get("TESTING"):
                    kust_ids_for, wallets_by_k = _get_kustodian_data_for_pakd(pakd["id"])
                    kust_onchain = 0
                    for kid in kust_ids_for:
                        kw = wallets_by_k.get(kid, [])
                        if kw:
                            kust_onchain += get_total_balance_idr(kw).get("total_idr", 0)
                else:
                    kust_ids_for, _ = _get_kustodian_data_for_pakd(pakd["id"])
                    kust_onchain = kust_onchain_map.get(pakd["id"], 0)

                loss_pakd = pakd_onchain * vec["pakd_loss"]
                loss_kust = kust_onchain * vec["kust_loss"]
                total_loss = loss_pakd + loss_kust

                equity_idr = pakd.get("equity_idr")
                if equity_idr is not None:
                    equity_post = equity_idr - total_loss
                else:
                    equity_post = (pakd_onchain + kust_onchain) - total_loss

                lulus_flag = equity_post >= EQUITY_MINIMUM_IDR
                lulus += 1 if lulus_flag else 0
                gagal += 0 if lulus_flag else 1

                per_pakd.append({
                    "id": pakd["id"],
                    "nama": pakd["nama"],
                    "pakd_onchain_idr": round(pakd_onchain),
                    "kustodian_onchain_idr": round(kust_onchain),
                    "loss_pakd_idr": round(loss_pakd),
                    "loss_kust_idr": round(loss_kust),
                    "total_loss_idr": round(total_loss),
                    "equity_post": round(equity_post),
                    "has_kustodian": len(kust_ids_for) > 0,
                    "threshold": EQUITY_MINIMUM_IDR,
                    "lulus": lulus_flag,
                })

            hasil_cyber_3070[vec_key] = {
                "label": vec["label"],
                "pakd_loss_pct": vec["pakd_loss"],
                "kust_loss_pct": vec["kust_loss"],
                "lulus": lulus,
                "gagal": gagal,
                "total": len(pakd_list),
                "per_pakd": per_pakd,
            }

        write_audit("STRESS TEST", f"Dual stress test (Pasal 50 + Pasal 91 + Cyber Penempatan AKD pada Kustodian) untuk {len(pakd_list)} PAKD")
        return jsonify({
            "pasal50":        hasil_pasal50,
            "pasal91":        hasil_pasal91,
            "cyber_3070":     hasil_cyber_3070,
            "eth_price_idr":  eth_price,
            "btc_price_idr":  btc_price,
            "sol_price_idr":  sol_price,
            "usdt_price_idr": usdt_price,
            "usdc_price_idr": usdc_price,
            "harga_fallback": harga_fallback,
            "threshold_idr":  EQUITY_MINIMUM_IDR,
            "threshold_ref":  "POJK No. 27 Tahun 2024, Pasal 50 ayat (1) huruf o",
        })

    except Exception as e:
        return _error_response("Stress test gagal", detail=e, status_code=500)


@app.route("/api/input-manual", methods=["POST"])
@require_super_admin_or_token
def input_manual():
    try:
        body = request.get_json(silent=True)
        if not body:
            return _error_response("Request body tidak valid atau bukan JSON")
        nama    = body.get("nama", "").strip() if isinstance(body.get("nama"), str) else ""
        pakd_id = body.get("id", "").strip()   if isinstance(body.get("id"), str)   else ""
        aset    = body.get("aset_dilaporkan", None)
        if not nama:
            return _error_response("Field nama wajib diisi")
        if not pakd_id:
            return _error_response("Field id wajib diisi")
        if aset is None or not isinstance(aset, (int, float)) or aset <= 0:
            return _error_response("Field aset_dilaporkan harus berupa angka positif")
        raw_wallets = body.get("wallets")
        if raw_wallets is None and "eth_wallet" in body:
            eth_addr = body.get("eth_wallet")
            raw_wallets = [{"network": "ethereum", "address": eth_addr}] if isinstance(eth_addr, str) else []
        if not isinstance(raw_wallets, list) or len(raw_wallets) < 1:
            return _error_response("Field wallets wajib berupa array minimal 1 entry")
        canonical_wallets = []
        for w in raw_wallets:
            entry = _normalize_wallet_entry(w, default_network="ethereum")
            if not entry or not entry.get("address"):
                return _error_response("Setiap wallet entry harus punya field address")
            ok, err = validate_wallet_address(entry["network"], entry["address"])
            if not ok:
                return _error_response(err)
            canonical_wallets.append(entry)
        pakd_list = load_pakd()
        for p in pakd_list:
            if p["id"] == pakd_id:
                return _error_response(f"ID {pakd_id} sudah terdaftar")
        ok, conflict_msg = _check_wallet_uniqueness(canonical_wallets, pakd_id, pakd_list)
        if not ok:
            return _error_response(conflict_msg)
        equity_idr_val                 = body.get("equity_idr")
        persediaan_akd_idr_val         = body.get("persediaan_akd_idr")
        simpanan_pedagang_akd_idr_val  = body.get("simpanan_pedagang_akd_idr")
        customer_akd_idr_val           = body.get("customer_akd_idr")
        for field_name, field_val in [
            ("equity_idr", equity_idr_val),
            ("persediaan_akd_idr", persediaan_akd_idr_val),
            ("simpanan_pedagang_akd_idr", simpanan_pedagang_akd_idr_val),
            ("customer_akd_idr", customer_akd_idr_val),
        ]:
            if field_val is not None and (not isinstance(field_val, (int, float)) or field_val < 0):
                return _error_response(f"Field {field_name} harus angka non-negatif jika diisi")
        new_entry = {
            "id":                        pakd_id,
            "nama":                      nama,
            "wallets":                   canonical_wallets,
            "aset_dilaporkan":           int(aset),
            "equity_idr":                int(equity_idr_val) if equity_idr_val is not None else None,
            "persediaan_akd_idr":        int(persediaan_akd_idr_val) if persediaan_akd_idr_val is not None else None,
            "simpanan_pedagang_akd_idr": int(simpanan_pedagang_akd_idr_val) if simpanan_pedagang_akd_idr_val is not None else None,
            "customer_akd_idr":          int(customer_akd_idr_val) if customer_akd_idr_val is not None else None,
        }
        pakd_list.append(new_entry)
        save_pakd(pakd_list)
        write_audit("INPUT MANUAL", f"{nama} ({pakd_id}) ditambahkan oleh OJK")
        return jsonify({"success": True, "message": f"{nama} berhasil ditambahkan", "data": new_entry})
    except Exception as e:
        return _error_response("Input manual gagal", detail=e, status_code=500)


@app.route("/api/audit/verify")
@require_role('super_admin')
def audit_verify():
    """T3.2: verifikasi integritas rantai hash audit_log.
    utuh=True + jumlah_event (baris yang ikut rantai, event_hash bukan
    NULL) pada rantai bersih. Kalau ada baris yang diedit manual setelah
    ditulis, utuh=False dan id_baris_rusak menunjuk baris pertama yang
    gagal verifikasi. jumlah_total_baris menghitung semua baris termasuk
    351 baris legacy pra-T3.1 yang di luar cakupan rantai (lihat
    audit.verify_chain untuk kebijakan itu).
    """
    conn = _get_db_conn()
    if not conn:
        return _error_response("Tidak bisa terhubung ke database", status_code=503)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, waktu, aksi, detail, created_at, actor_email, actor_role, "
            "source_ip, request_id, versi_perhitungan, previous_event_hash, event_hash "
            "FROM audit_log ORDER BY id ASC"
        )
        cols = ["id", "waktu", "aksi", "detail", "created_at", "actor_email", "actor_role",
                "source_ip", "request_id", "versi_perhitungan", "previous_event_hash", "event_hash"]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close()
    except Exception as e:
        _return_db_conn(conn)
        return _error_response("Gagal membaca audit_log", detail=e, status_code=500)
    _return_db_conn(conn)

    utuh, id_rusak = verify_chain(rows)
    jumlah_event = sum(1 for r in rows if r.get("event_hash") is not None)

    return jsonify({
        "utuh": utuh,
        "jumlah_event": jumlah_event,
        "jumlah_total_baris": len(rows),
        "id_baris_rusak": id_rusak,
    })


@app.route("/api/audit-log")
@require_auth
def audit_log():
    # Primary: Supabase
    conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            try:
                cur.execute("SELECT waktu, aksi, detail, actor_email, actor_role "
                            "FROM audit_log ORDER BY created_at DESC LIMIT 50")
                rows = cur.fetchall()
            except Exception:
                # Kolom actor belum ada (migrasi sprint5 belum dijalankan) → select legacy
                conn.rollback()
                cur.execute("SELECT waktu, aksi, detail, NULL, NULL "
                            "FROM audit_log ORDER BY created_at DESC LIMIT 50")
                rows = cur.fetchall()
            cur.close()
            _return_db_conn(conn)
            return jsonify({
                "data": [{"waktu": r[0], "aksi": r[1], "detail": r[2],
                          "aktor": r[3], "aktor_role": r[4]} for r in rows],
                "source": "database"
            })
        except Exception as e:
            print(f"[AUDIT_DB] read failed: {type(e).__name__}: {e}", flush=True)
            _return_db_conn(conn)

    # Fallback: file
    try:
        if not os.path.exists(AUDIT_FILE):
            return jsonify({"data": [], "source": "empty"})
        with open(AUDIT_FILE, "r") as f:
            logs = json.load(f)
        return jsonify({"data": logs, "source": "file"})
    except Exception as e:
        return _error_response("Gagal memuat audit log", detail=e, status_code=500)

@app.route("/api/wallet-challenge", methods=["POST"])
@require_auth
def wallet_challenge():
    body = request.get_json(silent=True)
    if not body:
        return _error_response("Request body tidak valid atau bukan JSON")
    address = (body.get("address") or "").strip()
    network = (body.get("network") or "ethereum").strip().lower()
    if not address:
        return _error_response("Field address wajib diisi")

    SUPPORTED_PROOF_NETWORKS = {"ethereum", "solana", "bitcoin"}
    if network not in SUPPORTED_PROOF_NETWORKS:
        return jsonify({
            "status":  "error",
            "message": f"Network '{network}' belum didukung untuk wallet challenge. "
                       f"Gunakan network: {', '.join(sorted(SUPPORTED_PROOF_NETWORKS))}",
        }), 400

    ok, err = validate_wallet_address(network, address)
    if not ok:
        return _error_response(err)

    nonce     = secrets.token_hex(16)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if network == "ethereum":
        challenge = (
            "PRIMA OJK — Bukti Kepemilikan Wallet\n"
            f"Address  : {address}\n"
            f"Network  : {network}\n"
            f"Nonce    : {nonce}\n"
            f"Timestamp: {timestamp}\n"
            "Pesan ini digunakan untuk membuktikan kepemilikan wallet kepada OJK PRIMA.\n"
            "Tanda tangan ini tidak mengotorisasi transaksi apapun."
        )
        instruction = (
            "Tandatangani field challenge menggunakan private key wallet Anda "
            "(EIP-191 personal_sign / MetaMask eth_sign), "
            "lalu kirim ke POST /api/wallet-verify."
        )
    elif network == "solana":
        challenge = (
            "PRIMA OJK — Bukti Kepemilikan Wallet Solana\n"
            f"Address  : {address}\n"
            f"Network  : {network}\n"
            f"Nonce    : {nonce}\n"
            f"Timestamp: {timestamp}\n"
            "Pesan ini digunakan untuk membuktikan kepemilikan wallet kepada OJK PRIMA.\n"
            "Tanda tangan ini tidak mengotorisasi transaksi apapun."
        )
        instruction = (
            "Tandatangani field challenge sebagai UTF-8 bytes menggunakan Ed25519 private key "
            "(Phantom signMessage / Solana wallet adapter signMessage). "
            "Kirim signature sebagai hex (128 karakter) ke POST /api/wallet-verify."
        )
    else:  # bitcoin
        if not address.startswith("1"):
            return jsonify({
                "status":  "error",
                "message": "Wallet challenge Bitcoin saat ini hanya didukung untuk alamat "
                           "legacy P2PKH (diawali '1'). P2WPKH/P2SH/P2TR belum didukung (roadmap Phase 2).",
            }), 400
        challenge = (
            "PRIMA OJK — Bukti Kepemilikan Wallet Bitcoin\n"
            f"Address  : {address}\n"
            f"Network  : {network}\n"
            f"Nonce    : {nonce}\n"
            f"Timestamp: {timestamp}\n"
            "Pesan ini digunakan untuk membuktikan kepemilikan wallet kepada OJK PRIMA.\n"
            "Tanda tangan ini tidak mengotorisasi transaksi apapun."
        )
        instruction = (
            "Tandatangani field challenge menggunakan format Bitcoin Signed Message "
            "(mis. Electrum: Tools > Sign/Verify Message, atau bitcoin-cli signmessage). "
            "Kirim signature base64 yang dihasilkan ke POST /api/wallet-verify."
        )

    CHALLENGE_STORE[address.lower()] = {
        "challenge": challenge,
        "network":   network,
        "expires":   time.time() + CHALLENGE_TTL,
    }
    write_audit("WALLET CHALLENGE ISSUED", f"Address {address} ({network}) pada {timestamp}")
    return jsonify({
        "address":     address,
        "network":     network,
        "challenge":   challenge,
        "expires_in":  CHALLENGE_TTL,
        "instruction": instruction,
    })


@app.route("/api/wallet-verify", methods=["POST"])
@require_auth
def wallet_verify():
    body = request.get_json(silent=True)
    if not body:
        return _error_response("Request body tidak valid atau bukan JSON")

    address   = (body.get("address")   or "").strip()
    signature = (body.get("signature") or "").strip()
    pakd_id   = (body.get("pakd_id")   or "").strip()

    if not address or not signature:
        return _error_response("Field address dan signature wajib diisi")

    stored = CHALLENGE_STORE.get(address.lower())
    if not stored:
        return jsonify({
            "status":  "error",
            "message": "Tidak ada challenge aktif untuk address ini. "
                       "Minta challenge baru melalui POST /api/wallet-challenge terlebih dahulu.",
        }), 400

    if time.time() > stored["expires"]:
        del CHALLENGE_STORE[address.lower()]
        return _error_response("Challenge sudah expired. Minta challenge baru.")

    challenge = stored["challenge"]
    network   = stored.get("network", "ethereum")

    if network == "ethereum":
        try:
            signable  = encode_defunct(text=challenge)
            recovered = Account.recover_message(signable, signature=signature)
        except Exception as exc:
            return jsonify({"status": "error", "message": f"Signature tidak dapat diparsing: {exc}"}), 400

        if recovered.lower() != address.lower():
            write_audit("WALLET VERIFY GAGAL", f"Claimed: {address} | Recovered: {recovered}")
            return jsonify({
                "verified":  False,
                "address":   address,
                "recovered": recovered,
                "message":   "Signature valid tetapi ditandatangani oleh address yang berbeda.",
            }), 400

        signer_display = recovered

    elif network == "solana":
        try:
            pubkey_bytes = base58.b58decode(address)
            if len(pubkey_bytes) != 32:
                raise ValueError(f"Decoded pubkey length {len(pubkey_bytes)}, expected 32")
            verify_key = nacl.signing.VerifyKey(pubkey_bytes)
        except Exception as exc:
            return jsonify({
                "status":  "error",
                "message": f"Address Solana tidak dapat diparse sebagai Ed25519 pubkey: {exc}",
            }), 400

        try:
            if len(signature) == 128:
                sig_bytes = bytes.fromhex(signature)
            else:
                import base64
                sig_bytes = base64.b64decode(signature)
            if len(sig_bytes) != 64:
                raise ValueError(f"Signature length {len(sig_bytes)}, expected 64 bytes")
        except Exception as exc:
            return jsonify({
                "status":  "error",
                "message": f"Signature tidak dapat diparse (kirim sebagai 128-char hex atau base64): {exc}",
            }), 400

        try:
            verify_key.verify(challenge.encode("utf-8"), sig_bytes)
        except nacl.exceptions.BadSignatureError:
            CHALLENGE_STORE.pop(address.lower(), None)
            write_audit("WALLET VERIFY GAGAL", f"Claimed Solana: {address} — bad Ed25519 sig")
            return jsonify({
                "verified": False,
                "address":  address,
                "message":  "Ed25519 signature tidak valid untuk address ini.",
            }), 400
        except Exception as exc:
            return jsonify({"status": "error", "message": f"Verifikasi Ed25519 gagal: {exc}"}), 400

        signer_display = address

    elif network == "bitcoin":
        from btc_verify import verify_bitcoin_signature
        verified_btc, err = verify_bitcoin_signature(address, challenge, signature)
        if not verified_btc:
            write_audit("WALLET VERIFY GAGAL", f"Claimed Bitcoin: {address} — {err}")
            return jsonify({
                "verified": False,
                "address":  address,
                "message":  err,
            }), 400
        signer_display = address

    else:
        return jsonify({"status": "error", "message": f"Network '{network}' tidak dikenali dalam challenge store"}), 400

    del CHALLENGE_STORE[address.lower()]

    pakd_list    = load_pakd()
    wallet_found = False
    matched_pakd = None
    for pakd in pakd_list:
        if pakd_id and pakd["id"] != pakd_id:
            continue
        for wallet in pakd.get("wallets", []):
            if wallet.get("address", "").lower() == address.lower():
                wallet["verified"]    = True
                wallet["verified_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                wallet_found = True
                matched_pakd = pakd["id"]

    if wallet_found:
        save_pakd(pakd_list)
        write_audit("WALLET VERIFIED", f"Address {address} ({network}) terverifikasi milik {matched_pakd}")

    # Titik ini hanya tercapai setelah verifikasi signature lolos.
    # Semua kegagalan signature return 400 lebih awal. signature_valid
    # hardcoded True
    return jsonify({
        "signature_valid": True,
        "verified":     wallet_found,
        "address":      address,
        "network":      network,
        "signer":       signer_display,
        "wallet_found": wallet_found,
        "pakd_id":      matched_pakd,
        "message":      "Kepemilikan wallet berhasil dibuktikan."
                        + (" Status wallet diperbarui menjadi verified." if wallet_found
                           else " Address tidak ditemukan di data PAKD."),
    })



@app.route('/api/export-csv-overview')
@require_auth
def export_csv_overview():
    import csv, io, psycopg2
    from datetime import datetime
    user = g.current_user
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        _csv_cols = """pakd_id, pakd_nama, created_at,
                    aset_dilaporkan_idr, aset_onchain_idr,
                    deviasi_persen, status, harga_fallback,
                    pakd_onchain_idr, kustodian_onchain_idr,
                    compliance_30_70, ratio_at_pakd, ratio_at_ptp"""
        if user['role'] in ('pakd', 'kustodian') and user.get('entity_id'):
            cur.execute(f"""
                SELECT DISTINCT ON (pakd_id) {_csv_cols}
                FROM reconciliation_snapshots
                WHERE pakd_id = %s
                ORDER BY pakd_id, created_at DESC
            """, (user['entity_id'],))
        else:
            cur.execute(f"""
                SELECT DISTINCT ON (pakd_id) {_csv_cols}
                FROM reconciliation_snapshots
                ORDER BY pakd_id, created_at DESC
            """)
        rows = cur.fetchall()
        col_names = [desc[0] for desc in cur.description]
        cur.close()
        _return_db_conn(conn)
    except Exception as e:
        return _error_response(str(e), status_code=500)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(col_names)
    writer.writerows(rows)

    write_audit("EKSPOR DATA",
                f"{user.get('email') or user.get('id')} ({user.get('role')}) mengekspor CSV overview rekonsiliasi ({len(rows)} baris)")

    filename = f"prima-overview-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "text/csv"
    return response

@app.route('/api/export-csv')
@require_auth
def export_csv():
    import csv, io, psycopg2
    from datetime import datetime
    user = g.current_user
    pakd_id = request.args.get('pakd_id')
    if user['role'] in ('pakd', 'kustodian') and user.get('entity_id'):
        if pakd_id and pakd_id != user['entity_id']:
            return jsonify({'error': 'Forbidden'}), 403
        pakd_id = user['entity_id']
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        if pakd_id:
            cur.execute(
                "SELECT pakd_id, pakd_nama, created_at, aset_dilaporkan_idr, aset_onchain_idr, deviasi_persen, status, harga_fallback, network_breakdown FROM reconciliation_snapshots WHERE pakd_id = %s ORDER BY created_at DESC LIMIT 200",
                (pakd_id,)
            )
        else:
            cur.execute(
                "SELECT pakd_id, pakd_nama, created_at, aset_dilaporkan_idr, aset_onchain_idr, deviasi_persen, status, harga_fallback, network_breakdown FROM reconciliation_snapshots ORDER BY created_at DESC LIMIT 500"
            )
        rows = cur.fetchall()
        col_names = [desc[0] for desc in cur.description]
        cur.close()
        _return_db_conn(conn)
    except Exception as e:
        return _error_response(str(e), status_code=500)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(col_names)
    writer.writerows(rows)

    write_audit("EKSPOR DATA",
                f"{user.get('email') or user.get('id')} ({user.get('role')}) mengekspor CSV riwayat rekonsiliasi "
                f"({'pakd_id=' + pakd_id if pakd_id else 'semua PAKD'}, {len(rows)} baris)")

    filename = f"prima-export-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "text/csv"
    return response


import uuid
from concurrent.futures import ThreadPoolExecutor as _TPE

_REFRESH_EXECUTOR = _TPE(max_workers=3)

def _cleanup_old_jobs():
    now = time.time()
    for jid in list(JOBS.keys()):
        if now - JOBS[jid]["created_at"] > 600:
            del JOBS[jid]

def _run_refresh_job(job_id, pakd_id_filter=None):
    def _job_update(status, result=None):
        conn = _get_db_conn()
        if not conn:
            return
        try:
            cur = conn.cursor()
            import json as _json
            cur.execute(
                "UPDATE reconciliation_jobs SET status=%s, result=%s WHERE job_id=%s",
                (status, _json.dumps(result) if result else None, job_id)
            )
            conn.commit()
            cur.close()
        except Exception as e:
            print(f"[JOBS] update failed: {e}", flush=True)
        finally:
            _return_db_conn(conn)
    _job_update("running")
    try:
        pakd_list = load_pakd()
        if pakd_id_filter:
            pakd_list = [p for p in pakd_list if p["id"] == pakd_id_filter]
        hasil = []
        for pakd in pakd_list:
            result_bal = get_total_balance_idr(pakd.get("wallets", []))
            total = result_bal["total_idr"]
            breakdown = result_bal["breakdown"]
            dilaporkan = _get_aset_dilaporkan(pakd["id"], fallback=pakd.get("aset_dilaporkan", 0))
            compliance_data = compute_30_70_compliance(pakd["id"], int(total))
            total_attributable, deviasi = deviasi_with_custody(
                total, (compliance_data.get("kustodian_onchain_idr") or 0), dilaporkan)
            _as_of = datetime.now(timezone.utc).isoformat()
            _kelengkapan = hitung_kelengkapan(
                result_bal["entries"], result_bal["provenance_harga"], _as_of)
            # D49: disatukan ke ambang surplus/defisit (0.01%/10%), lebih ketat
            # dari ternary lama (5%/20%) -- keputusan mentor 24 Agustus 2026.
            # Lihat core/verdict.py untuk detail keputusan dan alasan.
            _verdict = tetapkan_verdict_surplus(
                _kelengkapan["status"], total_attributable, dilaporkan, deviasi)
            status = _verdict["status"]
            _kelengkapan_status_out = _kelengkapan["status"]
            _sumber_gagal_out = _kelengkapan["sumber_gagal"]
            _aset_onchain_idr_final = (
                total if _kelengkapan_status_out == "LENGKAP" else None)
            _subtotal_diketahui_idr = total

            hasil.append({
                "id": pakd["id"], "nama": pakd["nama"],
                "aset_dilaporkan_idr": dilaporkan,
                "aset_onchain_idr": total,
                "deviasi_pct": _verdict["deviasi_pct"],
                "status": status,
                "kelengkapan_status":     _kelengkapan_status_out,
                "sumber_gagal":           _sumber_gagal_out,
                "aset_onchain_idr_final": _aset_onchain_idr_final,
                "subtotal_diketahui_idr": _subtotal_diketahui_idr,
                "breakdown": breakdown,
                "pakd_onchain_idr": int(total),
                "kustodian_onchain_idr": compliance_data["kustodian_onchain_idr"],
                "compliance_30_70": compliance_data["compliance_30_70"],
                "ratio_at_pakd": compliance_data["ratio_at_pakd"],
                "ratio_at_ptp": compliance_data["ratio_at_ptp"],
            })
        _, eth_fallback = get_eth_price_idr()
        _save_snapshots_batch(hasil, eth_fallback)
        _job_update("done", {"pakd_refreshed": len(hasil), "timestamp": time.time()})
    except Exception as e:
        _job_update("failed", {"detail": str(e)})

@app.route("/api/reconciliation/refresh", methods=["POST"])
@require_role('super_admin')
def reconciliation_refresh():
    _cleanup_old_jobs()
    pakd_id_filter = request.args.get("pakd_id") or None
    job_id = str(uuid.uuid4())
    conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO reconciliation_jobs (job_id, status) VALUES (%s, %s)", (job_id, "pending"))
            conn.commit()
            cur.close()
        except Exception as e:
            print(f"[JOBS] insert failed: {e}", flush=True)
        finally:
            _return_db_conn(conn)
    _REFRESH_EXECUTOR.submit(_run_refresh_job, job_id, pakd_id_filter)
    return jsonify({"job_id": job_id, "status": "pending"})

@app.route("/api/reconciliation/refresh/<job_id>", methods=["GET"])
def reconciliation_refresh_status(job_id):
    conn = _get_db_conn()
    if not conn:
        return jsonify({"status": "error", "detail": "db unavailable"}), 503
    try:
        cur = conn.cursor()
        cur.execute("SELECT status, result FROM reconciliation_jobs WHERE job_id=%s", (job_id,))
        row = cur.fetchone()
        cur.close()
    except Exception as e:
        print(f"[JOBS] select failed: {e}", flush=True)
        return jsonify({"status": "error", "detail": str(e)}), 500
    finally:
        _return_db_conn(conn)
    if not row:
        return jsonify({"status": "not_found"}), 404
    return jsonify({"job_id": job_id, "status": row[0], "result": row[1]})

@app.route('/ping')
def ping():
    db_ok = False
    db_latency = None
    conn = _get_db_conn()
    if conn:
        try:
            _t0 = time.time()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close()
            db_latency = round((time.time() - _t0) * 1000)
            db_ok = True
        except Exception as e:
            print(f"[PING] DB check failed: {type(e).__name__}: {e}", flush=True)
        finally:
            _return_db_conn(conn)

    status_code = 200 if db_ok else 503
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "connected" if db_ok else "unreachable",
        "db_latency_ms": db_latency,
        "cache_entries": {
            "balance": len(BALANCE_CACHE),
            "price":   len(PRICE_CACHE),
        },
        "uptime_seconds": round(time.time() - _SERVER_START_TIME),
    }, status_code

def _run_seeds():
    if os.environ.get("DATABASE_URL") and not app.config.get("TESTING"):
        init_data()
        init_kustodian_data()

_run_seeds()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port  = int(os.environ.get("PORT", 5000))
    app.run(debug=debug, host="0.0.0.0", port=port)

