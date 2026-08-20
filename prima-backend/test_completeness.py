"""T2.1 -- tes kelengkapan data portofolio.

Deterministik: AS_OF konstan, tidak ada datetime.now(), tidak ada
panggilan API. Bentuk entry mengikuti literal dict di app.py:1566.
"""

from core.completeness import hitung_kelengkapan

AS_OF = "2026-08-18T00:00:00Z"


def _w(network, address, native=1.0, error=None):
    """Satu entry wallet.

    Wallet yang error TIDAK memiliki kunci balance_native sama sekali:
    jalur exception di app.py (1551/1584/1700) tidak pernah menyetelnya.
    """
    if error is not None:
        return {"network": network, "address": address, "error": error}
    return {
        "network": network,
        "address": address,
        "balance_native": native,
        "error": None,
    }


def _p(sumber, umur=0):
    return {"nilai": 1.0, "sumber": sumber, "as_of": AS_OF, "umur_detik": umur}


def _prov_sehat():
    return {
        "ethereum": _p("cmc"),
        "bitcoin": _p("cmc"),
        "solana": _p("cmc"),
    }


def _entries_sehat():
    return [
        _w("ethereum", "0xeth"),
        _w("bitcoin", "bc1btc"),
        _w("solana", "SoLsol"),
    ]


# ---------------------------------------------------------------- HIJAU

def test_G1_semua_sehat_lengkap():
    hasil = hitung_kelengkapan(_entries_sehat(), _prov_sehat(), AS_OF)
    assert hasil["status"] == "LENGKAP", hasil
    assert hasil["sumber_gagal"] == [], hasil


def test_G2_satu_wallet_error():
    entries = [
        _w("ethereum", "0xeth"),
        _w("bitcoin", "bc1btc", error="BTC fetch error: timeout"),
        _w("solana", "SoLsol"),
    ]
    hasil = hitung_kelengkapan(entries, _prov_sehat(), AS_OF)
    assert hasil["status"] == "SEBAGIAN", hasil
    assert len(hasil["sumber_gagal"]) == 1, hasil
    assert hasil["sumber_gagal"][0]["jenis"] == "saldo", hasil
    assert hasil["sumber_gagal"][0]["address"] == "bc1btc", hasil


def test_G3_harga_eth_hardcoded():
    prov = _prov_sehat()
    prov["ethereum"] = _p("hardcoded")
    hasil = hitung_kelengkapan(_entries_sehat(), prov, AS_OF)
    assert hasil["status"] == "SEBAGIAN", hasil
    harga = [s for s in hasil["sumber_gagal"] if s["jenis"] == "harga"]
    assert [s["network"] for s in harga] == ["ethereum"], hasil


def test_G4_cache_muda_masih_lengkap():
    prov = _prov_sehat()
    prov["ethereum"] = _p("cache", umur=400)
    hasil = hitung_kelengkapan(_entries_sehat(), prov, AS_OF)
    assert hasil["status"] == "LENGKAP", hasil


def test_G5_cache_basi_jadi_sebagian():
    prov = _prov_sehat()
    prov["ethereum"] = _p("cache", umur=1200)
    hasil = hitung_kelengkapan(_entries_sehat(), prov, AS_OF)
    assert hasil["status"] == "SEBAGIAN", hasil


def test_G6_provenance_none_tidak_melempar():
    prov = _prov_sehat()
    prov["bitcoin"] = None
    entries = [_w("bitcoin", "bc1btc", native=0.5)]
    hasil = hitung_kelengkapan(entries, prov, AS_OF)
    assert hasil["status"] == "SEBAGIAN", hasil
    harga = [s for s in hasil["sumber_gagal"] if s["jenis"] == "harga"]
    assert [s["network"] for s in harga] == ["bitcoin"], hasil


def test_G7_as_of_diteruskan_apa_adanya():
    hasil = hitung_kelengkapan(_entries_sehat(), _prov_sehat(), AS_OF)
    assert hasil["as_of"] == AS_OF, hasil


def test_G8_provenance_objek_sama_tidak_disalin():
    prov = _prov_sehat()
    hasil = hitung_kelengkapan(_entries_sehat(), prov, AS_OF)
    assert hasil["provenance_harga"] is prov, hasil
    assert prov == _prov_sehat(), prov


# ----------------------------------------------------------------- MERAH

def test_R1_entries_kosong_tidak_tersedia():
    hasil = hitung_kelengkapan([], _prov_sehat(), AS_OF)
    assert hasil["status"] == "TIDAK_TERSEDIA", hasil


def test_R2_semua_wallet_error_tidak_tersedia():
    entries = [
        _w("ethereum", "0xeth", error="ETH fetch error: boom"),
        _w("bitcoin", "bc1btc", error="BTC fetch error: boom"),
        _w("solana", "SoLsol", error="SOL fetch error: boom"),
    ]
    hasil = hitung_kelengkapan(entries, _prov_sehat(), AS_OF)
    assert hasil["status"] == "TIDAK_TERSEDIA", hasil


def test_R3_kunci_harga_hilang_untuk_aset_yang_dipegang():
    prov = {"ethereum": _p("cmc")}
    entries = [_w("bitcoin", "bc1btc", native=0.5)]
    hasil = hitung_kelengkapan(entries, prov, AS_OF)
    assert hasil["status"] == "SEBAGIAN", hasil
    harga = [s for s in hasil["sumber_gagal"] if s["jenis"] == "harga"]
    assert [s["network"] for s in harga] == ["bitcoin"], hasil


def test_R4_harga_solana_none_tapi_tidak_memegang_sol():
    prov = _prov_sehat()
    prov["solana"] = None
    entries = [_w("ethereum", "0xeth", native=2.0)]
    hasil = hitung_kelengkapan(entries, prov, AS_OF)
    assert hasil["status"] == "LENGKAP", hasil


def test_R5_saldo_nol_tidak_butuh_harga():
    prov = _prov_sehat()
    prov["ethereum"] = None
    entries = [_w("ethereum", "0xeth", native=0.0)]
    hasil = hitung_kelengkapan(entries, prov, AS_OF)
    assert hasil["status"] == "LENGKAP", hasil


def test_H1_partial_fetch_status_tanpa_error_dihitung_gagal():
    """Cacat 1: fetch_status partial dengan error None masih harus
    menghasilkan SEBAGIAN. _saldo_gagal saat ini hanya membaca
    e.get("error"), buta terhadap fetch_status. Bentuk entry mengikuti
    jalur partial nyata di app.py (mis. 1640, 1742, 1777): balance_native
    tetap tersetel, error tetap None, hanya fetch_status yang berubah."""
    entries = [
        {
            "network": "ethereum", "address": "0xeth",
            "balance_native": 1.0, "error": None,
            "fetch_status": "partial",
        },
        _w("bitcoin", "bc1btc"),
        _w("solana", "SoLsol"),
    ]
    hasil = hitung_kelengkapan(entries, _prov_sehat(), AS_OF)
    assert hasil["status"] == "SEBAGIAN"
    assert any(sg["jenis"] == "saldo" and sg["network"] == "ethereum"
               for sg in hasil["sumber_gagal"])
