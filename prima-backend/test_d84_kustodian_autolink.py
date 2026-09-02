"""
D84: mendedikasikan wallet kustodian ke sebuah PAKD lewat PUT /api/kustodian/<id>
dulu hanya menulis wallets.pakd_id. Tautan entitasnya hidup di tabel terpisah,
kustodian_pakd, yang jalur itu tidak pernah sentuh -- sehingga
_get_kustodian_data_for_pakd() balik kosong dan compute_30_70_compliance()
melaporkan kustodian_onchain_idr None. Saldo wallet benar tersimpan, tapi mesin
kepatuhan Pasal 91 tidak pernah melihatnya: dashboard menampilkan "-" dan "N/A".
"""
from unittest.mock import patch, MagicMock
import app as app_mod


class _FakeCursor:
    def __init__(self, pakd_exists=True):
        self.executed = []
        self._pakd_exists = pakd_exists
        self._last_sql = ""

    def execute(self, sql, params=None):
        self._last_sql = sql
        self.executed.append((" ".join(sql.split()), params))

    def fetchone(self):
        s = self._last_sql
        if "FROM kustodian WHERE id" in s:
            return ("KUST-TEST",)
        if "FROM pakd WHERE id" in s:
            return ("PAKD-TEST",) if self._pakd_exists else None
        if "FROM wallets" in s:
            return None
        return None

    def fetchall(self):
        return []

    def close(self):
        pass

    def sql_touching(self, table):
        return [e for e in self.executed if table in e[0]]


def _fake_conn(cursor):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


_WALLET = {
    "network": "bitcoin",
    "address": "bc1qgya3z2na8cmes4sxr59f3u0edl9yt7w1mfl7hm",
    "verified": False,
    "verified_at": None,
    "pakd_id": "PAKD-TEST",
}


class TestD84AutoLink:

    def test_wallet_berdedikasi_menulis_baris_kustodian_pakd(self, client):
        cur = _FakeCursor(pakd_exists=True)
        conn = _fake_conn(cur)
        with patch.object(app_mod, "_get_db_conn", return_value=conn), \
             patch.object(app_mod, "_return_db_conn"), \
             patch.object(app_mod, "write_audit"), \
             patch.object(app_mod, "validate_wallet_address", return_value=(True, "")):
            resp = client.put("/api/kustodian/KUST-TEST",
                              json={"wallets": [_WALLET]},
                              headers={"X-Internal-Token": "test-internal-token-d49"})

        assert resp.status_code == 200, resp.get_json()
        links = cur.sql_touching("INSERT INTO kustodian_pakd")
        assert len(links) == 1, f"kustodian_pakd tidak ditulis; SQL: {[e[0] for e in cur.executed]}"
        assert links[0][1] == ("KUST-TEST", "PAKD-TEST")
        assert "ON CONFLICT DO NOTHING" in links[0][0]
        conn.commit.assert_called_once()

    def test_wallet_tanpa_pakd_id_tidak_membuat_tautan(self, client):
        cur = _FakeCursor(pakd_exists=True)
        conn = _fake_conn(cur)
        wallet = dict(_WALLET, pakd_id=None)
        with patch.object(app_mod, "_get_db_conn", return_value=conn), \
             patch.object(app_mod, "_return_db_conn"), \
             patch.object(app_mod, "write_audit"), \
             patch.object(app_mod, "validate_wallet_address", return_value=(True, "")):
            resp = client.put("/api/kustodian/KUST-TEST",
                              json={"wallets": [wallet]},
                              headers={"X-Internal-Token": "test-internal-token-d49"})

        assert resp.status_code == 200, resp.get_json()
        assert cur.sql_touching("INSERT INTO kustodian_pakd") == []

    def test_dedikasi_ke_pakd_tidak_terdaftar_ditolak_404(self, client):
        cur = _FakeCursor(pakd_exists=False)
        conn = _fake_conn(cur)
        with patch.object(app_mod, "_get_db_conn", return_value=conn), \
             patch.object(app_mod, "_return_db_conn"), \
             patch.object(app_mod, "write_audit"), \
             patch.object(app_mod, "validate_wallet_address", return_value=(True, "")):
            resp = client.put("/api/kustodian/KUST-TEST",
                              json={"wallets": [_WALLET]},
                              headers={"X-Internal-Token": "test-internal-token-d49"})

        assert resp.status_code == 404, resp.get_json()
        assert "PAKD-TEST" in resp.get_json()["message"]
        assert cur.sql_touching("INSERT INTO kustodian_pakd") == []
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_dua_wallet_ke_pakd_sama_hanya_satu_tautan(self, client):
        cur = _FakeCursor(pakd_exists=True)
        conn = _fake_conn(cur)
        w2 = dict(_WALLET, network="ethereum",
                  address="0xa0bA601C986493Fd35Bb0Ce4C0e0dF0a3Fb9A5e1")
        with patch.object(app_mod, "_get_db_conn", return_value=conn), \
             patch.object(app_mod, "_return_db_conn"), \
             patch.object(app_mod, "write_audit"), \
             patch.object(app_mod, "validate_wallet_address", return_value=(True, "")):
            resp = client.put("/api/kustodian/KUST-TEST",
                              json={"wallets": [_WALLET, w2]},
                              headers={"X-Internal-Token": "test-internal-token-d49"})

        assert resp.status_code == 200, resp.get_json()
        assert len(cur.sql_touching("INSERT INTO kustodian_pakd")) == 1


class TestD84ReturnTypeContract:

    def test_tanpa_koneksi_balik_dict_kosong(self):
        with patch.object(app_mod, "_get_db_conn", return_value=None):
            kust_ids, wallets_by_kust = app_mod._get_kustodian_data_for_pakd("PAKD-TEST")
        assert kust_ids == []
        assert isinstance(wallets_by_kust, dict)
        assert wallets_by_kust.get("apa pun", []) == []

    def test_tanpa_tautan_balik_dict_kosong(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        conn = _fake_conn(cur)
        with patch.object(app_mod, "_get_db_conn", return_value=conn), \
             patch.object(app_mod, "_return_db_conn"):
            kust_ids, wallets_by_kust = app_mod._get_kustodian_data_for_pakd("PAKD-TEST")
        assert kust_ids == []
        assert isinstance(wallets_by_kust, dict)

    def test_saat_query_gagal_balik_dict_kosong(self):
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("boom")
        conn = _fake_conn(cur)
        with patch.object(app_mod, "_get_db_conn", return_value=conn), \
             patch.object(app_mod, "_return_db_conn"):
            kust_ids, wallets_by_kust = app_mod._get_kustodian_data_for_pakd("PAKD-TEST")
        assert kust_ids == []
        assert isinstance(wallets_by_kust, dict)
