from flask import Flask, jsonify, request, send_from_directory, make_response
from flask_cors import CORS
import requests
import os
import json
import tempfile
from datetime import datetime
import re
import time
import secrets
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct

import base58
import nacl.signing
import nacl.exceptions

app = Flask(__name__)
CORS(app)

SATOSHI_PER_BTC    = 100_000_000
LAMPORTS_PER_SOL   = 1_000_000_000
PRICE_CACHE        = {}
BALANCE_CACHE      = {}
PRICE_TTL          = 300   # bumped from 60 (Day 15): CMC credit budget guard
BALANCE_TTL        = 300  # bumped: cache outlives request duration

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
DATA_FILE          = os.path.join(os.path.dirname(__file__), "pakd_data.json")
AUDIT_FILE         = os.path.join(os.path.dirname(__file__), "audit_log.json")

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
STABLECOIN_DECIMALS = 6

# Fallback IDR/USD rate used only when CoinGecko is unreachable.
# Conservative estimate — updated manually per quarter.
# Current reference: Bank Indonesia Kurs Tengah, April 2026.
FALLBACK_STABLECOIN_IDR = 16_350.0

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
        "nama": "PT Demo Aset Digital Indonesia",
        "wallets": [
            {
                "network":     "ethereum",
                "address":     "0xB6da511B4550B440415f8c640E986Ec41d9020C0",
                "verified":    False,
                "verified_at": None,
            },
            {
                "network":     "solana",
                "address":     "H13V5d2YdEvL9172K4jH5xfD7tGJN7UqEBR8y5Tb15B1",
                "verified":    False,
                "verified_at": None,
            },
        ],
        "aset_dilaporkan": 5_000_000_000,
        "equity_idr": None,
        "persediaan_akd_idr": None,
        "simpanan_pedagang_akd_idr": None,
        "customer_akd_idr": None,
    },
    {
        "id":   "PAKD-OJK-001",
        "nama": "PT Indodax Nasional Indonesia",
        "wallets": [
            {
                "network":     "ethereum",
                "address":     "0x28C6c06298d514Db089934071355E5743bf21d60",
                "verified":    False,
                "verified_at": None,
            }
        ],
        "aset_dilaporkan": 4_500_000_000_000,
        "equity_idr": None,
        "persediaan_akd_idr": None,
        "simpanan_pedagang_akd_idr": None,
        "customer_akd_idr": None,
    },
    {
        "id":   "PAKD-OJK-002",
        "nama": "PT Tokocrypto",
        "wallets": [
            {
                "network":     "ethereum",
                "address":     "0x71660c4005BA85c37ccec55d0C4493E66Fe775d3",
                "verified":    False,
                "verified_at": None,
            }
        ],
        "aset_dilaporkan": 1_200_000_000_000,
        "equity_idr": None,
        "persediaan_akd_idr": None,
        "simpanan_pedagang_akd_idr": None,
        "customer_akd_idr": None,
    },
    {
        "id":   "PAKD-OJK-003",
        "nama": "PT Pintu Kemana Saja",
        "wallets": [
            {
                "network":     "ethereum",
                "address":     "0x2910543Af39abA0CD09dBb2D50200b3E800A63D2",
                "verified":    False,
                "verified_at": None,
            }
        ],
        "aset_dilaporkan": 850_000_000_000,
        "equity_idr": None,
        "persediaan_akd_idr": None,
        "simpanan_pedagang_akd_idr": None,
        "customer_akd_idr": None,
    },
]


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

def _get_db_conn():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return None
    try:
        import psycopg2
        return psycopg2.connect(db_url, connect_timeout=5)
    except Exception:
        return None


def _save_snapshot(pakd_id, pakd_nama, aset_dilaporkan, aset_onchain, deviasi_pct, status, harga_fallback, breakdown):
    conn = _get_db_conn()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO reconciliation_snapshots
               (pakd_id, pakd_nama, aset_dilaporkan_idr, aset_onchain_idr,
                deviasi_persen, status, harga_fallback, network_breakdown)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (pakd_id, pakd_nama, int(aset_dilaporkan), int(aset_onchain),
             float(deviasi_pct), status, harga_fallback,
             json.dumps(breakdown))
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def load_pakd():
    conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, nama, aset_dilaporkan, equity_idr, persediaan_akd_idr, simpanan_pedagang_akd_idr, customer_akd_idr FROM pakd ORDER BY id")
            pakd_rows = cur.fetchall()
            result = []
            for row in pakd_rows:
                pakd_id = row[0]
                cur.execute("SELECT network, address, verified, verified_at FROM wallets WHERE pakd_id = %s", (pakd_id,))
                wallets = [{"network": w[0], "address": w[1], "verified": w[2], "verified_at": str(w[3]) if w[3] else None} for w in cur.fetchall()]
                result.append({
                    "id": row[0], "nama": row[1],
                    "aset_dilaporkan": row[2] or 0,
                    "equity_idr": row[3], "persediaan_akd_idr": row[4],
                    "simpanan_pedagang_akd_idr": row[5], "customer_akd_idr": row[6],
                    "wallets": wallets
                })
            cur.close()
            conn.close()
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
    except Exception:
        pass
    return [dict(p) for p in PAKD_DEFAULT]


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
                cur.execute("DELETE FROM wallets WHERE pakd_id = %s", (pakd["id"],))
                for w in pakd.get("wallets", []):
                    cur.execute("""
                        INSERT INTO wallets (pakd_id, network, address, verified, verified_at)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (pakd["id"], w["network"], w["address"], w.get("verified", False), w.get("verified_at")))
            conn.commit()
            cur.close()
            conn.close()
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

def write_audit(action, detail):
    try:
        logs = []
        if os.path.exists(AUDIT_FILE):
            with open(AUDIT_FILE, "r") as f:
                logs = json.load(f)
        logs.insert(0, {"waktu": datetime.now().strftime("%d %b %Y, %H:%M"), "aksi": action, "detail": detail})
        logs = logs[:50]
        dir_ = os.path.dirname(AUDIT_FILE) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(logs, f, indent=2)
        os.replace(tmp_path, AUDIT_FILE)
    except Exception:
        pass


def validate_wallet_address(network, address):
    if network not in SUPPORTED_NETWORKS:
        return False, f"Network '{network}' tidak didukung. Pilih: {', '.join(sorted(SUPPORTED_NETWORKS))}"
    if not WALLET_RE[network].match(address):
        return False, f"Alamat '{address}' tidak valid untuk network {network}"
    return True, None


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def get_cached_price(network, fetch_fn):
    """
    Return cached price for network. Calls fetch_fn only when cache is
    cold or older than PRICE_TTL seconds.
    """
    now = time.time()
    if network in PRICE_CACHE:
        cached_at, price = PRICE_CACHE[network]
        if now - cached_at < PRICE_TTL:
            return price
    price = fetch_fn()
    PRICE_CACHE[network] = (now, price)
    return price


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

CMC_ID_TO_CGKEY = {
    "1":    "bitcoin",
    "1027": "ethereum",
    "5426": "solana",
    "825":  "tether",
    "3408": "usd-coin",
}


def _refresh_price_cache_from_cmc():
    """
    Attempt to populate PRICE_CACHE for all 5 assets via single CMC call.

    Returns True if cache is fresh for all 5 assets after this call.
    Returns False if CMC key absent or call failed; callers fall through
    to existing CoinGecko per-asset logic.

    Idempotent: skips network call when cache already fully fresh.
    """
    api_key = os.environ.get("COINMARKETCAP_API_KEY", "")
    if not api_key:
        if os.environ.get('PRIMA_DEBUG'):
            print("[CMC] api_key absent, falling through to CoinGecko", flush=True)
        return False

    now = time.time()
    cgkeys = list(CMC_ID_TO_CGKEY.values())
    all_fresh = all(
        k in PRICE_CACHE and (now - PRICE_CACHE[k][0]) < PRICE_TTL
        for k in cgkeys
    )
    if all_fresh:
        return True

    try:
        resp = requests.get(
            "https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest",
            headers={"X-CMC_PRO_API_KEY": api_key, "Accept": "application/json"},
            params={
                "id":      ",".join(CMC_ID_TO_CGKEY.keys()),
                "convert": "IDR",
                "aux":     "",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})

        for cmc_id, cgkey in CMC_ID_TO_CGKEY.items():
            entry = data.get(cmc_id)
            # /v2 returns array per id; unwrap first element if list
            if isinstance(entry, list):
                entry = entry[0] if entry else None
            if not entry:
                continue
            price = entry.get("quote", {}).get("IDR", {}).get("price")
            if price is not None:
                PRICE_CACHE[cgkey] = (now, float(price))

        success = all(k in PRICE_CACHE for k in cgkeys)
        if os.environ.get('PRIMA_DEBUG'):
            print(f"[CMC] refresh success={success}, populated={list(PRICE_CACHE.keys())}", flush=True)
        return success
    except Exception as e:
        # Log to stdout for Render Logs visibility (Day 15 cascade debug)
        if os.environ.get('PRIMA_DEBUG'):
            print(f"[CMC] refresh failed: {type(e).__name__}: {e}", flush=True)
        return False


def get_eth_price_idr():
    """
    Fetch current ETH/IDR price.
    Cascade: CMC primary, CoinGecko fallback, hardcoded final.
    Returns (price_idr, harga_fallback_flag).
    """
    # Cascade Tier 1: CMC primary
    if _refresh_price_cache_from_cmc():
        cached = PRICE_CACHE.get("ethereum")
        if cached and (time.time() - cached[0]) < PRICE_TTL:
            return cached[1], False
    # Cascade Tier 2: CoinGecko fallback
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=idr"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return 39_910_503, True
        return resp.json()["ethereum"]["idr"], False
    except Exception:
        return 39_910_503, True


def get_eth_balance(address):
    url = (f"https://api.etherscan.io/v2/api?chainid=1&module=account"
           f"&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}")
    try:
        data = requests.get(url, timeout=10).json()
        if data["status"] == "1":
            return int(data["result"]) / 1e18
        return 0
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# ERC-20 token fetchers (Day 4)
# ---------------------------------------------------------------------------

def fetch_erc20_balance(address, contract_address, decimals=STABLECOIN_DECIMALS):
    """
    Fetch ERC-20 token balance via Etherscan V2 API.

    Uses tag=latest to match the confirmed chain state. Unconfirmed
    (pending) token transfers are excluded — same reasoning as BTC
    mempool and SOL processed commitment: unsettled transfers must not
    count toward regulatory reserve.

    Args:
        address          : Ethereum wallet address (checksummed or lowercase)
        contract_address : ERC-20 token contract address
        decimals         : Token decimal places (USDT=6, USDC=6, WETH=18)

    Returns:
        float — token balance in human-readable units (e.g. 1000.50 USDT)

    Source:
        https://docs.etherscan.io/v2/api-endpoints/accounts#get-erc20-token-account-balance-for-tokencontractaddress
    """
    url = (
        f"https://api.etherscan.io/v2/api"
        f"?chainid=1"
        f"&module=account"
        f"&action=tokenbalance"
        f"&contractaddress={contract_address}"
        f"&address={address}"
        f"&tag=latest"
        f"&apikey={ETHERSCAN_API_KEY}"
    )
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data["status"] == "1":
        return int(data["result"]) / (10 ** decimals)
    # status "0" with result "0" means zero balance, not an error.
    # Other status "0" cases (invalid address, etc.) return 0 and let
    # the caller surface the issue via reconciliation output.
    return 0.0


def fetch_stablecoin_prices_idr():
    """
    Fetch USDT and USDC prices in IDR from CoinGecko in a single request.

    Stablecoins are not guaranteed to be 1:1 with USD — USDC depegged
    to USD 0.87 on 11 March 2023 (SVB collapse). Fetching live prices
    matters for an accurate stress test baseline.

    Populates PRICE_CACHE["tether"] and PRICE_CACHE["usd-coin"] as a
    side effect, so subsequent get_cached_price calls for either token
    will hit cache without a second request.

    Returns:
        (usdt_price_idr: float, usdc_price_idr: float)
    """
    # Cascade Tier 1: CMC primary
    if _refresh_price_cache_from_cmc():
        usdt_cached = PRICE_CACHE.get("tether")
        usdc_cached = PRICE_CACHE.get("usd-coin")
        now = time.time()
        if (usdt_cached and (now - usdt_cached[0]) < PRICE_TTL and
            usdc_cached and (now - usdc_cached[0]) < PRICE_TTL):
            return usdt_cached[1], usdc_cached[1]
    # Cascade Tier 2: CoinGecko (existing logic below)
    url = "https://api.coingecko.com/api/v3/simple/price"
    resp = requests.get(
        url,
        params={"ids": "tether,usd-coin", "vs_currencies": "idr"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    usdt_price = float(data.get("tether",   {}).get("idr", FALLBACK_STABLECOIN_IDR))
    usdc_price = float(data.get("usd-coin", {}).get("idr", FALLBACK_STABLECOIN_IDR))

    # Populate cache for both tokens atomically from this single response.
    now = time.time()
    PRICE_CACHE["tether"]   = (now, usdt_price)
    PRICE_CACHE["usd-coin"] = (now, usdc_price)

    return usdt_price, usdc_price


def _get_stablecoin_prices_idr():
    """
    Return (usdt_price_idr, usdc_price_idr) using cache when fresh.

    Checks PRICE_CACHE for both tokens. If either is stale or absent,
    calls fetch_stablecoin_prices_idr() which refills both in one request.
    This prevents the caller from issuing two separate CoinGecko calls.
    """
    now  = time.time()
    usdt = PRICE_CACHE.get("tether")
    usdc = PRICE_CACHE.get("usd-coin")

    both_fresh = (
        usdt is not None and (now - usdt[0]) < PRICE_TTL and
        usdc is not None and (now - usdc[0]) < PRICE_TTL
    )
    if both_fresh:
        return usdt[1], usdc[1]

    try:
        return fetch_stablecoin_prices_idr()
    except Exception:
        usdt_fallback = usdt[1] if usdt else FALLBACK_STABLECOIN_IDR
        usdc_fallback = usdc[1] if usdc else FALLBACK_STABLECOIN_IDR
        return usdt_fallback, usdc_fallback


# ---------------------------------------------------------------------------
# Bitcoin fetchers
# ---------------------------------------------------------------------------

def fetch_btc_balance(address):
    """
    Fetch confirmed BTC balance from Blockstream Esplora public API.
    Returns float in BTC.

    Uses chain_stats only — mempool (unconfirmed) transactions are
    excluded because they cannot be counted as settled regulatory reserve.

    Source: https://github.com/Blockstream/esplora/blob/master/API.md
    """
    url = f"https://blockstream.info/api/address/{address}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    funded = data["chain_stats"]["funded_txo_sum"]
    spent  = data["chain_stats"]["spent_txo_sum"]
    return (funded - spent) / SATOSHI_PER_BTC


def fetch_btc_price_idr():
    """
    Fetch current BTC/IDR price.
    Cascade: CMC primary, CoinGecko fallback.
    Returns float (IDR per 1 BTC).
    """
    if _refresh_price_cache_from_cmc():
        cached = PRICE_CACHE.get("bitcoin")
        if cached and (time.time() - cached[0]) < PRICE_TTL:
            return cached[1]
    url = "https://api.coingecko.com/api/v3/simple/price"
    resp = requests.get(url, params={"ids": "bitcoin", "vs_currencies": "idr"}, timeout=10)
    resp.raise_for_status()
    return float(resp.json()["bitcoin"]["idr"])


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


def fetch_sol_price_idr():
    """
    Fetch current SOL/IDR price.
    Cascade: CMC primary, CoinGecko fallback.
    Returns float (IDR per 1 SOL).
    """
    if _refresh_price_cache_from_cmc():
        cached = PRICE_CACHE.get("solana")
        if cached and (time.time() - cached[0]) < PRICE_TTL:
            return cached[1]
    url  = "https://api.coingecko.com/api/v3/simple/price"
    resp = requests.get(
        url,
        params={"ids": "solana", "vs_currencies": "idr"},
        timeout=10,
    )
    resp.raise_for_status()
    return float(resp.json()["solana"]["idr"])

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


def _get_usd_idr_rate():
    """
    Return USD-to-IDR rate via USDT IDR price (USDT is USD-pegged within
    de-peg tolerance). No new API dependency: reuses _get_stablecoin_prices_idr.
    Falls back to FALLBACK_STABLECOIN_IDR on cascade failure.
    """
    try:
        usdt_idr, _ = _get_stablecoin_prices_idr()
        return float(usdt_idr)
    except Exception:
        return float(FALLBACK_STABLECOIN_IDR)
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
    if eth_price_idr is None:
        try:
            eth_price_idr = get_cached_price("ethereum", lambda: get_eth_price_idr()[0])
        except Exception:
            eth_price_idr = 39_910_503

    if btc_price_idr is None:
        try:
            btc_price_idr = get_cached_price("bitcoin", fetch_btc_price_idr)
        except Exception:
            btc_price_idr = 0.0

    if sol_price_idr is None:
        try:
            sol_price_idr = get_cached_price("solana", fetch_sol_price_idr)
        except Exception:
            sol_price_idr = 0.0

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

    # --- Accumulate across wallets ---
    total_idr      = 0.0
    eth_total_idr  = 0.0
    eth_native_sum = 0.0
    eth_usdt_sum   = 0.0
    eth_usdc_sum   = 0.0
    btc_total_idr  = 0.0
    sol_total_idr  = 0.0
    sol_native_sum = 0.0
    sol_usdt_sum   = 0.0
    sol_usdc_sum   = 0.0
    sol_other_token_sum       = 0.0
    eth_other_token_sum       = 0.0
    eth_unvalued_count_total  = 0
    eth_unvalued_contracts_global = []
    sol_unvalued_count_total  = 0
    sol_unvalued_mints_global = []
    breakdown      = []
    _t_eth = _t_btc = _t_sol = _t_pricing = 0.0

    for wallet in wallets:
        network  = wallet.get("network", "ethereum")
        address  = wallet.get("address", "")
        verified = wallet.get("verified", False)

        entry = {
            "network":        network,
            "address":        address,
            "balance_native": 0.0,
            "native_unit":    "",
            "balance_idr":    0.0,
            # ERC-20 fields — populated for ethereum wallets, None for others
            "eth_native_idr":   None,
            "usdt_balance":     None,
            "usdt_idr":         None,
            "usdc_balance":     None,
            "usdc_idr":         None,
            # SPL fields — populated for solana wallets, None for others
            "sol_native_idr":      None,
            "sol_usdt_balance":    None,
            "sol_usdt_idr":        None,
            "sol_usdc_balance":    None,
            "sol_usdc_idr":        None,
            # Day 16: full SPL enumeration fields, populated for solana wallets only
            "sol_other_token_idr": None,
            "sol_unvalued_count":  None,
            "sol_unvalued_mints":  None,
            # Day 17: ETH curated ERC-20 enumeration fields
            "eth_other_token_idr":    None,
            "eth_unvalued_count":     None,
            "eth_unvalued_contracts": None,
            "verified":            verified,
            "error":               None,
            }

        _tw = time.perf_counter()
        if network == "ethereum":
            entry["native_unit"] = "ETH"
            try:
                # Native ETH
                eth_bal = get_cached_balance(
                    "ethereum", address,
                    lambda a=address: get_eth_balance(a)
                )
                eth_native_idr_val = eth_bal * eth_price_idr

                # USDT (cache key namespaced to avoid collision with native ETH)
                usdt_bal = get_cached_balance(
                    "usdt_erc20", address,
                    lambda a=address: fetch_erc20_balance(a, USDT_CONTRACT)
                )
                usdt_idr_val = usdt_bal * usdt_price_idr

                # USDC
                usdc_bal = get_cached_balance(
                    "usdc_erc20", address,
                    lambda a=address: fetch_erc20_balance(a, USDC_CONTRACT)
                )
                usdc_idr_val = usdc_bal * usdc_price_idr

                wallet_total_idr = eth_native_idr_val + usdt_idr_val + usdc_idr_val

                entry["balance_native"] = eth_bal
                entry["balance_idr"]    = wallet_total_idr
                entry["eth_native_idr"] = round(eth_native_idr_val)
                entry["usdt_balance"]   = round(usdt_bal, 6)
                entry["usdt_idr"]       = round(usdt_idr_val)
                entry["usdc_balance"]   = round(usdc_bal, 6)
                entry["usdc_idr"]       = round(usdc_idr_val)

                eth_total_idr  += wallet_total_idr
                eth_native_sum += eth_native_idr_val
                eth_usdt_sum   += usdt_idr_val
                eth_usdc_sum   += usdc_idr_val

                # Day 17: curated ERC-20 long-tail enumeration (top-50)
                try:
                    curated_balances = fetch_curated_erc20_balances(address)
                    if curated_balances:
                        contracts_to_price = [t["contract"] for t in curated_balances]
                        curated_prices     = _get_coingecko_eth_token_prices(contracts_to_price)
                        usd_idr_rate       = _get_usd_idr_rate()

                        eth_other_idr_val           = 0.0
                        unvalued_contracts_per_addr = []

                        for token in curated_balances:
                            contract_lc = token["contract"].lower()
                            usd_price   = curated_prices.get(contract_lc)
                            if usd_price and usd_price > 0:
                                token_idr_val = token["balance"] * usd_price * usd_idr_rate
                                eth_other_idr_val += token_idr_val
                            else:
                                unvalued_contracts_per_addr.append(token["contract"])

                        entry["eth_other_token_idr"]    = round(eth_other_idr_val)
                        entry["eth_unvalued_count"]     = len(unvalued_contracts_per_addr)
                        entry["eth_unvalued_contracts"] = unvalued_contracts_per_addr

                        wallet_total_idr               += eth_other_idr_val
                        eth_total_idr                  += eth_other_idr_val
                        eth_other_token_sum            += eth_other_idr_val
                        eth_unvalued_count_total       += len(unvalued_contracts_per_addr)
                        eth_unvalued_contracts_global.extend(unvalued_contracts_per_addr)

                        entry["balance_idr"] = wallet_total_idr
                    else:
                        entry["eth_other_token_idr"]    = 0
                        entry["eth_unvalued_count"]     = 0
                        entry["eth_unvalued_contracts"] = []
                except Exception as curated_err:
                    if os.environ.get('PRIMA_DEBUG'):
                        print(f"[ETH_CURATED] {address[:8]} error: {curated_err}", flush=True)
                    entry["eth_other_token_idr"]    = 0
                    entry["eth_unvalued_count"]     = 0
                    entry["eth_unvalued_contracts"] = []


            except Exception as e:
                entry["error"] = f"ETH fetch error: {e}"

        elif network == "bitcoin":
            entry["native_unit"] = "BTC"
            try:
                bal = get_cached_balance(
                    "bitcoin", address,
                    lambda a=address: fetch_btc_balance(a)
                )
                entry["balance_native"] = round(bal, 8)
                entry["balance_idr"]    = bal * btc_price_idr
                btc_total_idr          += entry["balance_idr"]
            except Exception as e:
                entry["error"] = f"BTC fetch error: {e}"

        elif network == "solana":
            entry["native_unit"] = "SOL"
            try:
                # ---- Tier-1 logic UNTOUCHED: native SOL + USDT SPL + USDC SPL ----
                sol_bal = get_cached_balance(
                    "solana", address,
                    lambda a=address: fetch_sol_balance(a)
                )
                sol_native_idr_val = sol_bal * sol_price_idr

                sol_usdt_bal = get_cached_balance(
                    "sol_usdt_spl", address,
                    lambda a=address: fetch_spl_token_balance(a, USDT_MINT_SOL)
                )
                sol_usdt_idr_val = sol_usdt_bal * usdt_price_idr

                sol_usdc_bal = get_cached_balance(
                    "sol_usdc_spl", address,
                    lambda a=address: fetch_spl_token_balance(a, USDC_MINT_SOL)
                )
                sol_usdc_idr_val = sol_usdc_bal * usdc_price_idr

                # ---- Day 16: full SPL enumeration + two-gate hybrid filter ----
                # Gate 1 (POJK 23/2025 DAKD spirit): mint in verified set OR
                #        has tradable price signal in Jupiter
                # Gate 2 (valuation): Jupiter Price V3 returns non-null non-zero usdPrice
                # Both gates required → contribute to other_token_idr
                # Gate 1 fail OR Gate 2 fail → tracked in unvalued_mints
                other_token_idr_val   = 0.0
                unvalued_mints_local  = []

                try:
                    _spl_key = ("spl_enum", address)
                    _now = time.time()
                    if _spl_key in BALANCE_CACHE and (_now - BALANCE_CACHE[_spl_key][0]) < BALANCE_TTL:
                        all_holdings = BALANCE_CACHE[_spl_key][1]
                    else:
                        all_holdings = fetch_all_spl_balances(address)
                        BALANCE_CACHE[_spl_key] = (_now, all_holdings)
                except Exception as enum_err:
                    all_holdings = []
                    if os.environ.get('PRIMA_DEBUG'):
                        print(f"[SPL_ENUM] fetch_all_spl_balances({address}) failed: "
                          f"{type(enum_err).__name__}: {enum_err}", flush=True)

                tier1_mints     = {USDT_MINT_SOL, USDC_MINT_SOL, SOL_NATIVE_SENTINEL}
                candidate_mints = [h["mint"] for h in all_holdings if h["mint"] not in tier1_mints]

                if candidate_mints:
                    verified_set = _get_jupiter_verified_set()
                    prices       = _get_jupiter_prices(candidate_mints)
                    usd_idr_rate = _get_usd_idr_rate()

                    for holding in all_holdings:
                        mint = holding["mint"]
                        if mint in tier1_mints:
                            continue

                        in_verified = mint in verified_set
                        usd_price   = prices.get(mint)
                        has_price   = usd_price is not None and usd_price > 0
                        if not has_price:
                            usd_price = _get_dexscreener_price(mint)
                            has_price = usd_price is not None and usd_price > 0

                        pass_gate1 = in_verified or has_price   # hybrid (option c)
                        pass_gate2 = has_price                  # valuation gate

                        if pass_gate1 and pass_gate2:
                            token_idr = holding["ui_amount"] * usd_price * usd_idr_rate
                            other_token_idr_val += token_idr
                            # Distinct cache key per mint (prior bug class: collision)
                            BALANCE_CACHE[(f"sol_other_token:{mint}", address)] = (
                                time.time(), holding["ui_amount"]
                            )
                        else:
                            unvalued_mints_local.append(mint)

                wallet_total_idr = (
                    sol_native_idr_val
                    + sol_usdt_idr_val
                    + sol_usdc_idr_val
                    + other_token_idr_val
                )

                entry["balance_native"]      = round(sol_bal, 9)
                entry["balance_idr"]         = wallet_total_idr
                entry["sol_native_idr"]      = round(sol_native_idr_val)
                entry["sol_usdt_balance"]    = round(sol_usdt_bal, 6)
                entry["sol_usdt_idr"]        = round(sol_usdt_idr_val)
                entry["sol_usdc_balance"]    = round(sol_usdc_bal, 6)
                entry["sol_usdc_idr"]        = round(sol_usdc_idr_val)
                entry["sol_other_token_idr"] = round(other_token_idr_val)
                entry["sol_unvalued_count"]  = len(unvalued_mints_local)
                entry["sol_unvalued_mints"]  = unvalued_mints_local

                sol_total_idr             += wallet_total_idr
                sol_native_sum            += sol_native_idr_val
                sol_usdt_sum              += sol_usdt_idr_val
                sol_usdc_sum              += sol_usdc_idr_val
                sol_other_token_sum       += other_token_idr_val
                sol_unvalued_count_total  += len(unvalued_mints_local)
                sol_unvalued_mints_global.extend(unvalued_mints_local)

            except Exception as e:
                entry["error"] = f"SOL fetch error: {e}"

        else:
            entry["native_unit"] = network.upper()
            entry["error"]       = f"Network '{network}' belum didukung"

        _elapsed = time.perf_counter() - _tw
        if network == "ethereum":
            _t_eth += _elapsed
        elif network == "bitcoin":
            _t_btc += _elapsed
        elif network == "solana":
            _t_sol += _elapsed
        total_idr += entry["balance_idr"]
        breakdown.append(entry)

    _chain_timings = {
        "fetch_eth_total": round(_t_eth, 3),
        "fetch_btc_total": round(_t_btc, 3),
        "fetch_sol_total": round(_t_sol, 3),
    }
    if os.environ.get("PRIMA_DEBUG"):
        print(f"[PROFILING] chain timings: {_chain_timings}", flush=True)
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
    }


# ---------------------------------------------------------------------------
# Data init
# ---------------------------------------------------------------------------

def init_data():
    try:
        if not os.path.exists(DATA_FILE):
            save_pakd([dict(p) for p in PAKD_DEFAULT])
            return
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
        if not data:
            save_pakd([dict(p) for p in PAKD_DEFAULT])
    except Exception:
        save_pakd([dict(p) for p in PAKD_DEFAULT])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    resp = send_from_directory("../prima-frontend", "index.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/api/status")
def status():
    return jsonify({"status": "ok", "sistem": "PRIMA", "versi": "1.9-pasal50-pasal91"})

@app.route("/api/pakd", methods=["GET"])
def get_pakd():
    return jsonify(load_pakd())

@app.route("/api/pakd", methods=["POST"])
def create_pakd():
    body = request.get_json(force=True)
    if not body.get("id") or not body.get("nama"):
        return jsonify({"error": "id dan nama wajib diisi"}), 400
    data = load_pakd()
    if any(p["id"] == body["id"] for p in data):
        return jsonify({"error": f"PAKD {body['id']} sudah ada"}), 409
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

@app.route("/api/pakd/<pakd_id>", methods=["PUT"])
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
                data[i]["wallets"] = body["wallets"]
            save_pakd(data)
            write_audit("UPDATE_PAKD", f"Edit {pakd_id}")
            return jsonify(data[i])
    return jsonify({"error": f"PAKD {pakd_id} tidak ditemukan"}), 404

@app.route("/api/pakd/<pakd_id>", methods=["DELETE"])
def delete_pakd(pakd_id):
    data = load_pakd()
    new_data = [p for p in data if p["id"] != pakd_id]
    if len(new_data) == len(data):
        return jsonify({"error": f"PAKD {pakd_id} tidak ditemukan"}), 404
    conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM pakd WHERE id = %s", (pakd_id,))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[DB] delete_pakd failed: {e}", flush=True)
    save_pakd(new_data)
    write_audit("DELETE_PAKD", f"Hapus {pakd_id}")
    return jsonify({"deleted": pakd_id})

@app.route("/api/reconciliation")
def reconciliation():
    try:
        _t_total = time.perf_counter()
        _timings = {}
        pakd_list = load_pakd()
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
            aset_dilaporkan  = pakd["aset_dilaporkan"]

            if aset_dilaporkan > 0:
                selisih     = aset_onchain_idr - aset_dilaporkan
                deviasi_pct = selisih / aset_dilaporkan * 100
            else:
                selisih     = 0
                deviasi_pct = 0

            surplus = aset_onchain_idr >= aset_dilaporkan
            if surplus:
                status_rec = "Aman"
            else:
                deficit_pct = abs(deviasi_pct)
                if deficit_pct < 0.01:
                    status_rec = "Aman"
                elif deficit_pct <= 10:
                    status_rec = "Deviasi"
                else:
                    status_rec = "Kritis"

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
                "deviasi_pct":         round(deviasi_pct, 2),
                "surplus":             surplus,
                "status":              status_rec,
                "breakdown":           balance_result["breakdown"],
            })

        _timings["fetch_all_pakd"] = round(time.perf_counter() - _t_fetch, 3)
        write_audit("REKONSILIASI", f"{len(hasil)} PAKD direkonsiliasi (ETH native+USDT+USDC, BTC, SOL)")
        # Resolve harga_fallback flag from ETH price fetch
        _t0 = time.perf_counter()
        _, eth_fallback = get_eth_price_idr()
        _timings["pricing_eth_fallback"] = round(time.perf_counter() - _t0, 3)
        # Save snapshot to Supabase (non-blocking)
        _t0 = time.perf_counter()
        for h in hasil:
            _save_snapshot(
                h["id"], h["nama"],
                h["aset_dilaporkan_idr"], h["aset_onchain_idr"],
                h["deviasi_pct"], h["status"],
                eth_fallback, h["breakdown"]
            )
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
        return jsonify({"status": "error", "message": "Rekonsiliasi gagal", "detail": str(e)}), 500


@app.route("/api/reconciliation-history")
def reconciliation_history():
    conn = _get_db_conn()
    if not conn:
        return jsonify({"error": "Database tidak tersedia"}), 503
    try:
        pakd_id = request.args.get("pakd_id")
        limit = min(int(request.args.get("limit", 30)), 100)
        cur = conn.cursor()
        if pakd_id:
            cur.execute(
                """SELECT id, captured_at, pakd_id, pakd_nama,
                          aset_dilaporkan_idr, aset_onchain_idr,
                          deviasi_persen, status, harga_fallback, network_breakdown
                   FROM reconciliation_snapshots
                   WHERE pakd_id = %s
                   ORDER BY captured_at DESC LIMIT %s""",
                (pakd_id, limit)
            )
        else:
            cur.execute(
                """SELECT id, captured_at, pakd_id, pakd_nama,
                          aset_dilaporkan_idr, aset_onchain_idr,
                          deviasi_persen, status, harga_fallback, network_breakdown
                   FROM reconciliation_snapshots
                   ORDER BY captured_at DESC LIMIT %s""",
                (limit,)
            )
        rows = cur.fetchall()
        hasil = []
        for r in rows:
            hasil.append({
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
            })
        return jsonify({"data": hasil, "total": len(hasil)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/stress-test")
def stress_test():
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

        pakd_list = load_pakd()

        # Baseline on-chain balances at current prices (used by Pasal 91)
        baseline_result = {}
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

        write_audit("STRESS TEST", f"Dual stress test (Pasal 50 + Pasal 91) untuk {len(pakd_list)} PAKD")
        return jsonify({
            "pasal50":        hasil_pasal50,
            "pasal91":        hasil_pasal91,
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
        return jsonify({"status": "error", "message": "Stress test gagal", "detail": str(e)}), 500


@app.route("/api/input-manual", methods=["POST"])
def input_manual():
    try:
        body = request.get_json(silent=True)
        if not body:
            return jsonify({"status": "error", "message": "Request body tidak valid atau bukan JSON"}), 400
        nama    = body.get("nama", "").strip() if isinstance(body.get("nama"), str) else ""
        pakd_id = body.get("id", "").strip()   if isinstance(body.get("id"), str)   else ""
        aset    = body.get("aset_dilaporkan", None)
        if not nama:
            return jsonify({"status": "error", "message": "Field nama wajib diisi"}), 400
        if not pakd_id:
            return jsonify({"status": "error", "message": "Field id wajib diisi"}), 400
        if aset is None or not isinstance(aset, (int, float)) or aset <= 0:
            return jsonify({"status": "error", "message": "Field aset_dilaporkan harus berupa angka positif"}), 400
        raw_wallets = body.get("wallets")
        if raw_wallets is None and "eth_wallet" in body:
            eth_addr = body.get("eth_wallet")
            raw_wallets = [{"network": "ethereum", "address": eth_addr}] if isinstance(eth_addr, str) else []
        if not isinstance(raw_wallets, list) or len(raw_wallets) < 1:
            return jsonify({"status": "error", "message": "Field wallets wajib berupa array minimal 1 entry"}), 400
        canonical_wallets = []
        for w in raw_wallets:
            entry = _normalize_wallet_entry(w, default_network="ethereum")
            if not entry or not entry.get("address"):
                return jsonify({"status": "error", "message": "Setiap wallet entry harus punya field address"}), 400
            ok, err = validate_wallet_address(entry["network"], entry["address"])
            if not ok:
                return jsonify({"status": "error", "message": err}), 400
            canonical_wallets.append(entry)
        pakd_list = load_pakd()
        for p in pakd_list:
            if p["id"] == pakd_id:
                return jsonify({"status": "error", "message": f"ID {pakd_id} sudah terdaftar"}), 400
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
                return jsonify({"status": "error", "message": f"Field {field_name} harus angka non-negatif jika diisi"}), 400
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
        return jsonify({"status": "error", "message": "Input manual gagal", "detail": str(e)}), 500


@app.route("/api/audit-log")
def audit_log():
    try:
        if not os.path.exists(AUDIT_FILE):
            return jsonify({"data": []})
        with open(AUDIT_FILE, "r") as f:
            logs = json.load(f)
        return jsonify({"data": logs})
    except Exception as e:
        return jsonify({"status": "error", "message": "Gagal memuat audit log", "detail": str(e)}), 500

@app.route("/api/wallet-challenge", methods=["POST"])
def wallet_challenge():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"status": "error", "message": "Request body tidak valid atau bukan JSON"}), 400
    address = (body.get("address") or "").strip()
    network = (body.get("network") or "ethereum").strip().lower()
    if not address:
        return jsonify({"status": "error", "message": "Field address wajib diisi"}), 400

    SUPPORTED_PROOF_NETWORKS = {"ethereum", "solana"}
    if network not in SUPPORTED_PROOF_NETWORKS:
        return jsonify({
            "status":  "error",
            "message": f"Network '{network}' belum didukung untuk wallet challenge. "
                       f"Gunakan network: {', '.join(sorted(SUPPORTED_PROOF_NETWORKS))}",
        }), 400

    ok, err = validate_wallet_address(network, address)
    if not ok:
        return jsonify({"status": "error", "message": err}), 400

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
    else:  # solana
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
def wallet_verify():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"status": "error", "message": "Request body tidak valid atau bukan JSON"}), 400

    address   = (body.get("address")   or "").strip()
    signature = (body.get("signature") or "").strip()
    pakd_id   = (body.get("pakd_id")   or "").strip()

    if not address or not signature:
        return jsonify({"status": "error", "message": "Field address dan signature wajib diisi"}), 400

    stored = CHALLENGE_STORE.get(address.lower())
    if not stored:
        return jsonify({
            "status":  "error",
            "message": "Tidak ada challenge aktif untuk address ini. "
                       "Minta challenge baru melalui POST /api/wallet-challenge terlebih dahulu.",
        }), 400

    if time.time() > stored["expires"]:
        del CHALLENGE_STORE[address.lower()]
        return jsonify({"status": "error", "message": "Challenge sudah expired. Minta challenge baru."}), 400

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

    return jsonify({
        "verified":     True,
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
def export_csv_overview():
    import csv, io, psycopg2
    from datetime import datetime
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT ON (pakd_id)
                pakd_id, pakd_nama, created_at,
                aset_dilaporkan_idr, aset_onchain_idr,
                deviasi_persen, status, harga_fallback
            FROM reconciliation_snapshots
            ORDER BY pakd_id, created_at DESC
        """)
        rows = cur.fetchall()
        col_names = [desc[0] for desc in cur.description]
        cur.close()
        conn.close()
    except Exception as e:
        return {"error": str(e)}, 500

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(col_names)
    writer.writerows(rows)

    filename = f"prima-overview-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "text/csv"
    return response

@app.route('/api/export-csv')
def export_csv():
    import csv, io, psycopg2
    from datetime import datetime
    pakd_id = request.args.get('pakd_id')
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
        conn.close()
    except Exception as e:
        return {"error": str(e)}, 500

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(col_names)
    writer.writerows(rows)

    filename = f"prima-export-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "text/csv"
    return response

@app.route('/ping')
def ping():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    init_data()
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port  = int(os.environ.get("PORT", 5000))
    app.run(debug=debug, host="0.0.0.0", port=port)

