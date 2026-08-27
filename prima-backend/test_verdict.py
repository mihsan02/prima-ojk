"""T2.3/D6 -- tes gerbang verdict. Dua fungsi, dua formula, tidak
disatukan. Lihat docstring core/verdict.py untuk alasan D49."""
from core.verdict import tetapkan_verdict_ternary, tetapkan_verdict_surplus


def test_ternary_lengkap_aman():
    r = tetapkan_verdict_ternary("LENGKAP", 0.0)
    assert r == {"status": "Aman", "deviasi_pct": 0.0}


def test_ternary_lengkap_deviasi_batas_atas():
    r = tetapkan_verdict_ternary("LENGKAP", -20.0)
    assert r["status"] == "Deviasi"


def test_ternary_lengkap_kritis():
    r = tetapkan_verdict_ternary("LENGKAP", -20.01)
    assert r["status"] == "Kritis"


def test_ternary_sebagian_ditahan():
    r = tetapkan_verdict_ternary("SEBAGIAN", -50.0)
    assert r == {"status": "Data Tidak Lengkap", "deviasi_pct": None}


def test_ternary_tidak_tersedia_ditahan():
    r = tetapkan_verdict_ternary("TIDAK_TERSEDIA", 0.0)
    assert r["status"] == "Data Tidak Lengkap"


def test_surplus_lengkap_aman_karena_surplus():
    r = tetapkan_verdict_surplus("LENGKAP", 105, 100, 5.0)
    assert r["status"] == "Aman"
    assert r["surplus"] is True

def test_surplus_lengkap_aman_batas_atas():
    r = tetapkan_verdict_surplus("LENGKAP", 110, 100, 10.0)
    assert r["status"] == "Aman"
    assert r["surplus"] is True

def test_surplus_lengkap_tidak_wajar():
    r = tetapkan_verdict_surplus("LENGKAP", 500000, 10500, 4661.9)
    assert r["status"] == "Surplus Tidak Wajar"
    assert r["surplus"] is True


def test_surplus_lengkap_defisit_di_bawah_ambang_aman():
    r = tetapkan_verdict_surplus("LENGKAP", 99.999, 100, -0.001)
    assert r["status"] == "Aman"
    assert r["surplus"] is False


def test_surplus_lengkap_deviasi():
    r = tetapkan_verdict_surplus("LENGKAP", 90, 100, -10.0)
    assert r["status"] == "Deviasi"


def test_surplus_lengkap_kritis():
    r = tetapkan_verdict_surplus("LENGKAP", 80, 100, -20.0)
    assert r["status"] == "Kritis"


def test_surplus_sebagian_ditahan_surplus_none():
    r = tetapkan_verdict_surplus("SEBAGIAN", 50, 100, -50.0)
    assert r == {"status": "Data Tidak Lengkap", "deviasi_pct": None, "surplus": None}
