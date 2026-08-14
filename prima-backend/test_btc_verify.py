"""
Sprint 3: Bitcoin P2PKH wallet verification test suite.

Test vectors are generated at test time via a sign-then-verify round trip
using the `ecdsa` library itself (no external bitcoin-cli/Electrum
dependency, matching how the rest of this test suite avoids network
calls).
"""
import base64

import pytest
from ecdsa import SigningKey, SECP256k1
from ecdsa.util import sigencode_string

from btc_verify import (
    verify_bitcoin_signature,
    _bitcoin_message_hash,
    _compress_pubkey,
    _pubkey_to_p2pkh_address,
    _recover_pubkey_candidates,
)


def _make_p2pkh_vector(message, compressed=True):
    """Generate a fresh keypair + valid Bitcoin Signed Message signature."""
    sk = SigningKey.generate(curve=SECP256k1)
    vk = sk.get_verifying_key()
    if compressed:
        pubkey_bytes = _compress_pubkey(vk)
    else:
        pubkey_bytes = b'\x04' + vk.to_string()
    address = _pubkey_to_p2pkh_address(pubkey_bytes)

    msg_hash = _bitcoin_message_hash(message)
    rs_bytes = sk.sign_digest(msg_hash, sigencode=sigencode_string)
    candidates = _recover_pubkey_candidates(msg_hash, rs_bytes)
    recovery_id = next(i for i, c in enumerate(candidates) if c.to_string() == vk.to_string())
    recovery_flag = (31 if compressed else 27) + recovery_id
    sig_bytes = bytes([recovery_flag]) + rs_bytes
    signature_b64 = base64.b64encode(sig_bytes).decode()
    return address, signature_b64


class TestP2PKHVerification:
    def test_p2pkh_valid_signature_compressed(self):
        message = "This is a test message"
        address, sig_b64 = _make_p2pkh_vector(message, compressed=True)
        verified, err = verify_bitcoin_signature(address, message, sig_b64)
        assert verified is True
        assert err is None

    def test_p2pkh_valid_signature_uncompressed(self):
        message = "Uncompressed pubkey test"
        address, sig_b64 = _make_p2pkh_vector(message, compressed=False)
        verified, err = verify_bitcoin_signature(address, message, sig_b64)
        assert verified is True
        assert err is None

    def test_p2pkh_invalid_signature(self):
        message = "This is a test message"
        address, sig_b64 = _make_p2pkh_vector(message)
        verified, err = verify_bitcoin_signature(address, "a different message entirely", sig_b64)
        assert verified is False
        assert err is not None

    def test_p2pkh_wrong_address(self):
        message = "This is a test message"
        _, sig_b64 = _make_p2pkh_vector(message)
        other_address = "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"
        verified, err = verify_bitcoin_signature(other_address, message, sig_b64)
        assert verified is False
        assert 'tidak cocok' in err

    def test_p2pkh_mismatched_compression_flag_rejected(self):
        message = "Compression flag mismatch"
        address, sig_b64 = _make_p2pkh_vector(message, compressed=False)
        sig_bytes = bytearray(base64.b64decode(sig_b64))
        sig_bytes[0] = sig_bytes[0] + 4  # flip uncompressed(27-30) -> compressed(31-34) range
        tampered = base64.b64encode(bytes(sig_bytes)).decode()
        verified, err = verify_bitcoin_signature(address, message, tampered)
        assert verified is False

    def test_invalid_signature_length(self):
        address = "1D8mYbc7YNg8E7ccpADutmqK8aemsX3i8V"
        short_sig = base64.b64encode(b'short').decode()
        verified, err = verify_bitcoin_signature(address, "msg", short_sig)
        assert verified is False
        assert 'Panjang signature' in err

    def test_invalid_base64_signature(self):
        address = "1D8mYbc7YNg8E7ccpADutmqK8aemsX3i8V"
        verified, err = verify_bitcoin_signature(address, "msg", "not-valid-base64!!!")
        assert verified is False
        assert err is not None

    def test_invalid_recovery_flag(self):
        address = "1D8mYbc7YNg8E7ccpADutmqK8aemsX3i8V"
        # byte 0 = 99 is outside both the 27-30 and 31-34 ranges
        bad_sig = base64.b64encode(bytes([99]) + b'\x00' * 64).decode()
        verified, err = verify_bitcoin_signature(address, "msg", bad_sig)
        assert verified is False
        assert 'Recovery flag' in err


class TestUnsupportedAddressTypes:
    def test_p2wpkh_returns_unsupported(self):
        verified, err = verify_bitcoin_signature(
            "bc1q0cgwerdvvnxnwlpzmfet2gq80flrsdnkhqhp6e", "msg", base64.b64encode(b'\x00' * 65).decode())
        assert verified is False
        assert 'P2WPKH' in err
        assert 'roadmap' in err.lower()

    def test_p2sh_returns_unsupported(self):
        verified, err = verify_bitcoin_signature(
            "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy", "msg", base64.b64encode(b'\x00' * 65).decode())
        assert verified is False
        assert 'P2SH' in err

    def test_p2tr_returns_unsupported(self):
        verified, err = verify_bitcoin_signature(
            "bc1pcjpx4xd6lje4drllupg54tmzetvth48gwvwarzk939hlw229xzyqtmn33q", "msg",
            base64.b64encode(b'\x00' * 65).decode())
        assert verified is False
        assert 'P2TR' in err

    def test_unknown_address_format(self):
        verified, err = verify_bitcoin_signature("2unknownformat", "msg", base64.b64encode(b'\x00' * 65).decode())
        assert verified is False
        assert 'tidak dikenali' in err


class TestWalletProofIntegration:
    """Integration through the real Flask /api/wallet-challenge + /api/wallet-verify endpoints."""

    def test_bitcoin_challenge_and_verify_roundtrip(self, client):
        import os
        import time
        import jwt as pyjwt
        from unittest.mock import patch

        secret = os.environ['SUPABASE_JWT_SECRET']
        token = pyjwt.encode(
            {'sub': 'admin-1', 'email': 'a@a.com', 'aud': 'authenticated',
             'iat': int(time.time()), 'exp': int(time.time()) + 3600},
            secret, algorithm='HS256')
        headers = {'Authorization': f'Bearer {token}'}

        def mock_profile(uid):
            return {'role': 'super_admin', 'entity_type': None, 'entity_id': None, 'display_name': 'Admin'}

        with patch('auth._fetch_user_profile', side_effect=mock_profile):
            sk = SigningKey.generate(curve=SECP256k1)
            vk = sk.get_verifying_key()
            address = _pubkey_to_p2pkh_address(_compress_pubkey(vk))

            r = client.post('/api/wallet-challenge', headers=headers,
                             json={'address': address, 'network': 'bitcoin'})
            assert r.status_code == 200
            challenge_text = r.get_json()['challenge']

            msg_hash = _bitcoin_message_hash(challenge_text)
            rs_bytes = sk.sign_digest(msg_hash, sigencode=sigencode_string)
            candidates = _recover_pubkey_candidates(msg_hash, rs_bytes)
            recovery_id = next(i for i, c in enumerate(candidates) if c.to_string() == vk.to_string())
            sig_bytes = bytes([31 + recovery_id]) + rs_bytes
            sig_b64 = base64.b64encode(sig_bytes).decode()

            with patch('app.load_pakd', return_value=[]), patch('app.save_pakd'):
                r2 = client.post('/api/wallet-verify', headers=headers,
                                  json={'address': address, 'signature': sig_b64})
            assert r2.status_code == 200
            assert r2.get_json()['signature_valid'] is True
            assert r2.get_json()['wallet_found'] is False

            # Challenge is single-use: replay must fail
            r3 = client.post('/api/wallet-verify', headers=headers,
                              json={'address': address, 'signature': sig_b64})
            assert r3.status_code == 400

    def test_bitcoin_challenge_rejects_non_p2pkh(self, client):
        import os
        import time
        import jwt as pyjwt
        from unittest.mock import patch

        secret = os.environ['SUPABASE_JWT_SECRET']
        token = pyjwt.encode(
            {'sub': 'admin-1', 'email': 'a@a.com', 'aud': 'authenticated',
             'iat': int(time.time()), 'exp': int(time.time()) + 3600},
            secret, algorithm='HS256')

        def mock_profile(uid):
            return {'role': 'super_admin', 'entity_type': None, 'entity_id': None, 'display_name': 'Admin'}

        with patch('auth._fetch_user_profile', side_effect=mock_profile):
            r = client.post('/api/wallet-challenge', headers={'Authorization': f'Bearer {token}'},
                             json={'address': 'bc1q0cgwerdvvnxnwlpzmfet2gq80flrsdnkhqhp6e', 'network': 'bitcoin'})
            assert r.status_code == 400
            assert 'P2WPKH' in r.get_json()['message'] or 'legacy' in r.get_json()['message']


@pytest.fixture
def client():
    import os
    os.environ.setdefault('ADMIN_TOKEN', 'test-token-prima')
    os.environ.setdefault('SUPABASE_JWT_SECRET', 'prima-test-jwt-secret-for-pytest-1234')
    from app import app as flask_app
    flask_app.config['TESTING'] = True
    flask_app.config['PROPAGATE_EXCEPTIONS'] = True
    with flask_app.test_client() as c:
        yield c
