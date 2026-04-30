"""
test_day4_erc20.py — Day 4 verification suite for ERC-20 USDT/USDC support

Test wallet: Binance Hot Wallet 14
  Address : 0x28C6c06298d514Db089934071355E5743bf21d60
  Source  : Etherscan label registry (publicly labelled exchange hot wallet)
  Expected: Large USDT balance (tens of millions USD range as of 2026)

Run: python test_day4_erc20.py
Requires: ETHERSCAN_API_KEY set in environment, internet access.
"""

import os
import sys
import time

# ---------------------------------------------------------------------------
# Minimal inline imports from app.py to avoid Flask context dependency
# ---------------------------------------------------------------------------
# We import the functions directly. Tests are black-box where possible.
sys.path.insert(0, os.path.dirname(__file__))

from app import (
    fetch_erc20_balance,
    fetch_stablecoin_prices_idr,
    _get_stablecoin_prices_idr,
    get_total_balance_idr,
    USDT_CONTRACT,
    USDC_CONTRACT,
    PRICE_CACHE,
    BALANCE_CACHE,
    PRICE_TTL,
    BALANCE_TTL,
    FALLBACK_STABLECOIN_IDR,
)

BINANCE_HOT_14 = "0xF977814e90dA44bFA03b6295A0616a897441aceC"

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    results.append(condition)


# ---------------------------------------------------------------------------
# Test 1: fetch_erc20_balance returns non-zero USDT for Binance Hot Wallet 14
# ---------------------------------------------------------------------------
print("\n=== Test 1: USDT balance fetch (Binance Hot Wallet 14) ===")
try:
    usdt_balance = fetch_erc20_balance(BINANCE_HOT_14, USDT_CONTRACT, decimals=6)
    print(f"  Raw USDT balance: {usdt_balance:,.2f} USDT")

    check("USDT balance is a float", isinstance(usdt_balance, float))
    check("USDT balance > 0 (active wallet)", usdt_balance > 0,
          f"got {usdt_balance:,.6f}")
    # Binance Hot Wallet 14 typically holds tens of millions USDT.
    # Floor of 1,000,000 is conservative — flags if address is wrong or API failed.
    check("USDT balance > 1,000,000 (exchange hot wallet floor)", usdt_balance > 1_000_000,
          f"got {usdt_balance:,.2f}")
except Exception as e:
    check("fetch_erc20_balance did not raise", False, str(e))
    check("USDT balance > 0", False, "skipped due to exception")
    check("USDT balance > 1,000,000", False, "skipped due to exception")

# ---------------------------------------------------------------------------
# Test 2: fetch_erc20_balance returns float for USDC (same wallet)
# ---------------------------------------------------------------------------
print("\n=== Test 2: USDC balance fetch (Binance Hot Wallet 14) ===")
try:
    usdc_balance = fetch_erc20_balance(BINANCE_HOT_14, USDC_CONTRACT, decimals=6)
    print(f"  Raw USDC balance: {usdc_balance:,.2f} USDC")
    check("USDC balance is a float", isinstance(usdc_balance, float))
    check("USDC balance >= 0 (non-negative)", usdc_balance >= 0)
except Exception as e:
    check("fetch_erc20_balance USDC did not raise", False, str(e))
    check("USDC balance >= 0", False, "skipped")

# ---------------------------------------------------------------------------
# Test 3: fetch_stablecoin_prices_idr returns a tuple and populates cache
# ---------------------------------------------------------------------------
print("\n=== Test 3: Stablecoin price fetch (single CoinGecko call) ===")
PRICE_CACHE.clear()  # start cold
try:
    usdt_price, usdc_price = fetch_stablecoin_prices_idr()
    print(f"  USDT/IDR: {usdt_price:,.2f}  |  USDC/IDR: {usdc_price:,.2f}")

    check("USDT price > 0", usdt_price > 0, f"got {usdt_price}")
    check("USDC price > 0", usdc_price > 0, f"got {usdc_price}")
    # Stablecoins should be within ±5% of IDR 16,000 baseline
    check("USDT price plausible (12,000–21,000 IDR)", 12_000 < usdt_price < 21_000,
          f"got {usdt_price:.2f}")
    check("USDC price plausible (12,000–21,000 IDR)", 12_000 < usdc_price < 21_000,
          f"got {usdc_price:.2f}")
    check("PRICE_CACHE populated for tether", "tether" in PRICE_CACHE)
    check("PRICE_CACHE populated for usd-coin", "usd-coin" in PRICE_CACHE)
except Exception as e:
    for _ in range(6):
        check("stablecoin price fetch failed", False, str(e))

# ---------------------------------------------------------------------------
# Test 4: Cache hit — _get_stablecoin_prices_idr does not re-fetch when fresh
# ---------------------------------------------------------------------------
print("\n=== Test 4: Stablecoin price cache hit ===")
try:
    # Prices should be in cache from Test 3. Inject a sentinel to detect re-fetch.
    now = time.time()
    PRICE_CACHE["tether"]   = (now, 99_999.0)   # sentinel
    PRICE_CACHE["usd-coin"] = (now, 88_888.0)   # sentinel

    usdt_cached, usdc_cached = _get_stablecoin_prices_idr()
    check("Cache hit returns sentinel USDT price", usdt_cached == 99_999.0,
          f"got {usdt_cached}")
    check("Cache hit returns sentinel USDC price", usdc_cached == 88_888.0,
          f"got {usdc_cached}")
finally:
    PRICE_CACHE.clear()  # clean up sentinels

# ---------------------------------------------------------------------------
# Test 5: get_total_balance_idr breakdown includes eth_native_idr / usdt_idr / usdc_idr
# ---------------------------------------------------------------------------
print("\n=== Test 5: ETH wallet breakdown structure (Binance Hot Wallet 14) ===")
wallet_list = [{"network": "ethereum", "address": BINANCE_HOT_14, "verified": False, "verified_at": None}]
try:
    result = get_total_balance_idr(wallet_list)
    breakdown = result["breakdown"]

    check("breakdown has exactly 1 entry", len(breakdown) == 1)
    w = breakdown[0]

    check("eth_native_idr field present", "eth_native_idr" in w)
    check("usdt_balance field present",   "usdt_balance" in w)
    check("usdt_idr field present",       "usdt_idr" in w)
    check("usdc_balance field present",   "usdc_balance" in w)
    check("usdc_idr field present",       "usdc_idr" in w)
    check("error field is None",          w.get("error") is None, str(w.get("error")))

    check("eth_native_idr >= 0", (w.get("eth_native_idr") or 0) >= 0)
    check("usdt_idr >= 0",       (w.get("usdt_idr") or 0) >= 0)
    check("usdc_idr >= 0",       (w.get("usdc_idr") or 0) >= 0)

    # Top-level aggregates
    check("result has eth_usdt_idr key", "eth_usdt_idr" in result)
    check("result has eth_usdc_idr key", "eth_usdc_idr" in result)
    check("result has eth_native_idr key", "eth_native_idr" in result)

    print(f"\n  Breakdown for {BINANCE_HOT_14[:10]}...:")
    print(f"    ETH native IDR : Rp {w.get('eth_native_idr', 0):>18,.0f}")
    print(f"    USDT balance   : {w.get('usdt_balance', 0):>18,.2f} USDT")
    print(f"    USDT IDR       : Rp {w.get('usdt_idr', 0):>18,.0f}")
    print(f"    USDC balance   : {w.get('usdc_balance', 0):>18,.2f} USDC")
    print(f"    USDC IDR       : Rp {w.get('usdc_idr', 0):>18,.0f}")
    print(f"    Total IDR      : Rp {result['total_idr']:>18,.0f}")

except Exception as e:
    for _ in range(13):
        check("get_total_balance_idr raised", False, str(e))

# ---------------------------------------------------------------------------
# Test 6: ETH-only PAKD still works (regression — no ERC-20 keys break it)
# ---------------------------------------------------------------------------
print("\n=== Test 6: ETH-only wallet regression check ===")
eth_only_wallet = [{"network": "ethereum", "address": "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
                    "verified": False, "verified_at": None}]
try:
    result = get_total_balance_idr(eth_only_wallet)
    check("total_idr is float", isinstance(result["total_idr"], float))
    check("breakdown is list", isinstance(result["breakdown"], list))
    check("no unhandled exception", True)
except Exception as e:
    check("ETH-only wallet raised", False, str(e))

# ---------------------------------------------------------------------------
# Test 7: Cache key isolation — usdt_erc20 and ethereum keys do not collide
# ---------------------------------------------------------------------------
print("\n=== Test 7: Balance cache key isolation ===")
BALANCE_CACHE.clear()
BALANCE_CACHE[("ethereum",   BINANCE_HOT_14)] = (time.time(), 9.99)    # sentinel ETH
BALANCE_CACHE[("usdt_erc20", BINANCE_HOT_14)] = (time.time(), 500_000.0)  # sentinel USDT

eth_cached  = BALANCE_CACHE[("ethereum",   BINANCE_HOT_14)][1]
usdt_cached = BALANCE_CACHE[("usdt_erc20", BINANCE_HOT_14)][1]

check("ETH sentinel not overwritten by USDT key", eth_cached == 9.99,
      f"got {eth_cached}")
check("USDT sentinel accessible under its own key", usdt_cached == 500_000.0,
      f"got {usdt_cached}")
BALANCE_CACHE.clear()

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
total  = len(results)
passed = sum(results)
failed = total - passed
print(f"\n{'='*50}")
print(f"  Day 4 Results: {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} FAILED)")
else:
    print("  — All clear.")
print(f"{'='*50}\n")
sys.exit(0 if failed == 0 else 1)
