"""Bitcoin wallet ownership verification (legacy P2PKH signmessage only).

Scope: P2PKH ("1...") addresses using the standard Bitcoin Signed Message
format (BIP-137 style recovery-flag signatures), verified with the pure
Python `ecdsa` library (no external C deps, no `buidl`/BIP-322 support).

P2WPKH ("bc1q..."), P2SH ("3..."), and P2TR ("bc1p...") are out of scope
for this pass and return a descriptive "not yet supported" message
instead of attempting verification.
"""

import base64
import hashlib
import struct

from ecdsa import SECP256k1, VerifyingKey
from ecdsa.keys import MalformedPointError


def verify_bitcoin_signature(address: str, message: str, signature_b64: str):
    """Verify a Bitcoin Signed Message signature against a claimed address.

    Returns (verified: bool, error: str | None).
    """
    if address.startswith("1"):
        return _verify_p2pkh(address, message, signature_b64)
    elif address.startswith("bc1q"):
        return False, "P2WPKH (SegWit) verification belum didukung (roadmap Phase 2)"
    elif address.startswith("3"):
        return False, "P2SH address verification belum didukung (roadmap Phase 2)"
    elif address.startswith("bc1p"):
        return False, "P2TR (Taproot) verification belum didukung (roadmap Phase 2)"
    else:
        return False, f"Format alamat Bitcoin tidak dikenali: {address[:8]}..."


def _verify_p2pkh(address: str, message: str, signature_b64: str):
    try:
        sig_bytes = base64.b64decode(signature_b64, validate=True)
    except Exception as e:
        return False, f"Signature bukan base64 valid: {e}"

    if len(sig_bytes) != 65:
        return False, f"Panjang signature tidak valid: {len(sig_bytes)} bytes (expected 65)"

    recovery_flag = sig_bytes[0]
    if 27 <= recovery_flag <= 30:
        compressed = False
    elif 31 <= recovery_flag <= 34:
        compressed = True
    else:
        return False, f"Recovery flag tidak valid: {recovery_flag}"

    rs_bytes = sig_bytes[1:65]

    try:
        msg_hash = _bitcoin_message_hash(message)
        candidates = _recover_pubkey_candidates(msg_hash, rs_bytes)
        if not candidates:
            return False, "Gagal recover public key dari signature"
    except Exception as e:
        return False, f"P2PKH verification error: {e}"

    for vk in candidates:
        try:
            if compressed:
                pubkey_bytes = _compress_pubkey(vk)
            else:
                pubkey_bytes = b"\x04" + vk.to_string()
            derived_address = _pubkey_to_p2pkh_address(pubkey_bytes)
        except Exception:
            continue
        if derived_address == address:
            return True, None

    return False, f"Alamat tidak cocok dengan signature (expected {address})"


def _bitcoin_message_hash(message: str) -> bytes:
    """Double SHA-256 of a message in the Bitcoin Signed Message format."""
    prefix = b"\x18Bitcoin Signed Message:\n"
    msg_bytes = message.encode("utf-8")
    length_varint = _encode_varint(len(msg_bytes))
    full_msg = prefix + length_varint + msg_bytes
    return hashlib.sha256(hashlib.sha256(full_msg).digest()).digest()


def _encode_varint(n: int) -> bytes:
    if n < 0xFD:
        return struct.pack("<B", n)
    elif n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    elif n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    else:
        return b"\xff" + struct.pack("<Q", n)


def _recover_pubkey_candidates(msg_hash: bytes, rs_bytes: bytes):
    """Recover the (typically two) candidate public keys for a signature.

    The recovery-flag byte only tells us compressed-vs-uncompressed and the
    y-parity bucket, not which of ecdsa's returned candidates corresponds to
    it — rather than rely on library-internal ordering, the caller checks
    every candidate against the claimed address.
    """
    try:
        return VerifyingKey.from_public_key_recovery_with_digest(
            rs_bytes, msg_hash, curve=SECP256k1, hashfunc=hashlib.sha256,
        )
    except MalformedPointError:
        return []


def _compress_pubkey(vk) -> bytes:
    point = vk.pubkey.point
    prefix = b"\x02" if point.y() % 2 == 0 else b"\x03"
    return prefix + point.x().to_bytes(32, "big")


def _pubkey_to_p2pkh_address(pubkey_bytes: bytes) -> str:
    sha = hashlib.sha256(pubkey_bytes).digest()
    ripemd = hashlib.new("ripemd160", sha).digest()
    versioned = b"\x00" + ripemd  # mainnet P2PKH prefix
    checksum = hashlib.sha256(hashlib.sha256(versioned).digest()).digest()[:4]
    return _base58_encode(versioned + checksum)


def _base58_encode(data: bytes) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n = int.from_bytes(data, "big")
    result = ""
    while n > 0:
        n, remainder = divmod(n, 58)
        result = alphabet[remainder] + result
    for byte in data:
        if byte == 0:
            result = "1" + result
        else:
            break
    return result
