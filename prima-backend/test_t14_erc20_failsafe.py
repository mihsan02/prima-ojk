"""T1.4 (D2): fetch_erc20_balance gagal keras, bukan gagal diam.

Etherscan memakai status "0" untuk saldo nol asli DAN untuk galat --
docstring fungsi ini sendiri sudah mengakuinya sejak lama. Versi lama
mengembalikan 0.0 untuk keduanya, sehingga alamat tidak valid, kontrak
salah, atau rate limit terbaca sebagai "PAKD tidak memegang token ini".

Semua kasus mem-mock requests.get. Tidak ada panggilan ke Etherscan.
"""

import unittest
from unittest.mock import MagicMock, patch

from core.acquisition import fetch_erc20_balance

ADDR = "0x0681d8db095565fe8a346fa0277bffde9c0edbbf"
USDT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"


def _resp(payload):
    r = MagicMock()
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


class TestErc20FailSafe(unittest.TestCase):

    # ── (a) ditulis lebih dulu: nol asli TIDAK boleh dianggap gagal ──
    def test_a_status_nol_result_nol_mengembalikan_nol(self):
        """status "0" + result "0" = saldo nol yang benar-benar dilaporkan."""
        with patch("core.acquisition.requests.get",
                   return_value=_resp({"status": "0", "result": "0"})):
            hasil = fetch_erc20_balance(ADDR, USDT, decimals=6)

        self.assertEqual(hasil, 0.0)
        self.assertIsInstance(hasil, float)

    # ── (b) status "0" dengan result lain ──
    def test_b_status_nol_result_lain_melempar(self):
        with patch("core.acquisition.requests.get",
                   return_value=_resp({"status": "0",
                                       "message": "NOTOK",
                                       "result": "Max rate limit reached"})):
            with self.assertRaises(RuntimeError) as ctx:
                fetch_erc20_balance(ADDR, USDT, decimals=6)

        pesan = str(ctx.exception)
        self.assertIn("ERC-20 balance fetch failed for", pesan)
        self.assertIn(ADDR, pesan)
        self.assertIn(USDT, pesan)

    # ── (c) jalur sukses: konversi desimal ──
    def test_c_status_satu_konversi_desimal_benar(self):
        """USDT 6 desimal: 1_500_500_000 unit = 1500.50 token."""
        with patch("core.acquisition.requests.get",
                   return_value=_resp({"status": "1", "result": "1500500000"})):
            self.assertAlmostEqual(
                fetch_erc20_balance(ADDR, USDT, decimals=6), 1500.50, places=6)

    def test_c2_desimal_18_untuk_token_non_stablecoin(self):
        with patch("core.acquisition.requests.get",
                   return_value=_resp({"status": "1", "result": str(3 * 10**18)})):
            self.assertEqual(fetch_erc20_balance(ADDR, USDT, decimals=18), 3.0)

    def test_exception_jaringan_melempar_runtimeerror(self):
        with patch("core.acquisition.requests.get",
                   side_effect=ConnectionError("connection reset by peer")):
            with self.assertRaises(RuntimeError) as ctx:
                fetch_erc20_balance(ADDR, USDT, decimals=6)

        pesan = str(ctx.exception)
        self.assertIn("ERC-20 balance fetch failed for", pesan)
        self.assertIn("connection reset by peer", pesan)

    def test_pesan_menyebut_alamat_dan_kontrak(self):
        """Kontrak wajib ikut: satu alamat memegang banyak token."""
        with patch("core.acquisition.requests.get",
                   side_effect=TimeoutError("timed out")):
            with self.assertRaises(RuntimeError) as ctx:
                fetch_erc20_balance(ADDR, USDT, decimals=6)

        self.assertTrue(str(ctx.exception).startswith(
            f"ERC-20 balance fetch failed for {ADDR} contract {USDT}: "))

    def test_http_error_tidak_menyamar_jadi_nol(self):
        r = MagicMock()
        r.raise_for_status.side_effect = Exception("500 Server Error")
        with patch("core.acquisition.requests.get", return_value=r):
            with self.assertRaises(RuntimeError):
                fetch_erc20_balance(ADDR, USDT, decimals=6)


if __name__ == "__main__":
    unittest.main()
