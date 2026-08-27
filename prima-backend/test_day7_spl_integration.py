"""
test_day7_spl_integration.py — Day 7 (2 Mei 2026)
SPL USDT+USDC integration tests for get_total_balance_idr.

KOREKSI 20 Agustus 2026, sesi kesebelas: "All tests fully mocked" TIDAK
BENAR. Diverifikasi dengan menjalankan tiap tes terisolasi
(--durations=0). Enam dari delapan menembus jaringan live saat berdiri
sendiri -- durasi 12-27 detik per tes, konsisten dengan panggilan RPC
Solana dan API harga sungguhan, bukan mock:

    I1, I2, I4, I6, I7, I8  -- LIVE. Hanya me-mock get_cached_balance,
        tidak menggerbangi fetch_all_spl_balances /
        _get_jupiter_verified_set / _get_jupiter_prices /
        _get_dexscreener_price seperti yang dilakukan I3 (lihat
        catatan D43 di dalam test_I3).
    I3   -- fully mocked, sesuai desain (D43).
    I5   -- fully mocked secara kebetulan: ETH_WALLET tidak pernah
        memasuki cabang enumerasi SPL, bukan karena di-mock eksplisit.

TEMUAN KEDUA, di luar cakupan klaim docstring: I4, I6, I7, I8 tampak
cepat (<2 detik) ketika dijalankan dalam satu sesi pytest bersama
I1-I3, tapi melambat ke kelas 12-27 detik ketika dijalankan terisolasi.
Penyebabnya BALANCE_CACHE, dict modul-level, tidak dibersihkan antar
tes kecuali oleh satu `pop()` eksplisit di dalam test_I3 sendiri
(baris terpisah, hanya menggerbangi tes itu). Tes-tes lain diam-diam
menumpang hasil cache yang ditinggalkan tes sebelumnya dalam urutan
file yang sama. Ini bug independen dari klaim "fully mocked": hasil
tes bergantung pada urutan eksekusi, bukan cuma pada isolasi jaringan.
Belum ditambal di sini -- lihat defect terpisah di register.
"""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(__file__))
from unittest.mock import patch
import app as prima_app

MOCK_SOL_PRICE  = 2_500_000
MOCK_USDT_PRICE = 16_350
MOCK_USDC_PRICE = 16_340
MOCK_ETH_PRICE  = 40_000_000

SOL_WALLET = {"network": "solana",   "address": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"}
ETH_WALLET = {"network": "ethereum", "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"}

def _sol_router(cache_key, address, fetch_fn):
    if cache_key == "solana":       return 5.0
    if cache_key == "sol_usdt_spl": return 1_000.0
    if cache_key == "sol_usdc_spl": return 500.0
    return 0.0

def test_I1_usdt_spl_cache_key_called():
    with patch("app.get_cached_balance", side_effect=lambda k,a,f: 0.0) as m:
        prima_app.get_total_balance_idr([SOL_WALLET],
            sol_price_idr=MOCK_SOL_PRICE,
            usdt_price_idr=MOCK_USDT_PRICE,
            usdc_price_idr=MOCK_USDC_PRICE)
        keys = [c.args[0] for c in m.call_args_list]
        assert "sol_usdt_spl" in keys, f"sol_usdt_spl not in {keys}"

def test_I2_usdc_spl_cache_key_called():
    with patch("app.get_cached_balance", side_effect=lambda k,a,f: 0.0) as m:
        prima_app.get_total_balance_idr([SOL_WALLET],
            sol_price_idr=MOCK_SOL_PRICE,
            usdt_price_idr=MOCK_USDT_PRICE,
            usdc_price_idr=MOCK_USDC_PRICE)
        keys = [c.args[0] for c in m.call_args_list]
        assert "sol_usdc_spl" in keys, f"sol_usdc_spl not in {keys}"

def test_I3_spl_contributes_to_total_idr():
    # D43: fetch_all_spl_balances, _get_jupiter_verified_set,
    # _get_jupiter_prices, dan _get_dexscreener_price semuanya live-reachable
    # dari jalur "other SPL token" untuk SOL_WALLET (alamat mainnet
    # sungguhan). get_cached_balance patch di bawah TIDAK menggerbangi
    # keempatnya. Di-mock eksplisit di sini supaya test benar-benar
    # deterministik, bukan bergantung holding on-chain hari ini.
    prima_app.BALANCE_CACHE.pop(("spl_enum", SOL_WALLET["address"]), None)
    SYNTH_MINT = "MOCKtoken1111111111111111111111111111111"
    SYNTH_UI_AMOUNT = 10.0
    SYNTH_JUPITER_PRICE_USD = 2.5
    with patch("app.get_cached_balance", side_effect=_sol_router), \
         patch("app.fetch_all_spl_balances",
               return_value=[{"mint": SYNTH_MINT, "ui_amount": SYNTH_UI_AMOUNT}]), \
         patch("app._get_jupiter_verified_set", return_value=set()), \
         patch("app._get_jupiter_prices",
               return_value={SYNTH_MINT: SYNTH_JUPITER_PRICE_USD}), \
         patch("app._get_dexscreener_price", return_value=None) as mock_dex:
        result = prima_app.get_total_balance_idr([SOL_WALLET],
            sol_price_idr=MOCK_SOL_PRICE,
            eth_price_idr=MOCK_ETH_PRICE,
            usdt_price_idr=MOCK_USDT_PRICE,
            usdc_price_idr=MOCK_USDC_PRICE)
        mock_dex.assert_not_called()
    other_token_idr = SYNTH_UI_AMOUNT * SYNTH_JUPITER_PRICE_USD * MOCK_USDT_PRICE
    expected = (5.0*MOCK_SOL_PRICE + 1_000.0*MOCK_USDT_PRICE
                + 500.0*MOCK_USDC_PRICE + other_token_idr)
    assert result["total_idr"] == pytest.approx(expected, rel=1e-6)

def test_I4_sol_spl_idr_fields_nonzero():
    with patch("app.get_cached_balance", side_effect=_sol_router):
        result = prima_app.get_total_balance_idr([SOL_WALLET],
            sol_price_idr=MOCK_SOL_PRICE,
            usdt_price_idr=MOCK_USDT_PRICE,
            usdc_price_idr=MOCK_USDC_PRICE)
    assert "sol_usdt_idr" in result
    assert "sol_usdc_idr" in result
    assert result["sol_usdt_idr"] > 0
    assert result["sol_usdc_idr"] > 0

def test_I5_eth_branch_regression():
    def eth_router(k, a, f):
        return 2.5 if k == "ethereum" else 0.0
    with patch("app.get_cached_balance", side_effect=eth_router):
        result = prima_app.get_total_balance_idr([ETH_WALLET],
            eth_price_idr=MOCK_ETH_PRICE,
            usdt_price_idr=MOCK_USDT_PRICE,
            usdc_price_idr=MOCK_USDC_PRICE)
    assert result["eth_native_idr"] == pytest.approx(2.5*MOCK_ETH_PRICE, rel=1e-6)
    assert result["sol_usdt_idr"] == 0
    assert result["sol_usdc_idr"] == 0

def test_I6_zero_spl_no_crash():
    with patch("app.get_cached_balance", side_effect=lambda k,a,f: 0.0):
        result = prima_app.get_total_balance_idr([SOL_WALLET],
            sol_price_idr=MOCK_SOL_PRICE,
            usdt_price_idr=MOCK_USDT_PRICE,
            usdc_price_idr=MOCK_USDC_PRICE)
    assert result["sol_usdt_idr"] == 0
    assert result["sol_usdc_idr"] == 0
    assert result["breakdown"][0]["error"] is None

def test_I7_reconciliation_exposes_sol_spl_fields():
    mock_pakd = [{"id": "TEST-001", "nama": "Test", "wallets": [SOL_WALLET], "aset_dilaporkan": 50_000_000}]
    with patch("app.load_pakd", return_value=mock_pakd), \
         patch("app.get_cached_balance", side_effect=_sol_router), \
         patch("app.write_audit"), \
         patch("app._get_db_conn", return_value=None), \
         patch("auth.get_current_user", return_value={"id": "test", "role": "super_admin", "display_name": "Test", "entity_id": None, "entity_type": None}):
        resp = prima_app.app.test_client().get("/api/reconciliation")
    assert resp.status_code == 200
    entry = resp.get_json()["data"][0]
    assert "sol_usdt_idr" in entry
    assert "sol_usdc_idr" in entry
    assert entry["sol_usdt_idr"] > 0

def test_I8_stressed_price_bypasses_live_fetch():
    stressed_usdt = MOCK_USDT_PRICE * 0.85
    def router(k, a, f):
        if k == "solana":       return 5.0
        if k == "sol_usdt_spl": return 1_000.0
        return 0.0
    with patch("app.get_cached_balance", side_effect=router), \
         patch("core.pricing._get_stablecoin_prices_idr") as mock_fn:
        result = prima_app.get_total_balance_idr([SOL_WALLET],
            sol_price_idr=MOCK_SOL_PRICE,
            eth_price_idr=MOCK_ETH_PRICE,
            usdt_price_idr=stressed_usdt,
            usdc_price_idr=MOCK_USDC_PRICE)
    mock_fn.assert_not_called()
    assert result["sol_usdt_idr"] == pytest.approx(round(1_000.0 * stressed_usdt), abs=1)