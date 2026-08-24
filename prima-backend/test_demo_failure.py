"""
T2.5 — verifikasi gerbang DEMO_FORCE_PROVIDER_FAILURE dan jejak auditnya.

Tes ini TIDAK memakai importlib.reload(app). Gerbang diekstrak jadi
app._resolve_demo_force_provider_failure() supaya bisa dipanggil ulang
langsung, menghindari risiko reload mencemari 277 test lain di proses
yang sama.

Prices diisi eksplisit (bukan None) supaya cabang fetch-harga-real tidak
pernah dieksekusi -- wallet BTC/SOL sengaja kosong di semua kasus supaya
_proc_btc dan _proc_sol tidak memanggil jaringan sama sekali.
"""
import unittest
from unittest.mock import MagicMock

import app as prima_app


class TestT25DemoGateClosed(unittest.TestCase):
    """Gerbang wajib gagal-tertutup pada kombinasi env yang tidak lengkap."""

    def test_gate_closed_when_demo_mode_unset(self):
        with unittest.mock.patch.dict(
            "os.environ",
            {"DEMO_FORCE_PROVIDER_FAILURE": "ethereum"},
            clear=False,
        ):
            import os
            os.environ.pop("DEMO_MODE", None)
            result = prima_app._resolve_demo_force_provider_failure()
        self.assertEqual(result, [])

    def test_gate_closed_when_flask_env_is_production(self):
        # Kerapuhan yang didokumentasikan sadar: FLASK_ENV=production
        # eksplisit mengunci demo tertutup permanen, bahkan dengan
        # DEMO_MODE=true. Ini menutup celah disjungsi lama, tapi berarti
        # ops tidak boleh set FLASK_ENV=production di Render pada hari
        # demo tanpa menyadari efek ini.
        with unittest.mock.patch.dict(
            "os.environ",
            {
                "DEMO_MODE": "true",
                "FLASK_ENV": "production",
                "DEMO_FORCE_PROVIDER_FAILURE": "ethereum",
            },
        ):
            result = prima_app._resolve_demo_force_provider_failure()
        self.assertEqual(result, [])

    def test_gate_open_when_demo_mode_true_and_env_not_production(self):
        with unittest.mock.patch.dict(
            "os.environ",
            {
                "DEMO_MODE": "true",
                "FLASK_ENV": "",
                "DEMO_FORCE_PROVIDER_FAILURE": "ethereum, bitcoin",
            },
        ):
            result = prima_app._resolve_demo_force_provider_failure()
        self.assertEqual(result, ["ethereum", "bitcoin"])


class TestT25DemoFailureActivation(unittest.TestCase):
    """Saat gerbang terbuka, verifikasi dampak pada data dan audit."""

    def setUp(self):
        prima_app.BALANCE_CACHE.clear()
        self.addCleanup(prima_app.BALANCE_CACHE.clear)
        self._original_flag = prima_app.DEMO_FORCE_PROVIDER_FAILURE
        self.addCleanup(
            setattr, prima_app, "DEMO_FORCE_PROVIDER_FAILURE", self._original_flag
        )

    def _wallets(self):
        return [{"network": "ethereum", "address": "0xDEMO000", "verified": True}]

    def test_eth_failure_marks_wallet_gagal(self):
        prima_app.DEMO_FORCE_PROVIDER_FAILURE = ["ethereum"]
        prima_app.write_audit = MagicMock()

        result = prima_app.get_total_balance_idr(
            self._wallets(),
            eth_price_idr=45_000_000.0,
            btc_price_idr=900_000_000.0,
            sol_price_idr=3_000_000.0,
            usdt_price_idr=16_000.0,
            usdc_price_idr=16_000.0,
        )

        eth_entries = [e for e in result["entries"] if e["network"] == "ethereum"]
        self.assertEqual(len(eth_entries), 1)
        self.assertEqual(eth_entries[0]["fetch_status"], "gagal")
        self.assertIn("DEMO_FORCE_PROVIDER_FAILURE: ethereum", eth_entries[0]["error"])

    def test_eth_failure_writes_audit_event(self):
        prima_app.DEMO_FORCE_PROVIDER_FAILURE = ["ethereum"]
        mock_audit = MagicMock()
        prima_app.write_audit = mock_audit

        prima_app.get_total_balance_idr(
            self._wallets(),
            eth_price_idr=45_000_000.0,
            btc_price_idr=900_000_000.0,
            sol_price_idr=3_000_000.0,
            usdt_price_idr=16_000.0,
            usdc_price_idr=16_000.0,
        )

        mock_audit.assert_called_once_with(
            "DEMO_FAILURE_TRIGGERED", "Simulated ethereum provider failure (DEMO_MODE)"
        )

    def test_no_failure_when_flag_empty(self):
        # Kontrol negatif: flag kosong, wallet ETH tidak boleh gagal
        # karena alasan demo. (Bisa tetap gagal karena sebab lain di
        # lingkungan test -- yang diuji di sini hanya bahwa alasannya
        # BUKAN string DEMO_FORCE_PROVIDER_FAILURE.)
        prima_app.DEMO_FORCE_PROVIDER_FAILURE = []
        prima_app.write_audit = MagicMock()

        result = prima_app.get_total_balance_idr(
            self._wallets(),
            eth_price_idr=45_000_000.0,
            btc_price_idr=900_000_000.0,
            sol_price_idr=3_000_000.0,
            usdt_price_idr=16_000.0,
            usdc_price_idr=16_000.0,
        )

        eth_entries = [e for e in result["entries"] if e["network"] == "ethereum"]
        self.assertEqual(len(eth_entries), 1)
        if eth_entries[0]["fetch_status"] == "gagal":
            self.assertNotIn("DEMO_FORCE_PROVIDER_FAILURE", eth_entries[0].get("error") or "")


if __name__ == "__main__":
    unittest.main()


class TestT25DemoFailureBTC(unittest.TestCase):
    """Simetris dengan ETH: raise tunggal, satu except terluar."""

    def setUp(self):
        prima_app.BALANCE_CACHE.clear()
        self.addCleanup(prima_app.BALANCE_CACHE.clear)
        self._original_flag = prima_app.DEMO_FORCE_PROVIDER_FAILURE
        self.addCleanup(
            setattr, prima_app, "DEMO_FORCE_PROVIDER_FAILURE", self._original_flag
        )

    def _wallets(self):
        return [{"network": "bitcoin", "address": "bc1qDEMO000", "verified": True}]

    def test_btc_failure_marks_wallet_gagal(self):
        prima_app.DEMO_FORCE_PROVIDER_FAILURE = ["bitcoin"]
        prima_app.write_audit = MagicMock()

        result = prima_app.get_total_balance_idr(
            self._wallets(),
            eth_price_idr=45_000_000.0,
            btc_price_idr=900_000_000.0,
            sol_price_idr=3_000_000.0,
            usdt_price_idr=16_000.0,
            usdc_price_idr=16_000.0,
        )

        btc_entries = [e for e in result["entries"] if e["network"] == "bitcoin"]
        self.assertEqual(len(btc_entries), 1)
        self.assertEqual(btc_entries[0]["fetch_status"], "gagal")
        self.assertIn("DEMO_FORCE_PROVIDER_FAILURE: bitcoin", btc_entries[0]["error"])

    def test_btc_failure_writes_audit_event(self):
        prima_app.DEMO_FORCE_PROVIDER_FAILURE = ["bitcoin"]
        mock_audit = MagicMock()
        prima_app.write_audit = mock_audit

        prima_app.get_total_balance_idr(
            self._wallets(),
            eth_price_idr=45_000_000.0,
            btc_price_idr=900_000_000.0,
            sol_price_idr=3_000_000.0,
            usdt_price_idr=16_000.0,
            usdc_price_idr=16_000.0,
        )

        mock_audit.assert_called_once_with(
            "DEMO_FAILURE_TRIGGERED", "Simulated bitcoin provider failure (DEMO_MODE)"
        )


class TestT25DemoFailureSOL(unittest.TestCase):
    """Raise terjadi sebelum enumerasi SPL, jadi tetap jatuh ke except
    terluar (fetch_status='gagal') meskipun _proc_sol punya dua
    try/except bersarang lebih jauh ke bawah untuk kegagalan partial
    token SPL. Dua kelas kegagalan itu berbeda dan tidak boleh tertukar."""

    def setUp(self):
        prima_app.BALANCE_CACHE.clear()
        self.addCleanup(prima_app.BALANCE_CACHE.clear)
        self._original_flag = prima_app.DEMO_FORCE_PROVIDER_FAILURE
        self.addCleanup(
            setattr, prima_app, "DEMO_FORCE_PROVIDER_FAILURE", self._original_flag
        )

    def _wallets(self):
        return [{"network": "solana", "address": "DEMO000SoLwallet", "verified": True}]

    def test_sol_failure_marks_wallet_gagal_not_partial(self):
        prima_app.DEMO_FORCE_PROVIDER_FAILURE = ["solana"]
        prima_app.write_audit = MagicMock()

        result = prima_app.get_total_balance_idr(
            self._wallets(),
            eth_price_idr=45_000_000.0,
            btc_price_idr=900_000_000.0,
            sol_price_idr=3_000_000.0,
            usdt_price_idr=16_000.0,
            usdc_price_idr=16_000.0,
        )

        sol_entries = [e for e in result["entries"] if e["network"] == "solana"]
        self.assertEqual(len(sol_entries), 1)
        # Kunci ke "gagal", bukan "partial" -- membuktikan raise tidak
        # tertangkap oleh except bersarang enumerasi SPL/harga di bawahnya.
        self.assertEqual(sol_entries[0]["fetch_status"], "gagal")
        self.assertIn("DEMO_FORCE_PROVIDER_FAILURE: solana", sol_entries[0]["error"])

    def test_sol_failure_writes_audit_event(self):
        prima_app.DEMO_FORCE_PROVIDER_FAILURE = ["solana"]
        mock_audit = MagicMock()
        prima_app.write_audit = mock_audit

        prima_app.get_total_balance_idr(
            self._wallets(),
            eth_price_idr=45_000_000.0,
            btc_price_idr=900_000_000.0,
            sol_price_idr=3_000_000.0,
            usdt_price_idr=16_000.0,
            usdc_price_idr=16_000.0,
        )

        mock_audit.assert_called_once_with(
            "DEMO_FAILURE_TRIGGERED", "Simulated solana provider failure (DEMO_MODE)"
        )


class TestT25DemoFailureMultiChain(unittest.TestCase):
    """T2.6 kasus 6 pola: kombinasi chain gagal bersamaan, verifikasi
    tidak saling menutupi (mis. ETH gagal tidak membuat BTC entry hilang)."""

    def setUp(self):
        prima_app.BALANCE_CACHE.clear()
        self.addCleanup(prima_app.BALANCE_CACHE.clear)
        self._original_flag = prima_app.DEMO_FORCE_PROVIDER_FAILURE
        self.addCleanup(
            setattr, prima_app, "DEMO_FORCE_PROVIDER_FAILURE", self._original_flag
        )

    def test_two_chains_forced_third_untouched(self):
        # BTC di-mock sukses tanpa I/O nyata. Alamat placeholder yang
        # tidak dimock memicu panggilan HTTP asli ke Blockstream/mempool
        # dan gagal untuk alasan jaringan, bukan alasan demo -- ditemukan
        # lewat kegagalan test ini sebelum patch, dicatat supaya tidak
        # diulang.
        prima_app.DEMO_FORCE_PROVIDER_FAILURE = ["ethereum", "solana"]
        prima_app.write_audit = MagicMock()
        original_fetch_btc = prima_app.fetch_btc_balance
        prima_app.fetch_btc_balance = MagicMock(return_value=0.05)
        self.addCleanup(setattr, prima_app, "fetch_btc_balance", original_fetch_btc)

        wallets = [
            {"network": "ethereum", "address": "0xDEMO000", "verified": True},
            {"network": "bitcoin", "address": "bc1qDEMO000", "verified": True},
            {"network": "solana", "address": "DEMO000SoLwallet", "verified": True},
        ]

        result = prima_app.get_total_balance_idr(
            wallets,
            eth_price_idr=45_000_000.0,
            btc_price_idr=900_000_000.0,
            sol_price_idr=3_000_000.0,
            usdt_price_idr=16_000.0,
            usdc_price_idr=16_000.0,
        )

        by_network = {e["network"]: e for e in result["entries"]}
        self.assertEqual(by_network["ethereum"]["fetch_status"], "gagal")
        self.assertEqual(by_network["solana"]["fetch_status"], "gagal")
        self.assertEqual(by_network["bitcoin"]["fetch_status"], "sukses")
        self.assertEqual(prima_app.write_audit.call_count, 2)
