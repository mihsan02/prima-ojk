import pytest
import app as app_mod


def test_load_pakd_raises_when_fallback_disabled(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unreachable/db")
    monkeypatch.setattr(app_mod, "_get_db_conn", lambda: None)
    with pytest.raises(app_mod.DataSourceUnavailable):
        app_mod.load_pakd()


def test_save_pakd_raises_when_fallback_disabled(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unreachable/db")
    monkeypatch.setattr(app_mod, "_get_db_conn", lambda: None)
    with pytest.raises(app_mod.DataSourceUnavailable):
        app_mod.save_pakd([{"id": "X", "nama": "X"}])


def test_endpoint_returns_503_not_empty_list(client, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unreachable/db")
    monkeypatch.setattr(app_mod, "_get_db_conn", lambda: None)
    r = client.get("/api/pakd")
    assert r.status_code == 503, f"D80: dapat {r.status_code}, bukan 503"
    assert r.get_json()["error"] == "sumber_data_tidak_tersedia"


def test_fallback_still_works_when_no_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PRIMA_ALLOW_FILE_FALLBACK", "1")
    monkeypatch.setattr(app_mod, "_get_db_conn", lambda: None)
    assert len(app_mod.load_pakd()) > 0
