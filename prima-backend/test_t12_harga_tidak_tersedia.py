"""T1.2 (D3/D4): chain tanpa harga hilang dari breakdown, bukan bernilai nol.

Sebelum T1.2, kegagalan mengambil harga BTC/SOL menetapkan harga 0.0.
Seluruh kepemilikan di chain itu lalu dinilai nol rupiah secara diam, dan
verdict tetap keluar seolah PAKD memang tidak memegang aset tersebut.

Semua kasus mem-mock kaskade harga dan saldo. Tidak ada panggilan jaringan.
"""

import unittest
from unittest.mock import patch

import app as prima_app
import core.pricing as pricing

BTC_WALLET = {"network": "bitcoin",
              "address": "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
              "verified": True}
ETH_WALLET = {"network": "ethereum",
              "address": "0x0681d8db095565fe8a346fa0277bffde9c0edbbf",
              "verified": True}

MOCK_ETH_PRICE = 40_000_000.0
MOCK_USDT_PRICE = 16_400.0
MOCK_USDC_PRICE = 16_400.0


def _harga_btc_gagal(network, fetch_fn):
    """get_cached_price palsu: bitcoin selalu gagal, chain lain berhasil."""
    if network == "bitcoin":
        raise RuntimeError("BTC price fetch failed: dua tier kaskade habis")
    return {"ethereum": MOCK_ETH_PRICE, "solana": 1_500_000.0}[network]


class TestHargaTidakTersedia(unittest.TestCase):

    def setUp(self):
        pricing.PRICE_CACHE.clear()
        self.addCleanup(pricing.PRICE_CACHE.clear)

    def _hitung(self, wallets):
        with patch("app.get_cached_price", side_effect=_harga_btc_gagal), \
             patch("app.get_cached_balance", side_effect=lambda k, a, f: 1.0):
            return prima_app.get_total_balance_idr(
                wallets,
                usdt_price_idr=MOCK_USDT_PRICE,
                usdc_price_idr=MOCK_USDC_PRICE)

    # ── inti D3: bitcoin masuk himpunan, dan tidak ada baris BTC nol ──
    def test_btc_gagal_masuk_harga_tidak_tersedia(self):
        hasil = self._hitung([BTC_WALLET])
        self.assertIn("bitcoin", hasil["harga_tidak_tersedia"])

    def test_btc_gagal_tidak_meninggalkan_baris_bernilai_nol(self):
        """Hilang, bukan nol. Baris BTC bernilai 0 rupiah adalah kebohongan."""
        hasil = self._hitung([BTC_WALLET])

        baris_btc = [e for e in hasil["breakdown"] if e.get("network") == "bitcoin"]
        self.assertEqual(baris_btc, [], "wallet BTC tidak boleh muncul di breakdown")

        # Dan tidak ada baris bernilai nol dari chain mana pun sebagai gantinya.
        nol = [e for e in hasil["breakdown"] if e.get("balance_idr") == 0.0]
        self.assertEqual(nol, [], "tidak boleh ada baris bernilai nol rupiah")

    def test_chain_lain_tetap_dinilai_saat_btc_gagal(self):
        """Kegagalan harga BTC tidak boleh menjatuhkan penilaian ETH."""
        hasil = self._hitung([BTC_WALLET, ETH_WALLET])

        self.assertIn("bitcoin", hasil["harga_tidak_tersedia"])
        self.assertNotIn("ethereum", hasil["harga_tidak_tersedia"])

        baris_eth = [e for e in hasil["breakdown"] if e.get("network") == "ethereum"]
        self.assertEqual(len(baris_eth), 1)
        self.assertGreater(hasil["eth_balance_idr"], 0)

    def test_total_tidak_mengandung_chain_tanpa_harga(self):
        """total_idr hanya menjumlahkan yang benar-benar bisa dinilai."""
        hasil = self._hitung([BTC_WALLET, ETH_WALLET])
        self.assertEqual(hasil["total_idr"],
                         sum(e["balance_idr"] or 0 for e in hasil["breakdown"]))
        self.assertEqual(hasil["btc_balance_idr"], 0.0)

    def test_semua_harga_ada_maka_himpunan_kosong(self):
        """Jalur normal tidak boleh ikut berubah."""
        with patch("app.get_cached_price",
                   side_effect=lambda n, f: {"ethereum": MOCK_ETH_PRICE,
                                             "bitcoin": 1_400_000_000.0,
                                             "solana": 1_500_000.0}[n]), \
             patch("app.get_cached_balance", side_effect=lambda k, a, f: 1.0):
            hasil = prima_app.get_total_balance_idr(
                [BTC_WALLET],
                usdt_price_idr=MOCK_USDT_PRICE,
                usdc_price_idr=MOCK_USDC_PRICE)

        self.assertEqual(hasil["harga_tidak_tersedia"], [])
        baris_btc = [e for e in hasil["breakdown"] if e.get("network") == "bitcoin"]
        self.assertEqual(len(baris_btc), 1)
        self.assertGreater(baris_btc[0]["balance_idr"], 0)


if __name__ == "__main__":
    unittest.main()
