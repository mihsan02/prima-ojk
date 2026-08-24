"""T2.6 -- regression test untuk area yang D55 catat nol test:
T2.2 (kelengkapan di payload live), D50 (verdict ditahan saat data tidak
lengkap), D53 (batch write resilient), dan kompromi verdict indikatif
Opsi 1 (D60). Tujuh kasus, mengunci perilaku jalur nyata (HTTP), bukan
mengulang test unit murni yang sudah ada di test_completeness.py,
test_verdict.py, dan test_d30_kustodian_kelengkapan.py.

Pola mocking mengikuti test_d30_kustodian_kelengkapan.py dan
test_ereporting.py: patch.object pada titik masuk data, bukan DB nyata.
"""
import pytest
from unittest.mock import patch, MagicMock

import app as app_mod


PAKD_ID = "PAKD-DEMO-001"


def _bersihkan_cache():
    app_mod.BALANCE_CACHE.clear()
    app_mod.PRICE_CACHE.clear()


def _balance_result(total_idr, entries, provenance_harga, **extra):
    """Bentuk minimal balance_result yang dikonsumsi /api/reconciliation.
    Kunci wajib berdasarkan pemakaian di app.py sekitar baris 2926-3010."""
    base = {
        "total_idr": total_idr,
        "entries": entries,
        "provenance_harga": provenance_harga,
        "eth_balance_idr": 0, "eth_native_idr": 0, "eth_usdt_idr": 0, "eth_usdc_idr": 0,
        "btc_balance_idr": 0,
        "sol_balance_idr": 0, "sol_native_idr": 0, "sol_usdt_idr": 0, "sol_usdc_idr": 0,
        "sol_other_token_idr": 0, "sol_unvalued_count": 0, "sol_unvalued_mints": [],
        "eth_other_token_idr": 0, "eth_unvalued_count": 0, "eth_unvalued_contracts": [],
        "breakdown": [],
        "_chain_timings": {},
    }
    base.update(extra)
    return base


def _prov_ok(sumber="cmc", umur_detik=0):
    return {"sumber": sumber, "nilai": 1.0, "umur_detik": umur_detik}


def _patch_reconciliation_write():
    return patch.object(app_mod, "_get_db_conn", return_value=None)


class TestT26IntegrasiReconciliation:
    """Kasus 1-3: /api/reconciliation, jalur live yang menulis kelengkapan_status
    ke payload. Menutup celah D55 -- fungsi murni sudah teruji, jalur HTTP belum."""

    def test_kasus1_lengkap_tidak_memicu_indikatif(self, client):
        _bersihkan_cache()
        entries = [
            {"network": "ethereum", "address": "0xabc", "balance_native": 1.0,
             "fetch_status": "ok", "error": None},
            {"network": "bitcoin", "address": "bc1x", "balance_native": 1.0,
             "fetch_status": "ok", "error": None},
            {"network": "solana", "address": "sol1", "balance_native": 1.0,
             "fetch_status": "ok", "error": None},
        ]
        prov = {"ethereum": _prov_ok(), "bitcoin": _prov_ok(), "solana": _prov_ok()}
        br = _balance_result(100_000_000, entries, prov)

        with _patch_reconciliation_write(), \
             patch.object(app_mod, "get_total_balance_idr", return_value=br), \
             patch.object(app_mod, "_get_aset_dilaporkan", return_value=100_000_000):
            resp = client.get("/api/reconciliation")

        assert resp.status_code == 200
        entry = next(e for e in resp.json["data"] if e["id"] == PAKD_ID)
        assert entry["kelengkapan_status"] == "LENGKAP"
        assert entry["aset_onchain_idr_final"] is not None
        assert "status_indikatif" not in entry

    def test_kasus2_sebagian_satu_network_gagal(self, client):
        _bersihkan_cache()
        entries = [
            {"network": "ethereum", "address": "0xabc", "balance_native": 1.0,
             "fetch_status": "ok", "error": None},
            {"network": "bitcoin", "address": "bc1x", "balance_native": 1.0,
             "fetch_status": "ok", "error": None},
            {"network": "solana", "address": "sol1", "balance_native": None,
             "fetch_status": "partial", "error": "RPC timeout"},
        ]
        prov = {"ethereum": _prov_ok(), "bitcoin": _prov_ok(), "solana": None}
        br = _balance_result(80_000_000, entries, prov)

        with _patch_reconciliation_write(), \
             patch.object(app_mod, "get_total_balance_idr", return_value=br), \
             patch.object(app_mod, "_get_aset_dilaporkan", return_value=100_000_000):
            resp = client.get("/api/reconciliation")

        assert resp.status_code == 200
        entry = next(e for e in resp.json["data"] if e["id"] == PAKD_ID)
        assert entry["kelengkapan_status"] == "SEBAGIAN"
        assert entry["aset_onchain_idr_final"] is None
        assert entry["status"] == "Data Tidak Lengkap"
        assert len(entry["sumber_gagal"]) > 0

    def test_kasus3_tidak_tersedia_semua_gagal_D30(self, client):
        _bersihkan_cache()
        br = _balance_result(0, [], {"ethereum": None, "bitcoin": None, "solana": None})

        with _patch_reconciliation_write(), \
             patch.object(app_mod, "get_total_balance_idr", return_value=br), \
             patch.object(app_mod, "_get_aset_dilaporkan", return_value=100_000_000):
            resp = client.get("/api/reconciliation")

        assert resp.status_code == 200
        entry = next(e for e in resp.json["data"] if e["id"] == PAKD_ID)
        assert entry["kelengkapan_status"] == "TIDAK_TERSEDIA"
        assert entry["deviasi_pct"] is None, (
            "D61: deviasi_pct mentah bocor ke payload meski verdict ditahan "
            "Data Tidak Lengkap -- lihat core/verdict.py tetapkan_verdict_surplus")
        assert entry["ratio_at_pakd"] is not None, (
            "D30 dilanggar: ratio_at_pakd None saat data gagal total")
        assert isinstance(entry["ratio_at_pakd"], (int, float))


def _mock_conn_latest(row):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchall.side_effect = [[row], []]
    return conn


def _mock_conn_history(row):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchall.return_value = [row]
    return conn


def _row_latest(aset_dilaporkan, subtotal_diketahui, kelengkapan_status):
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    return (
        PAKD_ID, "Alpha Kripto Nusantara", aset_dilaporkan, subtotal_diketahui,
        None, "Data Tidak Lengkap", False, [],
        now, now,
        subtotal_diketahui, None, False, 0.20, 0.80,
        kelengkapan_status, [], {},
        (subtotal_diketahui if kelengkapan_status == "LENGKAP" else None),
        subtotal_diketahui,
    )


def _row_history(aset_dilaporkan, subtotal_diketahui, kelengkapan_status):
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    return (
        1, now, PAKD_ID, "Alpha Kripto Nusantara",
        aset_dilaporkan, subtotal_diketahui,
        None, "Data Tidak Lengkap", False, [],
        kelengkapan_status, [],
        (subtotal_diketahui if kelengkapan_status == "LENGKAP" else None),
        subtotal_diketahui,
    )


class TestT26D60VerdictIndikatif:
    """Kasus 4-7: blok _status_ind/_dev_ind di app.py:3193 dan 3283."""

    def test_kasus4_pas_dengan_galat_pembulatan_aman(self, client):
        aset_dilaporkan = 100_000_000
        subtotal = 99_999_999.9999
        conn = _mock_conn_latest(_row_latest(aset_dilaporkan, subtotal, "SEBAGIAN"))
        with patch.object(app_mod, "_get_db_conn", return_value=conn):
            resp = client.get("/api/reconciliation/latest")
        entry = next(e for e in resp.json["data"] if e["id"] == PAKD_ID)
        assert entry["status_indikatif"] == "Aman"

    def test_kasus5_defisit_kecil_bukan_aman(self, client):
        aset_dilaporkan = 100_000_000
        subtotal = 99_000_000
        conn = _mock_conn_latest(_row_latest(aset_dilaporkan, subtotal, "SEBAGIAN"))
        with patch.object(app_mod, "_get_db_conn", return_value=conn):
            resp = client.get("/api/reconciliation/latest")
        entry = next(e for e in resp.json["data"] if e["id"] == PAKD_ID)
        assert entry["status_indikatif"] != "Aman", (
            "D60: defisit 1% pada data SEBAGIAN tidak boleh lolos sebagai Aman")
        assert entry["status_indikatif"] == "Deviasi"

    def test_kasus6_defisit_besar_kritis(self, client):
        aset_dilaporkan = 100_000_000
        subtotal = 70_000_000
        conn = _mock_conn_latest(_row_latest(aset_dilaporkan, subtotal, "SEBAGIAN"))
        with patch.object(app_mod, "_get_db_conn", return_value=conn):
            resp = client.get("/api/reconciliation/latest")
        entry = next(e for e in resp.json["data"] if e["id"] == PAKD_ID)
        assert entry["status_indikatif"] == "Kritis"

    @pytest.mark.parametrize("endpoint,row_fn,mock_fn", [
        ("/api/reconciliation/latest", _row_latest, _mock_conn_latest),
        ("/api/reconciliation-history", _row_history, _mock_conn_history),
    ])
    def test_kasus7_surplus_besar_tetap_aman_dua_situs(
            self, client, endpoint, row_fn, mock_fn):
        aset_dilaporkan = 100_000_000
        subtotal = 1_000_000_000
        conn = mock_fn(row_fn(aset_dilaporkan, subtotal, "SEBAGIAN"))
        with patch.object(app_mod, "_get_db_conn", return_value=conn):
            resp = client.get(endpoint)
        assert resp.status_code == 200
        entry = next(e for e in resp.json["data"] if e.get("pakd_id", e.get("id")) == PAKD_ID)
        assert entry["status_indikatif"] == "Aman"
