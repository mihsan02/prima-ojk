from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import requests
import os
import json
import tempfile
from datetime import datetime
import re
import time

app = Flask(__name__)
CORS(app)

SATOSHI_PER_BTC    = 100_000_000
LAMPORTS_PER_SOL   = 1_000_000_000
PRICE_CACHE        = {}
BALANCE_CACHE      = {}
PRICE_TTL          = 60
BALANCE_TTL        = 30

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

WALLET_RE = {
    "ethereum": re.compile(r"^0x[0-9a-fA-F]{40}$"),
    "bitcoin":  re.compile(r"^(bc1[a-zA-Z0-9]{6,87}|[13][a-km-zA-HJ-NP-Z0-9]{25,34})$"),
    "solana":   re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$"),
}
SUPPORTED_NETWORKS = set(WALLET_RE.keys())

PAKD_DEFAULT = [
    {
        "id": "PAKD-OJK-001",
        "nama": "PT Indodax Nasional Indonesia",
        "wallets": [
            {"network": "ethereum", "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
             "verified": False, "verified_at": None}
        ],
        "aset_dilaporkan": 9814800000
    },
    {
        "id": "PAKD-OJK-002",
        "nama": "PT Tokocrypto",
        "wallets": [
            {"network": "ethereum", "address": "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
             "verified": False, "verified_at": None}
        ],
        "aset_dilaporkan": 3421000000
    }
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
            "eth_native_idr": None,
            "usdt_balance":   None,
            "usdt_idr":       None,
            "usdc_balance":   None,
            "usdc_idr":       None,
            "verified":       verified,
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
                bal = get_cached_balance(
                    "solana", address,
                    lambda a=address: fetch_sol_balance(a)
                )
                entry["balance_native"] = round(bal, 9)
                entry["balance_idr"]    = bal * sol_price_idr
                sol_total_idr          += entry["balance_idr"]
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
    resp = send_from_directory("../prima-frontend", "PRIMA Dashboard Standalone.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/api/status")
def status():
    return jsonify({"status": "ok", "sistem": "PRIMA", "versi": "1.4-multichain-erc20"})


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
                "aset_dilaporkan_idr": aset_dilaporkan,
                "deviasi_pct":         round(deviasi_pct, 2),
                "surplus":             surplus,
                "status":              status_rec,
                "breakdown":           balance_result["breakdown"],
            })

        write_audit("REKONSILIASI", f"{len(hasil)} PAKD direkonsiliasi (ETH native+USDT+USDC, BTC, SOL)")
        return jsonify({"data": hasil, "total_pakd": len(hasil)})

    except Exception as e:
        return jsonify({"status": "error", "message": "Rekonsiliasi gagal", "detail": str(e)}), 500


@app.route("/api/stress-test")
def stress_test():
    """
    Stress test solvabilitas tiga skenario.

    Volatile assets (ETH, BTC, SOL): -30% / -55% / -80%
    Stablecoin assets (USDT, USDC):  -3%  / -8%  / -15%

    Historical basis:
      ETH/BTC: CoinMarketCap historical, Nov 2017 ATH to Dec 2018 bottom (-84% BTC)
      USDC: depegged to USD 0.87 on 11 March 2023 during SVB collapse (Reuters)
      USDT: hit USD 0.95 during 2022 banking stress (CoinGecko historical)

    Threshold lulus: post-stress aset_onchain >= 80% aset_dilaporkan
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

        skenario = {
            "mild":     {"label": "Mild",     "volatile_drop": 0.30, "stable_drop": 0.03},
            "moderate": {"label": "Moderate", "volatile_drop": 0.55, "stable_drop": 0.08},
            "severe":   {"label": "Severe",   "volatile_drop": 0.80, "stable_drop": 0.15},
        }
        hasil = {}
        for key, s in skenario.items():
            lulus = gagal = 0
            eth_stressed  = eth_price  * (1 - s["volatile_drop"])
            btc_stressed  = btc_price  * (1 - s["volatile_drop"])
            sol_stressed  = sol_price  * (1 - s["volatile_drop"])
            usdt_stressed = usdt_price * (1 - s["stable_drop"])
            usdc_stressed = usdc_price * (1 - s["stable_drop"])

            for pakd in pakd_list:
                balance_result = get_total_balance_idr(
                    pakd["wallets"],
                    eth_price_idr=eth_stressed,
                    btc_price_idr=btc_stressed,
                    sol_price_idr=sol_stressed,
                    usdt_price_idr=usdt_stressed,
                    usdc_price_idr=usdc_stressed,
                )
                aset_onchain_stressed = balance_result["total_idr"]
                aset_dilaporkan       = pakd["aset_dilaporkan"]
                rasio = aset_onchain_stressed / aset_dilaporkan if aset_dilaporkan > 0 else 0
                if rasio >= 0.80:
                    lulus += 1
                else:
                    gagal += 1

            hasil[key] = {
                "label":         s["label"],
                "lulus":         lulus,
                "gagal":         gagal,
                "total":         len(pakd_list),
                "eth_stressed":  round(eth_stressed),
                "btc_stressed":  round(btc_stressed),
                "usdt_stressed": round(usdt_stressed, 2),
                "usdc_stressed": round(usdc_stressed, 2),
            }

        write_audit("STRESS TEST", f"Stress test multi-asset dijalankan untuk {len(pakd_list)} PAKD")
        return jsonify({
            "data":             hasil,
            "eth_price_idr":    eth_price,
            "btc_price_idr":    btc_price,
            "usdt_price_idr":   usdt_price,
            "usdc_price_idr":   usdc_price,
            "harga_fallback":   harga_fallback,
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
        new_entry = {"id": pakd_id, "nama": nama, "wallets": canonical_wallets, "aset_dilaporkan": int(aset)}
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


if __name__ == "__main__":
    init_data()
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug, port=5000)