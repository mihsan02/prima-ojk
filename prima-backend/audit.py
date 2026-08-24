"""
T3.1 -- rantai hash audit. write_audit() dipindah dari app.py:603 ke sini.

Tanda tangan publik (action, detail, actor=None) TIDAK berubah -- 25
pemanggil di app.py tidak perlu disentuh.

Desain kebijakan yang dikunci mentor 24 Agustus 2026:
- 351 baris audit_log lama (sebelum T3.1) TIDAK dibackfill. event_hash
  tetap NULL untuk baris itu, didokumentasikan sebagai batas rantai.
  Rantai baru dimulai dari baris pertama sesudah migrasi ini berjalan.
- versi_perhitungan memakai string versi API yang sudah ada
  ("1.9-pasal50-pasal91"), diekstrak ke konstanta di sini. app.py
  /api/status mengimpornya dari sini supaya tidak pernah drift.
- Genesis previous_event_hash untuk baris rantai pertama: 64 karakter
  '0', konvensi umum sepanjang digest SHA-256 hex.

Kontrak write_audit TIDAK berubah: tidak pernah raise. Kegagalan apa pun
di jalur rantai (kolom belum ada karena migrasi belum jalan di
environment ini) jatuh ke insert legacy tanpa kolom hash -- baris tetap
tersimpan, di luar rantai, sama seperti 351 baris lama. Kegagalan
Supabase total jatuh ke file fallback, dan baris yang jatuh ke situ
ditandai eksplisit chain_status supaya kegagalan rantai TERLIHAT, bukan
senyap.

_current_actor, _get_db_conn, _return_db_conn TETAP di app.py (dipakai
pemanggil lain juga -- _current_actor dipanggil independen oleh
log_data_access). Diimpor di sini lewat deferred import di dalam fungsi
untuk menghindari circular import: app.py mengimpor write_audit dari
modul ini di bagian atas filenya, jadi modul ini tidak boleh mengimpor
apa pun dari app di level atas.
"""
import os
import json
import hashlib
import threading
import tempfile
import uuid
from datetime import datetime, timezone

from flask import request

VERSI_PERHITUNGAN = "1.9-pasal50-pasal91"  # sinkron dengan app.py /api/status
GENESIS_HASH = "0" * 64

# AUDIT_FILE diambil lewat deferred import dari app.py (lihat write_audit)
# -- supaya test yang mem-patch app.AUDIT_FILE benar-benar berpengaruh.

_chain_lock = threading.Lock()


def _canonical_payload(event_dict):
    return json.dumps(event_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _compute_event_hash(previous_hash, event_dict):
    payload = _canonical_payload(event_dict)
    return hashlib.sha256((previous_hash + payload).encode("utf-8")).hexdigest()


def _resolve_source_ip():
    try:
        return request.remote_addr
    except RuntimeError:
        return None
    except Exception:
        return None


def write_audit(action, detail, actor=None):
    from app import _current_actor, _get_db_conn, _return_db_conn, AUDIT_FILE  # deferred: hindari circular import

    display_time  = datetime.now().strftime("%d %b %Y, %H:%M")
    timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if actor is None:
        actor = _current_actor()
    actor_email = (actor or {}).get("email") or None
    actor_role  = (actor or {}).get("role") or None
    source_ip   = _resolve_source_ip()
    request_id  = uuid.uuid4().hex

    conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            try:
                with _chain_lock:
                    cur.execute(
                        "SELECT event_hash FROM audit_log WHERE event_hash IS NOT NULL "
                        "ORDER BY id DESC LIMIT 1"
                    )
                    row = cur.fetchone()
                    previous_hash = row[0] if row else GENESIS_HASH

                    event_dict = {
                        "waktu": display_time, "aksi": action, "detail": detail,
                        "created_at": timestamp_utc, "actor_email": actor_email,
                        "actor_role": actor_role, "source_ip": source_ip,
                        "request_id": request_id, "versi_perhitungan": VERSI_PERHITUNGAN,
                    }
                    event_hash = _compute_event_hash(previous_hash, event_dict)

                    cur.execute(
                        "INSERT INTO audit_log (waktu, aksi, detail, created_at, actor_email, "
                        "actor_role, previous_event_hash, event_hash, source_ip, request_id, "
                        "versi_perhitungan) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (display_time, action, detail, timestamp_utc, actor_email, actor_role,
                         previous_hash, event_hash, source_ip, request_id, VERSI_PERHITUNGAN)
                    )
            except Exception:
                # Kolom rantai belum ada (migrasi T3.1 belum jalan di environment
                # ini) atau kolom actor belum ada (migrasi sprint5 belum jalan).
                # Insert legacy -- baris tetap tersimpan, di luar rantai, sama
                # seperti 351 baris sebelum T3.1.
                conn.rollback()
                try:
                    cur.execute(
                        "INSERT INTO audit_log (waktu, aksi, detail, created_at, actor_email, actor_role) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (display_time, action, detail, timestamp_utc, actor_email, actor_role)
                    )
                except Exception:
                    conn.rollback()
                    cur.execute(
                        "INSERT INTO audit_log (waktu, aksi, detail, created_at) VALUES (%s, %s, %s, %s)",
                        (display_time, action, detail, timestamp_utc)
                    )
            conn.commit()
            cur.close()
        except Exception as e:
            print(f"[AUDIT_DB] write failed: {type(e).__name__}: {e}", flush=True)
        finally:
            _return_db_conn(conn)
        return

    # Fallback: file (ephemeral). Ditandai chain_status supaya kegagalan
    # rantai TERLIHAT, bukan senyap -- lubang yang ditambal sesi ini.
    try:
        logs = []
        if os.path.exists(AUDIT_FILE):
            with open(AUDIT_FILE, "r") as f:
                logs = json.load(f)
        logs.insert(0, {
            "waktu": display_time, "aksi": action, "detail": detail,
            "aktor": actor_email, "aktor_role": actor_role,
            "chain_status": "unchained_file_fallback",
        })
        logs = logs[:50]
        dir_ = os.path.dirname(AUDIT_FILE) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(logs, f, indent=2)
        os.replace(tmp_path, AUDIT_FILE)
    except Exception as e:
        print(f"[AUDIT_FILE] write failed: {type(e).__name__}: {e}", flush=True)


def verify_chain(rows):
    """
    rows: list of dict, urut menaik berdasarkan id, masing-masing berisi
    minimal: id, aksi, waktu, detail, created_at, actor_email, actor_role,
    source_ip, request_id, versi_perhitungan, previous_event_hash, event_hash.

    Baris dengan event_hash None (legacy pra-T3.1) dilewati -- rantai
    dimulai dari baris pertama yang punya event_hash. Ini business logic
    murni; endpoint HTTP terautentikasi (GET /api/audit/verify) adalah
    T3.2, belum dibangun sesi ini.

    Return: (utuh: bool, id_rusak: int|None)
    """
    chained_rows = [r for r in rows if r.get("event_hash") is not None]
    expected_previous = None
    for r in chained_rows:
        event_dict = {
            "waktu": r["waktu"], "aksi": r["aksi"], "detail": r["detail"],
            "created_at": r["created_at"], "actor_email": r["actor_email"],
            "actor_role": r["actor_role"], "source_ip": r["source_ip"],
            "request_id": r["request_id"], "versi_perhitungan": r["versi_perhitungan"],
        }
        prev = r["previous_event_hash"]
        if expected_previous is not None and prev != expected_previous:
            return False, r["id"]
        recomputed = _compute_event_hash(prev, event_dict)
        if recomputed != r["event_hash"]:
            return False, r["id"]
        expected_previous = r["event_hash"]
    return True, None
