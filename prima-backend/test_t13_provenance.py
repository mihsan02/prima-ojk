"""T1.3 BAGIAN B (D5): provenance harga dan pemetaannya ke kelengkapan.

get_eth_price_idr() dulu mengembalikan (39_910_503, True) pada kegagalan.
Nilai hardcoded itu tetap ada sebagai tier terakhir -- yang berubah adalah
pemakaiannya kini terlacak, bukan keberadaannya.

Empat baris pemetaan yang ditutup tes ini:

    cmc / coingecko, live      -> LENGKAP
    cache, umur <= 900 detik   -> LENGKAP
    cache, umur >  900 detik   -> SEBAGIAN
    hardcoded                  -> SEBAGIAN, selalu

Ambang 900 detik sengaja jauh di atas PRICE_TTL (300 s): Render free tier
sering cold start, dan aturan biner akan menyalakan DATA TIDAK LENGKAP
pada latensi CMC yang normal.

PRICE_CACHE dibersihkan tiap kasus.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

import core.pricing as pricing

CACHE_400 = 400     # <= 900 -> LENGKAP
CACHE_1200 = 1200   # >  900 -> SEBAGIAN


class TestKelengkapanDariProvenance(unittest.TestCase):
    """Pemetaan murni, tanpa jaringan. Ini yang dibaca T2.1 dan T2.3."""

    # ── dua kasus cache ditulis lebih dulu: paling mudah salah ──
    def test_cache_400_detik_lengkap(self):
        prov = {"nilai": 40_000_000, "sumber": "cache",
                "as_of": "2026-08-17T00:00:00Z", "umur_detik": CACHE_400}
        self.assertEqual(pricing.kelengkapan_dari_provenance(prov), "LENGKAP")

    def test_cache_1200_detik_sebagian(self):
        prov = {"nilai": 40_000_000, "sumber": "cache",
                "as_of": "2026-08-17T00:00:00Z", "umur_detik": CACHE_1200}
        self.assertEqual(pricing.kelengkapan_dari_provenance(prov), "SEBAGIAN")

    def test_cache_tepat_di_ambang_900_masih_lengkap(self):
        """Ambangnya inklusif: <= 900, bukan < 900."""
        prov = {"nilai": 40_000_000, "sumber": "cache",
                "as_of": "2026-08-17T00:00:00Z", "umur_detik": 900}
        self.assertEqual(pricing.kelengkapan_dari_provenance(prov), "LENGKAP")

    def test_cache_901_detik_sudah_sebagian(self):
        prov = {"nilai": 40_000_000, "sumber": "cache",
                "as_of": "2026-08-17T00:00:00Z", "umur_detik": 901}
        self.assertEqual(pricing.kelengkapan_dari_provenance(prov), "SEBAGIAN")

    def test_cmc_live_lengkap(self):
        prov = {"nilai": 40_000_000, "sumber": "cmc",
                "as_of": "2026-08-17T00:00:00Z", "umur_detik": 0}
        self.assertEqual(pricing.kelengkapan_dari_provenance(prov), "LENGKAP")

    def test_coingecko_live_lengkap(self):
        prov = {"nilai": 40_000_000, "sumber": "coingecko",
                "as_of": "2026-08-17T00:00:00Z", "umur_detik": 0}
        self.assertEqual(pricing.kelengkapan_dari_provenance(prov), "LENGKAP")

    def test_hardcoded_selalu_sebagian(self):
        """Umur nol pun tidak menolongnya: hardcoded bukan harga pasar."""
        for umur in (0, 10, 900, 5_000):
            prov = {"nilai": pricing.HARGA_ETH_HARDCODED, "sumber": "hardcoded",
                    "as_of": "2026-08-17T00:00:00Z", "umur_detik": umur}
            self.assertEqual(pricing.kelengkapan_dari_provenance(prov), "SEBAGIAN",
                             "hardcoded dengan umur %s harus SEBAGIAN" % umur)


class TestProvenanceDariKaskade(unittest.TestCase):
    """Tier mana yang menghasilkan nilai, diuji lewat kaskade sungguhan."""

    def setUp(self):
        pricing.PRICE_CACHE.clear()
        pricing._CMC_LIVE_WRITE_AT = None
        self.addCleanup(pricing.PRICE_CACHE.clear)

    def test_cache_dalam_ttl_bukan_tulisan_live_disebut_cache(self):
        """Entri lama yang masih segar: sumber "cache", bukan "cmc"."""
        umur = 120.0
        pricing.PRICE_CACHE["ethereum"] = (time.time() - umur, 41_000_000.0)
        with patch("core.pricing._refresh_price_cache_from_cmc", return_value=True):
            prov = pricing.get_eth_price_with_provenance()

        self.assertEqual(prov["sumber"], "cache")
        self.assertEqual(prov["nilai"], 41_000_000.0)
        self.assertAlmostEqual(prov["umur_detik"], umur, delta=2)
        self.assertEqual(pricing.kelengkapan_dari_provenance(prov), "LENGKAP")

    def test_tulisan_live_cmc_disebut_cmc(self):
        now = time.time()
        pricing.PRICE_CACHE["ethereum"] = (now, 42_000_000.0)
        pricing._CMC_LIVE_WRITE_AT = now
        with patch("core.pricing._refresh_price_cache_from_cmc", return_value=True):
            prov = pricing.get_eth_price_with_provenance()

        self.assertEqual(prov["sumber"], "cmc")
        self.assertEqual(pricing.kelengkapan_dari_provenance(prov), "LENGKAP")

    def test_coingecko_saat_cmc_gagal(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"ethereum": {"idr": 43_000_000}}
        with patch("core.pricing._refresh_price_cache_from_cmc", return_value=False), \
             patch("core.pricing.requests.get", return_value=resp):
            prov = pricing.get_eth_price_with_provenance()

        self.assertEqual(prov["sumber"], "coingecko")
        self.assertEqual(prov["nilai"], 43_000_000)
        self.assertEqual(prov["umur_detik"], 0)
        self.assertEqual(pricing.kelengkapan_dari_provenance(prov), "LENGKAP")

    def test_hardcoded_saat_dua_tier_gagal(self):
        with patch("core.pricing._refresh_price_cache_from_cmc", return_value=False), \
             patch("core.pricing.requests.get", side_effect=Exception("network down")):
            prov = pricing.get_eth_price_with_provenance()

        self.assertEqual(prov["sumber"], "hardcoded")
        self.assertEqual(prov["nilai"], pricing.HARGA_ETH_HARDCODED)
        self.assertEqual(pricing.kelengkapan_dari_provenance(prov), "SEBAGIAN")

    def test_as_of_iso8601_utc(self):
        with patch("core.pricing._refresh_price_cache_from_cmc", return_value=False), \
             patch("core.pricing.requests.get", side_effect=Exception("network down")):
            prov = pricing.get_eth_price_with_provenance()

        self.assertTrue(prov["as_of"].endswith("Z"), prov["as_of"])
        self.assertIn("T", prov["as_of"])


class TestKompatibilitasPemanggilLama(unittest.TestCase):
    """Kelima pemanggil di app.py membongkar tuple 2-elemen."""

    def setUp(self):
        pricing.PRICE_CACHE.clear()
        pricing._CMC_LIVE_WRITE_AT = None
        self.addCleanup(pricing.PRICE_CACHE.clear)

    def test_bentuk_return_tetap_tuple_dua(self):
        with patch("core.pricing._refresh_price_cache_from_cmc", return_value=False), \
             patch("core.pricing.requests.get", side_effect=Exception("down")):
            hasil = pricing.get_eth_price_idr()

        self.assertIsInstance(hasil, tuple)
        self.assertEqual(len(hasil), 2)

    def test_flag_fallback_true_hanya_saat_hardcoded(self):
        with patch("core.pricing._refresh_price_cache_from_cmc", return_value=False), \
             patch("core.pricing.requests.get", side_effect=Exception("down")):
            nilai, fallback = pricing.get_eth_price_idr()
        self.assertEqual(nilai, pricing.HARGA_ETH_HARDCODED)
        self.assertIs(fallback, True)

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"ethereum": {"idr": 43_000_000}}
        with patch("core.pricing._refresh_price_cache_from_cmc", return_value=False), \
             patch("core.pricing.requests.get", return_value=resp):
            nilai, fallback = pricing.get_eth_price_idr()
        self.assertEqual(nilai, 43_000_000)
        self.assertIs(fallback, False)


if __name__ == "__main__":
    unittest.main()
