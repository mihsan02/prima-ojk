"""
Day 16: SPL token enumeration with Jupiter pricing.
Three-test minimum per spec. Zero live network calls.
"""
import pytest
from unittest.mock import patch, MagicMock
import app


@pytest.fixture(autouse=True)
def reset_caches():
    """Clear all caches before each test to prevent cross-test pollution."""
    app.PRICE_CACHE.clear()
    app.BALANCE_CACHE.clear()
    app.JUPITER_STRICT_CACHE.clear()
    app.JUPITER_PRICE_CACHE.clear()
    yield
    app.PRICE_CACHE.clear()
    app.BALANCE_CACHE.clear()
    app.JUPITER_STRICT_CACHE.clear()
    app.JUPITER_PRICE_CACHE.clear()


def _spl_rpc_response(holdings):
    """
    Build a mocked Solana RPC getTokenAccountsByOwner response.
    holdings: list of (mint, ui_amount) tuples.
    """
    return {
        "result": {
            "value": [
                {
                    "account": {
                        "data": {
                            "parsed": {
                                "info": {
                                    "mint": mint,
                                    "tokenAmount": {"uiAmount": ui_amount},
                                }
                            }
                        }
                    }
                }
                for mint, ui_amount in holdings
            ]
        }
    }


def test_enumeration_filters_zero_balances():
    """fetch_all_spl_balances must drop zero and None ui_amount entries."""
    rpc_resp = _spl_rpc_response([
        ("MintAAA111111111111111111111111111111111111", 100.5),
        ("MintBBB222222222222222222222222222222222222", 0),
        ("MintCCC333333333333333333333333333333333333", None),
        ("MintDDD444444444444444444444444444444444444", 7.0),
    ])

    mock_post = MagicMock()
    mock_post.return_value.json.return_value  = rpc_resp
    mock_post.return_value.raise_for_status.return_value = None

    with patch("app.requests.post", mock_post):
        result = app.fetch_all_spl_balances("FakeOwnerAddress")

    assert len(result) == 2
    mints = {h["mint"] for h in result}
    assert "MintAAA111111111111111111111111111111111111" in mints
    assert "MintDDD444444444444444444444444444444444444" in mints
    assert "MintBBB222222222222222222222222222222222222" not in mints
    assert "MintCCC333333333333333333333333333333333333" not in mints


def test_two_gate_filter_passes_strict_listed_priced_token():
    """
    Verified-set mint with non-zero Jupiter price must contribute to
    sol_other_token_idr and NOT appear in unvalued_mints.
    """
    target_mint = "BabyDog3Min7AddrPrXxxxxxxxxxxxxxxxxxxxxxxxx"

    rpc_resp = _spl_rpc_response([(target_mint, 1_000_000.0)])

    # Mock Solana RPC
    mock_post = MagicMock()
    mock_post.return_value.json.return_value  = rpc_resp
    mock_post.return_value.raise_for_status.return_value = None

    # Mock Jupiter verified tag + price endpoints (both GET)
    def fake_get(url, **kwargs):
        m = MagicMock()
        m.raise_for_status.return_value = None
        if "/tokens/v2/tag" in url:
            m.json.return_value = [{"id": target_mint, "symbol": "BABY"}]
        elif "/price/v3" in url:
            m.json.return_value = {target_mint: {"usdPrice": 0.0000056, "decimals": 5}}
        else:
            m.json.return_value = {}
        return m

    with patch("app.requests.post", mock_post), \
         patch("app.requests.get", side_effect=fake_get), \
         patch("app.get_cached_balance", side_effect=lambda key, addr, fn: 0.0), \
         patch("app._get_stablecoin_prices_idr", return_value=(16_500.0, 16_500.0)):

        wallets = [{"network": "solana", "address": "FakeOwnerAddress", "verified": True}]
        result  = app.get_total_balance_idr(
            wallets,
            eth_price_idr=0, btc_price_idr=0, sol_price_idr=0,
            usdt_price_idr=16_500.0, usdc_price_idr=16_500.0,
        )

    assert result["sol_other_token_idr"] > 0
    assert result["sol_unvalued_count"]  == 0
    assert target_mint not in result["sol_unvalued_mints"]
    # Sanity: 1_000_000 * 0.0000056 * 16500 = ~92,400 IDR
    assert 50_000 < result["sol_other_token_idr"] < 150_000


def test_two_gate_filter_rejects_non_strict_listed_token():
    """
    Mint NOT in verified set AND no Jupiter price must be excluded from
    sol_other_token_idr and tracked in sol_unvalued_mints.
    """
    unknown_mint = "Scam5p4mTokenMintXxxxxxxxxxxxxxxxxxxxxxxxxxx"

    rpc_resp = _spl_rpc_response([(unknown_mint, 500_000.0)])

    mock_post = MagicMock()
    mock_post.return_value.json.return_value  = rpc_resp
    mock_post.return_value.raise_for_status.return_value = None

    def fake_get(url, **kwargs):
        m = MagicMock()
        m.raise_for_status.return_value = None
        if "/tokens/v2/tag" in url:
            m.json.return_value = []                 # empty verified set
        elif "/price/v3" in url:
            m.json.return_value = {}                 # no price entry
        else:
            m.json.return_value = {}
        return m

    with patch("app.requests.post", mock_post), \
         patch("app.requests.get", side_effect=fake_get), \
         patch("app.get_cached_balance", side_effect=lambda key, addr, fn: 0.0), \
         patch("app._get_stablecoin_prices_idr", return_value=(16_500.0, 16_500.0)):

        wallets = [{"network": "solana", "address": "FakeOwnerAddress", "verified": True}]
        result  = app.get_total_balance_idr(
            wallets,
            eth_price_idr=0, btc_price_idr=0, sol_price_idr=0,
            usdt_price_idr=16_500.0, usdc_price_idr=16_500.0,
        )

    assert result["sol_other_token_idr"] == 0
    assert result["sol_unvalued_count"]  == 1
    assert unknown_mint in result["sol_unvalued_mints"]


def test_spl_enum_failure_degrades_to_partial_native_still_succeeds():
    """
    T2.3 (D6): fetch_all_spl_balances failing (RPC error) must not crash
    the wallet -- native SOL still succeeds via the separate get_cached_balance
    mock, and the entry degrades to fetch_status "partial", not "gagal".
    """
    mock_post = MagicMock()
    mock_post.side_effect = Exception("Solana RPC unreachable")

    with patch("app.requests.post", mock_post), \
         patch("app.get_cached_balance", side_effect=lambda key, addr, fn: 5.0 if key == "solana" else 0.0):

        wallets = [{"network": "solana", "address": "FakeOwnerAddress", "verified": True}]
        result  = app.get_total_balance_idr(
            wallets,
            eth_price_idr=0, btc_price_idr=0, sol_price_idr=2_850_000.0,
            usdt_price_idr=16_500.0, usdc_price_idr=16_500.0,
        )

    entry = result["breakdown"][0]
    assert entry["error"] is None
    assert entry["fetch_status"] == "partial"
    assert result["sol_balance_idr"] > 0
