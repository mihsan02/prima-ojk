"""
PRIMA — Day 2 Multi-Chain Sprint: Bitcoin Support
==================================================
Additions to prima-backend/app.py:

  1.  SATOSHI_PER_BTC constant
  2.  Cache infrastructure (PRICE_CACHE, BALANCE_CACHE) — add near top with other globals
  3.  fetch_btc_balance(address) → float (BTC)
  4.  fetch_btc_price_idr()     → float (IDR)
  5.  get_cached_price(network, fetch_fn)
  6.  get_cached_balance(network, address, fetch_fn)
  7.  get_total_balance_idr(wallets) — replaces / extends your existing get_total_balance()
  8.  Reconciliation endpoint update — adds btc_balance_idr and breakdown to response

Integration instructions
------------------------
A) Find the block of constants near your Etherscan / CoinGecko config and insert:
     SATOSHI_PER_BTC = 100_000_000
     PRICE_CACHE     = {}
     BALANCE_CACHE   = {}
     PRICE_TTL       = 60   # seconds
     BALANCE_TTL     = 30   # seconds

B) Add the five new functions anywhere above the reconciliation endpoint.

C) In the reconciliation endpoint, replace the call to your current balance
   fetcher with get_total_balance_idr(pakd["wallets"]) and spread the
   returned dict into the response payload.

D) Do NOT touch your existing ETH fetcher function — get_total_balance_idr
   calls it internally.
"""

import time
import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SATOSHI_PER_BTC = 100_000_000  # 1 BTC = 100 million satoshi


# ---------------------------------------------------------------------------
# Cache infrastructure
# Add these near your other module-level globals, e.g. next to DATA_FILE.
# ---------------------------------------------------------------------------

PRICE_CACHE   = {}   # key: "bitcoin" | "ethereum" → (timestamp, float)
BALANCE_CACHE = {}   # key: (network, address)     → (timestamp, float)
PRICE_TTL     = 60   # seconds before price is re-fetched
BALANCE_TTL   = 30   # seconds before balance is re-fetched


# ---------------------------------------------------------------------------
# Helpers: cache wrappers
# ---------------------------------------------------------------------------

def get_cached_price(network: str, fetch_fn) -> float:
    """
    Return a cached price for `network`, calling `fetch_fn` only when the
    cache is cold or stale (> PRICE_TTL seconds old).
    """
    now = time.time()
    if network in PRICE_CACHE:
        cached_at, price = PRICE_CACHE[network]
        if now - cached_at < PRICE_TTL:
            return price
    price = fetch_fn()
    PRICE_CACHE[network] = (now, price)
    return price


def get_cached_balance(network: str, address: str, fetch_fn) -> float:
    """
    Return a cached balance for (network, address), calling `fetch_fn` only
    when the cache is cold or stale (> BALANCE_TTL seconds old).
    """
    now = time.time()
    key = (network, address)
    if key in BALANCE_CACHE:
        cached_at, balance = BALANCE_CACHE[key]
        if now - cached_at < BALANCE_TTL:
            return balance
    balance = fetch_fn()
    BALANCE_CACHE[key] = (now, balance)
    return balance


# ---------------------------------------------------------------------------
# Bitcoin fetchers
# ---------------------------------------------------------------------------

def fetch_btc_balance(address: str) -> float:
    """
    Fetch confirmed BTC balance for a native SegWit (bc1q...) or legacy
    (1... / 3...) address from Blockstream Esplora public API.

    Returns balance in BTC (float).

    Why chain_stats only, not mempool_stats:
    Unconfirmed transactions must not count toward regulatory reserve claims.
    A PAKD cannot declare solvency based on transactions that may be evicted
    from the mempool. Only chain_stats reflects settled, confirmed balance.

    Esplora response shape (relevant fields):
      {
        "chain_stats": {
          "funded_txo_sum": <int, satoshis received, confirmed>,
          "spent_txo_sum":  <int, satoshis spent, confirmed>
        },
        "mempool_stats": { ... }   ← intentionally ignored
      }

    Source: https://github.com/Blockstream/esplora/blob/master/API.md
    """
    url = f"https://blockstream.info/api/address/{address}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    funded = data["chain_stats"]["funded_txo_sum"]  # satoshis
    spent  = data["chain_stats"]["spent_txo_sum"]   # satoshis
    balance_satoshi = funded - spent
    return balance_satoshi / SATOSHI_PER_BTC


def fetch_btc_price_idr() -> float:
    """
    Fetch current BTC/IDR price from CoinGecko public API.
    Returns price as float (IDR per 1 BTC).

    Endpoint: GET https://api.coingecko.com/api/v3/simple/price
    Params:   ids=bitcoin, vs_currencies=idr
    Response: { "bitcoin": { "idr": 1234567890 } }
    """
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "bitcoin", "vs_currencies": "idr"}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return float(resp.json()["bitcoin"]["idr"])


# ---------------------------------------------------------------------------
# Unified balance fetcher — replaces / extends your current ETH-only version
# ---------------------------------------------------------------------------

def get_total_balance_idr(wallets: list, eth_price_idr: float = None, btc_price_idr: float = None) -> dict:
    """
    Fetch on-chain balance for all wallets of a PAKD across Ethereum and Bitcoin.
    Solana support is Day 3 — wallets with network="solana" are recorded with
    balance=0 and a note, so they don't crash the endpoint but are visible in
    the breakdown.

    Parameters
    ----------
    wallets       : list of dicts — [{network, address, verified, verified_at}, ...]
    eth_price_idr : optional override (used in tests / stress-test callers)
    btc_price_idr : optional override (used in tests / stress-test callers)

    Returns
    -------
    {
      "total_idr"       : float,
      "eth_balance_idr" : float,
      "btc_balance_idr" : float,
      "breakdown"       : [
        {
          "network"        : str,
          "address"        : str,
          "balance_native" : float,
          "native_unit"    : str,
          "balance_idr"    : float,
          "verified"       : bool,
          "error"          : str | None   ← set if fetch failed
        },
        ...
      ]
    }
    """
    # Fetch prices once per reconciliation call (cache handles rate limiting)
    if eth_price_idr is None:
        try:
            eth_price_idr = get_cached_price("ethereum", fetch_eth_price_idr)
        except Exception as e:
            eth_price_idr = 0.0
            eth_price_error = str(e)
        else:
            eth_price_error = None

    if btc_price_idr is None:
        try:
            btc_price_idr = get_cached_price("bitcoin", fetch_btc_price_idr)
        except Exception as e:
            btc_price_idr = 0.0
            btc_price_error = str(e)
        else:
            btc_price_error = None

    total_idr     = 0.0
    eth_total_idr = 0.0
    btc_total_idr = 0.0
    breakdown     = []

    for wallet in wallets:
        network  = wallet.get("network", "ethereum")
        address  = wallet.get("address", "")
        verified = wallet.get("verified", False)
        entry = {
            "network"        : network,
            "address"        : address,
            "balance_native" : 0.0,
            "native_unit"    : "",
            "balance_idr"    : 0.0,
            "verified"       : verified,
            "error"          : None,
        }

        if network == "ethereum":
            entry["native_unit"] = "ETH"
            try:
                bal = get_cached_balance(
                    network, address,
                    lambda a=address: fetch_eth_balance(a)
                )
                entry["balance_native"] = bal
                entry["balance_idr"]    = bal * eth_price_idr
                eth_total_idr          += entry["balance_idr"]
            except Exception as e:
                entry["error"] = f"ETH fetch error: {e}"

        elif network == "bitcoin":
            entry["native_unit"] = "BTC"
            try:
                bal = get_cached_balance(
                    network, address,
                    lambda a=address: fetch_btc_balance(a)
                )
                entry["balance_native"] = bal
                entry["balance_idr"]    = bal * btc_price_idr
                btc_total_idr          += entry["balance_idr"]
            except Exception as e:
                entry["error"] = f"BTC fetch error: {e}"

        else:
            # Solana — Day 3
            entry["native_unit"] = "SOL"
            entry["error"]       = "Solana support: Day 3"

        total_idr += entry["balance_idr"]
        breakdown.append(entry)

    return {
        "total_idr"       : total_idr,
        "eth_balance_idr" : eth_total_idr,
        "btc_balance_idr" : btc_total_idr,
        "breakdown"       : breakdown,
    }


# ---------------------------------------------------------------------------
# Reconciliation endpoint — REPLACE the body of your existing /api/reconciliation
# with the pattern below. The diff is: call get_total_balance_idr() and spread
# the returned keys into the response dict.
# ---------------------------------------------------------------------------

# BEFORE (your current endpoint, roughly):
#
#   total_idr = fetch_all_wallets(pakd)
#   response = {
#       "pakd_id": pakd["id"],
#       "total_balance_idr": total_idr,
#       ...
#   }
#
# AFTER:

def reconciliation_response_builder(pakd: dict) -> dict:
    """
    NOT a Flask endpoint — this is a helper you call inside your endpoint.
    Keeps the endpoint itself thin.

    Assumes pakd["wallets"] is the new schema:
      [{network, address, verified, verified_at}, ...]
    The _migrate_record() from Day 1 guarantees this on load.
    """
    balance_result = get_total_balance_idr(pakd["wallets"])

    total_idr       = balance_result["total_idr"]
    aset_dilaporkan = pakd.get("aset_dilaporkan", 0)

    if aset_dilaporkan > 0:
        deviasi_persen = ((total_idr - aset_dilaporkan) / aset_dilaporkan) * 100
    else:
        deviasi_persen = 0.0

    if deviasi_persen >= 0:
        status = "Aman"
    elif deviasi_persen >= -10:
        status = "Deviasi"
    else:
        status = "Kritis"

    return {
        "pakd_id"         : pakd["id"],
        "nama"            : pakd.get("nama", ""),
        "total_balance_idr": total_idr,
        "eth_balance_idr" : balance_result["eth_balance_idr"],
        "btc_balance_idr" : balance_result["btc_balance_idr"],
        "aset_dilaporkan" : aset_dilaporkan,
        "deviasi_persen"  : round(deviasi_persen, 2),
        "status"          : status,
        "breakdown"       : balance_result["breakdown"],
    }
