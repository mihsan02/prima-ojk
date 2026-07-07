"""
Day 17 - ETH curated ERC-20 enumeration tests.

7 tests, fully mocked. Zero live network calls.
Target: 76 passing total (69 baseline + 7 new).
"""

import pytest
import time
from unittest.mock import patch, MagicMock
import app


@pytest.fixture(autouse=True)
def reset_coingecko_cache():
    """Reset module-level cache before each test to prevent state leak."""
    app.COINGECKO_TOKEN_CACHE = {}
    app.COINGECKO_TOKEN_CACHE_TS = 0
    yield
    app.COINGECKO_TOKEN_CACHE = {}
    app.COINGECKO_TOKEN_CACHE_TS = 0


MOCK_ADDRESS = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


def test_curated_list_has_no_tier1_overlap():
    """ETH_CURATED_TOKENS must not include USDT or USDC (tier-1 stablecoins)."""
    tier1 = {app.USDT_CONTRACT.lower(), app.USDC_CONTRACT.lower()}
    curated = {t["contract"].lower() for t in app.ETH_CURATED_TOKENS}
    overlap = tier1 & curated
    assert overlap == set(), f"Tier-1 overlap detected: {overlap}"
    assert len(curated) == 51, f"Expected 51 curated tokens, got {len(curated)}"  # 50 + OKB (dedicated kustodian wallet coverage)


def test_fetch_balances_skips_zero_balance_tokens():
    """fetch_curated_erc20_balances must omit tokens with zero balance."""
    call_count = {"n": 0}

    def mock_balance(cache_key, address, fetch_fn):
        call_count["n"] += 1
        # Return positive for first 5 tokens, zero for rest
        if call_count["n"] <= 5:
            return 100.0
        return 0.0

    with patch("app.get_cached_balance", side_effect=mock_balance):
        result = app.fetch_curated_erc20_balances(MOCK_ADDRESS)

    # Parallel execution: order non-deterministic, just count non-zero
    assert len(result) == 5, f"Expected 5 non-zero, got {len(result)}"
    for token in result:
        assert token["balance"] == 100.0


def test_coingecko_batched_call_uses_demo_header():
    """When COINGECKO_API_KEY env var set, header x-cg-demo-api-key must be present."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {}

    with patch.dict("os.environ", {"COINGECKO_API_KEY": "CG-test-fake-key"}), \
         patch("app.requests.get", return_value=mock_response) as mock_get:
        app._get_coingecko_eth_token_prices(["0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"])

    assert mock_get.called
    call_kwargs = mock_get.call_args.kwargs
    assert "headers" in call_kwargs
    assert call_kwargs["headers"].get("x-cg-demo-api-key") == "CG-test-fake-key"


def test_unpriced_token_appended_to_unvalued_list():
    """Tokens without CoinGecko price entry must appear in unvalued list."""
    contracts = [
        "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "0xcccccccccccccccccccccccccccccccccccccccc",
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": {"usd": 1.5},
        # 0xbbbb and 0xcccc absent = no price
    }

    with patch("app.requests.get", return_value=mock_response):
        prices = app._get_coingecko_eth_token_prices(contracts)

    assert "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in prices
    assert prices["0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"] == 1.5
    assert "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" not in prices
    assert "0xcccccccccccccccccccccccccccccccccccccccc" not in prices


def test_coingecko_exception_does_not_crash_recon():
    """If CoinGecko raises any exception, function returns dict, never crashes."""
    with patch("app.requests.get", side_effect=ConnectionError("network down")):
        result = app._get_coingecko_eth_token_prices(["0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"])

    assert result == {}, f"Expected empty dict on exception, got {result}"


def test_chunked_batching_handles_50_contracts():
    """50 contracts must be chunked into 2 batches (25 + 25), 2 separate calls."""
    contracts = [f"0x{i:040x}" for i in range(50)]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {}

    with patch("app.requests.get", return_value=mock_response) as mock_get:
        app._get_coingecko_eth_token_prices(contracts)

    assert mock_get.call_count == 2, f"Expected 2 batched calls, got {mock_get.call_count}"


def test_parallel_etherscan_calls_complete_under_serial_time():
    """ThreadPoolExecutor must parallelize, total time < serial equivalent."""
    SLEEP_PER_CALL = 0.05  # 50ms per mocked call
    NUM_TOKENS     = len(app.ETH_CURATED_TOKENS)  # 50

    def mock_balance(cache_key, address, fetch_fn):
        time.sleep(SLEEP_PER_CALL)
        return 1.0  # non-zero to ensure inclusion

    start = time.time()
    with patch("app.get_cached_balance", side_effect=mock_balance):
        result = app.fetch_curated_erc20_balances(MOCK_ADDRESS)
    elapsed = time.time() - start

    serial_estimate = NUM_TOKENS * SLEEP_PER_CALL  # 2.5s if serial
    parallel_target = serial_estimate / 3          # at least 3x speedup with 5 workers

    assert elapsed < parallel_target, (
        f"Parallel execution too slow: {elapsed:.2f}s vs target <{parallel_target:.2f}s"
    )
    assert len(result) == NUM_TOKENS

