"""
T3.2 -- GET /api/audit/verify. Endpoint HTTP yang membungkus
audit.verify_chain() (business logic, sudah diuji T3.1) di balik
autentikasi require_role('super_admin').

Autentikasi TIDAK diuji ulang di sini -- require_role sudah infrastruktur
existing dengan cakupan tesnya sendiri di tempat lain. Fixture `client`
dari conftest.py sudah menyuntik JWT super_admin secara default, jadi
setiap test di sini otomatis lolos gerbang auth; yang diuji murni logika
endpoint: bentuk query, pemetaan kolom, dan bentuk respons JSON.
"""
from unittest.mock import MagicMock, patch

import audit


COLS = ["id", "waktu", "aksi", "detail", "created_at", "actor_email", "actor_role",
        "source_ip", "request_id", "versi_perhitungan", "previous_event_hash", "event_hash"]


def _build_chain_rows(n, start_id=1):
    """Bangun n baris rantai valid memakai fungsi hash audit.py sendiri --
    supaya fixture test merefleksikan skema hash produksi, bukan string
    hash palsu yang kebetulan lolos."""
    rows = []
    previous_hash = audit.GENESIS_HASH
    for i in range(n):
        row_id = start_id + i
        event_dict = {
            "waktu": f"waktu-{row_id}", "aksi": f"AKSI_{row_id}", "detail": f"detail {row_id}",
            "created_at": f"2026-08-24T00:00:0{i}Z", "actor_email": None, "actor_role": None,
            "source_ip": None, "request_id": f"req-{row_id}", "versi_perhitungan": audit.VERSI_PERHITUNGAN,
        }
        event_hash = audit._compute_event_hash(previous_hash, event_dict)
        rows.append((
            row_id, event_dict["waktu"], event_dict["aksi"], event_dict["detail"],
            event_dict["created_at"], event_dict["actor_email"], event_dict["actor_role"],
            event_dict["source_ip"], event_dict["request_id"], event_dict["versi_perhitungan"],
            previous_hash, event_hash,
        ))
        previous_hash = event_hash
    return rows


class TestAuditVerifyEndpoint:

    def test_clean_chain_returns_utuh_true(self, client):
        rows = _build_chain_rows(3)
        fake_conn = MagicMock()
        fake_cur = fake_conn.cursor.return_value
        fake_cur.fetchall.return_value = rows

        with patch('app._get_db_conn', return_value=fake_conn), \
             patch('app._return_db_conn'):
            resp = client.get('/api/audit/verify')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['utuh'] is True
        assert data['jumlah_event'] == 3
        assert data['jumlah_total_baris'] == 3
        assert data['id_baris_rusak'] is None

    def test_tampered_row_returns_utuh_false_with_id(self, client):
        rows = list(_build_chain_rows(3))
        tampered = list(rows[1])
        tampered[3] = "DIUBAH MANUAL LEWAT SQL"
        rows[1] = tuple(tampered)

        fake_conn = MagicMock()
        fake_cur = fake_conn.cursor.return_value
        fake_cur.fetchall.return_value = rows

        with patch('app._get_db_conn', return_value=fake_conn), \
             patch('app._return_db_conn'):
            resp = client.get('/api/audit/verify')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['utuh'] is False
        assert data['id_baris_rusak'] == rows[1][0]

    def test_legacy_rows_excluded_from_jumlah_event(self, client):
        legacy_row = (0, "x", "OLD", "lama", "x", None, None, None, None, None, None, None)
        chain_rows = _build_chain_rows(2, start_id=1)
        rows = [legacy_row] + list(chain_rows)

        fake_conn = MagicMock()
        fake_cur = fake_conn.cursor.return_value
        fake_cur.fetchall.return_value = rows

        with patch('app._get_db_conn', return_value=fake_conn), \
             patch('app._return_db_conn'):
            resp = client.get('/api/audit/verify')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['utuh'] is True
        assert data['jumlah_event'] == 2
        assert data['jumlah_total_baris'] == 3

    def test_db_unreachable_returns_error(self, client):
        with patch('app._get_db_conn', return_value=None):
            resp = client.get('/api/audit/verify')
        assert resp.status_code == 503
