import time
import unittest
from unittest.mock import patch, MagicMock

SATOSHI_PER_BTC = 100_000_000
PRICE_CACHE = {}
BALANCE_CACHE = {}
PRICE_TTL = 60
BALANCE_TTL = 30

def get_cached_price(network, fetch_fn):
    now = time.time()
    if network in PRICE_CACHE:
        cached_at, price = PRICE_CACHE[network]
        if now - cached_at < PRICE_TTL:
            return price
    price = fetch_fn()
    PRICE_CACHE[network] = (now, price)
    return price

def get_cached_balance(network, address, fetch_fn):
    now = time.time()
    key = (network, address)
    if key in BALANCE_CACHE:
        cached_at, balance = BALANCE_CACHE[key]
        if now - cached_at < BALANCE_TTL:
            return balance
    balance = fetch_fn()
    BALANCE_CACHE[key] = (now, balance)
    return balance

def fetch_btc_balance(address):
    import requests
    resp = requests.get(f"https://blockstream.info/api/address/{address}", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    funded = data["chain_stats"]["funded_txo_sum"]
    spent  = data["chain_stats"]["spent_txo_sum"]
    return (funded - spent) / SATOSHI_PER_BTC

def fetch_btc_price_idr():
    import requests
    resp = requests.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": "bitcoin", "vs_currencies": "idr"}, timeout=10)
    resp.raise_for_status()
    return float(resp.json()["bitcoin"]["idr"])

def get_eth_balance(address):
    return 2.0

def get_total_balance_idr(wallets, eth_price_idr=None, btc_price_idr=None):
    if eth_price_idr is None:
        eth_price_idr = 39_910_503
    if btc_price_idr is None:
        btc_price_idr = 0.0
    total_idr = 0.0
    eth_total_idr = 0.0
    btc_total_idr = 0.0
    breakdown = []
    for wallet in wallets:
        network  = wallet.get("network", "ethereum")
        address  = wallet.get("address", "")
        verified = wallet.get("verified", False)
        entry = {"network": network, "address": address, "balance_native": 0.0, "native_unit": "", "balance_idr": 0.0, "verified": verified, "error": None, "fetch_status": "sukses"}
        if network == "ethereum":
            entry["native_unit"] = "ETH"
            try:
                bal = get_cached_balance(network, address, lambda a=address: get_eth_balance(a))
                entry["balance_native"] = bal
                entry["balance_idr"]    = bal * eth_price_idr
                eth_total_idr          += entry["balance_idr"]
            except Exception as e:
                entry["error"] = f"ETH fetch error: {e}"
        elif network == "bitcoin":
            entry["native_unit"] = "BTC"
            try:
                bal = get_cached_balance(network, address, lambda a=address: fetch_btc_balance(a))
                entry["balance_native"] = bal
                entry["balance_idr"]    = bal * btc_price_idr
                btc_total_idr          += entry["balance_idr"]
            except Exception as e:
                entry["fetch_status"] = "gagal"
                entry["error"] = f"BTC fetch error: {e}"
        else:
            entry["native_unit"] = "SOL"
            entry["error"] = "Solana support: Day 3"
        total_idr += entry["balance_idr"]
        breakdown.append(entry)
    return {"total_idr": total_idr, "eth_balance_idr": eth_total_idr, "btc_balance_idr": btc_total_idr, "breakdown": breakdown}

class TestFetchBtcBalance(unittest.TestCase):
    def _make_resp(self, funded, spent):
        m = MagicMock()
        m.json.return_value = {"chain_stats": {"funded_txo_sum": funded, "spent_txo_sum": spent}, "mempool_stats": {"funded_txo_sum": 99999999, "spent_txo_sum": 0}}
        m.raise_for_status.return_value = None
        return m

    def test_basic_conversion(self):
        with patch("requests.get", return_value=self._make_resp(200_000_000, 100_000_000)):
            self.assertAlmostEqual(fetch_btc_balance("bc1q"), 1.0, places=8)

    def test_fractional(self):
        with patch("requests.get", return_value=self._make_resp(350_000_000, 300_000_000)):
            self.assertAlmostEqual(fetch_btc_balance("bc1q"), 0.5, places=8)

    def test_ignores_mempool(self):
        with patch("requests.get", return_value=self._make_resp(100_000_000, 0)):
            self.assertAlmostEqual(fetch_btc_balance("bc1q"), 1.0, places=8)

    def test_zero_wallet(self):
        with patch("requests.get", return_value=self._make_resp(0, 0)):
            self.assertEqual(fetch_btc_balance("bc1q"), 0.0)

class TestFetchBtcPriceIdr(unittest.TestCase):
    def test_returns_float(self):
        m = MagicMock()
        m.json.return_value = {"bitcoin": {"idr": 1_600_000_000}}
        m.raise_for_status.return_value = None
        with patch("requests.get", return_value=m):
            self.assertAlmostEqual(fetch_btc_price_idr(), 1_600_000_000.0)

class TestGetTotalBalanceIdr(unittest.TestCase):
    def setUp(self):
        PRICE_CACHE.clear()
        BALANCE_CACHE.clear()

    def _btc_resp(self, funded, spent):
        m = MagicMock()
        m.json.return_value = {"chain_stats": {"funded_txo_sum": funded, "spent_txo_sum": spent}, "mempool_stats": {"funded_txo_sum": 0, "spent_txo_sum": 0}}
        m.raise_for_status.return_value = None
        return m

    def test_btc_only_idr_correct(self):
        wallets = [{"network": "bitcoin", "address": "bc1q", "verified": True, "verified_at": None}]
        with patch("requests.get", return_value=self._btc_resp(100_000_000, 0)):
            result = get_total_balance_idr(wallets, eth_price_idr=0.0, btc_price_idr=1_600_000_000)
        self.assertAlmostEqual(result["total_idr"], 1_600_000_000.0)
        self.assertAlmostEqual(result["btc_balance_idr"], 1_600_000_000.0)
        # T2.3 (D6): status fetch per-wallet.
        self.assertEqual(result["breakdown"][0]["fetch_status"], "sukses")

    def test_btc_fetch_error_sets_fetch_status_gagal(self):
        """T2.3 (D6): BTC tidak pernah "partial" -- satu try/except, gagal
        kalau except tereksekusi (baris yang mengisi entry["error"])."""
        wallets = [{"network": "bitcoin", "address": "bc1q", "verified": True, "verified_at": None}]
        broken_resp = MagicMock()
        broken_resp.raise_for_status.side_effect = Exception("BTC RPC down")
        with patch("requests.get", return_value=broken_resp):
            result = get_total_balance_idr(wallets, eth_price_idr=0.0, btc_price_idr=1_600_000_000)
        self.assertIsNotNone(result["breakdown"][0]["error"])
        self.assertEqual(result["breakdown"][0]["fetch_status"], "gagal")

    def test_eth_plus_btc_total(self):
        BALANCE_CACHE.clear()
        wallets = [
            {"network": "ethereum", "address": "0xETH", "verified": True, "verified_at": None},
            {"network": "bitcoin",  "address": "bc1qBTC", "verified": True, "verified_at": None},
        ]
        with patch("requests.get", return_value=self._btc_resp(50_000_000, 0)):
            result = get_total_balance_idr(wallets, eth_price_idr=50_000_000, btc_price_idr=1_600_000_000)
        self.assertAlmostEqual(result["eth_balance_idr"], 100_000_000.0, places=0)
        self.assertAlmostEqual(result["btc_balance_idr"], 800_000_000.0, places=0)
        self.assertAlmostEqual(result["total_idr"], 900_000_000.0, places=0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
