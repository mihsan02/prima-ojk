from flask import Flask, jsonify, request, send_from_directory
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
PRICE_TTL          = 60
BALANCE_TTL        = 30

CHALLENGE_STORE = {}
CHALLENGE_TTL   = 300

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
USDT_MINT_SOL = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
USDC_MINT_SOL = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
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
            }
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


def load_pakd():
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

def get_eth_price_idr():
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
    Fetch current BTC/IDR price from CoinGecko public API.
    Returns float (IDR per 1 BTC).
    """
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
        "https://api.mainnet-beta.solana.com",
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
    Fetch current SOL/IDR price from CoinGecko public API.
    Returns float (IDR per 1 SOL).
    """
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
        "https://api.mainnet-beta.solana.com",
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

# ---------------------------------------------------------------------------
# Unified multi-network balance fetcher (updated Day 4)
# ---------------------------------------------------------------------------

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
    breakdown      = []

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
            "sol_native_idr":   None,
            "sol_usdt_balance": None,
            "sol_usdt_idr":     None,
            "sol_usdc_balance": None,
            "sol_usdc_idr":     None,
            "verified":         verified,
            "error":          None,
        }

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
                # Native SOL
                sol_bal = get_cached_balance(
                    "solana", address,
                    lambda a=address: fetch_sol_balance(a)
                )
                sol_native_idr_val = sol_bal * sol_price_idr

                # USDT SPL (cache key namespaced to avoid collision with native SOL)
                sol_usdt_bal = get_cached_balance(
                    "sol_usdt_spl", address,
                    lambda a=address: fetch_spl_token_balance(a, USDT_MINT_SOL)
                )
                sol_usdt_idr_val = sol_usdt_bal * usdt_price_idr

                # USDC SPL
                sol_usdc_bal = get_cached_balance(
                    "sol_usdc_spl", address,
                    lambda a=address: fetch_spl_token_balance(a, USDC_MINT_SOL)
                )
                sol_usdc_idr_val = sol_usdc_bal * usdc_price_idr

                wallet_total_idr = sol_native_idr_val + sol_usdt_idr_val + sol_usdc_idr_val

                entry["balance_native"]   = round(sol_bal, 9)
                entry["balance_idr"]      = wallet_total_idr
                entry["sol_native_idr"]   = round(sol_native_idr_val)
                entry["sol_usdt_balance"] = round(sol_usdt_bal, 6)
                entry["sol_usdt_idr"]     = round(sol_usdt_idr_val)
                entry["sol_usdc_balance"] = round(sol_usdc_bal, 6)
                entry["sol_usdc_idr"]     = round(sol_usdc_idr_val)

                sol_total_idr  += wallet_total_idr
                sol_native_sum += sol_native_idr_val
                sol_usdt_sum   += sol_usdt_idr_val
                sol_usdc_sum   += sol_usdc_idr_val

            except Exception as e:
                entry["error"] = f"SOL fetch error: {e}"

        else:
            entry["native_unit"] = network.upper()
            entry["error"]       = f"Network '{network}' belum didukung"

        total_idr += entry["balance_idr"]
        breakdown.append(entry)

    return {
        "total_idr":       total_idr,
        "eth_balance_idr": eth_total_idr,
        "eth_native_idr":  eth_native_sum,
        "eth_usdt_idr":    eth_usdt_sum,
        "eth_usdc_idr":    eth_usdc_sum,
        "btc_balance_idr": btc_total_idr,
        "sol_balance_idr": sol_total_idr,
        "sol_native_idr":  sol_native_sum,
        "sol_usdt_idr":    sol_usdt_sum,
        "sol_usdc_idr":    sol_usdc_sum,
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


@app.route("/api/reconciliation")
def reconciliation():
    try:
        pakd_list = load_pakd()
        hasil = []

        for pakd in pakd_list:
            wallets = pakd["wallets"]

            balance_result   = get_total_balance_idr(wallets)
            aset_onchain_idr = balance_result["total_idr"]
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
                if deficit_pct < 5:
                    status_rec = "Aman"
                elif deficit_pct < 15:
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
                "aset_dilaporkan_idr": aset_dilaporkan,
                "deviasi_pct":         round(deviasi_pct, 2),
                "surplus":             surplus,
                "status":              status_rec,
                "breakdown":           balance_result["breakdown"],
            })

        write_audit("REKONSILIASI", f"{len(hasil)} PAKD direkonsiliasi (ETH native+USDT+USDC, BTC, SOL)")
        # Resolve harga_fallback flag from ETH price fetch
        _, eth_fallback = get_eth_price_idr()
        return jsonify({
            "data":          hasil,
            "total_pakd":    len(hasil),
            "harga_fallback": eth_fallback,
        })

    except Exception as e:
        return jsonify({"status": "error", "message": "Rekonsiliasi gagal", "detail": str(e)}), 500


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
        baseline_idr = {}
        for pakd in pakd_list:
            result = get_total_balance_idr(
                pakd["wallets"],
                eth_price_idr=eth_price,
                btc_price_idr=btc_price,
                sol_price_idr=sol_price,
                usdt_price_idr=usdt_price,
                usdc_price_idr=usdc_price,
            )
            baseline_idr[pakd["id"]] = result["total_idr"]

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
                result = get_total_balance_idr(
                    pakd["wallets"],
                    eth_price_idr=eth_stressed,
                    btc_price_idr=btc_stressed,
                    sol_price_idr=sol_stressed,
                    usdt_price_idr=usdt_stressed,
                    usdc_price_idr=usdc_stressed,
                )
                aset_stressed = result["total_idr"]
                aset_baseline = baseline_idr[pakd["id"]]

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
                aset_onchain = baseline_idr[pakd["id"]]

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

if __name__ == "__main__":
    init_data()
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port  = int(os.environ.get("PORT", 5000))
    app.run(debug=debug, host="0.0.0.0", port=port)