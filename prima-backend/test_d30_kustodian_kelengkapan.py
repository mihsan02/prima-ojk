"""D30 — kustodian on-chain total meluruh menjadi int.

Tiga test, ketiganya mengukur kerugian yang sama dalam bentuk berbeda:
dua keadaan yang berbeda isinya menerbitkan keluaran yang identik.

Tidak satu pun test di berkas ini mengasersi keberadaan kunci baru pada
kode pra-perbaikan. Merah karena kunci yang belum ada hanya mengukur
ketiadaan fungsi. Asersi atas isi ditempatkan SESUDAH asersi kerugian,
sehingga pra-perbaikan ia tidak pernah tercapai, dan pasca-perbaikan ia
menjaga agar tambalan yang salah tidak lolos hijau.
"""

WALLETS_ETH = [{"network": "ethereum", "address": "0xabc"}]

# ETH bernilai, SOL hadir tapi harganya gagal. Total tetap positif.
PARSIAL = {
    "total_idr": 40_000_000_000.0,
    "entries": [
        {"network": "ethereum", "address": "0xabc",
         "balance_native": 12.0, "balance_idr": 40_000_000_000.0},
        # Saldo terbaca, harga tidak. Tanpa kunci "error": kunci itu
        # berarti kegagalan saldo, dan menyalahgunakannya di sini akan
        # mengulang D26 di dalam fixture.
        {"network": "solana", "address": "SoL111",
         "balance_native": 1600.0},
    ],
    "provenance_harga": {
        "ethereum": {"sumber": "cmc", "umur_detik": 12},
        "solana": None,
    },
}

# ETH saja, semuanya berhasil. Total identik dengan PARSIAL.
LENGKAP = {
    "total_idr": 40_000_000_000.0,
    "entries": [
        {"network": "ethereum", "address": "0xabc",
         "balance_native": 12.0, "balance_idr": 40_000_000_000.0},
    ],
    "provenance_harga": {
        "ethereum": {"sumber": "cmc", "umur_detik": 12},
    },
}

# Kegagalan total. Memicu retry lalu jalur last-known-good.
GAGAL_TOTAL = {
    "total_idr": 0.0,
    "entries": [
        {"network": "ethereum", "address": "0xabc",
         "error": "Etherscan rate limit"},
    ],
    "provenance_harga": {"ethereum": None, "bitcoin": None, "solana": None},
}


def _bersihkan_cache():
    """D22. Bersihkan LKG dan tiga cache yang bisa menyimpan hasil lama.

    D30: getattr diganti referensi langsung setelah lokasinya diverifikasi
    lewat grep -- BALANCE_CACHE dan JUPITER_PRICE_CACHE ada di app,
    PRICE_CACHE ada di core.pricing. JUPITER_PRICE_CACHE ikut dibersihkan
    karena harga token SPL yang tersisa dari test lain bisa menggeser
    total dan membuat cabang yang diuji berpindah.
    """
    import app as app_mod
    import core.pricing as pricing_mod
    app_mod._KUST_ONCHAIN_LKG.clear()
    app_mod.BALANCE_CACHE.clear()
    app_mod.JUPITER_PRICE_CACHE.clear()
    pricing_mod.PRICE_CACHE.clear()


class TestD30KelengkapanKustodian:
    """Total kustodian tidak membawa kelengkapan, jadi parsial dan lengkap identik."""

    def test_parsial_dan_lengkap_menghasilkan_keluaran_identik(self):
        import app as app_mod
        from unittest.mock import patch as _patch
        _bersihkan_cache()

        with _patch.object(app_mod, "get_total_balance_idr",
                           return_value=PARSIAL) as m_parsial:
            hasil_parsial = app_mod._get_kustodian_onchain_resilient(
                "KUST-PARSIAL", WALLETS_ETH)
        assert m_parsial.call_count == 1, (
            "premis batal: total positif seharusnya lewat cabang sukses, "
            f"bukan cabang retry. call_count={m_parsial.call_count}")

        _bersihkan_cache()
        with _patch.object(app_mod, "get_total_balance_idr",
                           return_value=LENGKAP) as m_lengkap:
            hasil_lengkap = app_mod._get_kustodian_onchain_resilient(
                "KUST-LENGKAP", WALLETS_ETH)
        assert m_lengkap.call_count == 1, (
            "premis batal: total positif seharusnya lewat cabang sukses, "
            f"bukan cabang retry. call_count={m_lengkap.call_count}")

        # KERUGIAN. Kustodian yang harga SOL-nya gagal dan kustodian yang
        # asetnya lengkap menerbitkan angka pengawasan yang sama persis.
        assert hasil_parsial != hasil_lengkap, (
            "kustodian dengan harga SOL gagal dan kustodian dengan aset "
            f"lengkap menerbitkan keluaran identik: {hasil_parsial!r}")

        # Penjaga pasca-perbaikan. Tidak tercapai sebelum tambalan.
        assert hasil_parsial["total_idr"] == hasil_lengkap["total_idr"]
        assert hasil_parsial["sumber_total"] == "live"
        assert "solana" in hasil_parsial["provenance_harga"]
        assert hasil_parsial["provenance_harga"]["solana"] is None
        assert "solana" not in hasil_lengkap["provenance_harga"]

    def test_lkg_parsial_tidak_terbedakan_dari_lkg_lengkap(self):
        import app as app_mod
        from unittest.mock import patch as _patch

        def _isi_lalu_gagalkan(kunci, saldo_awal):
            _bersihkan_cache()
            with _patch.object(app_mod, "get_total_balance_idr",
                               return_value=saldo_awal) as m1:
                app_mod._get_kustodian_onchain_resilient(kunci, WALLETS_ETH)
            assert m1.call_count == 1, (
                f"premis batal: pengisian LKG untuk {kunci} tidak lewat "
                f"cabang sukses. call_count={m1.call_count}")

            with _patch.object(app_mod, "get_total_balance_idr",
                               return_value=GAGAL_TOTAL) as m2, \
                 _patch.object(app_mod.time, "sleep"):
                hasil = app_mod._get_kustodian_onchain_resilient(
                    kunci, WALLETS_ETH)
            assert m2.call_count == 2, (
                f"premis batal: {kunci} tidak lewat cabang retry lalu LKG. "
                f"call_count={m2.call_count}")
            return hasil

        dari_lkg_parsial = _isi_lalu_gagalkan("KUST-P", PARSIAL)
        dari_lkg_lengkap = _isi_lalu_gagalkan("KUST-L", LENGKAP)

        # KERUGIAN. Nilai lama yang parsial disajikan sama dengan nilai
        # lama yang lengkap, selama satu TTL penuh.
        assert dari_lkg_parsial != dari_lkg_lengkap, (
            "nilai LKG parsial dan nilai LKG lengkap tersaji identik: "
            f"{dari_lkg_parsial!r}")

        # Penjaga pasca-perbaikan. Provenance yang tersimpan adalah milik
        # nilai yang dipakai, bukan milik percobaan yang gagal sesudahnya.
        assert dari_lkg_parsial["sumber_total"] == "lkg"
        assert dari_lkg_parsial["lkg_umur_detik"] is not None
        assert "solana" in dari_lkg_parsial["provenance_harga"]
        assert dari_lkg_parsial["provenance_harga"] != GAGAL_TOTAL["provenance_harga"]

    def test_payload_pengawasan_identik_untuk_dua_keadaan_berbeda(self):
        import app as app_mod
        from unittest.mock import patch as _patch

        def _jalankan(saldo):
            _bersihkan_cache()
            with _patch.object(
                    app_mod, "_get_kustodian_data_for_pakd",
                    return_value=(["KUST-001"], {"KUST-001": WALLETS_ETH})), \
                 _patch.object(
                    app_mod, "_get_reported_values",
                    return_value={"customer_at_pakd_idr": 30_000_000_000,
                                  "customer_at_ptp_idr": 70_000_000_000,
                                  "proprietary_idr": 0}), \
                 _patch.object(app_mod, "get_total_balance_idr",
                               return_value=saldo) as m, \
                 _patch.object(app_mod.time, "sleep"):
                hasil = app_mod.compute_30_70_compliance(
                    "PAKD-001", 0, as_of="2026-08-18T04:00:00+00:00")
            assert m.call_count == 1, (
                "premis batal: total positif seharusnya lewat cabang "
                f"sukses. call_count={m.call_count}")
            return hasil

        payload_parsial = _jalankan(PARSIAL)
        payload_lengkap = _jalankan(LENGKAP)

        # KERUGIAN. Payload yang dibaca frontend dan ditulis ke snapshot
        # tidak membedakan penyebut lengkap dari penyebut kurang.
        assert payload_parsial != payload_lengkap, (
            "payload compute_30_70_compliance identik untuk dua keadaan "
            f"on-chain yang berbeda: {payload_parsial!r}")

        # Penjaga pasca-perbaikan. Nama kunci "status" dan "sumber_gagal"
        # berasal dari catatan hitung_kelengkapan tanggal 19 Agustus dan
        # WAJIB dikonfirmasi lewat grep sebelum fase hijau. Bila berbeda,
        # hanya dua baris ini yang berubah; asersi kerugian di atas tidak
        # terpengaruh.
        assert payload_parsial["kustodian_kelengkapan"]["status"] == "SEBAGIAN"
        assert payload_lengkap["kustodian_kelengkapan"]["status"] == "LENGKAP"
        assert payload_parsial["kustodian_kelengkapan"]["sumber_gagal"]
        assert not payload_lengkap["kustodian_kelengkapan"]["sumber_gagal"]
