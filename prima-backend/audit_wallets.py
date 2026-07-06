"""Wallet address audit — READ-ONLY, flag only.

Context: two ethereum addresses under entity_type='KUSTODIAN' turned out to be
real Binance hot wallets (Binance 16 / KUST-001, Binance 28 / KUST-002) with
live balances far beyond any demo scenario. Both were replaced manually. This
script sweeps the ENTIRE wallets table — PAKD-linked rows included, all
networks — and flags anything whose live on-chain balance exceeds a magnitude
threshold. It performs no UPDATE and no DELETE.

Flagging is by balance magnitude, not an address blocklist: the largest
legitimate figure in REPORTED_VALUES_DEFAULT is Rp 8 miliar, so anything above
Rp 100 miliar cannot be demo data.

Usage:  DATABASE_URL=... python audit_wallets.py
"""

import sys
import time

from app import _get_db_conn, _return_db_conn, get_total_balance_idr

THRESHOLD_IDR = 100_000_000_000  # Rp 100 miliar
SLEEP_BETWEEN_WALLETS = 1.5      # free-tier API keys throttle rapid calls


def _p(line):
    print(line, flush=True)


def confirm_schema(conn):
    """Step 1: confirm which linkage columns actually exist on wallets."""
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'wallets'
        ORDER BY ordinal_position
    """)
    cols = [r[0] for r in cur.fetchall()]
    cur.close()
    _p(f"[SCHEMA] wallets columns: {', '.join(cols) if cols else '(table not found)'}")
    if not cols:
        _p("[ERROR] wallets table not found — aborting.")
        sys.exit(1)
    return cols


def enumerate_wallets(conn, cols):
    """One query returning every row regardless of linkage column used."""
    has_pakd_id = 'pakd_id' in cols
    has_entity = 'entity_id' in cols and 'entity_type' in cols
    has_id = 'id' in cols

    if has_pakd_id and has_entity:
        owner_expr = "COALESCE(entity_id, pakd_id::text)"
        type_expr = "COALESCE(entity_type, CASE WHEN pakd_id IS NOT NULL THEN 'PAKD' ELSE '?' END)"
    elif has_entity:
        owner_expr, type_expr = "entity_id", "entity_type"
    elif has_pakd_id:
        owner_expr, type_expr = "pakd_id::text", "'PAKD'"
    else:
        _p("[ERROR] wallets has neither pakd_id nor entity_id/entity_type — aborting.")
        sys.exit(1)

    id_expr = "id" if has_id else "NULL"
    cur = conn.cursor()
    cur.execute(f"""
        SELECT {id_expr} AS row_id, {type_expr} AS owner_type, {owner_expr} AS owner,
               network, address
        FROM wallets
        ORDER BY owner_type, owner, network, address
    """)
    rows = cur.fetchall()
    cur.close()
    return rows, owner_expr


def check_duplicates(conn, owner_expr):
    """Step 4: duplicate rows across EVERY entity type, not just KUSTODIAN."""
    cur = conn.cursor()
    cur.execute(f"""
        SELECT {owner_expr} AS owner, network, address, COUNT(*)
        FROM wallets
        GROUP BY owner, network, address
        HAVING COUNT(*) > 1
    """)
    dups = cur.fetchall()
    cur.close()
    return dups


def main():
    conn = _get_db_conn()
    if not conn:
        _p("[ERROR] Could not get DB connection (DATABASE_URL set?). Aborting.")
        sys.exit(1)
    try:
        cols = confirm_schema(conn)
        rows, owner_expr = enumerate_wallets(conn, cols)
        _p(f"[AUDIT] {len(rows)} wallet rows to check, threshold Rp {THRESHOLD_IDR:,}")

        warnings = 0
        for i, (row_id, owner_type, owner, network, address) in enumerate(rows):
            addr_short = (address[:10] + '...' + address[-6:]) if address and len(address) > 20 else address
            try:
                # Reuse the production balance logic, one wallet at a time.
                result = get_total_balance_idr([{"network": network, "address": address}])
                balance_idr = result.get("total_idr", 0) or 0
                flag = ""
                if balance_idr > THRESHOLD_IDR:
                    warnings += 1
                    flag = "  <<< WARNING: balance exceeds demo threshold — likely a REAL third-party wallet"
                _p(f"[WALLET] id={row_id} {owner_type}/{owner} {network:9s} {addr_short:24s} "
                   f"Rp {balance_idr:>22,.0f}{flag}")
            except Exception as e:
                _p(f"[WALLET] id={row_id} {owner_type}/{owner} {network:9s} {addr_short:24s} "
                   f"[ERROR] balance fetch failed: {type(e).__name__}: {e}")
            if i < len(rows) - 1:
                time.sleep(SLEEP_BETWEEN_WALLETS)

        dups = check_duplicates(conn, owner_expr)
        if dups:
            _p(f"[DUPLICATES] {len(dups)} duplicate (owner, network, address) groups found:")
            for owner, network, address, count in dups:
                _p(f"[DUPLICATES]   {owner} {network} {address} x{count}")
        else:
            _p("[DUPLICATES] none — zero duplicate rows across all entity types.")

        _p(f"[SUMMARY] {len(rows)} wallets audited, {warnings} WARNING(s), "
           f"{len(dups)} duplicate group(s).")
        if warnings:
            _p("[SUMMARY] Fix for flagged ETHEREUM rows (manual, after review):")
            _p("[SUMMARY]   UPDATE wallets SET address = '0x' || lpad('deadN', 40, '0') WHERE id = <id>;")
            _p("[SUMMARY] For flagged bitcoin/solana rows: do NOT reuse the ethereum placeholder "
               "format — agree on a chain-appropriate placeholder first.")
    finally:
        _return_db_conn(conn)


if __name__ == "__main__":
    main()
