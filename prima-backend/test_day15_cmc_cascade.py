"""
Test CMC cascade primary price source (Day 15).

Validates:
- CMC absent -> returns False, falls through to CoinGecko
- CMC success -> populates all 5 PRICE_CACHE entries
- CMC failure -> returns False, no partial cache pollution
- CMC idempotent -> no network call when cache fresh
- ETH cascade end-to-end with CMC unavailable

Schema note: CMC /v2/cryptocurrency/quotes/latest returns data[id] as
array of objects, not dict. Mock fixtures wrap each entry in [].
"""
import time
import pytest
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
import app


@pytest.fixture(autouse=True)
def reset_cache():
    """Clear PRICE_CACHE before and after each test."""
    app.PRICE_CACHE.clear()
    yield
    app.PRICE_CACHE.clear()


def test_cmc_no_key_returns_false(monkeypatch):
    """When COINMARKETCAP_API_KEY env is unset, refresh returns False
    without making any network call."""
    monkeypatch.delenv("COINMARKETCAP_API_KEY", raising=False)
    with patch("app.requests.get") as mock_get:
        result = app._refresh_price_cache_from_cmc()
        assert result is False
        mock_get.assert_not_called()


def test_cmc_success_populates_all_5(monkeypatch):
    """CMC 200 OK with full payload populates PRICE_CACHE for all 5 cgkeys.
    Schema: /v2 returns data[id] as array per CMC API contract."""
    monkeypatch.setenv("COINMARKETCAP_API_KEY", "test_key_32_chars_xxxxxxxxxxxxxx")
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = lambda: None
    fake_response.json.return_value = {
        "data": {
            "1":    [{"quote": {"IDR": {"price": 1_400_000_000}}}],
            "1027": [{"quote": {"IDR": {"price": 40_000_000}}}],
            "5426": [{"quote": {"IDR": {"price": 1_500_000}}}],
            "825":  [{"quote": {"IDR": {"price": 16_400}}}],
            "3408": [{"quote": {"IDR": {"price": 16_400}}}],
        }
    }
    with patch("app.requests.get", return_value=fake_response):
        result = app._refresh_price_cache_from_cmc()
    assert result is True
    assert app.PRICE_CACHE["bitcoin"][1] == 1_400_000_000
    assert app.PRICE_CACHE["ethereum"][1] == 40_000_000
    assert app.PRICE_CACHE["solana"][1] == 1_500_000
    assert app.PRICE_CACHE["tether"][1] == 16_400
    assert app.PRICE_CACHE["usd-coin"][1] == 16_400


def test_cmc_network_failure_returns_false(monkeypatch):
    """When CMC raises exception, refresh returns False, cache unpolluted."""
    monkeypatch.setenv("COINMARKETCAP_API_KEY", "test_key_32_chars_xxxxxxxxxxxxxx")
    with patch("app.requests.get", side_effect=Exception("network down")):
        result = app._refresh_price_cache_from_cmc()
    assert result is False
    assert "bitcoin" not in app.PRICE_CACHE


def test_cmc_idempotent_when_cache_fresh(monkeypatch):
    """When all 5 prices are fresh in cache, refresh skips network call."""
    monkeypatch.setenv("COINMARKETCAP_API_KEY", "test_key_32_chars_xxxxxxxxxxxxxx")
    now = time.time()
    for cgkey in ["bitcoin", "ethereum", "solana", "tether", "usd-coin"]:
        app.PRICE_CACHE[cgkey] = (now, 1.0)
    with patch("app.requests.get") as mock_get:
        result = app._refresh_price_cache_from_cmc()
        assert result is True
        mock_get.assert_not_called()


def test_eth_cascade_falls_through_to_coingecko_when_cmc_absent(monkeypatch):
    """Without CMC key, get_eth_price_idr falls through to CoinGecko Tier 2."""
    monkeypatch.delenv("COINMARKETCAP_API_KEY", raising=False)
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"ethereum": {"idr": 39_500_000}}
    with patch("app.requests.get", return_value=fake_resp):
        price, fallback = app.get_eth_price_idr()
    assert price == 39_500_000
    assert fallback is False
