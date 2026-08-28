"""
D70 -- regresi: recalc_snapshot() menduplikasi logic surplus/status
secara inline, hilang cabang "Surplus Tidak Wajar" untuk surplus_pct
> 10%. Sebelum patch, PAKD surplus 12% lolos sebagai "Aman" lewat
endpoint ini, padahal internal_refresh_all/_run_refresh_job akan
menandainya "Surplus Tidak Wajar" untuk input identik -- dua verdict
berbeda untuk satu PAKD tergantung endpoint terakhir yang dipanggil.

Pola mocking direplikasi dari test_d49_verdict_consistency.py:
_get_db_conn di-mock lewat cursor palsu untuk dua query recalc_snapshot
(snapshot lama, data PAKD). compute_30_70_compliance TIDAK di-mock,
dibiarkan berjalan asli terhadap _get_db_conn()=None, konsisten dengan
pola yang sudah terbukti aman di 309+ test yang ada.

Angka defisit 15% dan surplus_pct disamakan dengan test_verdict.py
baris 41-44 (surplus_pct 4661.9% -> "Surplus Tidak Wajar") dan
test_d49 (defisit 15% -> "Kritis") untuk konsistensi lintas dokumen.
"""
from unittest.mock import patch, MagicMock

import app as app_mod

PAKD_ID = "PAKD-DEMO-001"


def _make_conn(snapshot_row, pakd_row):
    cur = MagicMock()
    cur.fetchone.side_effect = [snapshot_row, pakd_row]
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


class TestD70RecalcSnapshotVerdictConsistency:

    def test_surplus_12_persen_jadi_surplus_tidak_wajar_bukan_aman(self, client):
        snapshot_row = (112_000_000, None, False)
        pakd_row = ("PAKD Demo Satu", 100_000_000)
        conn = _make_conn(snapshot_row, pakd_row)

        with patch.object(app_mod, "_get_db_conn", return_value=conn), \
             patch.object(app_mod, "_return_db_conn"), \
             patch.object(app_mod, "_get_aset_dilaporkan", return_value=100_000_000), \
             patch.object(app_mod, "write_audit"):
            resp = client.post(f"/api/pakd/{PAKD_ID}/recalc-snapshot")

        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        got = body.get("status_rekonsiliasi")
        assert got == "Surplus Tidak Wajar", (
            "D70 belum tertutup di recalc_snapshot -- dapat " + repr(got) +
            ", harusnya 'Surplus Tidak Wajar'"
        )

    def test_surplus_5_persen_tetap_aman(self, client):
        snapshot_row = (105_000_000, None, False)
        pakd_row = ("PAKD Demo Satu", 100_000_000)
        conn = _make_conn(snapshot_row, pakd_row)

        with patch.object(app_mod, "_get_db_conn", return_value=conn), \
             patch.object(app_mod, "_return_db_conn"), \
             patch.object(app_mod, "_get_aset_dilaporkan", return_value=100_000_000), \
             patch.object(app_mod, "write_audit"):
            resp = client.post(f"/api/pakd/{PAKD_ID}/recalc-snapshot")

        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["status_rekonsiliasi"] == "Aman"

    def test_defisit_15_persen_tetap_kritis(self, client):
        snapshot_row = (85_000_000, None, False)
        pakd_row = ("PAKD Demo Satu", 100_000_000)
        conn = _make_conn(snapshot_row, pakd_row)

        with patch.object(app_mod, "_get_db_conn", return_value=conn), \
             patch.object(app_mod, "_return_db_conn"), \
             patch.object(app_mod, "_get_aset_dilaporkan", return_value=100_000_000), \
             patch.object(app_mod, "write_audit"):
            resp = client.post(f"/api/pakd/{PAKD_ID}/recalc-snapshot")

        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["status_rekonsiliasi"] == "Kritis"
