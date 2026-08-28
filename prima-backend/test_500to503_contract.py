"""
Perbaikan kontrak: empat pemanggil load_pakd() yang punya try/except
Exception sendiri akan menelan DataSourceUnavailable dan membalas 500
generik, bukan 503 dari errorhandler global (lihat D80). Tiga situs
Flask handler ditambah `except DataSourceUnavailable: raise` supaya
exception naik ke errorhandler. Situs keempat (_run_refresh_job)
berjalan di thread background, tidak boleh re-raise -- exception di
thread tidak ditangkap siapa pun dan job akan macet selamanya di
status 'running'. Situs itu tetap menangkap dan mencatat 'failed',
hanya dengan detail error_type yang lebih jelas.
"""
import app as app_mod


def _force_datasource_unavailable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unreachable/db")
    monkeypatch.delenv("PRIMA_ALLOW_FILE_FALLBACK", raising=False)
    monkeypatch.setattr(app_mod, "_get_db_conn", lambda: None)


def test_reconciliation_returns_503_not_500(client, monkeypatch):
    _force_datasource_unavailable(monkeypatch)
    resp = client.get("/api/reconciliation")
    assert resp.status_code == 503, (
        f"dapat {resp.status_code}, harusnya 503 (DataSourceUnavailable "
        f"tertelan except Exception generik)"
    )
    assert resp.get_json()["error"] == "sumber_data_tidak_tersedia"


def test_internal_refresh_all_returns_503_and_releases_lock(monkeypatch):
    _force_datasource_unavailable(monkeypatch)
    monkeypatch.setenv("INTERNAL_TOKEN", "test-internal-token-503")
    app_mod.REFRESH_LOCK["running"] = False
    app_mod.REFRESH_LOCK["started_at"] = None

    with app_mod.app.test_client() as c:
        resp = c.post("/api/internal/refresh-all",
                       headers={"X-Internal-Token": "test-internal-token-503"})

    assert resp.status_code == 503, f"dapat {resp.status_code}, harusnya 503"
    assert app_mod.REFRESH_LOCK["running"] is False, (
        "REFRESH_LOCK tidak dilepas -- finally harus tetap jalan saat re-raise"
    )


def test_input_manual_returns_503_not_500(client, monkeypatch):
    """Payload direplikasi dari test_P6_input_manual_accepts_new_fields
    (test_day15_pasal50_pasal91.py) supaya lolos validasi field wajib
    (nama, id, aset_dilaporkan positif, wallets valid) dan benar-benar
    sampai ke load_pakd() -- bukan gagal duluan di validasi dengan 400."""
    _force_datasource_unavailable(monkeypatch)
    resp = client.post("/api/input-manual", json={
        "id":              "PAKD-TEST-503",
        "nama":            "Test 503",
        "aset_dilaporkan": 500_000_000_000,
        "wallets":         [{"network": "ethereum",
                              "address": "0x28C6c06298d514Db089934071355E5743bf21d60"}],
    })
    assert resp.status_code == 503, f"dapat {resp.status_code}, harusnya 503"


def test_run_refresh_job_marks_failed_not_uncaught(monkeypatch):
    """Situs keempat TIDAK boleh re-raise. _job_update adalah closure
    lokal (bukan atribut modul) yang sendirinya no-op dengan print kalau
    _get_db_conn() balik None -- jadi yang dibuktikan di sini bukan isi
    _job_update, tapi bahwa _run_refresh_job TIDAK melempar exception
    tak tertangkap saat DataSourceUnavailable terjadi. Kalau re-raise,
    thread background mati diam-diam dan job macet selamanya di
    status 'running' (lebih buruk dari status 'failed')."""
    _force_datasource_unavailable(monkeypatch)
    try:
        app_mod._run_refresh_job("test-job-503")
    except app_mod.DataSourceUnavailable:
        raise AssertionError(
            "_run_refresh_job membiarkan DataSourceUnavailable naik tak "
            "tertangkap -- job akan macet di status running selamanya "
            "karena tidak ada errorhandler di thread background"
        )
