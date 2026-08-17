"""T2.1b: provenance untuk harga yang lewat get_cached_price.

Kaskade ETH sudah melaporkan asal-usulnya lewat
get_eth_price_with_provenance(). BTC dan SOL tidak: keduanya melewati
get_cached_price(), yang hanya mengembalikan float telanjang, sehingga
T2.1 tidak punya cara membedakan harga yang baru diambil dari harga
yang duduk di cache.

get_price_with_provenance() memuat logika get_cached_price() apa adanya
dan melaporkan bentuk _provenance() yang sama seperti jalur ETH.
get_cached_price() menyusut menjadi pembungkus yang mengambil "nilai",
sehingga kelima pemanggilnya di app.py tidak perlu tahu apa pun.

Yang sengaja TIDAK ditambahkan: nilai hardcoded untuk BTC dan SOL.
fetch_btc_price_idr() dan fetch_sol_price_idr() memanggil
raise_for_status(), dan lemparan itu harus tetap naik -- harga yang
salah lebih berbahaya bagi rekonsiliasi daripada harga yang absen.

PRICE_CACHE dibersihkan di setUp tiap kasus.
"""

import time
import unittest

import core.pricing as pricing

UMUR_CACHE_HIT = 120        # < PRICE_TTL (300)
NILAI_CACHE = 1_600_000_000.0
NILAI_LIVE = 1_650_000_000.0


class TestGetPriceWithProvenance(unittest.TestCase):

    def setUp(self):
        pricing.PRICE_CACHE.clear()
        self.addCleanup(pricing.PRICE_CACHE.clear)

    def test_cache_hit_120_detik_sumber_cache(self):
        """Entri masih dalam TTL: fetch_fn tidak boleh tersentuh."""
        pricing.PRICE_CACHE["bitcoin"] = (
            time.time() - UMUR_CACHE_HIT, NILAI_CACHE)

        def _fetch_tidak_boleh_dipanggil():
            self.fail("fetch_fn dipanggil padahal cache masih segar")

        prov = pricing.get_price_with_provenance(
            "bitcoin", _fetch_tidak_boleh_dipanggil)

        self.assertEqual(prov["sumber"], "cache", prov)
        self.assertEqual(prov["nilai"], NILAI_CACHE, prov)
        self.assertAlmostEqual(prov["umur_detik"], UMUR_CACHE_HIT,
                               delta=2, msg=prov)

    def test_cache_miss_sumber_live_umur_nol(self):
        panggilan = []

        def _fetch():
            panggilan.append(1)
            return NILAI_LIVE

        prov = pricing.get_price_with_provenance("solana", _fetch)

        self.assertEqual(len(panggilan), 1, "fetch_fn harus dipanggil sekali")
        self.assertEqual(prov["sumber"], "live", prov)
        self.assertEqual(prov["nilai"], NILAI_LIVE, prov)
        self.assertEqual(prov["umur_detik"], 0, prov)

    def test_get_cached_price_tetap_mengembalikan_float(self):
        """Penjaga regresi: tanda tangan dan bentuk return tidak berubah.

        Kelima pemanggil di app.py membongkar float, dan lima berkas tes
        mem-patch app.get_cached_price dengan pengganti berparameter dua.
        Kasus ini harus hijau sebelum maupun sesudah T2.1b.
        """
        hasil = pricing.get_cached_price("bitcoin", lambda: NILAI_LIVE)

        self.assertNotIsInstance(hasil, dict, hasil)
        self.assertIsInstance(hasil, float, hasil)
        self.assertEqual(hasil, NILAI_LIVE)

    def test_exception_fetch_fn_naik_apa_adanya(self):
        """Tidak ada hardcoded BTC/SOL: kegagalan harus terlihat."""
        class GagalHarga(Exception):
            pass

        def _fetch_gagal():
            raise GagalHarga("coingecko 503")

        with self.assertRaises(GagalHarga):
            pricing.get_price_with_provenance("bitcoin", _fetch_gagal)

        self.assertNotIn("bitcoin", pricing.PRICE_CACHE,
                         "kegagalan tidak boleh menulis apa pun ke cache")


if __name__ == "__main__":
    unittest.main()
