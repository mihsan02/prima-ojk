
# test_day10_deployment_proof.py
# Day 10 — 6 tests: deployment health + wallet proof flow (unit, mocked)
# Target: 6/6 pass — brings suite to 55/55

import pytest
from unittest.mock import patch, MagicMock
import time

# ---------------------------------------------------------------------------
# Import app
# ---------------------------------------------------------------------------
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import app as prima


# ---------------------------------------------------------------------------
# Test 1: /api/status returns correct version string
# ---------------------------------------------------------------------------
def test_status_version():
    client = prima.app.test_client()
    resp   = client.get("/api/status")
    data   = resp.get_json()
    assert resp.status_code == 200
    assert data["status"]  == "ok"
    assert data["versi"]   == "1.9-pasal50-pasal91"


# ---------------------------------------------------------------------------
# Test 2: /api/wallet-challenge rejects unsupported network
# ---------------------------------------------------------------------------
def test_wallet_challenge_unsupported_network():
    client = prima.app.test_client()
    resp   = client.post(
        "/api/wallet-challenge",
        json={"address": "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq", "network": "bitcoin"},
        content_type="application/json",
    )
    data = resp.get_json()
    assert resp.status_code == 400
    assert data["status"] == "error"
    # Bitcoin is not in SUPPORTED_PROOF_NETWORKS (eth + sol only)
    assert "belum didukung" in data["message"]


# ---------------------------------------------------------------------------
# Test 3: /api/wallet-challenge issues challenge for valid ethereum address
# ---------------------------------------------------------------------------
def test_wallet_challenge_ethereum_issued():
    client  = prima.app.test_client()
    address = "0x28C6c06298d514Db089934071355E5743bf21d60"
    resp    = client.post(
        "/api/wallet-challenge",
        json={"address": address, "network": "ethereum"},
        content_type="application/json",
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["address"]  == address
    assert data["network"]  == "ethereum"
    assert "Nonce" in data["challenge"]
    assert data["expires_in"] == prima.CHALLENGE_TTL
    # Cleanup challenge store to avoid side effects on other tests
    prima.CHALLENGE_STORE.pop(address.lower(), None)


# ---------------------------------------------------------------------------
# Test 4: /api/wallet-challenge issues challenge for valid solana address
# ---------------------------------------------------------------------------
def test_wallet_challenge_solana_issued():
    client  = prima.app.test_client()
    address = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
    resp    = client.post(
        "/api/wallet-challenge",
        json={"address": address, "network": "solana"},
        content_type="application/json",
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["network"] == "solana"
    assert "Ed25519" in data["instruction"]
    prima.CHALLENGE_STORE.pop(address.lower(), None)


# ---------------------------------------------------------------------------
# Test 5: /api/wallet-verify returns 400 when no active challenge
# ---------------------------------------------------------------------------
def test_wallet_verify_no_active_challenge():
    client = prima.app.test_client()
    # Use an address guaranteed not to have an active challenge
    address = "0x000000000000000000000000000000000000dEaD"
    prima.CHALLENGE_STORE.pop(address.lower(), None)
    resp = client.post(
        "/api/wallet-verify",
        json={"address": address, "signature": "0xdeadbeef"},
        content_type="application/json",
    )
    data = resp.get_json()
    assert resp.status_code == 400
    assert data["status"] == "error"
    assert "challenge" in data["message"].lower()


# ---------------------------------------------------------------------------
# Test 6: /api/wallet-verify returns 400 when challenge is expired
# ---------------------------------------------------------------------------
def test_wallet_verify_expired_challenge():
    client  = prima.app.test_client()
    address = "0xAbCdEf0123456789AbCdEf0123456789AbCdEf01"
    # Inject an already-expired challenge directly into the store
    prima.CHALLENGE_STORE[address.lower()] = {
        "challenge": "PRIMA OJK test challenge",
        "network":   "ethereum",
        "expires":   time.time() - 1,   # already expired
    }
    resp = client.post(
        "/api/wallet-verify",
        json={"address": address, "signature": "0xdeadbeef"},
        content_type="application/json",
    )
    data = resp.get_json()
    assert resp.status_code == 400
    assert "expired" in data["message"].lower()
    # Store entry should have been removed by the route handler
    assert address.lower() not in prima.CHALLENGE_STORE