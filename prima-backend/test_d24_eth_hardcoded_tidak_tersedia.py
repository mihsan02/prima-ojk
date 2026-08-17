"""D24: harga ETH hardcoded diperlakukan sebagai harga yang tidak tersedia.

Sebelum D24, blok ETH di get_total_balance_idr() menyimpang dari pola
BTC dan SOL. Keduanya, saat kaskade harganya habis, menyetel harga None
dan menambahkan chain-nya ke harga_tidak_tersedia -- chain itu lalu
hilang dari breakdown alih-alih dinilai keliru. Blok ETH justru
menyetel 39_910_503, konstanta D5, dan tidak menambahkan apa pun ke
himpunan tersebut. Akibatnya seluruh kepemilikan ETH dinilai memakai
harga karangan tanpa satu pun penanda bahwa harganya tidak nyata.

D24 menyamakan ETH dengan BTC dan SOL, di satu blok saja. Kaskade ETH
sendiri tidak diubah: get_eth_price_with_provenance() tetap boleh
mengembalikan tier hardcoded, dan pemanggilnya yang memutuskan bahwa
tier itu tidak layak dipakai untuk rekonsiliasi.

Kasus (a) menggerakkan kaskade sungguhan sampai ke tier hardcoded
dengan mematikan CMC dan CoinGecko, bukan mem-patch hasil akhirnya.
PRICE_CACHE dibersihkan supaya tier cache basi T2.0 tidak menyela.
"""

import pathlib
import unittest
from unittest.mock import MagicMock, patch

import app as prima_app
import core.pricing as pricing

ETH_WALLET = {"network": "ethereum",
              "address": "0x0681d8db095565fe8a346fa0277bffde9c0edbbf",
              "verified": True}

MOCK_USDT_PRICE = 16_400.0
MOCK_USDC_PRICE = 16_400.0
HARGA_COINGECKO = 44_000_000.0
SALDO_ETH = 1.0


class TestHargaEthHardcoded(unittest.TestCase):

    def setUp(self):
        pricing.PRICE_CACHE.clear()
        pricing._CMC_LIVE_WRITE_AT = None
        self.addCleanup(pricing.PRICE_CACHE.clear)

    def _hitung(self, patch_requests):
        with patch("core.pricing._refresh_price_cache_from_cmc", return_value=False), \
             patch("core.pricing.requests.get", **patch_requests), \
             patch("app.get_cached_balance", side_effect=lambda k, a, f: SALDO_ETH):
            # Harga BTC/SOL disuntikkan supaya blok keduanya tidak ikut
            # berjalan: mematikan jaringan untuk kaskade ETH juga
            # mematikan kaskade mereka, dan kegagalan itu bukan D24.
            return prima_app.get_total_balance_idr(
                [ETH_WALLET],
                btc_price_idr=1_600_000_000.0,
                sol_price_idr=2_500_000.0,
                usdt_price_idr=MOCK_USDT_PRICE,
                usdc_price_idr=MOCK_USDC_PRICE)

    def test_kaskade_habis_ke_hardcoded_masuk_harga_tidak_tersedia(self):
        """Inti D24: tier hardcoded diperlakukan seperti kegagalan.

        Kaskade digerakkan sungguhan -- CMC mati, CoinGecko melempar,
        PRICE_CACHE kosong -- sehingga get_eth_price_with_provenance()
        sampai ke tier terakhirnya.
        """
        hasil = self._hitung({"side_effect": Exception("network down")})

        self.assertEqual(hasil["harga_tidak_tersedia"], ["eth_native"],
                         f"eth_native_idr={hasil['eth_native_idr']!r}")

    def test_kaskade_sukses_nilai_terpakai_himpunan_kosong(self):
        """Sisi lain: harga nyata tetap dipakai dan tidak menandai apa pun."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"ethereum": {"idr": HARGA_COINGECKO}}
        resp.raise_for_status.return_value = None

        hasil = self._hitung({"return_value": resp})

        self.assertEqual(hasil["harga_tidak_tersedia"], [], hasil)
        self.assertEqual(hasil["eth_native_idr"], SALDO_ETH * HARGA_COINGECKO,
                         hasil)

    def test_native_tak_dinilai_tapi_stablecoin_bertahan(self):
        """D24 Bagian A: penjaga harga ETH di jalur penilaian.

        Tanpa penjaga, eth_bal * eth_price_idr melempar TypeError saat
        harganya None, dan blok except di sekitarnya mengubahnya menjadi
        entry["error"] = "ETH fetch error: ..." -- kegagalan harga
        dilaporkan sebagai kegagalan fetch saldo.

        Polanya mengikuti Solana, bukan Bitcoin. Wallet ETH memegang USDT
        dan USDC yang dihargai lewat kaskade stablecoin terpisah dan tetap
        sahih, jadi wallet-nya bertahan di breakdown dengan komponen
        native saja yang tidak dinilai. Men-skip seluruh chain seperti BTC
        akan menghapus aset stabil yang harganya baik-baik saja.
        """
        hasil = self._hitung({"side_effect": Exception("network down")})

        baris = [e for e in hasil["breakdown"] if e.get("network") == "ethereum"]
        self.assertEqual(len(baris), 1, hasil["breakdown"])
        entry = baris[0]

        self.assertNotIn("unsupported operand", str(entry["error"]), entry)
        self.assertIsNone(entry["eth_native_idr"], entry)
        self.assertEqual(entry["usdt_idr"], round(SALDO_ETH * MOCK_USDT_PRICE), entry)
        self.assertEqual(entry["usdc_idr"], round(SALDO_ETH * MOCK_USDC_PRICE), entry)

    def test_penanda_bertahan_walau_wallet_masih_bernilai(self):
        """Ketiga sifat sekaligus, pada satu wallet yang sama.

        Pola SOL membuat wallet ETH tetap muncul dengan USDT-nya dinilai.
        Justru karena itu penanda harga_tidak_tersedia menjadi krusial:
        tanpa penanda, wallet yang tampak bernilai wajar menyembunyikan
        fakta bahwa komponen ETH native-nya tidak dinilai sama sekali,
        dan verdict rekonsiliasi keluar seolah datanya utuh.
        """
        hasil = self._hitung({"side_effect": Exception("network down")})

        entry = [e for e in hasil["breakdown"] if e.get("network") == "ethereum"][0]

        self.assertEqual(entry["usdt_idr"], round(SALDO_ETH * MOCK_USDT_PRICE), entry)
        self.assertIsNone(entry["eth_native_idr"], entry)
        self.assertIn("eth_native", hasil["harga_tidak_tersedia"],
                      f"harga_tidak_tersedia={hasil['harga_tidak_tersedia']!r}, "
                      f"usdt_idr={entry['usdt_idr']!r}")

    def test_konstanta_d5_tidak_tersisa_di_app(self):
        """Angka itu milik pricing.py sebagai tier, bukan milik app.py."""
        sumber_app = pathlib.Path(prima_app.__file__).read_text()

        tersisa = [f"{n}: {baris.strip()}"
                   for n, baris in enumerate(sumber_app.splitlines(), 1)
                   if "39_910_503" in baris]

        self.assertEqual(tersisa, [], "39_910_503 masih ada di app.py")


if __name__ == "__main__":
    unittest.main()
