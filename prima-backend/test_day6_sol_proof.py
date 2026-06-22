"""
test_day6_sol_proof.py
─────────────────────────────────────────────────────────────────────────────
Test suite: Solana Ed25519 wallet ownership proof
Endpoints: POST /api/wallet-challenge  (Solana branch)
           POST /api/wallet-verify     (Solana Ed25519 branch)

Signing mechanics:
  Solana uses Ed25519. Unlike Ethereum ECDSA, Ed25519 is not recoverable —
  the verifier needs the public key explicitly. Here, the wallet address IS
  the base58-encoded 32-byte Ed25519 public key.

  Server flow:
    1. Decode address (base58 → 32 bytes) → VerifyKey
    2. Decode signature (hex 128 chars → 64 bytes)
    3. VerifyKey.verify(challenge_utf8, sig_bytes)
    4. BadSignatureError → reject; success → mark wallet verified

Test coverage:
    [W1]  Challenge issued for Solana address — correct fields returned
    [W2]  Challenge text includes address, network="solana", nonce, timestamp
    [W3]  Verify succeeds with correct Ed25519 signature (good path)
    [W4]  Verify fails with corrupted signature (wrong signer equivalent)
    [W5]  Verify fails when no challenge exists for address
    [W6]  Verify fails after challenge expires (TTL overridden to past)
    [W7]  wallet-challenge rejects unknown network (not ethereum/solana)
    [W8]  wallet-challenge rejects invalid Solana address format
    [W9]  wallet-verify rejects unparseable signature (not hex, not base64)
    [W10] wallet-verify accepts base64-encoded signature (compatibility branch)
    [W11] PAKD_DEFAULT now has 3 entries (not 2)
    [W12] All PAKD_DEFAULT wallets have realistic (non-Vitalik) addresses

Run:
    cd prima-backend
    python -m pytest test_day6_sol_proof.py -v
"""

import os
import time
import base64
import pytest
import nacl.signing
import base58
from unittest.mock import patch
from app import app as flask_app, CHALLENGE_STORE, PAKD_DEFAULT

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        original_open = c.open
        def patched_open(*args, **kwargs):
            headers = dict(kwargs.get('headers') or {})
            headers.setdefault('X-Admin-Token', os.environ.get('ADMIN_TOKEN', 'test-token-prima'))
            kwargs['headers'] = headers
            return original_open(*args, **kwargs)
        c.open = patched_open
        yield c


def make_sol_keypair():
    """
    Generate a fresh Ed25519 keypair and return (address_base58, signing_key).
    address_base58 is a valid Solana wallet address (base58 pubkey).
    """
    sk  = nacl.signing.SigningKey.generate()
    addr = base58.b58encode(sk.verify_key.encode()).decode()
    return addr, sk


def sign_challenge(signing_key, challenge_text):
    """Sign challenge as UTF-8 bytes; return hex-encoded 64-byte signature."""
    sig_bytes = signing_key.sign(challenge_text.encode("utf-8")).signature
    return sig_bytes.hex()


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_w1_challenge_issued_for_solana(client):
    """[W1] Challenge endpoint returns address, network, challenge, expires_in."""
    addr, _ = make_sol_keypair()
    resp = client.post("/api/wallet-challenge", json={"address": addr, "network": "solana"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["address"]     == addr
    assert data["network"]     == "solana"
    assert "challenge"         in data
    assert data["expires_in"]  == 300
    # Cleanup
    CHALLENGE_STORE.pop(addr.lower(), None)


def test_w2_challenge_text_contents(client):
    """[W2] Challenge body contains address, network, nonce, timestamp."""
    addr, _ = make_sol_keypair()
    resp = client.post("/api/wallet-challenge", json={"address": addr, "network": "solana"})
    challenge = resp.get_json()["challenge"]
    assert addr     in challenge
    assert "solana" in challenge
    assert "Nonce"  in challenge
    assert "Timestamp" in challenge
    CHALLENGE_STORE.pop(addr.lower(), None)


def test_w3_verify_succeeds_correct_signature(client):
    """[W3] Full round-trip: issue challenge → sign → verify → verified=True."""
    addr, sk = make_sol_keypair()

    # Issue challenge
    r1 = client.post("/api/wallet-challenge", json={"address": addr, "network": "solana"})
    challenge_text = r1.get_json()["challenge"]

    # Sign
    sig_hex = sign_challenge(sk, challenge_text)

    # Verify
    r2 = client.post("/api/wallet-verify", json={
        "address":   addr,
        "signature": sig_hex,
        "pakd_id":   "",
    })
    assert r2.status_code == 200
    body = r2.get_json()
    assert body["verified"] is True
    assert body["address"]  == addr
    assert body["network"]  == "solana"


def test_w4_verify_fails_corrupted_signature(client):
    """[W4] Signature from a DIFFERENT key → verify must reject (400)."""
    addr, sk_owner = make_sol_keypair()
    _,    sk_other  = make_sol_keypair()

    r1 = client.post("/api/wallet-challenge", json={"address": addr, "network": "solana"})
    challenge_text = r1.get_json()["challenge"]

    # Sign with wrong key
    bad_sig = sign_challenge(sk_other, challenge_text)

    r2 = client.post("/api/wallet-verify", json={
        "address":   addr,
        "signature": bad_sig,
    })
    assert r2.status_code == 400
    body = r2.get_json()
    assert body["verified"] is False
    # Challenge must be consumed even on failure (prevent replay)
    assert addr.lower() not in CHALLENGE_STORE


def test_w5_verify_fails_no_active_challenge(client):
    """[W5] Verify without a prior challenge → 400 with informative message."""
    addr, sk = make_sol_keypair()
    # No call to wallet-challenge
    dummy_sig = "ab" * 64  # 128 hex chars, syntactically valid
    r = client.post("/api/wallet-verify", json={"address": addr, "signature": dummy_sig})
    assert r.status_code == 400
    assert "challenge aktif" in r.get_json()["message"]


def test_w6_verify_fails_after_expiry(client):
    """[W6] Challenge marked as expired in store → 400 expired message."""
    addr, sk = make_sol_keypair()

    r1 = client.post("/api/wallet-challenge", json={"address": addr, "network": "solana"})
    challenge_text = r1.get_json()["challenge"]

    # Force expiry
    CHALLENGE_STORE[addr.lower()]["expires"] = time.time() - 1

    sig_hex = sign_challenge(sk, challenge_text)
    r2 = client.post("/api/wallet-verify", json={"address": addr, "signature": sig_hex})
    assert r2.status_code == 400
    assert "expired" in r2.get_json()["message"].lower()


def test_w7_challenge_rejects_unknown_network(client):
    """[W7] Network other than ethereum/solana → 400 with supported list."""
    addr, _ = make_sol_keypair()
    r = client.post("/api/wallet-challenge", json={"address": addr, "network": "tron"})
    assert r.status_code == 400
    assert "tron" in r.get_json()["message"]


def test_w8_challenge_rejects_invalid_solana_address(client):
    """[W8] Malformed address string → 400 from validate_wallet_address."""
    r = client.post("/api/wallet-challenge", json={
        "address": "0xNOT_A_SOLANA_ADDRESS",
        "network": "solana",
    })
    assert r.status_code == 400


def test_w9_verify_rejects_garbage_signature(client):
    """[W9] Signature is not hex and not valid base64 → 400 parse error."""
    addr, sk = make_sol_keypair()
    client.post("/api/wallet-challenge", json={"address": addr, "network": "solana"})

    r = client.post("/api/wallet-verify", json={
        "address":   addr,
        "signature": "this-is-not-a-signature!!!",
    })
    assert r.status_code == 400
    CHALLENGE_STORE.pop(addr.lower(), None)


def test_w10_verify_accepts_base64_signature(client):
    """[W10] Base64-encoded signature is also accepted (wallet adapter compat)."""
    addr, sk = make_sol_keypair()

    r1 = client.post("/api/wallet-challenge", json={"address": addr, "network": "solana"})
    challenge_text = r1.get_json()["challenge"]

    # Sign and encode as base64 instead of hex
    sig_bytes  = sk.sign(challenge_text.encode("utf-8")).signature
    sig_b64    = base64.b64encode(sig_bytes).decode()

    r2 = client.post("/api/wallet-verify", json={
        "address":   addr,
        "signature": sig_b64,
    })
    assert r2.status_code == 200
    assert r2.get_json()["verified"] is True


# ─────────────────────────────────────────────────────────────────────────────
# PAKD_DEFAULT sanity checks
# ─────────────────────────────────────────────────────────────────────────────

VITALIK  = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
ETH_FOUND = "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe"

def test_w11_pakd_default_has_required_entries():
    """[W11] PAKD_DEFAULT contains at least 3 valid entries with required fields."""
    assert len(PAKD_DEFAULT) >= 3, (
        f"Expected at least 3 PAKD entries, got {len(PAKD_DEFAULT)}. "
        "Tambahkan entitas ke PAKD_DEFAULT."
    )
    required_fields = {"id", "nama", "wallets", "aset_dilaporkan"}
    for idx, pakd in enumerate(PAKD_DEFAULT):
        missing = required_fields - set(pakd.keys())
        assert not missing, (
            f"PAKD_DEFAULT[{idx}] missing fields: {missing}"
        )
        assert isinstance(pakd["wallets"], list) and len(pakd["wallets"]) >= 1, (
            f"PAKD_DEFAULT[{idx}] ({pakd.get('id')}) must have at least 1 wallet"
        )
        assert isinstance(pakd["aset_dilaporkan"], int) and pakd["aset_dilaporkan"] >= 0, (
            f"PAKD_DEFAULT[{idx}] ({pakd.get('id')}) aset_dilaporkan must be non-negative int"
        )


def test_w12_pakd_default_no_vitalik_addresses():
    """[W12] Vitalik and Ethereum Foundation placeholder addresses removed."""
    all_addresses = [
        w["address"].lower()
        for p in PAKD_DEFAULT
        for w in p.get("wallets", [])
    ]
    assert VITALIK.lower()   not in all_addresses, "Vitalik address masih ada di PAKD_DEFAULT"
    assert ETH_FOUND.lower() not in all_addresses, "Ethereum Foundation address masih ada di PAKD_DEFAULT"
    # All addresses should be non-empty strings
    for addr in all_addresses:
        assert len(addr) > 10, f"Address terlalu pendek: {addr}"
