"""D25: get_total_balance_idr harus melaporkan provenance harga.

Kelengkapan data hanya bisa dinilai kalau pemanggil tahu dari mana tiap
harga datang. Tanpa kunci "provenance_harga" pada kembalian,
hitung_kelengkapan() menerima dict kosong dan menganggap SETIAP jaringan
yang dipegang PAKD kehilangan harga -- tidak ada satu pun PAKD yang bisa
dinyatakan LENGKAP.

Semua harga dan saldo di-mock. Nol panggilan jaringan.
"""

import unittest
from unittest.mock import patch

import app as prima_app
import core.pricing as pricing
from core.completeness import hitung_kelengkapan

AS_OF = "2026-08-19T00:00:00Z"

ETH_WALLET = {"network": "ethereum",
              "address": "0x0681d8db095565fe8a346fa0277bffde9c0edbbf",
              "verified": True}
BTC_WALLET = {"network": "bitcoin",
              "address": "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
              "verified": True}
SOL_WALLET = {"network": "solana",
              "address": "So11111111111111111111111111111111111111112",
              "verified": True}
WALLETS = [ETH_WALLET, BTC_WALLET, SOL_WALLET]

MOCK_ETH_PRICE = 40_000_000.0
MOCK_BTC_PRICE = 1_500_000_000.0
MOCK_SOL_PRICE = 1_500_000.0
MOCK_USDT_PRICE = 16_400.0
MOCK_USDC_PRICE = 16_400.0

HARGA = {"ethereum": MOCK_ETH_PRICE,
         "bitcoin": MOCK_BTC_PRICE,
         "solana": MOCK_SOL_PRICE}


def _prov(network, sumber="cmc", umur=0):
    return {"nilai": HARGA[network], "sumber": sumber,
            "as_of": AS_OF, "umur_detik": umur}


def _harga_sehat(network, fetch_fn):
    """get_cached_price palsu: ketiga jaringan berhasil."""
    return HARGA[network]


def _prov_sehat(network, fetch_fn):
    """get_price_with_provenance palsu: ketiga jaringan bersumber cmc."""
    return _prov(network)


class TestD25Provenance(unittest.TestCase):

    def setUp(self):
        pricing.PRICE_CACHE.clear()
        self.addCleanup(pricing.PRICE_CACHE.clear)

    def _hitung(self, prov_eth):
        """Jalankan get_total_balance_idr dengan seluruh I/O di-mock.

        get_price_with_provenance dipatch dengan create=True: D25 belum
        memakainya di app.py, dan patch ini yang akan menangkapnya begitu
        jalur BTC/SOL dipindah ke sana.
        """
        with patch("app.get_eth_price_with_provenance", return_value=prov_eth), \
             patch("app.get_cached_price", side_effect=_harga_sehat), \
             patch("app.get_price_with_provenance", side_effect=_prov_sehat), \
             patch("app.get_cached_balance", side_effect=lambda k, a, f: 1.0), \
             patch("app.fetch_curated_erc20_balances", return_value=[]), \
             patch("app.fetch_all_spl_balances", return_value=[]):
            return prima_app.get_total_balance_idr(
                WALLETS,
                usdt_price_idr=MOCK_USDT_PRICE,
                usdc_price_idr=MOCK_USDC_PRICE)

    def _kelengkapan(self, result):
        return hitung_kelengkapan(
            result.get("entries") or [],
            result.get("provenance_harga") or {},
            AS_OF,
        )

    # ── D25-1: jalur sehat, ketiga harga cmc ──
    def test_d25_1_jalur_sehat_lengkap(self):
        result = self._hitung(_prov("ethereum"))
        self.assertIn("provenance_harga", result)
        self.assertIn("entries", result)
        self.assertEqual(len(result["entries"]), 3, result.get("entries"))
        for net in ("ethereum", "bitcoin", "solana"):
            self.assertIsNotNone(result["provenance_harga"].get(net), net)
        hasil = self._kelengkapan(result)
        self.assertEqual(hasil["status"], "LENGKAP", hasil)
        self.assertEqual(hasil["sumber_gagal"], [], hasil)

    # ── D25-2: harga ETH jatuh ke tier hardcoded ──
    def test_d25_2_eth_hardcoded_sebagian(self):
        result = self._hitung(_prov("ethereum", sumber="hardcoded"))
        hasil = self._kelengkapan(result)
        self.assertEqual(hasil["status"], "SEBAGIAN", hasil)
        self.assertEqual(
            result["provenance_harga"]["ethereum"]["sumber"], "hardcoded",
            result["provenance_harga"])
        harga_gagal = [s["network"] for s in hasil["sumber_gagal"]
                       if s["jenis"] == "harga"]
        self.assertIn("ethereum", harga_gagal, hasil)


if __name__ == "__main__":
    unittest.main()
