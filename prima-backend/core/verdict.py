"""T2.3/D6 -- gerbang verdict.

D49 DITUTUP 24 Agustus 2026. Dua formula verdict berbeda pernah hidup
di app.py: ternary (internal_refresh_all, _run_refresh_job, 5%/20%) dan
surplus/defisit (reconciliation, 0.01%/10%). PAKD dengan defisit 15%
bisa berstatus "Deviasi" lewat dua situs pertama tapi "Kritis" lewat
situs ketiga, tergantung endpoint mana terakhir menulis snapshot ke
tabel yang sama.

T0.1 (24 Agustus 2026) mengonfirmasi tidak ada pasal POJK yang mengatur
ambang deviasi persen ini -- keduanya murni kebijakan internal PRIMA,
bukan turunan regulasi. Keputusan mentor: surplus/defisit (0.01%/10%)
jadi kanonik tunggal karena lebih ketat -- ternary selalu sama longgar
atau lebih longgar, tidak pernah lebih ketat, di dua pita (0.01%-5% dan
10%-20%). Melonggarkan ambang pengawasan tanpa dasar pasal adalah
risiko gagal-terbuka; mengetatkan adalah gagal-tertutup, arah yang
lebih aman untuk alat kepatuhan tanpa rujukan regulasi yang menentukan
salah satu.

Ketiga situs produksi (reconciliation app.py ~2955, internal_refresh_all
~3057, _run_refresh_job ~4143) sekarang memanggil tetapkan_verdict_surplus.
tetapkan_verdict_ternary DIPERTAHANKAN di modul ini, tidak dihapus --
kalau ada test yang menguji fungsi ini langsung, tetap valid -- tapi
TIDAK LAGI dipanggil dari app.py sejak D49 ditutup.

Field 'surplus' (boolean) dikonsumsi frontend (core.js baris 39, 77,
967) untuk filter agregat KPI. Situs internal_refresh_all dan
_run_refresh_job belum menulis field ini ke reconciliation_snapshots --
di luar cakupan D49, dicatat sebagai temuan terbuka terpisah.

recalc_snapshot (situs 1, app.py ~2264) TIDAK memanggil modul ini,
tetap di luar cakupan D49 -- lihat keterangan Opsi A di bawah.

Sejak T2.4 Bagian A2, kelengkapan_status/sumber_gagal/provenance_harga/
aset_onchain_idr_final/subtotal_diketahui_idr PERSISTEN di
reconciliation_snapshots untuk tiga situs verdict. recalc_snapshot tetap
menulis NULL untuk kelima kolom itu -- bukan gap persistensi lagi,
melainkan keterbatasan struktural: fungsi ini menghitung ulang dari
snapshot lama tanpa fetch on-chain baru, sehingga tidak pernah punya
kelengkapan baru untuk dilaporkan. Keputusan Opsi A, didokumentasikan
sebagai batasan diketahui.
"""


def tetapkan_verdict_ternary(kelengkapan_status: str, deviasi: float) -> dict:
    """
    Gerbang untuk formula ternary (internal_refresh_all, _job_update).
    Ambang asli dipertahankan: 5% dan 20%.
    """
    if kelengkapan_status != "LENGKAP":
        return {"status": "Data Tidak Lengkap", "deviasi_pct": None}
    status = ("Aman" if deviasi >= 0 or abs(deviasi) <= 5
              else "Deviasi" if abs(deviasi) <= 20
              else "Kritis")
    return {"status": status, "deviasi_pct": round(deviasi, 2)}


def tetapkan_verdict_surplus(kelengkapan_status: str, total_attributable: float,
                              aset_dilaporkan: float, deviasi_pct: float) -> dict:
    """
    Gerbang untuk formula surplus/defisit (reconciliation).
    Ambang asli dipertahankan: 0.01% dan 10%.
    """
    if kelengkapan_status != "LENGKAP":
        return {"status": "Data Tidak Lengkap", "deviasi_pct": None, "surplus": None}
    surplus = total_attributable >= aset_dilaporkan
    if surplus:
        status = "Aman"
    else:
        deficit_pct = abs(deviasi_pct)
        status = ("Aman" if deficit_pct < 0.01
                   else "Deviasi" if deficit_pct <= 10
                   else "Kritis")
    return {"status": status, "deviasi_pct": round(deviasi_pct, 2), "surplus": surplus}
