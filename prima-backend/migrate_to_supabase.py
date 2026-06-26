"""
Migration script: pakd_data.json -> Supabase PostgreSQL
Run once: python3 prima-backend/migrate_to_supabase.py
"""
import json
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv("/workspaces/prima-ojk/.env")

DATABASE_URL = os.environ["DATABASE_URL"]

CREATE_PAKD = """
CREATE TABLE IF NOT EXISTS pakd (
    id TEXT PRIMARY KEY,
    nama TEXT NOT NULL,
    aset_dilaporkan BIGINT DEFAULT 0,
    equity_idr BIGINT,
    persediaan_akd_idr BIGINT,
    simpanan_pedagang_akd_idr BIGINT,
    customer_akd_idr BIGINT
);
"""

CREATE_WALLETS = """
CREATE TABLE IF NOT EXISTS wallets (
    id SERIAL PRIMARY KEY,
    pakd_id TEXT REFERENCES pakd(id) ON DELETE CASCADE,
    network TEXT NOT NULL,
    address TEXT NOT NULL,
    verified BOOLEAN DEFAULT FALSE,
    verified_at TIMESTAMP
);
"""

def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    cur.execute(CREATE_PAKD)
    cur.execute(CREATE_WALLETS)
    conn.commit()
    print("Tables created.")

    with open("prima-backend/pakd_data.json") as f:
        data = json.load(f)

    for pakd in data:
        cur.execute("""
            INSERT INTO pakd (id, nama, aset_dilaporkan, equity_idr,
                persediaan_akd_idr, simpanan_pedagang_akd_idr, customer_akd_idr)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (
            pakd["id"],
            pakd["nama"],
            pakd.get("aset_dilaporkan", 0),
            pakd.get("equity_idr"),
            pakd.get("persediaan_akd_idr"),
            pakd.get("simpanan_pedagang_akd_idr"),
            pakd.get("customer_akd_idr"),
        ))

        for wallet in pakd.get("wallets", []):
            cur.execute("""
                INSERT INTO wallets (pakd_id, network, address, verified, verified_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                pakd["id"],
                wallet["network"],
                wallet["address"],
                wallet.get("verified", False),
                wallet.get("verified_at"),
            ))

    conn.commit()
    cur.close()
    conn.close()
    print(f"Migrated {len(data)} PAKD records.")

if __name__ == "__main__":
    main()
