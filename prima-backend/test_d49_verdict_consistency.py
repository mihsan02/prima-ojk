"""
D49 -- regresi: situs 3 (internal_refresh_all) dan situs 4
(_run_refresh_job) memakai tetapkan_verdict_surplus (kanonik), bukan
tetapkan_verdict_ternary (dibuang). Sebelum patch, PAKD defisit 15%
lolos sebagai "Deviasi" di kedua situs ini -- sesudah patch, harus
"Kritis", konsisten dengan situs 2 (/api/reconciliation) yang sudah
memakai formula ini sejak awal.

Pola mocking direplikasi dari test_final_failsafe.py (T2.6): patch
titik masuk data, bukan DB nyata. compute_30_70_compliance TIDAK
di-mock, dibiarkan berjalan asli terhadap _get_db_conn()=None,
konsisten dengan pola test_final_failsafe.py yang sudah terbukti aman
di 283+ test yang ada.

/api/internal/refresh-all TIDAK memakai dekorator auth apa pun --
diverifikasi lewat pembacaan langsung sebelum menulis test ini, bukan
diasumsikan. Temuan ini dicatat terpisah untuk register, di luar
cakupan D49.
"""
import os
from unittest.mock import patch

import app as app_mod

PAKD_ID = "PAKD-DEMO-001"


def _bersihkan_cache():
    app_mod.BALANCE_CACHE.clear()
    app_mod.PRICE_CACHE.clear()


def _balance_result(total_idr, entries, provenance_harga, **extra):
    base = {
        "total_idr": total_idr, "entries": entries, "provenance_harga": provenance_harga,
        "eth_balance_idr": 0, "eth_native_idr": 0, "eth_usdt_idr": 0, "eth_usdc_idr": 0,
        "btc_balance_idr": 0,
        "sol_balance_idr": 0, "sol_native_idr": 0, "sol_usdt_idr": 0, "sol_usdc_idr": 0,
        "sol_other_token_idr": 0, "sol_unvalued_count": 0, "sol_unvalued_mints": [],
        "eth_other_token_idr": 0, "eth_unvalued_count": 0, "eth_unvalued_contracts": [],
        "breakdown": [], "_chain_timings": {},
    }
    base.update(extra)
    return base


def _prov_ok(sumber="cmc", umur_detik=0):
    return {"sumber": sumber, "nilai": 1.0, "umur_detik": umur_detik}


def _entries_lengkap():
    return [
        {"network": "ethereum", "address": "0xabc", "balance_native": 1.0,
         "fetch_status": "ok", "error": None},
        {"network": "bitcoin", "address": "bc1x", "balance_native": 1.0,
         "fetch_status": "ok", "error": None},
        {"network": "solana", "address": "sol1", "balance_native": 1.0,
         "fetch_status": "ok", "error": None},
    ]


def _prov_lengkap():
    return {"ethereum": _prov_ok(), "bitcoin": _prov_ok(), "solana": _prov_ok()}


class TestD49InternalRefreshAll:
    """Situs 3: POST /api/internal/refresh-all -- nol auth, diverifikasi."""

    def setup_method(self):
        app_mod.REFRESH_LOCK["running"] = False
        app_mod.REFRESH_LOCK["started_at"] = None

    def test_defisit_15_persen_jadi_kritis_bukan_deviasi(self, client):
        _bersihkan_cache()
        br = _balance_result(85_000_000, _entries_lengkap(), _prov_lengkap())

        with patch.dict(os.environ, {"INTERNAL_TOKEN": "test-internal-token-d49"}), \
             patch.object(app_mod, "_get_db_conn", return_value=None), \
             patch.object(app_mod, "get_total_balance_idr", return_value=br), \
             patch.object(app_mod, "_get_aset_dilaporkan", return_value=100_000_000), \
             patch.object(app_mod, "_save_snapshots_batch") as mock_save, \
             patch.object(app_mod, "get_eth_price_idr", return_value=(1.0, False)):
            resp = client.post("/api/internal/refresh-all",
                               headers={"X-Internal-Token": "test-internal-token-d49"})

        assert resp.status_code == 200
        assert mock_save.called, "verdict tidak pernah disimpan -- cek apakah pipeline sampai ke _save_snapshots_batch"
        hasil_arg = mock_save.call_args[0][0]
        entry = next(e for e in hasil_arg if e["id"] == PAKD_ID)
        assert entry["status"] == "Kritis", (
            f"D49 belum tertutup di internal_refresh_all -- dapat '{entry['status']}', "
            f"harusnya 'Kritis' (surplus/defisit: defisit>10% = Kritis)"
        )

    def test_defisit_3_persen_jadi_deviasi_bukan_aman(self, client):
        _bersihkan_cache()
        br = _balance_result(97_000_000, _entries_lengkap(), _prov_lengkap())

        with patch.dict(os.environ, {"INTERNAL_TOKEN": "test-internal-token-d49"}), \
             patch.object(app_mod, "_get_db_conn", return_value=None), \
             patch.object(app_mod, "get_total_balance_idr", return_value=br), \
             patch.object(app_mod, "_get_aset_dilaporkan", return_value=100_000_000), \
             patch.object(app_mod, "_save_snapshots_batch") as mock_save, \
             patch.object(app_mod, "get_eth_price_idr", return_value=(1.0, False)):
            resp = client.post("/api/internal/refresh-all",
                               headers={"X-Internal-Token": "test-internal-token-d49"})

        assert resp.status_code == 200
        hasil_arg = mock_save.call_args[0][0]
        entry = next(e for e in hasil_arg if e["id"] == PAKD_ID)
        assert entry["status"] == "Deviasi", (
            f"D49 belum tertutup -- dapat '{entry['status']}', harusnya 'Deviasi' "
            f"(surplus/defisit: 0.01% < defisit <= 10% = Deviasi)"
        )


class TestD49RunRefreshJob:
    """Situs 4: _run_refresh_job -- dipanggil langsung sebagai fungsi."""

    def test_defisit_15_persen_jadi_kritis_bukan_deviasi(self):
        _bersihkan_cache()
        br = _balance_result(85_000_000, _entries_lengkap(), _prov_lengkap())

        with patch.object(app_mod, "_get_db_conn", return_value=None), \
             patch.object(app_mod, "get_total_balance_idr", return_value=br), \
             patch.object(app_mod, "_get_aset_dilaporkan", return_value=100_000_000), \
             patch.object(app_mod, "_save_snapshots_batch") as mock_save, \
             patch.object(app_mod, "get_eth_price_idr", return_value=(1.0, False)):
            app_mod._run_refresh_job("test-job-d49", pakd_id_filter=PAKD_ID)

        assert mock_save.called, "verdict tidak pernah disimpan"
        hasil_arg = mock_save.call_args[0][0]
        entry = next(e for e in hasil_arg if e["id"] == PAKD_ID)
        assert entry["status"] == "Kritis", (
            f"D49 belum tertutup di _run_refresh_job -- dapat '{entry['status']}'"
        )

    def test_defisit_3_persen_jadi_deviasi_bukan_aman(self):
        _bersihkan_cache()
        br = _balance_result(97_000_000, _entries_lengkap(), _prov_lengkap())

        with patch.object(app_mod, "_get_db_conn", return_value=None), \
             patch.object(app_mod, "get_total_balance_idr", return_value=br), \
             patch.object(app_mod, "_get_aset_dilaporkan", return_value=100_000_000), \
             patch.object(app_mod, "_save_snapshots_batch") as mock_save, \
             patch.object(app_mod, "get_eth_price_idr", return_value=(1.0, False)):
            app_mod._run_refresh_job("test-job-d49", pakd_id_filter=PAKD_ID)

        hasil_arg = mock_save.call_args[0][0]
        entry = next(e for e in hasil_arg if e["id"] == PAKD_ID)
        assert entry["status"] == "Deviasi", (
            f"D49 belum tertutup di _run_refresh_job -- dapat '{entry['status']}'"
        )
