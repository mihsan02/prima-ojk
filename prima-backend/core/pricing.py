"""Kaskade harga: cache, sumber harga, dan kurs USD->IDR.

Dipisah dari app.py pada T1.2 (D3/D4). Arah dependensi satu arah:
app -> core. Modul ini tidak boleh meng-import app.

Isi modul dipindah apa adanya dari app.py -- T1.2 tidak mengubah
perilaku fungsi mana pun di sini. Fallback ETH hardcoded (D5) dan
_get_usd_idr_rate (D14) sengaja dibiarkan utuh; keduanya T1.3.
"""

import os
import time

import requests


PRICE_CACHE        = {}


# int immutable: app.PRICE_TTL hanya salinan nilai. Tes yang perlu
# memaksa cache basi harus monkeypatch core.pricing.PRICE_TTL,
# bukan app.PRICE_TTL.
PRICE_TTL          = 300   # bumped from 60 (Day 15): CMC credit budget guard


MAX_PRICE_CACHE         = 100


def _evict_stale_entries(cache_dict, max_entries):
    """Hapus entry terlama jika cache melebihi batas."""
    if len(cache_dict) <= max_entries:
        return
    sorted_keys = sorted(
        cache_dict.keys(),
        key=lambda k: cache_dict[k][0] if isinstance(cache_dict[k], tuple) else 0
    )
    to_remove = len(cache_dict) - max_entries
    for k in sorted_keys[:to_remove]:
        del cache_dict[k]


# Fallback IDR/USD rate used only when CoinGecko is unreachable.
# Conservative estimate — updated manually per quarter.
# Current reference: Bank Indonesia Kurs Tengah, April 2026.
FALLBACK_STABLECOIN_IDR = 16_350.0


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
        _evict_stale_entries(PRICE_CACHE, MAX_PRICE_CACHE)
        return success
    except Exception as e:
        # Log to stdout for Render Logs visibility (Day 15 cascade debug)
        if os.environ.get('PRIMA_DEBUG'):
            print(f"[JUPITER] price fetch failed: {type(e).__name__}: {e}", flush=True)
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


def _get_usd_idr_rate(usdt_price_idr=None):
    """
    Return USD-to-IDR rate via USDT IDR price (USDT is USD-pegged within
    de-peg tolerance). No new API dependency: reuses _get_stablecoin_prices_idr.
    Falls back to FALLBACK_STABLECOIN_IDR on cascade failure.

    T1.3 (D14): usdt_price_idr dioper oleh pemanggil yang SUDAH punya harga
    USDT -- termasuk stress test yang mengoper harga ter-depeg. Tanpa ini
    penilaian "other token" diam-diam memakai kurs live, sehingga stress
    test Pasal 50/91 menguji dengan tekanan yang lebih ringan dari yang
    diminta. Kalau None, perilaku lama tidak berubah.
    """
    if usdt_price_idr is not None:
        return float(usdt_price_idr)
    try:
        usdt_idr, _ = _get_stablecoin_prices_idr()
        return float(usdt_idr)
    except Exception:
        return float(FALLBACK_STABLECOIN_IDR)
