"""
test_day9_frontend_bridge.py
Day 9 — Frontend Bridge Tests

Verifies that backend API response shapes match what the frontend needs
to display SPL token breakdowns and stress test sol_stressed data.

Coverage:
  [F1] /api/reconciliation — SOL wallet returns sol_usdt_idr, sol_usdc_idr,
       sol_native_idr with non-zero values
  [F2] aset_onchain_idr for SOL PAKD > sol_native_idr alone (SPL counted)
  [F3] /api/stress-test — sol_stressed present in mild, moderate, severe
  [F4] /api/status — versi == "1.7-multichain-full"
  [F5] /api/reconciliation — ETH wallet still returns eth_native_idr,
       eth_usdt_idr, eth_usdc_idr (regression check after frontend edits)

All tests: full mock, no live API calls, no network required.

Run:
    cd prima-backend
    python -m pytest test_day9_frontend_bridge.py -v
"""

import sys
import os
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as prima_app


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

# Stress test routes call get_cached_price("bitcoin", fn) and
# get_cached_price("solana", fn). The naive lambda approach
#   lambda net, fn: {"bitcoin": X, "solana": Y}.get(net, fn())
# evaluates fn() eagerly regardless of whether net is in the dict,
# causing a live network call that fails in Codespaces and sets
# sol_price = 0.0 via the except block in the route.
# This function only calls fn() when net is genuinely not in the table.
_MOCK_PRICE_TABLE = {
    "bitcoin": 1_500_000_000,
    "solana":  2_500_000,        # MOCK_SOL_SPOT — defined below
}

def _mock_get_cached_price(net, fn):
    if net in _MOCK_PRICE_TABLE:
        return _MOCK_PRICE_TABLE[net]
    return fn()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    prima_app.app.config["TESTING"] = True
    with prima_app.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

MOCK_PAKD_SOL = [
    {
        "id":   "PAKD-TEST-SOL",
        "nama": "PT Test Exchange Solana",
        "wallets": [
            {
                "network":     "solana",
                "address":     "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH",
                "verified":    False,
                "verified_at": None,
            }
        ],
        "aset_dilaporkan": 10_000_000_000,
    }
]

MOCK_PAKD_ETH = [
    {
        "id":   "PAKD-TEST-ETH",
        "nama": "PT Test Exchange ETH",
        "wallets": [
            {
                "network":     "ethereum",
                "address":     "0x28C6c06298d514Db089934071355E5743bf21d60",
                "verified":    False,
                "verified_at": None,
            }
        ],
        "aset_dilaporkan": 5_000_000_000,
    }
]

# Solana wallet with significant SPL holdings.
# sol_balance_idr must equal sol_native_idr + sol_usdt_idr + sol_usdc_idr
# 500_000_000 + 7_000_000_000 + 7_500_000_000 = 15_000_000_000 ✓
MOCK_SOL_BALANCE_RESULT = {
    "total_idr":       15_000_000_000,
    "eth_balance_idr": 0,
    "eth_native_idr":  0,
    "eth_usdt_idr":    0,
    "eth_usdc_idr":    0,
    "btc_balance_idr": 0,
    "sol_balance_idr": 15_000_000_000,
    "sol_native_idr":  500_000_000,
    "sol_usdt_idr":    7_000_000_000,
    "sol_usdc_idr":    7_500_000_000,
    "breakdown": [
        {
            "network":          "solana",
            "address":          "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH",
            "balance_native":   30.123,
            "native_unit":      "SOL",
            "balance_idr":      15_000_000_000,
            "eth_native_idr":   None,
            "usdt_balance":     None,
            "usdt_idr":         None,
            "usdc_balance":     None,
            "usdc_idr":         None,
            "sol_native_idr":   500_000_000,
            "sol_usdt_balance": 428_571.428571,
            "sol_usdt_idr":     7_000_000_000,
            "sol_usdc_balance": 459_041.916168,
            "sol_usdc_idr":     7_500_000_000,
            "verified":         False,
            "error":            None,
        }
    ],
}

# ETH wallet with ERC-20 holdings.
# eth_balance_idr must equal eth_native_idr + eth_usdt_idr + eth_usdc_idr
# 3_000_000_000 + 2_500_000_000 + 2_500_000_000 = 8_000_000_000 ✓
MOCK_ETH_BALANCE_RESULT = {
    "total_idr":       8_000_000_000,
    "eth_balance_idr": 8_000_000_000,
    "eth_native_idr":  3_000_000_000,
    "eth_usdt_idr":    2_500_000_000,
    "eth_usdc_idr":    2_500_000_000,
    "btc_balance_idr": 0,
    "sol_balance_idr": 0,
    "sol_native_idr":  0,
    "sol_usdt_idr":    0,
    "sol_usdc_idr":    0,
    "breakdown": [
        {
            "network":          "ethereum",
            "address":          "0x28C6c06298d514Db089934071355E5743bf21d60",
            "balance_native":   0.075,
            "native_unit":      "ETH",
            "balance_idr":      8_000_000_000,
            "eth_native_idr":   3_000_000_000,
            "usdt_balance":     152_905.198,
            "usdt_idr":         2_500_000_000,
            "usdc_balance":     152_905.198,
            "usdc_idr":         2_500_000_000,
            "sol_native_idr":   None,
            "sol_usdt_balance": None,
            "sol_usdt_idr":     None,
            "sol_usdc_balance": None,
            "sol_usdc_idr":     None,
            "verified":         False,
            "error":            None,
        }
    ],
}

# Stress test mock: minimal SOL-only PAKD
MOCK_STRESS_BALANCE = {
    "total_idr":       4_000_000_000,
    "eth_balance_idr": 0,
    "eth_native_idr":  0,
    "eth_usdt_idr":    0,
    "eth_usdc_idr":    0,
    "btc_balance_idr": 0,
    "sol_balance_idr": 4_000_000_000,
    "sol_native_idr":  4_000_000_000,
    "sol_usdt_idr":    0,
    "sol_usdc_idr":    0,
    "breakdown":       [],
}

# SOL spot price used in stress test mocks (IDR per SOL)
MOCK_SOL_SPOT = 2_500_000


# ---------------------------------------------------------------------------
# [F1] SOL reconciliation response has SPL fields with non-zero values
# ---------------------------------------------------------------------------

class TestF1SolReconciliationFields:
    """
    /api/reconciliation must return sol_usdt_idr, sol_usdc_idr, sol_native_idr
    at the PAKD level and at the per-wallet breakdown level.

    Without these fields the frontend cannot render SPL token rows.
    """

    def test_sol_pakd_level_has_spl_fields(self, client):
        with (
            patch("app.load_pakd", return_value=MOCK_PAKD_SOL),
            patch("app.get_total_balance_idr", return_value=MOCK_SOL_BALANCE_RESULT),
            patch("app.write_audit"),
        ):
            resp = client.get("/api/reconciliation")
        assert resp.status_code == 200
        data = resp.get_json()["data"][0]
        for field in ("sol_usdt_idr", "sol_usdc_idr", "sol_native_idr"):
            assert field in data, f"[F1] '{field}' missing from /api/reconciliation PAKD object"

    def test_sol_spl_fields_nonzero(self, client):
        with (
            patch("app.load_pakd", return_value=MOCK_PAKD_SOL),
            patch("app.get_total_balance_idr", return_value=MOCK_SOL_BALANCE_RESULT),
            patch("app.write_audit"),
        ):
            resp = client.get("/api/reconciliation")
        data = resp.get_json()["data"][0]
        assert data["sol_usdt_idr"]   > 0, "[F1] sol_usdt_idr should be positive"
        assert data["sol_usdc_idr"]   > 0, "[F1] sol_usdc_idr should be positive"
        assert data["sol_native_idr"] > 0, "[F1] sol_native_idr should be positive"

    def test_sol_per_wallet_breakdown_has_spl_fields(self, client):
        """Breakdown per-wallet entry for a Solana wallet must carry SPL sub-fields."""
        with (
            patch("app.load_pakd", return_value=MOCK_PAKD_SOL),
            patch("app.get_total_balance_idr", return_value=MOCK_SOL_BALANCE_RESULT),
            patch("app.write_audit"),
        ):
            resp = client.get("/api/reconciliation")
        breakdown = resp.get_json()["data"][0]["breakdown"]
        sol_entry = next(e for e in breakdown if e["network"] == "solana")
        assert sol_entry["sol_native_idr"]   is not None, "[F1] sol_native_idr None in breakdown"
        assert sol_entry["sol_usdt_balance"] is not None, "[F1] sol_usdt_balance None in breakdown"
        assert sol_entry["sol_usdt_idr"]     is not None, "[F1] sol_usdt_idr None in breakdown"
        assert sol_entry["sol_usdc_balance"] is not None, "[F1] sol_usdc_balance None in breakdown"
        assert sol_entry["sol_usdc_idr"]     is not None, "[F1] sol_usdc_idr None in breakdown"


# ---------------------------------------------------------------------------
# [F2] aset_onchain_idr includes SPL when SOL wallet has SPL > 0
# ---------------------------------------------------------------------------

class TestF2SolOnchainIncludesSPL:
    """
    aset_onchain_idr for a Solana PAKD must exceed sol_native_idr alone
    by at least the combined value of sol_usdt_idr + sol_usdc_idr.

    A PAKD holding 100M USDC on Solana must not appear as if it holds
    only its native SOL position. This is the core undercounting risk
    that frontend integration is meant to surface.
    """

    def test_aset_onchain_exceeds_native_sol(self, client):
        with (
            patch("app.load_pakd", return_value=MOCK_PAKD_SOL),
            patch("app.get_total_balance_idr", return_value=MOCK_SOL_BALANCE_RESULT),
            patch("app.write_audit"),
        ):
            resp = client.get("/api/reconciliation")
        data    = resp.get_json()["data"][0]
        spl_sum = data["sol_usdt_idr"] + data["sol_usdc_idr"]
        assert data["aset_onchain_idr"] >= data["sol_native_idr"] + spl_sum, (
            "[F2] aset_onchain_idr does not include SPL token value — "
            f"onchain={data['aset_onchain_idr']}, native={data['sol_native_idr']}, "
            f"spl_sum={spl_sum}"
        )

    def test_sol_balance_idr_equals_native_plus_spl(self, client):
        """
        sol_balance_idr at the PAKD level must equal
        sol_native_idr + sol_usdt_idr + sol_usdc_idr.

        If this invariant breaks, the frontend total will diverge from
        the component sum, which is a reconciliation logic error.
        """
        with (
            patch("app.load_pakd", return_value=MOCK_PAKD_SOL),
            patch("app.get_total_balance_idr", return_value=MOCK_SOL_BALANCE_RESULT),
            patch("app.write_audit"),
        ):
            resp = client.get("/api/reconciliation")
        data     = resp.get_json()["data"][0]
        expected = data["sol_native_idr"] + data["sol_usdt_idr"] + data["sol_usdc_idr"]
        assert data["sol_balance_idr"] == expected, (
            f"[F2] sol_balance_idr {data['sol_balance_idr']} != "
            f"native+usdt+usdc {expected}"
        )


# ---------------------------------------------------------------------------
# [F3] Stress test response includes sol_stressed in all three scenarios
# ---------------------------------------------------------------------------

class TestF3StressTestSolStressed:
    """
    /api/stress-test must return sol_stressed in each scenario dict.
    Field added in Hari 8 but not yet read by frontend stress-test panel.
    These tests confirm the backend contract before the frontend render work.
    """

    # Reusable patch context for stress test routes
    @staticmethod
    def _stress_patches():
        return [
            patch("app.get_eth_price_idr",         return_value=(40_000_000, False)),
            patch("app.get_cached_price",           side_effect=lambda net, fn: {
                "bitcoin": 1_500_000_000,
                "solana":  MOCK_SOL_SPOT,
            }.get(net, fn())),
            patch("app._get_stablecoin_prices_idr", return_value=(16_350.0, 16_350.0)),
            patch("app.load_pakd",                  return_value=MOCK_PAKD_SOL),
            patch("app.get_total_balance_idr",      return_value=MOCK_STRESS_BALANCE),
            patch("app.write_audit"),
        ]

    def test_sol_stressed_present_in_all_scenarios(self, client):
        with (
            patch("app.get_eth_price_idr",         return_value=(40_000_000, False)),
            patch("app.get_cached_price",           side_effect=_mock_get_cached_price),
            patch("app._get_stablecoin_prices_idr", return_value=(16_350.0, 16_350.0)),
            patch("app.load_pakd",                  return_value=MOCK_PAKD_SOL),
            patch("app.get_total_balance_idr",      return_value=MOCK_STRESS_BALANCE),
            patch("app.write_audit"),
        ):
            resp = client.get("/api/stress-test")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        for scenario in ("mild", "moderate", "severe"):
            assert scenario in data, f"[F3] Scenario '{scenario}' missing from stress-test response"
            assert "sol_stressed" in data[scenario], (
                f"[F3] sol_stressed missing from stress-test response for scenario '{scenario}'"
            )

    def test_sol_stressed_ordering_mild_gt_moderate_gt_severe(self, client):
        """
        Stressed SOL price must degrade strictly: mild > moderate > severe.
        Volatile drops: -30% / -55% / -80%.
        spot=2_500_000 → mild=1_750_000 / moderate=1_125_000 / severe=500_000
        """
        with (
            patch("app.get_eth_price_idr",         return_value=(40_000_000, False)),
            patch("app.get_cached_price",           side_effect=_mock_get_cached_price),
            patch("app._get_stablecoin_prices_idr", return_value=(16_350.0, 16_350.0)),
            patch("app.load_pakd",                  return_value=MOCK_PAKD_SOL),
            patch("app.get_total_balance_idr",      return_value=MOCK_STRESS_BALANCE),
            patch("app.write_audit"),
        ):
            resp = client.get("/api/stress-test")
        scenarios = resp.get_json()["data"]
        mild_val     = scenarios["mild"]["sol_stressed"]
        moderate_val = scenarios["moderate"]["sol_stressed"]
        severe_val   = scenarios["severe"]["sol_stressed"]
        assert mild_val > moderate_val > severe_val, (
            f"[F3] sol_stressed ordering wrong: "
            f"mild={mild_val}, moderate={moderate_val}, severe={severe_val}"
        )

    def test_sol_stressed_mild_matches_30pct_drop(self, client):
        """
        Mild scenario: volatile_drop=0.30, so sol_stressed = round(spot * 0.70).
        spot=2_500_000 → expected=1_750_000
        """
        with (
            patch("app.get_eth_price_idr",         return_value=(40_000_000, False)),
            patch("app.get_cached_price",           side_effect=_mock_get_cached_price),
            patch("app._get_stablecoin_prices_idr", return_value=(16_350.0, 16_350.0)),
            patch("app.load_pakd",                  return_value=MOCK_PAKD_SOL),
            patch("app.get_total_balance_idr",      return_value=MOCK_STRESS_BALANCE),
            patch("app.write_audit"),
        ):
            resp = client.get("/api/stress-test")
        mild_sol  = resp.get_json()["data"]["mild"]["sol_stressed"]
        expected  = round(MOCK_SOL_SPOT * 0.70)
        assert mild_sol == expected, (
            f"[F3] mild sol_stressed expected {expected}, got {mild_sol}"
        )


# ---------------------------------------------------------------------------
# [F4] /api/status returns correct version string
# ---------------------------------------------------------------------------

class TestF4StatusVersion:
    def test_version_string_is_current(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("versi") == "1.7-multichain-full", (
            f"[F4] Expected versi='1.7-multichain-full', got '{data.get('versi')}'"
        )

    def test_status_fields_complete(self, client):
        resp = client.get("/api/status")
        data = resp.get_json()
        assert data.get("status") == "ok",    "[F4] status field should be 'ok'"
        assert data.get("sistem") == "PRIMA", "[F4] sistem field should be 'PRIMA'"


# ---------------------------------------------------------------------------
# [F5] ETH wallet breakdown fields regression check
# ---------------------------------------------------------------------------

class TestF5EthRegressionCheck:
    """
    After any frontend JS edits, /api/reconciliation must still return
    eth_native_idr, eth_usdt_idr, eth_usdc_idr at both the PAKD level
    and per-wallet breakdown level.

    These tests exist because frontend edits to add SPL rendering
    could accidentally break the ETH render path via shared code.
    """

    def test_eth_pakd_level_has_all_erc20_fields(self, client):
        with (
            patch("app.load_pakd", return_value=MOCK_PAKD_ETH),
            patch("app.get_total_balance_idr", return_value=MOCK_ETH_BALANCE_RESULT),
            patch("app.write_audit"),
        ):
            resp = client.get("/api/reconciliation")
        assert resp.status_code == 200
        data = resp.get_json()["data"][0]
        for field in ("eth_native_idr", "eth_usdt_idr", "eth_usdc_idr"):
            assert field in data, f"[F5] '{field}' missing from /api/reconciliation ETH PAKD"

    def test_eth_erc20_fields_nonzero(self, client):
        with (
            patch("app.load_pakd", return_value=MOCK_PAKD_ETH),
            patch("app.get_total_balance_idr", return_value=MOCK_ETH_BALANCE_RESULT),
            patch("app.write_audit"),
        ):
            resp = client.get("/api/reconciliation")
        data = resp.get_json()["data"][0]
        assert data["eth_native_idr"] > 0, "[F5] eth_native_idr should be positive"
        assert data["eth_usdt_idr"]   > 0, "[F5] eth_usdt_idr should be positive"
        assert data["eth_usdc_idr"]   > 0, "[F5] eth_usdc_idr should be positive"

    def test_eth_per_wallet_breakdown_has_erc20_fields(self, client):
        """Per-wallet breakdown entry for Ethereum must include ERC-20 sub-fields."""
        with (
            patch("app.load_pakd", return_value=MOCK_PAKD_ETH),
            patch("app.get_total_balance_idr", return_value=MOCK_ETH_BALANCE_RESULT),
            patch("app.write_audit"),
        ):
            resp = client.get("/api/reconciliation")
        breakdown = resp.get_json()["data"][0]["breakdown"]
        eth_entry = next(e for e in breakdown if e["network"] == "ethereum")
        assert eth_entry["eth_native_idr"] is not None, "[F5] eth_native_idr None in breakdown"
        assert eth_entry["usdt_balance"]   is not None, "[F5] usdt_balance None in breakdown"
        assert eth_entry["usdt_idr"]       is not None, "[F5] usdt_idr None in breakdown"
        assert eth_entry["usdc_balance"]   is not None, "[F5] usdc_balance None in breakdown"
        assert eth_entry["usdc_idr"]       is not None, "[F5] usdc_idr None in breakdown"

    def test_eth_balance_idr_equals_native_plus_erc20(self, client):
        """
        eth_balance_idr at PAKD level must equal
        eth_native_idr + eth_usdt_idr + eth_usdc_idr.
        Same invariant as [F2] for ETH.
        """
        with (
            patch("app.load_pakd", return_value=MOCK_PAKD_ETH),
            patch("app.get_total_balance_idr", return_value=MOCK_ETH_BALANCE_RESULT),
            patch("app.write_audit"),
        ):
            resp = client.get("/api/reconciliation")
        data     = resp.get_json()["data"][0]
        expected = data["eth_native_idr"] + data["eth_usdt_idr"] + data["eth_usdc_idr"]
        assert data["eth_balance_idr"] == expected, (
            f"[F5] eth_balance_idr {data['eth_balance_idr']} != "
            f"native+usdt+usdc {expected}"
        )


# ---------------------------------------------------------------------------
# Entry point guard (required — see Day 9 Task 1 pattern)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v"],
        capture_output=False,
    )
    sys.exit(result.returncode)
