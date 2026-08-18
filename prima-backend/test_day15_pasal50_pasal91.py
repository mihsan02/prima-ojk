"""
test_day15_pasal50_pasal91.py — Day 15
Dual stress test: Pasal 50 (Risiko Pasar) + Pasal 91 (Risiko Siber).

Regulatory anchor:
  Pasal 50(1)(o) POJK No. 27 Tahun 2024 — ekuitas minimum Rp 50.000.000.000
  Pasal 91(1)    POJK No. 27 Tahun 2024 — tanggung jawab kehilangan AKD Konsumen

Coverage:
  [P1] Response has pasal50 + pasal91 keys, threshold_ref present
  [P2] pasal50 mild sol_stressed = round(spot * 0.75)  [drop -25%]
  [P3] pasal50 sol_stressed ordering: mild > moderate > severe
  [P4] pasal50 per_pakd entries have required fields
  [P5] pasal91 severe: equity_post = 0 when loss=100% and equity_idr=None
  [P6] /api/input-manual accepts 4 new optional fields without error

All tests fully mocked — no live network calls.

Run:
    cd prima-backend
    python -m pytest test_day15_pasal50_pasal91.py -v
"""

import sys
import os
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as prima_app

# ---------------------------------------------------------------------------
# Mock constants
# ---------------------------------------------------------------------------

MOCK_SOL_SPOT   = 2_500_000
MOCK_ETH_SPOT   = 40_000_000
MOCK_BTC_SPOT   = 1_500_000_000
MOCK_USDT_PRICE = 16_350.0
MOCK_USDC_PRICE = 16_340.0

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
    "entries": [
        {
            "network":        "solana",
            "address":        "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH",
            "balance_native": 1600.0,
            "error":          None,
        },
    ],
    "provenance_harga": {
        "solana": {
            "nilai":      MOCK_SOL_SPOT,
            "sumber":     "cmc",
            "as_of":      "2026-08-20T00:00:00Z",
            "umur_detik": 0,
        },
    },
    "breakdown":       [],
}

MOCK_PAKD_SOL = [
    {
        "id":              "PAKD-TEST-SOL",
        "nama":            "PT Test Exchange Solana",
        "wallets":         [{"network": "solana", "address": "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH", "verified": False, "verified_at": None}],
        "aset_dilaporkan": 10_000_000_000,
    }
]

_MOCK_PRICE_TABLE = {"bitcoin": MOCK_BTC_SPOT, "solana": MOCK_SOL_SPOT}

def _mock_get_cached_price(net, fn):
    if net in _MOCK_PRICE_TABLE:
        return _MOCK_PRICE_TABLE[net]
    return fn()

def _stress_patches():
    return [
        patch("app.get_eth_price_idr",         return_value=(MOCK_ETH_SPOT, False)),
        patch("app.get_cached_price",           side_effect=_mock_get_cached_price),
        patch("core.pricing._get_stablecoin_prices_idr", return_value=(MOCK_USDT_PRICE, MOCK_USDC_PRICE)),
        patch("app.load_pakd",                  return_value=MOCK_PAKD_SOL),
        patch("app.get_total_balance_idr",      return_value=MOCK_STRESS_BALANCE),
        patch("app.write_audit"),
    ]


@pytest.fixture
def client():
    import os
    prima_app.app.config["TESTING"] = True
    with prima_app.app.test_client() as c:
        original_open = c.open
        def patched_open(*args, **kwargs):
            headers = dict(kwargs.get('headers') or {})
            headers['X-Admin-Token'] = os.environ.get('ADMIN_TOKEN', 'test-token-prima')
            kwargs['headers'] = headers
            return original_open(*args, **kwargs)
        c.open = patched_open
        yield c


# ---------------------------------------------------------------------------
# [P1] Top-level response structure
# ---------------------------------------------------------------------------

def test_P1_response_structure(client):
    """[P1] Response has pasal50, pasal91, threshold_idr, threshold_ref."""
    with _stress_patches()[0], _stress_patches()[1], _stress_patches()[2], \
         _stress_patches()[3], _stress_patches()[4], _stress_patches()[5]:
        resp = client.get("/api/stress-test")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "pasal50"       in data, "[P1] pasal50 key missing"
    assert "pasal91"       in data, "[P1] pasal91 key missing"
    assert "threshold_idr" in data, "[P1] threshold_idr missing"
    assert "threshold_ref" in data, "[P1] threshold_ref missing"
    assert data["threshold_idr"] == prima_app.EQUITY_MINIMUM_IDR
    assert "Pasal 50" in data["threshold_ref"]


# ---------------------------------------------------------------------------
# [P2] Pasal 50 mild sol_stressed correctness
# ---------------------------------------------------------------------------

def test_P2_pasal50_mild_sol_stressed(client):
    """[P2] Pasal 50 mild drop=-25%, sol_stressed = round(spot * 0.75)."""
    with (
        patch("app.get_eth_price_idr",         return_value=(MOCK_ETH_SPOT, False)),
        patch("app.get_cached_price",           side_effect=_mock_get_cached_price),
        patch("core.pricing._get_stablecoin_prices_idr", return_value=(MOCK_USDT_PRICE, MOCK_USDC_PRICE)),
        patch("app.load_pakd",                  return_value=MOCK_PAKD_SOL),
        patch("app.get_total_balance_idr",      return_value=MOCK_STRESS_BALANCE),
        patch("app.write_audit"),
    ):
        resp = client.get("/api/stress-test")
    mild = resp.get_json()["pasal50"]["mild"]
    expected = round(MOCK_SOL_SPOT * 0.75)
    assert mild["sol_stressed"] == expected, (
        f"[P2] Expected sol_stressed={expected}, got {mild['sol_stressed']}"
    )


# ---------------------------------------------------------------------------
# [P3] Pasal 50 sol_stressed ordering
# ---------------------------------------------------------------------------

def test_P3_pasal50_sol_stressed_ordering(client):
    """[P3] sol_stressed must degrade: mild > moderate > severe."""
    with (
        patch("app.get_eth_price_idr",         return_value=(MOCK_ETH_SPOT, False)),
        patch("app.get_cached_price",           side_effect=_mock_get_cached_price),
        patch("core.pricing._get_stablecoin_prices_idr", return_value=(MOCK_USDT_PRICE, MOCK_USDC_PRICE)),
        patch("app.load_pakd",                  return_value=MOCK_PAKD_SOL),
        patch("app.get_total_balance_idr",      return_value=MOCK_STRESS_BALANCE),
        patch("app.write_audit"),
    ):
        resp = client.get("/api/stress-test")
    p50  = resp.get_json()["pasal50"]
    mild = p50["mild"]["sol_stressed"]
    mod  = p50["moderate"]["sol_stressed"]
    sev  = p50["severe"]["sol_stressed"]
    assert mild > mod > sev, f"[P3] ordering wrong: mild={mild}, mod={mod}, sev={sev}"


# ---------------------------------------------------------------------------
# [P4] Pasal 50 per_pakd fields
# ---------------------------------------------------------------------------

def test_P4_pasal50_per_pakd_fields(client):
    """[P4] Each pasal50 scenario has per_pakd list with required fields."""
    with (
        patch("app.get_eth_price_idr",         return_value=(MOCK_ETH_SPOT, False)),
        patch("app.get_cached_price",           side_effect=_mock_get_cached_price),
        patch("core.pricing._get_stablecoin_prices_idr", return_value=(MOCK_USDT_PRICE, MOCK_USDC_PRICE)),
        patch("app.load_pakd",                  return_value=MOCK_PAKD_SOL),
        patch("app.get_total_balance_idr",      return_value=MOCK_STRESS_BALANCE),
        patch("app.write_audit"),
    ):
        resp = client.get("/api/stress-test")
    p50  = resp.get_json()["pasal50"]
    required = {"id", "nama", "aset_onchain_idr", "aset_stressed",
                "equity_post", "equity_sumber", "threshold", "lulus"}
    for scenario in ("mild", "moderate", "severe"):
        assert "per_pakd" in p50[scenario], f"[P4] per_pakd missing in pasal50[{scenario}]"
        entry = p50[scenario]["per_pakd"][0]
        missing = required - set(entry.keys())
        assert not missing, f"[P4] pasal50[{scenario}] per_pakd missing fields: {missing}"
        assert entry["threshold"] == prima_app.EQUITY_MINIMUM_IDR


# ---------------------------------------------------------------------------
# [P5] Pasal 91 severe: equity_post = 0 with proxy and 100% loss
# ---------------------------------------------------------------------------

def test_P5_pasal91_severe_equity_zero(client):
    """[P5] Severe cyber loss (100%) with no equity_idr → equity_post=0."""
    with (
        patch("app.get_eth_price_idr",         return_value=(MOCK_ETH_SPOT, False)),
        patch("app.get_cached_price",           side_effect=_mock_get_cached_price),
        patch("core.pricing._get_stablecoin_prices_idr", return_value=(MOCK_USDT_PRICE, MOCK_USDC_PRICE)),
        patch("app.load_pakd",                  return_value=MOCK_PAKD_SOL),
        patch("app.get_total_balance_idr",      return_value=MOCK_STRESS_BALANCE),
        patch("app.write_audit"),
    ):
        resp = client.get("/api/stress-test")
    severe_entry = resp.get_json()["pasal91"]["severe"]["per_pakd"][0]
    # 100% loss with proxy: equity_post = aset_onchain - aset_onchain = 0
    assert severe_entry["equity_post"] == 0, (
        f"[P5] Expected equity_post=0 for severe cyber, got {severe_entry['equity_post']}"
    )
    assert severe_entry["lulus"] is False, "[P5] Should fail threshold when equity_post=0"
    assert severe_entry["equity_sumber"] == "proxy_onchain"


# ---------------------------------------------------------------------------
# [P6] /api/input-manual accepts 4 new optional fields
# ---------------------------------------------------------------------------

def test_P6_input_manual_accepts_new_fields(client):
    """[P6] equity_idr, persediaan_akd_idr, simpanan_pedagang_akd_idr, customer_akd_idr accepted."""
    with patch("app.load_pakd", return_value=[]), \
         patch("app.save_pakd"), \
         patch("app.write_audit"):
        resp = client.post("/api/input-manual", json={
            "id":                         "PAKD-TEST-P6",
            "nama":                       "PT Test Pasal 50",
            "wallets":                    [{"network": "ethereum", "address": "0x28C6c06298d514Db089934071355E5743bf21d60"}],
            "aset_dilaporkan":            500_000_000_000,
            "equity_idr":                 150_000_000_000,
            "persediaan_akd_idr":         80_000_000_000,
            "simpanan_pedagang_akd_idr":  20_000_000_000,
            "customer_akd_idr":           250_000_000_000,
        })
    assert resp.status_code == 200, f"[P6] Expected 200, got {resp.status_code}: {resp.get_json()}"
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["equity_idr"]          == 150_000_000_000
    assert data["data"]["customer_akd_idr"]    == 250_000_000_000


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v"],
        capture_output=False,
    )
    sys.exit(result.returncode)


def test_D25b_mock_stress_balance_membawa_kelengkapan_lengkap():
    from core.completeness import hitung_kelengkapan
    entries = MOCK_STRESS_BALANCE.get("entries") or []
    prov    = MOCK_STRESS_BALANCE.get("provenance_harga") or {}
    hasil = hitung_kelengkapan(entries, prov, as_of="2026-08-20T00:00:00Z")
    assert hasil["status"] == "LENGKAP", hasil
    assert "solana" in prov and prov["solana"] is not None, prov
    assert hasil["sumber_gagal"] == [], hasil["sumber_gagal"]
