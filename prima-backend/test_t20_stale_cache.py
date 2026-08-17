"""T2.0: tier stale cache pada get_eth_price_with_provenance().

Sebelum T2.0 kaskade ETH punya tiga tier: CMC, CoinGecko, hardcoded.
Tier 1 hanya mengembalikan entri cache selama (now - cached[0]) < PRICE_TTL
(300 s), dan tidak ada jalur lain yang menghasilkan sumber == "cache".
Akibatnya cabang "cache, umur > 900 -> SEBAGIAN" di
kelengkapan_dari_provenance() tidak bisa dicapai kaskade sungguhan: begitu
entri melewati 300 detik, hasilnya melompat ke hardcoded.

Lompatan itu membuang informasi. Harga ETH berumur 400 detik masih jauh
lebih dekat ke pasar daripada konstanta 39_910_503 yang ditulis pada D5.
T2.0 menyisipkan tier stale cache antara CoinGecko dan hardcoded: entri
PRICE_CACHE dipakai berapa pun umurnya, dan hardcoded hanya dipakai kalau
entrinya memang tidak ada.

Yang TIDAK berubah: PRICE_TTL, UMUR_CACHE_LENGKAP_DETIK, dan
kelengkapan_dari_provenance() itu sendiri. Penurunan mutu tetap terbaca
lewat umur_detik, bukan lewat ambang baru.

PRICE_CACHE dibersihkan di setUp tiap kasus.
"""

import time
import unittest
from unittest.mock import patch

import core.pricing as pricing

UMUR_STALE_MASIH_LENGKAP = 400    # > PRICE_TTL (300), <= 900
UMUR_STALE_SUDAH_SEBAGIAN = 1200  # > 900
NILAI_CACHE = 41_500_000.0


class TestTierStaleCache(unittest.TestCase):
    """CMC dan CoinGecko gagal, PRICE_CACHE berisi entri basi."""

    def setUp(self):
        pricing.PRICE_CACHE.clear()
        pricing._CMC_LIVE_WRITE_AT = None
        self.addCleanup(pricing.PRICE_CACHE.clear)

    def test_cache_basi_400_detik_dipakai_bukan_hardcoded(self):
        pricing.PRICE_CACHE["ethereum"] = (
            time.time() - UMUR_STALE_MASIH_LENGKAP, NILAI_CACHE)

        with patch("core.pricing._refresh_price_cache_from_cmc", return_value=False), \
             patch("core.pricing.requests.get", side_effect=Exception("network down")):
            prov = pricing.get_eth_price_with_provenance()

        # prov utuh dibawa ke pesan kegagalan: tanpa tier stale cache yang
        # muncul di sini adalah sumber "hardcoded" berikut konstanta D5,
        # dan itu yang harus terbaca langsung dari output merah.
        self.assertEqual(prov["sumber"], "cache", prov)
        self.assertEqual(prov["nilai"], NILAI_CACHE, prov)
        self.assertAlmostEqual(prov["umur_detik"], UMUR_STALE_MASIH_LENGKAP,
                               delta=2, msg=prov)

    def test_cache_basi_1200_detik_turun_ke_sebagian(self):
        """Cabang yang sebelumnya tidak terjangkau kaskade.

        Umur di atas UMUR_CACHE_LENGKAP_DETIK tidak menolak nilainya --
        nilainya tetap dipakai, statusnya yang turun. Itu pembagian kerja
        yang sama seperti sebelumnya: pricing melaporkan, T2.3 menahan.
        """
        pricing.PRICE_CACHE["ethereum"] = (
            time.time() - UMUR_STALE_SUDAH_SEBAGIAN, NILAI_CACHE)

        with patch("core.pricing._refresh_price_cache_from_cmc", return_value=False), \
             patch("core.pricing.requests.get", side_effect=Exception("network down")):
            prov = pricing.get_eth_price_with_provenance()

        self.assertEqual(prov["sumber"], "cache", prov)
        self.assertEqual(prov["nilai"], NILAI_CACHE, prov)
        self.assertAlmostEqual(prov["umur_detik"], UMUR_STALE_SUDAH_SEBAGIAN,
                               delta=2, msg=prov)
        self.assertEqual(pricing.kelengkapan_dari_provenance(prov), "SEBAGIAN", prov)

    def test_hardcoded_hanya_saat_cache_kosong(self):
        """Batas tier baru: tanpa entri sama sekali, hardcoded tetap jalan."""
        with patch("core.pricing._refresh_price_cache_from_cmc", return_value=False), \
             patch("core.pricing.requests.get", side_effect=Exception("network down")):
            prov = pricing.get_eth_price_with_provenance()

        self.assertEqual(prov["sumber"], "hardcoded", prov)
        self.assertEqual(prov["nilai"], pricing.HARGA_ETH_HARDCODED, prov)


if __name__ == "__main__":
    unittest.main()
