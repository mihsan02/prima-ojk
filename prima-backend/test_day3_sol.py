"""
Day 3 unit tests: Solana balance fetcher, SOL price fetcher,
and get_total_balance_idr() with Solana wallets.

Run: python -m pytest test_day3_sol.py -v
"""
import pytest
from unittest.mock import patch, MagicMock
from app import (
    fetch_sol_balance,
    fetch_sol_price_idr,
    get_total_balance_idr,
    LAMPORTS_PER_SOL,
)


def make_sol_rpc_response(lamports):
    mock = MagicMock()
    mock.raise_for_status = lambda: None
    mock.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"value": lamports, "context": {"slot": 999}},
    }
    return mock


def make_coingecko_sol_response(price_idr):
    mock = MagicMock()
    mock.raise_for_status = lambda: None
    mock.json.return_value = {"solana": {"idr": price_idr}}
    return mock


@patch("app.requests.post")
def test_fetch_sol_balance_correct_conversion(mock_post):
    mock_post.return_value = make_sol_rpc_response(2_500_000_000)
    result = fetch_sol_balance("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263")
    assert result == pytest.approx(2.5, rel=1e-9)


@patch("app.requests.post")
def test_fetch_sol_balance_zero(mock_post):
    mock_post.return_value = make_sol_rpc_response(0)
    result = fetch_sol_balance("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263")
    assert result == 0.0


@patch("app.requests.get")
def test_fetch_sol_price_idr(mock_get):
    mock_get.return_value = make_coingecko_sol_response(2_850_000)
    price = fetch_sol_price_idr()
    assert price == pytest.approx(2_850_000.0)


# Test 1: test_total_balance_single_sol_wallet
@patch("app.fetch_all_spl_balances", return_value=[])
@patch("app.get_cached_balance")
@patch("app.get_cached_price")
def test_total_balance_single_sol_wallet(mock_price, mock_balance, mock_spl_enum):
    mock_price.return_value = 2_850_000.0
    mock_balance.side_effect = lambda k, a, f: 10.0 if k == "solana" else 0.0
    mock_balance.side_effect = lambda k, a, f: 10.0 if k == "solana" else 0.0
    wallets = [{"network": "solana", "address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "verified": False}]
    result = get_total_balance_idr(wallets, eth_price_idr=0, btc_price_idr=0, sol_price_idr=2_850_000.0, usdt_price_idr=0, usdc_price_idr=0)
    assert result["sol_balance_idr"] == pytest.approx(28_500_000.0)
    assert result["total_idr"]       == pytest.approx(28_500_000.0)
    assert result["eth_balance_idr"] == 0.0
    assert result["btc_balance_idr"] == 0.0

    wallets = [{"network": "solana", "address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "verified": False}]
    result = get_total_balance_idr(wallets, eth_price_idr=0, btc_price_idr=0, sol_price_idr=2_850_000.0)

    assert result["sol_balance_idr"] == pytest.approx(28_500_000.0)
    assert result["total_idr"]       == pytest.approx(28_500_000.0)
    assert result["eth_balance_idr"] == 0.0
    assert result["btc_balance_idr"] == 0.0


@patch("app.fetch_all_spl_balances", return_value=[])
@patch("app.get_cached_balance")
def test_total_balance_multichain_combined(mock_balance, mock_spl_enum):
    def side_effect(cache_key, address, fetch_fn):
        return {"ethereum": 2.0, "bitcoin": 0.1, "solana": 50.0}.get(cache_key, 0.0)
    mock_balance.side_effect = side_effect
    wallets = [
        {"network": "ethereum", "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "verified": False},
        {"network": "bitcoin",  "address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh", "verified": False},
        {"network": "solana",   "address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "verified": False},
    ]
    result = get_total_balance_idr(
        wallets,
        eth_price_idr=40_000_000,
        btc_price_idr=1_600_000_000,
        sol_price_idr=2_850_000,
        usdt_price_idr=0,
        usdc_price_idr=0,
    )
    assert result["eth_balance_idr"] == pytest.approx(80_000_000.0)
    assert result["btc_balance_idr"] == pytest.approx(160_000_000.0)
    assert result["sol_balance_idr"] == pytest.approx(142_500_000.0)
    assert result["total_idr"]       == pytest.approx(382_500_000.0)

    mock_balance.side_effect = side_effect

    wallets = [
        {"network": "ethereum", "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "verified": False},
        {"network": "bitcoin",  "address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh", "verified": False},
        {"network": "solana",   "address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "verified": False},
    ]

    result = get_total_balance_idr(
        wallets,
        eth_price_idr=40_000_000,
        btc_price_idr=1_600_000_000,
        sol_price_idr=2_850_000,
    )

    assert result["eth_balance_idr"] == pytest.approx(80_000_000.0)
    assert result["btc_balance_idr"] == pytest.approx(160_000_000.0)
    assert result["sol_balance_idr"] == pytest.approx(142_500_000.0)
    assert result["total_idr"]       == pytest.approx(382_500_000.0)


@patch("app.get_cached_balance")
@patch("app.get_cached_price")
def test_sol_rpc_error_isolated(mock_price, mock_balance):
    mock_price.return_value = 2_850_000.0
    mock_balance.side_effect = Exception("Connection timeout")

    wallets = [{"network": "solana", "address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "verified": False}]
    result = get_total_balance_idr(wallets, eth_price_idr=0, btc_price_idr=0, sol_price_idr=2_850_000.0)

    assert result["total_idr"]       == 0.0
    assert result["sol_balance_idr"] == 0.0
    assert "SOL fetch error" in result["breakdown"][0]["error"]
