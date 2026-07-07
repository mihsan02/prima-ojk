"""Demo data calibration — derive reported values FROM live on-chain balances.

Full-consistency calibration (Sprint 4 follow-up):
  * customer_at_pakd_idr = the PAKD's real on-chain balance (own wallets)
  * customer_at_ptp_idr  = balance of the kustodian wallets DEDICATED to the
    PAKD (1 wallet = 1 PAKD, via wallets.pakd_id on KUSTODIAN rows)
  * proprietary_idr      = 0

With deviasi counting the dedicated custody balance, this makes every page
tally: Overview deviasi ≈ 0, Kustodian monitoring deviation ≈ 0, and the
"dilaporkan vs on-chain" comparison cells match. Compliance ratios then follow
the real balances — tune wallet funding to stage COMPLIANT/VIOLATION cases.

DRY-RUN by default: prints the plan and resulting ratios/statuses.
Pass --apply to upsert confirmed rows into laporan_ereporting.

Usage:
  DATABASE_URL=... python scripts/calibrate_demo_data.py            # dry-run
  DATABASE_URL=... python scripts/calibrate_demo_data.py --apply
  DATABASE_URL=... python scripts/calibrate_demo_data.py --periode 2026-07 --apply

Prerequisite: kustodian wallets must point at funded addresses AND each must
be assigned to its PAKD (wallets.pakd_id). Run audit_wallets.py first — any
wallet over the audit threshold is a real third-party address and must be
replaced before calibrating against it.
"""

import argparse
import sys
import time
from datetime import date

sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))

from app import (_get_db_conn, _return_db_conn, get_total_balance_idr,
                 _get_reported_values)

SUSPICIOUS_IDR = 100_000_000_000  # same threshold as audit_wallets.py


def _p(line):
    print(line, flush=True)


def _fetch_wallets(cur, entity_type, entity_id):
    if entity_type == 'KUSTODIAN':
        # returns dedicated pakd_id per wallet (1 wallet = 1 PAKD)
        cur.execute("""
            SELECT network, address, pakd_id FROM wallets
            WHERE entity_type = 'KUSTODIAN' AND entity_id = %s
        """, (entity_id,))
        return [{"network": r[0], "address": r[1], "pakd_id": r[2]} for r in cur.fetchall()]
    cur.execute("""
        SELECT network, address FROM wallets
        WHERE (entity_type = 'PAKD' AND entity_id = %s)
           OR (pakd_id = %s AND (entity_type IS NULL OR entity_type = 'PAKD'))
    """, (entity_id, entity_id))
    return [{"network": r[0], "address": r[1]} for r in cur.fetchall()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write laporan_ereporting rows (default: dry-run)")
    ap.add_argument("--periode", default=date.today().strftime("%Y-%m"))
    args = ap.parse_args()

    conn = _get_db_conn()
    if not conn:
        _p("[ERROR] Could not get DB connection (DATABASE_URL set?). Aborting.")
        sys.exit(1)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, nama FROM kustodian ORDER BY id")
        kustodians = cur.fetchall()
        cur.execute("SELECT kustodian_id, pakd_id FROM kustodian_pakd")
        links = cur.fetchall()
        pakds_by_kust = {}
        for kid, pid in links:
            pakds_by_kust.setdefault(kid, []).append(pid)

        plan = {}  # pakd_id -> {at_pakd, at_ptp}
        for kust_id, kust_nama in kustodians:
            wallets = _fetch_wallets(cur, 'KUSTODIAN', kust_id)
            _p(f"[KUST] {kust_id} ({kust_nama}): {len(wallets)} wallet(s)")
            # 1 wallet = 1 PAKD: custody per PAKD = balance of its dedicated wallets
            linked = pakds_by_kust.get(kust_id, [])
            dedicated = {pid: [] for pid in linked}
            unassigned = []
            for w in wallets:
                if w.get('pakd_id') in dedicated:
                    dedicated[w['pakd_id']].append(w)
                else:
                    unassigned.append(w)
            if unassigned:
                _p(f"[KUST]   WARNING: {len(unassigned)} unassigned wallet(s) — set wallets.pakd_id "
                   f"(UI: tombol 🔗 di tabel Wallet Kustodian) or they count toward no PAKD.")

            for pid in linked:
                ded = dedicated[pid]
                kust_bal = get_total_balance_idr(ded)["total_idr"] if ded else 0
                if ded:
                    time.sleep(1.5)
                if kust_bal > SUSPICIOUS_IDR:
                    _p(f"[KUST]   WARNING: dedicated wallet(s) for {pid} hold Rp {kust_bal:,.0f} — likely "
                       f"a REAL third-party wallet. Replace before calibrating. Skipping {pid}.")
                    continue
                if not ded:
                    _p(f"[KUST]   WARNING: {pid} has no dedicated wallet at {kust_id} — at_ptp will be 0.")

                pw = _fetch_wallets(cur, 'PAKD', pid)
                own_bal = get_total_balance_idr(pw)["total_idr"] if pw else 0
                time.sleep(1.5)
                if own_bal > SUSPICIOUS_IDR:
                    _p(f"[PAKD]   WARNING: {pid} own balance Rp {own_bal:,.0f} exceeds audit threshold — "
                       f"likely a REAL third-party wallet. Replace it, then re-run.")
                _p(f"[PAKD]   {pid}: own on-chain Rp {own_bal:,.0f} | dedicated custody Rp {kust_bal:,.0f}")
                plan[pid] = {
                    "at_pakd": round(own_bal),
                    "at_ptp": round(kust_bal),
                }

        _p("")
        _p(f"[PLAN] periode={args.periode} (proprietary_idr set to 0 for all)")
        for pid, v in sorted(plan.items()):
            old = _get_reported_values(pid, conn=conn)
            total_cust = v["at_pakd"] + v["at_ptp"]
            ratio = (v["at_pakd"] / total_cust) if total_cust > 0 else 0
            status = "COMPLIANT" if ratio <= 0.30 else "VIOLATION"
            _p(f"[PLAN] {pid}: at_pakd Rp {old.get('customer_at_pakd_idr', 0) or 0:,.0f} -> Rp {v['at_pakd']:,} | "
               f"at_ptp Rp {old.get('customer_at_ptp_idr', 0) or 0:,.0f} -> Rp {v['at_ptp']:,} | "
               f"ratio {ratio * 100:.1f}% -> {status}")

        if not args.apply:
            _p("[DRY-RUN] No rows written. Re-run with --apply to upsert laporan_ereporting.")
            return

        for pid, v in sorted(plan.items()):
            cur.execute("""
                INSERT INTO laporan_ereporting
                    (entity_type, entity_id, periode, report_type, file_hash,
                     customer_at_pakd_idr, customer_at_ptp_idr, proprietary_idr,
                     uploaded_by, status, confirmed_at)
                VALUES ('PAKD', %s, %s, 'pakd', %s, %s, %s, 0, %s, 'confirmed', NOW())
                ON CONFLICT (entity_id, periode, report_type)
                DO UPDATE SET
                    file_hash = EXCLUDED.file_hash,
                    customer_at_pakd_idr = EXCLUDED.customer_at_pakd_idr,
                    customer_at_ptp_idr = EXCLUDED.customer_at_ptp_idr,
                    proprietary_idr = 0,
                    uploaded_by = EXCLUDED.uploaded_by,
                    status = 'confirmed',
                    confirmed_at = NOW()
            """, (pid, args.periode, f"calibration-{date.today().isoformat()}",
                  v["at_pakd"], v["at_ptp"], "calibrate_demo_data.py"))
            _p(f"[APPLY] upserted laporan_ereporting for {pid} periode {args.periode}")
        conn.commit()
        cur.close()
        _p("[APPLY] committed. Run a reconciliation refresh so snapshots pick up the new values.")
    except Exception as e:
        print(f"[ERROR] calibration failed: {type(e).__name__}: {e}", flush=True)
        try:
            conn.rollback()
        except Exception:
            pass
        sys.exit(1)
    finally:
        _return_db_conn(conn)


if __name__ == "__main__":
    main()
