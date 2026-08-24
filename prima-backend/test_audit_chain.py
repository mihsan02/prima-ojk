"""
T3.1 -- rantai hash audit. Test default (mock DB, cepat) + satu test
integrasi bertanda terpisah (Supabase asli, dikecualikan dari suite
default lewat skipUnless env var).

Keputusan mentor 24 Agustus 2026:
- 351 baris lama tidak dibackfill -- verify_chain() melewati baris
  dengan event_hash None, rantai dimulai dari baris pertama yang punya
  event_hash.
- versi_perhitungan = string versi API yang sudah ada, diimpor dari
  audit.VERSI_PERHITUNGAN supaya tidak drift dari /api/status.
- Test konkurensi mock DB layer, bukan Supabase asli (menghindari
  risiko pool size 1 / deadlock selama pengembangan test).
"""
import os
import threading
import unittest
from unittest.mock import patch

import audit


class _FakeCursor:
    """Meniru cukup permukaan psycopg2 cursor untuk SELECT+INSERT chain."""

    def __init__(self, shared_rows):
        self._shared_rows = shared_rows
        self._last_select_result = None

    def execute(self, sql, params=None):
        sql_norm = " ".join(sql.split())
        if sql_norm.startswith("SELECT event_hash FROM audit_log"):
            chained = [r for r in self._shared_rows if r.get("event_hash") is not None]
            self._last_select_result = (chained[-1]["event_hash"],) if chained else None
        elif "INSERT INTO audit_log" in sql_norm and "previous_event_hash" in sql_norm:
            (waktu, aksi, detail, created_at, actor_email, actor_role,
             previous_event_hash, event_hash, source_ip, request_id,
             versi_perhitungan) = params
            self._shared_rows.append({
                "id": len(self._shared_rows) + 1, "waktu": waktu, "aksi": aksi,
                "detail": detail, "created_at": created_at, "actor_email": actor_email,
                "actor_role": actor_role, "previous_event_hash": previous_event_hash,
                "event_hash": event_hash, "source_ip": source_ip, "request_id": request_id,
                "versi_perhitungan": versi_perhitungan,
            })
        else:
            raise AssertionError(f"SQL tak terduga di fake cursor: {sql_norm[:100]}")

    def fetchone(self):
        return self._last_select_result

    def close(self):
        pass


class _FakeConn:
    def __init__(self, shared_rows):
        self._shared_rows = shared_rows

    def cursor(self):
        return _FakeCursor(self._shared_rows)

    def commit(self):
        pass

    def rollback(self):
        pass


class _MockedDBTestCase(unittest.TestCase):
    """Base: patch app._get_db_conn/_return_db_conn/_current_actor supaya
    write_audit tidak pernah menyentuh Supabase asli."""

    def setUp(self):
        self.shared_rows = []
        self.fake_conn = _FakeConn(self.shared_rows)
        self._patchers = [
            patch("app._get_db_conn", return_value=self.fake_conn),
            patch("app._return_db_conn", lambda conn: None),
            patch("app._current_actor", return_value=None),
        ]
        for p in self._patchers:
            p.start()
            self.addCleanup(p.stop)


class TestAuditChainSequential(_MockedDBTestCase):

    def test_three_sequential_writes_chain_correctly(self):
        audit.write_audit("EVENT_A", "detail pertama")
        audit.write_audit("EVENT_B", "detail kedua")
        audit.write_audit("EVENT_C", "detail ketiga")

        self.assertEqual(len(self.shared_rows), 3)
        self.assertEqual(self.shared_rows[0]["previous_event_hash"], audit.GENESIS_HASH)
        self.assertEqual(self.shared_rows[1]["previous_event_hash"], self.shared_rows[0]["event_hash"])
        self.assertEqual(self.shared_rows[2]["previous_event_hash"], self.shared_rows[1]["event_hash"])
        hashes = [r["event_hash"] for r in self.shared_rows]
        self.assertEqual(len(hashes), len(set(hashes)), "event_hash harus unik semua")

    def test_tampering_detected_by_verify_chain(self):
        audit.write_audit("EVENT_A", "detail asli")
        audit.write_audit("EVENT_B", "detail tak tersentuh")
        audit.write_audit("EVENT_C", "detail lagi")

        utuh, id_rusak = audit.verify_chain(self.shared_rows)
        self.assertTrue(utuh)
        self.assertIsNone(id_rusak)

        self.shared_rows[1]["detail"] = "DIUBAH MANUAL"
        utuh, id_rusak = audit.verify_chain(self.shared_rows)
        self.assertFalse(utuh)
        self.assertEqual(id_rusak, self.shared_rows[1]["id"])

    def test_legacy_rows_without_event_hash_are_skipped_not_broken(self):
        legacy_row = {
            "id": 0, "waktu": "x", "aksi": "OLD", "detail": "lama",
            "created_at": "x", "actor_email": None, "actor_role": None,
            "source_ip": None, "request_id": None, "versi_perhitungan": None,
            "previous_event_hash": None, "event_hash": None,
        }
        audit.write_audit("EVENT_A", "baris pertama rantai baru")
        rows_with_legacy = [legacy_row] + self.shared_rows
        utuh, id_rusak = audit.verify_chain(rows_with_legacy)
        self.assertTrue(utuh, "baris legacy (event_hash None) tidak boleh dianggap kerusakan")


class TestAuditChainConcurrency(_MockedDBTestCase):
    """Sepuluh tulisan bersamaan -- membuktikan threading.Lock benar-benar
    menyerialkan baca-hash-terakhir + tulis, bukan cuma menyerialkan tulis
    saja (race pada baca akan menghasilkan cabang)."""

    def test_ten_concurrent_writes_produce_single_unbranched_chain(self):
        threads = [
            threading.Thread(target=audit.write_audit, args=(f"EVENT_{i}", f"detail {i}"))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(self.shared_rows), 10)

        event_hashes = {r["event_hash"] for r in self.shared_rows}
        previous_hashes = [r["previous_event_hash"] for r in self.shared_rows]

        self.assertEqual(len(event_hashes), 10, "event_hash harus unik semua")
        self.assertEqual(previous_hashes.count(audit.GENESIS_HASH), 1,
                          "tepat satu baris boleh mewarisi GENESIS_HASH")

        for h in event_hashes:
            occurrences = previous_hashes.count(h)
            self.assertLessEqual(
                occurrences, 1,
                f"event_hash {h[:8]}... dipakai sebagai previous oleh >1 baris -- rantai bercabang"
            )

        utuh, id_rusak = audit.verify_chain(self.shared_rows)
        self.assertTrue(utuh, f"rantai tidak utuh, rusak di id {id_rusak}")


class TestAuditChainIntegration(unittest.TestCase):
    """Integrasi asli ke Supabase Codespace. TIDAK ikut suite default.

    Jalankan manual: RUN_AUDIT_INTEGRATION=1 pytest test_audit_chain.py -k Integration -v

    Menulis baris nyata bertanda AUDIT_CHAIN_INTEGRATION_TEST ke audit_log.
    TIDAK dihapus sesudahnya -- audit log append-only, menghapus baris
    sendiri bertentangan dengan tujuan tabel ini. Baris uji mudah dikenali
    lewat nama aksinya kalau perlu dibersihkan manual di masa depan.
    """

    @unittest.skipUnless(
        os.environ.get("RUN_AUDIT_INTEGRATION") == "1",
        "set RUN_AUDIT_INTEGRATION=1 untuk menjalankan lawan Supabase asli"
    )
    def test_real_supabase_chain_write_and_verify(self):
        from dotenv import load_dotenv
        load_dotenv("/workspaces/prima-ojk/.env")
        import app  # noqa: F401 -- memastikan _DB_POOL app.py terinisialisasi

        audit.write_audit("AUDIT_CHAIN_INTEGRATION_TEST", "baris 1 uji integrasi")
        audit.write_audit("AUDIT_CHAIN_INTEGRATION_TEST", "baris 2 uji integrasi")
        audit.write_audit("AUDIT_CHAIN_INTEGRATION_TEST", "baris 3 uji integrasi")

        conn = app._get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, waktu, aksi, detail, created_at, actor_email, actor_role, "
            "source_ip, request_id, versi_perhitungan, previous_event_hash, event_hash "
            "FROM audit_log WHERE aksi = 'AUDIT_CHAIN_INTEGRATION_TEST' ORDER BY id ASC"
        )
        cols = ["id", "waktu", "aksi", "detail", "created_at", "actor_email", "actor_role",
                "source_ip", "request_id", "versi_perhitungan", "previous_event_hash", "event_hash"]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close()
        app._return_db_conn(conn)

        self.assertGreaterEqual(len(rows), 3)
        utuh, id_rusak = audit.verify_chain(rows[-3:])
        self.assertTrue(utuh, f"rantai integrasi asli tidak utuh, rusak di id {id_rusak}")


if __name__ == "__main__":
    unittest.main()
