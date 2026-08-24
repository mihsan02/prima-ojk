"""T2.3/D6 -- gerbang verdict.

Dua fungsi terpisah karena dua formula verdict berbeda hidup di
app.py: ternary (internal_refresh_all, _job_update) dan
surplus/defisit (reconciliation). Ambang keduanya BEDA -- 5%/20% vs
0.01%/10% -- dan sengaja TIDAK disatukan di sini. Menyatukannya akan
diam-diam mengubah kebijakan supervisi salah satu jalur. Dicatat
sebagai D49, belum ditambal.

recalc_snapshot (situs 1, app.py ~2264) TIDAK memanggil modul ini.
Sejak T2.4 Bagian A2, kelengkapan_status/sumber_gagal/provenance_harga/
aset_onchain_idr_final/subtotal_diketahui_idr PERSISTEN di
reconciliation_snapshots untuk tiga situs verdict (app.py 2929, 3022,
4006). recalc_snapshot tetap menulis NULL untuk kelima kolom itu --
bukan gap persistensi lagi, melainkan keterbatasan struktural: fungsi
ini menghitung ulang dari snapshot lama tanpa fetch on-chain baru,
sehingga tidak pernah punya kelengkapan baru untuk dilaporkan.
Keputusan Opsi A, didokumentasikan sebagai batasan diketahui.
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
