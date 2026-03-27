"""
PRIMA — Proof of Concept: Rekonsiliasi Aset On-Chain vs Laporan PAKD
====================================================================
Sistem Pemantauan Transparansi Aset Pedagang Aset Keuangan Digital
Dibangun untuk DIGDAYA X Hackathon 2026

FRAMING TEKNIS:
  Rekonsiliasi: membandingkan saldo on-chain vs kewajiban fiat yang dilaporkan.
  Stress test: menguji apakah rasio cadangan likuid PAKD (kas, obligasi,
  stablecoin) cukup untuk memenuhi gelombang penarikan dana nasabah selama
  krisis pasar. Ini berbeda dari menguji apakah aset kripto menutup semua
  kewajiban fiat — yang tidak bermakna karena kedua sisi bergerak bersama.

  Metodologi stress test mengacu pada konsep Liquidity Coverage Ratio (LCR)
  yang digunakan dalam pengawasan perbankan konvensional, diadaptasi untuk
  konteks PAKD.

Dependensi: pandas, numpy
Install   : pip install pandas numpy
Jalankan  : python reconciliation_poc.py
"""

import pandas as pd
import numpy as np
from datetime import date

# ─────────────────────────────────────────────────────────
# KONFIGURASI SISTEM
# ─────────────────────────────────────────────────────────

THRESHOLD_AMAN     = 5.0   # Deviasi < 5%  → AMAN
THRESHOLD_KRITIS   = 20.0  # Deviasi ≥ 20% → KRITIS, Tier 2 Alert

# Stress test: skenario penurunan harga kripto historis
# → dipakai sebagai proxy tingkat penarikan nasabah (withdrawal surge)
# Referensi: Chainalysis 2024 Crypto Crime Report
STRESS_SCENARIOS = {
    "mild":     {"penarikan": 0.30, "label": "Mild (-30%)",     "referensi": "Koreksi BTC Q2 2021"},
    "moderate": {"penarikan": 0.55, "label": "Moderate (-55%)", "referensi": "Bear market 2022"},
    "severe":   {"penarikan": 0.80, "label": "Severe (-80%)",   "referensi": "Bear market 2018"},
}

PERIODE_LAPORAN        = date(2026, 2, 28)
TANGGAL_REKONSILIASI   = date(2026, 3, 25)

# ─────────────────────────────────────────────────────────
# DATA DUMMY: 25 PAKD BERIZIN OJK
# Kolom: Nama, ID OJK, Aset On-Chain (Rp Juta),
#         Kewajiban Dilaporkan (Rp Juta),
#         Rasio Cadangan Likuid (%)
#
# Rasio Cadangan Likuid = proporsi kewajiban yang dapat
# dipenuhi dari kas/stablecoin/obligasi tanpa menjual kripto.
# Sumber: laporan PAKD kepada OJK (data dummy untuk POC).
# ─────────────────────────────────────────────────────────

DATA_PAKD = [
    # nama,                              id_ojk,          onchain,     laporan,    cadangan%
    # ── KRITIS: deviasi >20% ────────────────────────────────────────────────────────────
    ("PT Bitharga Indonesia",          "PAKD-OJK-018",   142_300,    198_700,    5),
    # ── DEVIASI: deviasi 5–20% ──────────────────────────────────────────────────────────
    ("PT Triv Karya Utama",            "PAKD-OJK-022",    87_400,     93_200,   45),
    ("PT Zipmex Indonesia",            "PAKD-OJK-011",    54_100,     57_800,   48),
    # ── AMAN: deviasi <5% ───────────────────────────────────────────────────────────────
    ("PT Indodax Nasional Indonesia",  "PAKD-OJK-001", 9_821_400,  9_814_800,   95),
    ("PT Tokocrypto",                  "PAKD-OJK-002", 3_412_700,  3_421_000,   92),
    ("PT Pintu Kemana Saja",           "PAKD-OJK-004", 2_187_300,  2_191_000,   90),
    ("PT Luno Indonesia",              "PAKD-OJK-005", 1_544_800,  1_549_200,   88),
    ("PT Upbit Indonesia",             "PAKD-OJK-007", 1_238_600,  1_242_100,   85),
    ("PT Rekeningku Dotcom Indonesia", "PAKD-OJK-003",   987_200,    991_400,   83),
    ("PT Coinstore Indonesia",         "PAKD-OJK-009",   654_100,    657_800,   82),
    ("PT Aset Digital Berkat",         "PAKD-OJK-010",   543_200,    545_900,   80),
    ("PT Bursa Kripto Prima",          "PAKD-OJK-012",   432_100,    434_700,   80),
    ("PT Kriptoku Indonesia",          "PAKD-OJK-013",   387_400,    389_200,   80),
    ("PT Koins Digital Indonesia",     "PAKD-OJK-014",   312_800,    315_100,   81),
    ("PT Nanovest International",      "PAKD-OJK-015",   287_600,    289_800,   82),
    ("PT Kripto Maksima Koin",         "PAKD-OJK-016",   243_100,    244_900,   83),
    ("PT Tiga Ihsan Solusi",           "PAKD-OJK-017",   198_700,    200_100,   80),
    ("PT Diginex Indonesia",           "PAKD-OJK-019",   176_400,    177_800,   75),
    ("PT Coinlist Indonesia",          "PAKD-OJK-020",   154_300,    155_500,   72),
    ("PT Blockchainseq Indonesia",     "PAKD-OJK-021",   132_100,    133_200,   70),
    ("PT CoinWId Indonesia",           "PAKD-OJK-023",   112_400,    113_300,   68),
    ("PT Sievert Logistik Indonesia",  "PAKD-OJK-006",    76_400,     77_100,   65),
    ("PT Tec Global Solusi",           "PAKD-OJK-025",    87_300,     88_000,   56),
    ("PT Bitmuda Internasional",       "PAKD-OJK-024",    98_700,     99_500,   52),
    ("PT Cipta Koin Kripto",           "PAKD-OJK-008",    65_200,     65_800,   50),
]

# ─────────────────────────────────────────────────────────
# REKONSILIASI
# ─────────────────────────────────────────────────────────

def klasifikasi_status(deviasi_persen: float) -> tuple[str, str]:
    abs_dev = abs(deviasi_persen)
    if abs_dev < THRESHOLD_AMAN:
        return "AMAN", "—"
    elif abs_dev < THRESHOLD_KRITIS:
        return "DEVIASI", "Tier 1"
    else:
        return "KRITIS", "Tier 2"


def hitung_rekonsiliasi(nama, id_ojk, onchain, laporan, cadangan_persen) -> dict:
    selisih        = onchain - laporan
    deviasi_persen = (selisih / laporan) * 100
    status, tier   = klasifikasi_status(deviasi_persen)
    return {
        "nama_pakd":                nama,
        "id_ojk":                   id_ojk,
        "aset_onchain_juta":        onchain,
        "kewajiban_laporan_juta":   laporan,
        "rasio_cadangan_persen":    cadangan_persen,
        "selisih_juta":             selisih,
        "deviasi_persen":           round(deviasi_persen, 2),
        "status":                   status,
        "tier_alert":               tier,
        "periode_laporan":          PERIODE_LAPORAN,
        "tanggal_rekonsiliasi":     TANGGAL_REKONSILIASI,
    }


# ─────────────────────────────────────────────────────────
# STRESS TEST
# ─────────────────────────────────────────────────────────

def jalankan_stress_test(df: pd.DataFrame) -> pd.DataFrame:
    """
    Menguji ketahanan likuiditas PAKD terhadap gelombang penarikan
    selama krisis pasar.

    Asumsi: krisis kripto mendorong X% nasabah menarik dana dalam fiat.
    PAKD lulus jika rasio cadangan likuid >= tingkat penarikan simulasi.

    Contoh: Mild (-30%) → simulasi 30% nasabah menarik serentak.
    PAKD dengan cadangan likuid 35% → lulus. Cadangan 25% → gagal.
    """
    hasil = []
    for _, baris in df.iterrows():
        for kunci, skenario in STRESS_SCENARIOS.items():
            tingkat_penarikan = skenario["penarikan"] * 100  # dalam persen
            rasio             = baris["rasio_cadangan_persen"]
            lulus             = rasio >= tingkat_penarikan
            kekurangan        = max(0, (tingkat_penarikan - rasio) / 100
                                   * baris["kewajiban_laporan_juta"])
            hasil.append({
                "skenario":                   skenario["label"],
                "nama_pakd":                  baris["nama_pakd"],
                "rasio_cadangan_persen":      rasio,
                "tingkat_penarikan_persen":   tingkat_penarikan,
                "hasil":                      "LULUS" if lulus else "GAGAL",
                "kekurangan_likuiditas_juta": round(kekurangan, 2),
            })
    return pd.DataFrame(hasil)


# ─────────────────────────────────────────────────────────
# PELAPORAN
# ─────────────────────────────────────────────────────────

def cetak_rekonsiliasi(df: pd.DataFrame) -> None:
    print("\n" + "=" * 70)
    print("PRIMA — LAPORAN REKONSILIASI ASET PAKD")
    print(f"Periode laporan  : {PERIODE_LAPORAN.strftime('%B %Y')}")
    print(f"Tanggal proses   : {TANGGAL_REKONSILIASI.strftime('%d %B %Y')}")
    print("=" * 70)

    n_aman    = len(df[df["status"] == "AMAN"])
    n_deviasi = len(df[df["status"] == "DEVIASI"])
    n_kritis  = len(df[df["status"] == "KRITIS"])

    print(f"\nTotal PAKD berizin    : {len(df)}")
    print(f"  ✓ Aman              : {n_aman}")
    print(f"  ⚠ Deviasi (Tier 1) : {n_deviasi}")
    print(f"  ✗ Kritis (Tier 2)  : {n_kritis}")

    total_on  = df["aset_onchain_juta"].sum() / 1_000_000
    total_lap = df["kewajiban_laporan_juta"].sum() / 1_000_000
    gap       = total_lap - total_on
    dev_ind   = (gap / total_lap) * 100

    print(f"\nTotal aset on-chain   : Rp {total_on:,.2f} T")
    print(f"Total kewajiban       : Rp {total_lap:,.2f} T")
    print(f"Gap agregat industri  : Rp {gap:,.2f} T ({dev_ind:.2f}%)")

    df_alert = df[df["status"] != "AMAN"]
    if not df_alert.empty:
        print(f"\n{'─' * 70}")
        print("PAKD YANG MEMERLUKAN TINDAK LANJUT:")
        print(f"{'─' * 70}")
        for _, b in df_alert.iterrows():
            arah = "↓ DEFISIT" if b["selisih_juta"] < 0 else "↑ SURPLUS"
            print(
                f"  [{b['tier_alert']}] {b['nama_pakd']}\n"
                f"         Deviasi    : {b['deviasi_persen']:+.2f}% {arah}\n"
                f"         On-chain   : Rp {b['aset_onchain_juta']:,.1f} Juta\n"
                f"         Dilaporkan : Rp {b['kewajiban_laporan_juta']:,.1f} Juta\n"
            )


def cetak_stress_test(df_stress: pd.DataFrame) -> None:
    print(f"\n{'=' * 70}")
    print("PRIMA — LAPORAN STRESS TEST SOLVABILITAS")
    print("Metode  : Liquidity Coverage Ratio (LCR) — adaptasi PAKD")
    print("Sumber  : Drawdown historis kripto (Chainalysis, 2024)")
    print(f"{'=' * 70}\n")

    for label in df_stress["skenario"].unique():
        df_s    = df_stress[df_stress["skenario"] == label]
        n_lulus = len(df_s[df_s["hasil"] == "LULUS"])
        n_gagal = len(df_s[df_s["hasil"] == "GAGAL"])
        total   = len(df_s)
        total_k = df_s["kekurangan_likuiditas_juta"].sum() / 1_000_000

        ikon = "✓" if n_gagal == 0 else ("⚠" if n_gagal <= 5 else "✗")
        print(f"  {ikon} Skenario {label}")
        print(f"    Lulus : {n_lulus}/{total} PAKD")
        if n_gagal > 0:
            print(f"    Gagal : {n_gagal} PAKD")
            print(f"    Estimasi kekurangan likuiditas industri: Rp {total_k:,.2f} T")
            gagal_list = df_s[df_s["hasil"] == "GAGAL"]["nama_pakd"].tolist()
            for nama in gagal_list:
                cadangan = df_s[df_s["nama_pakd"] == nama]["rasio_cadangan_persen"].values[0]
                print(f"      – {nama} (cadangan: {cadangan}%)")
        print()


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────

def main():
    print("\nPRIMA v1.0 — Memulai proses rekonsiliasi...")
    print(f"Sumber data : Dummy data (POC) · {len(DATA_PAKD)} PAKD berizin\n")

    # Rekonsiliasi
    print("Menjalankan rekonsiliasi on-chain vs laporan PAKD...")
    hasil        = [hitung_rekonsiliasi(*baris) for baris in DATA_PAKD]
    df_rekon     = pd.DataFrame(hasil)
    cetak_rekonsiliasi(df_rekon)

    # Stress test
    print(f"\n{'─' * 70}")
    print("Menjalankan stress test solvabilitas...")
    df_stress    = jalankan_stress_test(df_rekon)
    cetak_stress_test(df_stress)

    # Export
    df_rekon.to_csv("output_rekonsiliasi.csv", index=False)
    df_stress.to_csv("output_stress_test.csv", index=False)

    print(f"{'─' * 70}")
    print("Output tersimpan:")
    print("  · output_rekonsiliasi.csv")
    print("  · output_stress_test.csv")
    print("\nPRIMA — Proses selesai.")


if __name__ == "__main__":
    main()
