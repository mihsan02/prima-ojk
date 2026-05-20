# PRIMA Baseline Profiling - 20 Mei 2026

## Setup
- Produksi: prima-ojk.onrender.com
- PAKD aktif: 4 (skenario real, bukan 25 PAKD stress test)
- Wallet distribusi: ETH-heavy, 0 BTC wallet aktif
- Commit: 99de842

## Hasil

| Segmen | Run 1 (cold) | Run 2 (warm) | Run 3 (mixed ~4 menit) |
|---|---|---|---|
| fetch_eth_total | 63.775s | 0.010s | 0.009s |
| fetch_sol_total | 5.897s | 3.645s | 3.283s |
| db_write | 5.523s | 5.530s | 5.583s |
| fetch_btc_total | 0.0s | 0.0s | 0.0s |
| pricing_eth_fallback | 0.0s | 0.0s | 0.0s |
| total | 77.453s | 11.128s | 10.808s |

## Temuan

1. ETH dominan 82.3% cold cache. Konfirmasi: Multicall3 prioritas Day 21.
2. db_write flat 5.5s tidak terpengaruh cache. Proyeksi 25 PAKD = ~34s. Wajib batch INSERT Day 20.
3. SOL 3.3-3.6s warm cache. Jupiter verified set masih network call. Acceptable untuk demo.
4. ETH warm cache hampir 0s. BALANCE_TTL=300s efektif. Path A (background cron) solve cold start.

## Keputusan Arsitektur

- Path A (background snapshot): prioritas utama. Solve cold start tanpa Multicall3.
- Path B (Multicall3): tetap dikerjakan Day 21 untuk refresh manual <30s.
- Batch db_write: tambahan wajib Day 20, tidak ada di plan awal.
