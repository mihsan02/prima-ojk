"""T1.1 (D1): get_eth_balance harus gagal keras, bukan gagal diam.

Sebelum T1.1 fungsi ini mengembalikan 0 baik saat exception maupun saat
Etherscan membalas status != "1". Pemanggil tidak punya cara membedakan
"saldo memang nol" dari "pengambilan gagal", sehingga kegagalan jaringan
terbaca sebagai saldo nol.

Semua kasus di bawah mem-mock requests.get. Tidak ada panggilan nyata ke
Etherscan.
"""

import unittest
from unittest.mock import MagicMock, patch

from core.acquisition import get_eth_balance

ADDR = "0x0681d8db095565fe8a346fa0277bffde9c0edbbf"


def _resp(payload):
    """Objek balasan palsu yang .json()-nya mengembalikan payload."""
    r = MagicMock()
    r.json.return_value = payload
    return r


class TestEthBalanceFailSafe(unittest.TestCase):

    # ── (c) ditulis lebih dulu: nol asli TIDAK boleh dianggap gagal ──
    def test_c_saldo_nol_asli_mengembalikan_nol_tanpa_raise(self):
        """status "1" + result "0" = saldo nol yang benar-benar dilaporkan."""
        with patch("core.acquisition.requests.get",
                   return_value=_resp({"status": "1", "result": "0"})):
            hasil = get_eth_balance(ADDR)

        self.assertEqual(hasil, 0.0)
        self.assertIsInstance(hasil, float)

    def test_c2_status_bukan_satu_tapi_result_nol_tetap_nol(self):
        """Pengecualian eksplisit: result literal "0" berarti saldo nol asli.

        Ini pembeda halus dari kasus (b) -- sama-sama status "0", tapi di
        sini result-nya "0" sehingga saldo tetap dapat dipastikan.
        """
        with patch("core.acquisition.requests.get",
                   return_value=_resp({"status": "0", "result": "0"})):
            self.assertEqual(get_eth_balance(ADDR), 0.0)

    # ── (a) exception dari requests.get ──
    def test_a_exception_melempar_runtimeerror(self):
        with patch("core.acquisition.requests.get",
                   side_effect=ConnectionError("connection reset by peer")):
            with self.assertRaises(RuntimeError) as ctx:
                get_eth_balance(ADDR)

        pesan = str(ctx.exception)
        self.assertIn("ETH balance fetch failed for", pesan)
        self.assertIn(ADDR, pesan)
        self.assertIn("connection reset by peer", pesan)

    # ── (b) status "0" dengan result BUKAN "0" ──
    def test_b_status_nol_dengan_result_bukan_nol_melempar(self):
        with patch("core.acquisition.requests.get",
                   return_value=_resp({"status": "0",
                                       "message": "NOTOK",
                                       "result": "Max rate limit reached"})):
            with self.assertRaises(RuntimeError) as ctx:
                get_eth_balance(ADDR)

        pesan = str(ctx.exception)
        self.assertIn("ETH balance fetch failed for", pesan)
        self.assertIn(ADDR, pesan)

    # ── kontrak pesan yang dibaca T2.1 untuk mengisi sumber_gagal ──
    def test_pesan_menyebut_sumber_bukan_generik(self):
        """T2.1 membaca string ini dari entry["error"], jadi formatnya kontrak."""
        with patch("core.acquisition.requests.get",
                   side_effect=TimeoutError("timed out")):
            with self.assertRaises(RuntimeError) as ctx:
                get_eth_balance(ADDR)

        self.assertTrue(str(ctx.exception).startswith(
            f"ETH balance fetch failed for {ADDR}: "))

    def test_saldo_normal_tetap_dikonversi_dari_wei(self):
        """Jalur sukses tidak boleh ikut berubah: 1 ETH = 1e18 wei."""
        with patch("core.acquisition.requests.get",
                   return_value=_resp({"status": "1", "result": str(2 * 10**18)})):
            self.assertEqual(get_eth_balance(ADDR), 2.0)


if __name__ == "__main__":
    unittest.main()
