"""
test_day5_wallet_proof.py
─────────────────────────────────────────────────────────────────────────────
End-to-end test for POST /api/wallet-challenge dan POST /api/wallet-verify.

Requirements:
    pip install eth-account requests
    Flask server running: python app.py

Run:
    python test_day5_wallet_proof.py

Coverage:
    [T1] Challenge issued dengan field yang benar
    [T2] Challenge ditolak untuk network bukan ethereum
    [T3] Challenge ditolak untuk address tidak valid
    [T4] Full flow: challenge → sign → verify → wallet_found=True (PAKD baru)
    [T5] Full flow: challenge → sign → verify → wallet_found=False (address asing)
    [T6] Verify ditolak tanpa challenge aktif
    [T7] Verify ditolak ketika signer != claimed address
    [T8] Duplicate challenge: challenge lama di-overwrite
"""

import sys
import requests
from eth_account import Account
from eth_account.messages import encode_defunct

BASE_URL = "http://localhost:5000"
PASS = "PASS"
FAIL = "FAIL"
results = []


def run(label, fn):
    try:
        fn()
        print(f"[{PASS}]  {label}")
        results.append((label, True))
    except AssertionError as e:
        print(f"[{FAIL}]  {label}")
        print(f"         AssertionError: {e}")
        results.append((label, False))
    except Exception as e:
        print(f"[{FAIL}]  {label}")
        print(f"         {type(e).__name__}: {e}")
        results.append((label, False))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_challenge(address, network="ethereum"):
    return requests.post(
        f"{BASE_URL}/api/wallet-challenge",
        json={"address": address, "network": network},
        timeout=10,
    )


def sign_challenge(account, challenge_text):
    """Sign using EIP-191 personal_sign — same method MetaMask uses."""
    signable = encode_defunct(text=challenge_text)
    signed   = account.sign_message(signable)
    return "0x" + signed.signature.hex()


def verify(address, signature, pakd_id=None):
    body = {"address": address, "signature": signature}
    if pakd_id:
        body["pakd_id"] = pakd_id
    return requests.post(
        f"{BASE_URL}/api/wallet-verify",
        json=body,
        timeout=10,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test cases
# ─────────────────────────────────────────────────────────────────────────────

def t1_challenge_fields():
    """Challenge response harus punya semua field yang dibutuhkan."""
    acc  = Account.create()
    resp = get_challenge(acc.address)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    for field in ["address", "challenge", "expires_in", "instruction"]:
        assert field in data, f"Field '{field}' hilang dari response"
    assert data["address"] == acc.address
    assert data["expires_in"] == 300
    assert acc.address in data["challenge"], "Address harus ada di dalam challenge string"
    assert "Nonce" in data["challenge"],     "Nonce harus ada di dalam challenge string"
    assert "Timestamp" in data["challenge"], "Timestamp harus ada di dalam challenge string"


def t2_challenge_rejects_non_eth():
    """Challenge harus ditolak untuk network selain ethereum."""
    acc  = Account.create()
    resp = get_challenge(acc.address, network="bitcoin")
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    msg = resp.json().get("message", "").lower()
    assert "belum didukung" in msg or "tidak didukung" in msg, \
        f"Pesan error tidak informatif: {resp.json()}"


def t3_challenge_rejects_invalid_address():
    """Challenge harus ditolak untuk address ETH yang tidak valid."""
    resp = get_challenge("0xinvalidaddress123")
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"


def t4_full_flow_wallet_found():
    """
    Full flow: challenge -> sign -> verify.
    Address didaftarkan ke PAKD dulu via input-manual.
    wallet_found harus True.
    """
    acc = Account.create()

    # Daftarkan address ke PAKD baru
    add_resp = requests.post(
        f"{BASE_URL}/api/input-manual",
        json={
            "id":              f"PAKD-T4-{acc.address[-6:]}",
            "nama":            "PT Test Wallet Proof T4",
            "wallets":         [{"network": "ethereum", "address": acc.address}],
            "aset_dilaporkan": 1_000_000_000,
        },
        timeout=10,
    )
    assert add_resp.status_code == 200, f"Gagal tambah PAKD: {add_resp.text}"
    pakd_id = add_resp.json()["data"]["id"]

    # Step 1: Minta challenge
    ch_resp = get_challenge(acc.address)
    assert ch_resp.status_code == 200, f"Challenge gagal: {ch_resp.text}"
    challenge_text = ch_resp.json()["challenge"]

    # Step 2: Sign dengan private key yang benar
    signature = sign_challenge(acc, challenge_text)

    # Step 3: Verify
    v_resp = verify(acc.address, signature, pakd_id=pakd_id)
    assert v_resp.status_code == 200, f"Verify gagal: {v_resp.text}"
    vdata = v_resp.json()
    assert vdata["verified"]     is True, f"verified harus True: {vdata}"
    assert vdata["wallet_found"] is True, f"wallet_found harus True: {vdata}"
    assert vdata["recovered"].lower() == acc.address.lower(), \
        f"recovered != address: {vdata['recovered']} vs {acc.address}"


def t5_full_flow_wallet_not_found():
    """
    Signature valid tapi address tidak ada di PAKD manapun.
    verified=True, wallet_found=False — keduanya harus independen.
    """
    acc = Account.create()

    ch_resp = get_challenge(acc.address)
    assert ch_resp.status_code == 200
    challenge_text = ch_resp.json()["challenge"]
    signature      = sign_challenge(acc, challenge_text)

    v_resp = verify(acc.address, signature)
    assert v_resp.status_code == 200, f"Verify gagal: {v_resp.text}"
    vdata = v_resp.json()
    assert vdata["verified"]     is True,  "verified harus True walau tidak ada di PAKD"
    assert vdata["wallet_found"] is False, "wallet_found harus False untuk address asing"


def t6_verify_without_challenge():
    """Verify tanpa challenge aktif harus ditolak dengan 400."""
    acc    = Account.create()
    v_resp = verify(acc.address, "0x" + "ab" * 65)
    assert v_resp.status_code == 400, f"Expected 400, got {v_resp.status_code}"
    msg = v_resp.json().get("message", "").lower()
    assert "challenge" in msg, f"Pesan error harus menyebut 'challenge': {msg}"


def t7_wrong_signer():
    """
    Skenario serangan: PAKD mengklaim wallet A tapi menandatangani dengan key B.
    Response harus 400, verified=False, recovered menunjuk ke B.
    """
    wallet_a = Account.create()   # address yang diklaim
    wallet_b = Account.create()   # actual signer (bukan pemilik)

    ch_resp = get_challenge(wallet_a.address)
    assert ch_resp.status_code == 200
    challenge_text = ch_resp.json()["challenge"]

    # Tandatangani dengan wallet B
    signature = sign_challenge(wallet_b, challenge_text)

    # Klaim sebagai wallet A
    v_resp = verify(wallet_a.address, signature)
    assert v_resp.status_code == 400, \
        f"Expected 400, got {v_resp.status_code}: {v_resp.text}"
    vdata = v_resp.json()
    assert vdata.get("verified") is False, "verified harus False untuk wrong signer"
    assert "recovered" in vdata, "Response harus sertakan recovered address"
    assert vdata["recovered"].lower() == wallet_b.address.lower(), \
        f"Recovered harus menunjuk ke wallet B: {vdata['recovered']}"


def t8_duplicate_challenge_overwrites():
    """
    Challenge kedua harus menginvalidasi challenge pertama.
    Signature dari challenge lama harus ditolak.
    """
    acc = Account.create()

    # Challenge pertama — sign tapi jangan submit dulu
    ch1_text = get_challenge(acc.address).json()["challenge"]
    sig1     = sign_challenge(acc, ch1_text)

    # Challenge kedua — overwrite yang pertama
    ch2_text = get_challenge(acc.address).json()["challenge"]
    sig2     = sign_challenge(acc, ch2_text)

    # sig1 tidak match dengan ch2 yang tersimpan — harus 400
    v_bad = verify(acc.address, sig1)
    assert v_bad.status_code == 400, \
        f"Signature challenge lama seharusnya ditolak, got {v_bad.status_code}: {v_bad.text}"

    # sig2 match — harus 200
    v_good = verify(acc.address, sig2)
    assert v_good.status_code == 200, \
        f"Signature challenge terbaru harus diterima, got {v_good.status_code}: {v_good.text}"
    assert v_good.json()["verified"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("PRIMA Hari 5 — Wallet Ownership Proof Test Suite")
    print("=" * 60)

    try:
        ping = requests.get(f"{BASE_URL}/api/status", timeout=5)
        print(f"Server: {ping.json()}\n")
    except Exception as e:
        print(f"[ERROR] Server tidak bisa dihubungi: {e}")
        print("Pastikan Flask sudah running: python app.py")
        sys.exit(1)

    run("[T1] Challenge fields lengkap",             t1_challenge_fields)
    run("[T2] Challenge tolak non-ethereum network", t2_challenge_rejects_non_eth)
    run("[T3] Challenge tolak address tidak valid",  t3_challenge_rejects_invalid_address)
    run("[T4] Full flow - wallet_found=True",        t4_full_flow_wallet_found)
    run("[T5] Full flow - wallet_found=False",       t5_full_flow_wallet_not_found)
    run("[T6] Verify tanpa challenge aktif",         t6_verify_without_challenge)
    run("[T7] Wrong signer ditolak",                 t7_wrong_signer)
    run("[T8] Duplicate challenge overwrite",        t8_duplicate_challenge_overwrites)

    print()
    print("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total  = len(results)
    print(f"Hasil: {passed}/{total} PASS")
    if passed == total:
        print("Status: SEMUA LULUS — siap commit")
    else:
        print("Status: ADA KEGAGALAN")
        for label, ok in results:
            if not ok:
                print(f"  - {label}")
    print("=" * 60)
    sys.exit(0 if passed == total else 1)
