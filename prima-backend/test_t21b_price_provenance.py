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

import pathlib
import time
import unittest
from unittest.mock import MagicMock, patch

import core.pricing as pricing

UMUR_CACHE_HIT = 120        # < PRICE_TTL (300)
NILAI_CACHE = 1_600_000_000.0
NILAI_LIVE = 1_650_000_000.0
NILAI_CMC = 1_700_000_000.0
NILAI_COINGECKO = 1_710_000_000.0


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

    def test_cache_miss_fetch_fn_terpanggil_umur_nol(self):
        """fetch_fn polos: dilabeli "coingecko" karena tidak lewat CMC.

        Label itu tidak akurat untuk fetch_fn sembarang -- lihat D23 di
        docstring get_price_with_provenance(). Yang dikunci kasus ini
        adalah fetch_fn benar-benar dipanggil dan umurnya nol.
        """
        panggilan = []

        def _fetch():
            panggilan.append(1)
            return NILAI_LIVE

        prov = pricing.get_price_with_provenance("solana", _fetch)

        self.assertEqual(len(panggilan), 1, "fetch_fn harus dipanggil sekali")
        self.assertEqual(prov["sumber"], "coingecko", prov)
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


class TestSumberTierSebenarnya(unittest.TestCase):
    """Tier yang sebenarnya dipakai, bukan label karangan.

    Sebelum perbaikan ini get_price_with_provenance() melaporkan sumber
    "live", yang tidak dikenal kelengkapan_dari_provenance() dan jatuh ke
    cabang SEBAGIAN terakhirnya. Akibatnya harga BTC/SOL yang baru saja
    berhasil diambil tidak pernah bisa dibaca LENGKAP.

    Perbaikannya menyimpulkan tier dari jejak yang ditinggalkan
    _refresh_price_cache_from_cmc() di PRICE_CACHE, bukan menambah nama
    tier baru ke fungsi pemetaan.
    """

    def setUp(self):
        pricing.PRICE_CACHE.clear()
        pricing._CMC_LIVE_WRITE_AT = None
        self.addCleanup(pricing.PRICE_CACHE.clear)

    def _refresh_cmc_menulis(self):
        """Tiruan _refresh_price_cache_from_cmc() yang berhasil.

        Menulis PRICE_CACHE dan menstempel _CMC_LIVE_WRITE_AT dengan
        stempel yang sama, persis seperti pricing.py:124-135.
        """
        now = time.time()
        pricing._CMC_LIVE_WRITE_AT = now
        pricing.PRICE_CACHE["bitcoin"] = (now, NILAI_CMC)
        return True

    def test_jalur_cmc_dilaporkan_cmc(self):
        with patch("core.pricing._refresh_price_cache_from_cmc",
                   side_effect=self._refresh_cmc_menulis):
            prov = pricing.get_price_with_provenance(
                "bitcoin", pricing.fetch_btc_price_idr)

        self.assertEqual(prov["sumber"], "cmc", prov)
        self.assertEqual(prov["nilai"], NILAI_CMC, prov)

    def test_jalur_coingecko_dilaporkan_coingecko(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"bitcoin": {"idr": NILAI_COINGECKO}}
        resp.raise_for_status.return_value = None

        with patch("core.pricing._refresh_price_cache_from_cmc", return_value=False), \
             patch("core.pricing.requests.get", return_value=resp):
            prov = pricing.get_price_with_provenance(
                "bitcoin", pricing.fetch_btc_price_idr)

        self.assertEqual(prov["sumber"], "coingecko", prov)
        self.assertEqual(prov["nilai"], NILAI_COINGECKO, prov)

    def test_kedua_tier_terbaca_lengkap(self):
        """Regresi: inilah yang rusak sebelum perbaikan.

        kelengkapan_dari_provenance() tidak disentuh. Kedua tier sudah
        dipetakan ke LENGKAP di sana sejak T1.3 -- yang salah selama ini
        hanya nama tier yang dilaporkan kepadanya.
        """
        with patch("core.pricing._refresh_price_cache_from_cmc",
                   side_effect=self._refresh_cmc_menulis):
            prov_cmc = pricing.get_price_with_provenance(
                "bitcoin", pricing.fetch_btc_price_idr)

        pricing.PRICE_CACHE.clear()
        pricing._CMC_LIVE_WRITE_AT = None

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"bitcoin": {"idr": NILAI_COINGECKO}}
        resp.raise_for_status.return_value = None
        with patch("core.pricing._refresh_price_cache_from_cmc", return_value=False), \
             patch("core.pricing.requests.get", return_value=resp):
            prov_cg = pricing.get_price_with_provenance(
                "bitcoin", pricing.fetch_btc_price_idr)

        self.assertEqual(pricing.kelengkapan_dari_provenance(prov_cmc),
                         "LENGKAP", prov_cmc)
        self.assertEqual(pricing.kelengkapan_dari_provenance(prov_cg),
                         "LENGKAP", prov_cg)

    def test_string_live_tidak_tersisa_di_modul(self):
        """Nama tier karangan itu harus hilang, bukan sekadar tak terpakai."""
        sumber_modul = pathlib.Path(pricing.__file__).read_text()

        tersisa = [f"{n}: {baris.strip()}"
                   for n, baris in enumerate(sumber_modul.splitlines(), 1)
                   if '"live"' in baris]

        self.assertEqual(tersisa, [], "string \"live\" masih ada di pricing.py")


if __name__ == "__main__":
    unittest.main()
