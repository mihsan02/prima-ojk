"""T1.3 BAGIAN A (D14) + D21: kurs USD->IDR ikut harga USDT yang dioper.

_get_usd_idr_rate() dulu selalu memanggil _get_stablecoin_prices_idr()
sendiri, mengabaikan usdt_price_idr yang sudah dipegang pemanggil. Saat
stress test Pasal 50/91 mengoper USDT ter-depeg, penilaian "other token"
di ETH dan SOL diam-diam tetap memakai kurs live -- jadi stress test
menguji dengan tekanan lebih ringan daripada yang diminta.

Tes ini sengaja TIDAK mem-mock get_total_balance_idr. Itulah sebabnya
cacat ini bertahan: test_day15_pasal50_pasal91.py mem-mock fungsi itu
seluruhnya, sehingga jalur penilaian tidak pernah dieksekusi dan nol tes
mengawasi D14.

BALANCE_CACHE dibersihkan di setiap kasus. Cache itu menyimpan hasil
spl_enum antar-kasus dalam satu proses dan pernah memberi hasil nol palsu
saat diagnostik D20.
"""

import unittest
from unittest.mock import patch

import app as prima_app
import core.pricing as pricing

SOL_WALLET = {"network": "solana",
              "address": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
              "verified": True}

MINT_LAIN = "MintLain1111111111111111111111111111111111"

MOCK_SOL_PRICE = 1_500_000.0
MOCK_ETH_PRICE = 40_000_000.0
USDT_NORMAL = 16_400.0
USDC_NORMAL = 16_400.0

DEPEG = 0.85
USDT_DEPEG = USDT_NORMAL * DEPEG

# Holding "other token" yang tetap: 10 unit @ USD 2.00
UI_AMOUNT = 10.0
USD_PRICE = 2.00
HOLDINGS = [{"mint": MINT_LAIN, "ui_amount": UI_AMOUNT, "amount": UI_AMOUNT}]


def _saldo(cache_key, address, fetch_fn):
    return {"solana": 5.0, "sol_usdt_spl": 1_000.0, "sol_usdc_spl": 0.0}.get(cache_key, 0.0)


class TestDepegMerambatKeOtherToken(unittest.TestCase):

    def setUp(self):
        # WAJIB: spl_enum di-cache antar-kasus dalam satu proses.
        prima_app.BALANCE_CACHE.clear()
        pricing.PRICE_CACHE.clear()
        self.addCleanup(prima_app.BALANCE_CACHE.clear)
        self.addCleanup(pricing.PRICE_CACHE.clear)

    def _hitung(self, usdt_price_idr):
        with patch("app.get_cached_balance", side_effect=_saldo), \
             patch("app.fetch_all_spl_balances", return_value=HOLDINGS), \
             patch("app._get_jupiter_verified_set", return_value={MINT_LAIN}), \
             patch("app._get_jupiter_prices", return_value={MINT_LAIN: USD_PRICE}):
            return prima_app.get_total_balance_idr(
                [SOL_WALLET],
                sol_price_idr=MOCK_SOL_PRICE,
                eth_price_idr=MOCK_ETH_PRICE,
                usdt_price_idr=usdt_price_idr,
                usdc_price_idr=USDC_NORMAL)

    def test_kurs_normal_memakai_harga_usdt_yang_dioper(self):
        hasil = self._hitung(USDT_NORMAL)
        self.assertAlmostEqual(hasil["sol_other_token_idr"],
                               UI_AMOUNT * USD_PRICE * USDT_NORMAL, delta=1)

    def test_depeg_menurunkan_nilai_other_token_proporsional(self):
        """Inti D14: tekanan yang diminta harus benar-benar terasa."""
        normal = self._hitung(USDT_NORMAL)["sol_other_token_idr"]
        depeg = self._hitung(USDT_DEPEG)["sol_other_token_idr"]

        self.assertGreater(normal, 0, "prasyarat: jalur other-token harus jalan")
        self.assertLess(depeg, normal, "depeg harus menurunkan nilai other token")
        self.assertAlmostEqual(depeg / normal, DEPEG, places=6)

    def test_nilai_depeg_sama_dengan_hitungan_manual(self):
        hasil = self._hitung(USDT_DEPEG)
        self.assertAlmostEqual(hasil["sol_other_token_idr"],
                               UI_AMOUNT * USD_PRICE * USDT_DEPEG, delta=1)

    def test_kaskade_stablecoin_tidak_disentuh_saat_harga_dioper(self):
        """Kalau harga sudah dioper, tidak boleh ada fetch kurs live."""
        with patch("core.pricing._get_stablecoin_prices_idr") as mock_kaskade:
            self._hitung(USDT_DEPEG)
        mock_kaskade.assert_not_called()

    def test_tanpa_argumen_perilaku_lama_dipertahankan(self):
        """_get_usd_idr_rate() tanpa argumen tetap memakai kaskade."""
        with patch("core.pricing._get_stablecoin_prices_idr",
                   return_value=(USDT_NORMAL, USDC_NORMAL)) as mock_kaskade:
            rate = pricing._get_usd_idr_rate()

        mock_kaskade.assert_called_once()
        self.assertEqual(rate, USDT_NORMAL)

    def test_argumen_eksplisit_dipakai_apa_adanya(self):
        with patch("core.pricing._get_stablecoin_prices_idr") as mock_kaskade:
            rate = pricing._get_usd_idr_rate(USDT_DEPEG)

        mock_kaskade.assert_not_called()
        self.assertEqual(rate, USDT_DEPEG)


if __name__ == "__main__":
    unittest.main()
