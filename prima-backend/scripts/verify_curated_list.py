"""
PRIMA Day 17 - Verifikasi 50 contract ETH curated list (V2 patched).

Changes vs v1:
  - Etherscan endpoint V2 dengan chainid=1 wajib param
  - Explicit dotenv path resolution
  - Print Etherscan raw response saat FAIL untuk diagnostic
"""

import os
import time
import requests
from dotenv import load_dotenv

# Explicit path, file ada di parent directory bukan prima-backend/
load_dotenv("/workspaces/prima-ojk/.env")

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

WHALE_ADDRESS = "0x28C6c06298d514Db089934071355E5743bf21d60"  # Binance 14

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


def check_etherscan_balance(contract):
    """Etherscan V2 endpoint dengan chainid=1 wajib."""
    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid":         1,
        "module":          "account",
        "action":          "tokenbalance",
        "contractaddress": contract,
        "address":         WHALE_ADDRESS,
        "tag":             "latest",
        "apikey":          ETHERSCAN_API_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data.get("status") == "1":
            return True, int(data["result"])
        return False, data.get("message", "unknown") + ": " + str(data.get("result", ""))[:50]
    except Exception as e:
        return False, str(e)[:50]


def check_coingecko_price(contracts_csv):
    url = "https://api.coingecko.com/api/v3/simple/token_price/ethereum"
    headers = {"x-cg-demo-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY else {}
    params = {
        "contract_addresses": contracts_csv,
        "vs_currencies":      "usd",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"  WARNING CoinGecko HTTP {r.status_code}")
            return {}
        return r.json()
    except Exception as e:
        print(f"  WARNING CoinGecko exception: {e}")
        return {}


def main():
    print("=" * 78)
    print(f"PRIMA Day 17 curated list verification (V2 patched)")
    print(f"Total contracts: {len(ETH_CURATED_TOKENS)}")
    print(f"Etherscan key loaded: {bool(ETHERSCAN_API_KEY)}, len={len(ETHERSCAN_API_KEY or '')}")
    print(f"CoinGecko key loaded: {bool(COINGECKO_API_KEY)}, len={len(COINGECKO_API_KEY or '')}")
    print("=" * 78)

    if not ETHERSCAN_API_KEY:
        print("FATAL: ETHERSCAN_API_KEY env var not set")
        return

    # Stage 1: CoinGecko batched, 2 batches of 25
    all_prices = {}
    for i in range(0, len(ETH_CURATED_TOKENS), 25):
        batch = ETH_CURATED_TOKENS[i:i+25]
        csv = ",".join(t["contract"] for t in batch)
        print(f"\nCoinGecko batch {i//25 + 1} ({len(batch)} contracts)...")
        result = check_coingecko_price(csv)
        all_prices.update({k.lower(): v for k, v in result.items()})
        time.sleep(2)

    # Stage 2: per-contract Etherscan V2 smoke test
    print("\n" + "=" * 78)
    print(f"{'#':3} {'SYMBOL':8} {'CG_PRICE':14} {'ETHERSCAN':25} VERDICT")
    print("=" * 78)

    pass_count = 0
    fail_list  = []

    for idx, token in enumerate(ETH_CURATED_TOKENS, 1):
        contract_lc = token["contract"].lower()
        price_data  = all_prices.get(contract_lc, {})
        usd_price   = price_data.get("usd") if price_data else None

        es_ok, es_data = check_etherscan_balance(token["contract"])
        time.sleep(0.25)

        cg_status = f"${usd_price:.4f}" if usd_price else "no price"
        es_status = "OK" if es_ok else str(es_data)[:25]

        if usd_price and usd_price > 0 and es_ok:
            verdict = "PASS"
            pass_count += 1
        else:
            verdict = "FAIL"
            fail_list.append({
                "symbol":   token["symbol"],
                "contract": token["contract"],
                "cg":       cg_status,
                "es":       es_status,
            })

        print(f"{idx:3} {token['symbol']:8} {cg_status:14} {es_status:25} {verdict}")

    print("\n" + "=" * 78)
    print(f"PASS: {pass_count} / {len(ETH_CURATED_TOKENS)}")
    print(f"FAIL: {len(fail_list)}")

    if fail_list:
        print("\nContracts requiring manual replacement or removal:")
        for f in fail_list:
            print(f"  {f['symbol']:8} {f['contract']}  cg={f['cg']}  es={f['es']}")
    else:
        print("\nAll 50 contracts verified. Lanjut ke app.py integration.")


if __name__ == "__main__":
    main()
