"""D53: isolasi per-baris _save_snapshots_batch.

Opsi C (keputusan mentor): coba executemany batch dulu (jalur cepat).
Kalau gagal, fallback ke per-baris, commit tiap baris sukses, rollback
setelah baris gagal (wajib -- transaksi Postgres aborted tanpa rollback
akan menjatuhkan baris SESUDAHNYA juga, bukan cuma baris yang error).
Kegagalan per-baris harus eksplisit dengan pakd_id, bukan cuma print.
"""
import json
from unittest.mock import MagicMock, patch
import app as app_mod


def _hasil(pid, aset_onchain_idr=1_000_000, deviasi_pct=0.0):
    return {
        "id": pid, "nama": f"PAKD {pid}",
        "aset_dilaporkan_idr": 1_000_000, "aset_onchain_idr": aset_onchain_idr,
        "deviasi_pct": deviasi_pct, "status": "Aman",
        "breakdown": {}, "pakd_onchain_idr": None,
        "kustodian_onchain_idr": None, "compliance_30_70": None,
        "ratio_at_pakd": None, "ratio_at_ptp": None,
        "kelengkapan_status": "LENGKAP", "sumber_gagal": None,
        "provenance_harga": None, "aset_onchain_idr_final": aset_onchain_idr,
        "subtotal_diketahui_idr": aset_onchain_idr,
    }


class TestD53BatchIsolation:
    def test_semua_sukses_satu_round_trip(self):
        """Jalur bahagia: 3 PAKD sehat, executemany sekali, commit sekali,
        TIDAK jatuh ke fallback per-baris (round-trip tetap minimal)."""
        hasil_list = [_hasil("PAKD-A"), _hasil("PAKD-B"), _hasil("PAKD-C")]
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        cur.executemany.return_value = None  # sukses

        with patch.object(app_mod, "_get_db_conn", return_value=conn), \
             patch.object(app_mod, "_return_db_conn"):
            result = app_mod._save_snapshots_batch(hasil_list, harga_fallback=False)

        assert cur.executemany.call_count == 1, (
            "Jalur bahagia wajib satu executemany, bukan turun ke per-baris")
        assert cur.execute.call_count == 0, (
            "Tidak boleh ada fallback per-baris kalau batch sukses")
        assert conn.commit.call_count == 1
        assert conn.rollback.call_count == 0
        assert result["failed"] == []
        assert len(result["saved"]) == 3

    def test_satu_gagal_fallback_menyelamatkan_dua_lainnya(self):
        """PAKD-B gagal (mis. TypeError dari harga null). Fallback per-baris
        wajib: A dan C tetap tersimpan, B tercatat eksplisit dengan pakd_id,
        rollback dipanggil setelah baris B gagal (bukan opsional)."""
        hasil_list = [_hasil("PAKD-A"), _hasil("PAKD-B"), _hasil("PAKD-C")]
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        cur.executemany.side_effect = Exception("simulated: null harga")
        # Baris B (indeks 1) gagal saat fallback per-baris; A dan C sukses.
        cur.execute.side_effect = [None, Exception("simulated: null harga"), None]

        with patch.object(app_mod, "_get_db_conn", return_value=conn), \
             patch.object(app_mod, "_return_db_conn"):
            result = app_mod._save_snapshots_batch(hasil_list, harga_fallback=False)

        assert cur.executemany.call_count == 1, "wajib coba batch dulu"
        assert cur.execute.call_count == 3, "fallback wajib coba ketiga baris"
        assert conn.commit.call_count == 2, (
            "A dan C masing-masing commit sendiri di jalur fallback")
        assert conn.rollback.call_count == 1, (
            "Wajib rollback tepat setelah baris B gagal -- tanpa ini transaksi "
            "aborted dan baris C (sesudah B) ikut gagal walau datanya benar")
        assert len(result["saved"]) == 2
        assert result["saved"] == ["PAKD-A", "PAKD-C"]
        assert len(result["failed"]) == 1
        assert result["failed"][0]["pakd_id"] == "PAKD-B"
        assert "error" in result["failed"][0]
