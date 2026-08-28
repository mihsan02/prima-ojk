"""
Item 1 (dari sesi "job state to Postgres, reduced"): reconciliation_refresh()
tidak pernah mengecek job aktif sebelum submit -- dua klik cepat bisa
menjalankan dua rekonsiliasi paralel, dua-duanya menulis snapshot lewat
_save_snapshots_batch. Fast-path SELECT + partial unique index
uq_reconciliation_jobs_active (dibuat lewat /tmp/add_job_dedup_index.py,
tidak ada di migrate_to_supabase.py -- itu skrip run-once, bukan
migrasi berulang) sekarang mencegah ini.

Cabang IntegrityError/UniqueViolation (race sungguhan antara SELECT dan
INSERT) tidak diuji di sini -- butuh dua koneksi konkuren sungguhan,
di luar jangkauan test unit bermock. Kebenaran cabang itu bergantung
pada index yang sudah dikonfirmasi ada di produksi (lihat catatan sesi),
bukan pada test ini.
"""
from unittest.mock import MagicMock

import app as app_mod


class _FakeCursor:
    """Cursor palsu: fetchone() dikontrol lewat parameter, tidak perlu
    Postgres asli. Menyimulasikan dua kondisi: ada job aktif / tidak ada."""
    def __init__(self, existing_job_row):
        self._existing = existing_job_row
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append(sql)

    def fetchone(self):
        return self._existing

    def close(self):
        pass


def _make_conn(existing_job_row):
    cur = _FakeCursor(existing_job_row)
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


def test_refresh_returns_409_when_job_already_active(client, monkeypatch):
    conn, cur = _make_conn(existing_job_row=("job-yang-sudah-jalan",))
    monkeypatch.setattr(app_mod, "_get_db_conn", lambda: conn)
    monkeypatch.setattr(app_mod, "_return_db_conn", lambda c: None)
    monkeypatch.setattr(app_mod, "_REFRESH_EXECUTOR", MagicMock())

    resp = client.post("/api/reconciliation/refresh")

    assert resp.status_code == 409, (
        f"dapat {resp.status_code}, harusnya 409 -- dedup tidak mencegah "
        f"job kedua walau job aktif terdeteksi"
    )
    body = resp.get_json()
    assert body["job_id"] == "job-yang-sudah-jalan"
    assert body["status"] == "sudah_berjalan"


def test_refresh_creates_job_when_none_active(client, monkeypatch):
    conn, cur = _make_conn(existing_job_row=None)
    monkeypatch.setattr(app_mod, "_get_db_conn", lambda: conn)
    monkeypatch.setattr(app_mod, "_return_db_conn", lambda c: None)
    mock_executor = MagicMock()
    monkeypatch.setattr(app_mod, "_REFRESH_EXECUTOR", mock_executor)

    resp = client.post("/api/reconciliation/refresh")

    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["status"] == "pending"
    assert body["job_id"]
    assert mock_executor.submit.called, "job seharusnya tetap disubmit ke executor"
