# PRIMA — Cheatsheet Tanda Tangan Challenge

Dokumen ini menunjukkan cara menandatangani challenge dari `/api/wallet-challenge` secara lokal untuk pengujian dan demo. Snippet menggunakan dependensi yang sama dengan backend PRIMA: `eth-account` untuk Ethereum dan `PyNaCl` untuk Solana.

## Persyaratan

```bash
pip install eth-account pynacl base58 requests
```

## Endpoint Live

- Production: `https://prima-ojk.onrender.com`
- Local dev: `http://localhost:5000`

## Ethereum (EIP-191 personal_sign)

```python
import requests
from eth_account import Account
from eth_account.messages import encode_defunct

API   = "https://prima-ojk.onrender.com"
PRIV  = "0x___REPLACE_DENGAN_PRIVATE_KEY_DEMO_WALLET___"

acct = Account.from_key(PRIV)
addr = acct.address

# 1. Minta challenge
r = requests.post(f"{API}/api/wallet-challenge", json={
    "address": addr,
    "network": "ethereum",
})
challenge = r.json()["challenge"]
print("challenge text:")
print(challenge)

# 2. Tanda tangani via EIP-191
signed = acct.sign_message(encode_defunct(text=challenge))
sig_hex = signed.signature.hex()
print("signature (paste ke modal):", sig_hex)

# 3. Verifikasi (atau lakukan via UI)
r = requests.post(f"{API}/api/wallet-verify", json={
    "address":   addr,
    "signature": sig_hex,
    "pakd_id":   "PAKD-OJK-001",
})
print(r.json())
```

## Solana (Ed25519, signMessage)

```python
import requests
import nacl.signing
import base58

API           = "https://prima-ojk.onrender.com"
SECRET_BASE58 = "___REPLACE_DENGAN_SECRET_KEY_BASE58___"  # 64-byte secret dari Phantom export

# Phantom secret key adalah 64 byte (32 seed + 32 pubkey). Ambil 32 byte pertama sebagai seed.
secret_bytes = base58.b58decode(SECRET_BASE58)
sk           = nacl.signing.SigningKey(secret_bytes[:32])
pk_bytes     = bytes(sk.verify_key)
addr         = base58.b58encode(pk_bytes).decode()

r = requests.post(f"{API}/api/wallet-challenge", json={
    "address": addr,
    "network": "solana",
})
challenge = r.json()["challenge"]

sig_bytes = sk.sign(challenge.encode("utf-8")).signature
sig_hex   = sig_bytes.hex()  # 128 karakter hex
print("signature:", sig_hex)

r = requests.post(f"{API}/api/wallet-verify", json={
    "address":   addr,
    "signature": sig_hex,
})
print(r.json())
```

## curl (manual)

```bash
# 1. Minta challenge
curl -X POST https://prima-ojk.onrender.com/api/wallet-challenge \
  -H "Content-Type: application/json" \
  -d '{"address":"0x28C6c06298d514Db089934071355E5743bf21d60","network":"ethereum"}'

# 2. Verifikasi signature
curl -X POST https://prima-ojk.onrender.com/api/wallet-verify \
  -H "Content-Type: application/json" \
  -d '{"address":"0x28C6...","signature":"0x...","pakd_id":"PAKD-OJK-001"}'
```

## Strategi Demo (Pitch 3 Menit)

Live signing dalam demo bisa makan 60 detik dan rawan error. Strategi yang direkomendasikan:

1. Sebelum demo, jalankan snippet Ethereum sekali untuk wallet demo dengan PRIVKEY yang sudah disiapkan. Catat: alamat wallet harus sudah terdaftar di `pakd_data.json`, dan jangan klik tombol Verify dulu.
2. Saat demo: klik tombol Verify di tabel PAKD. Modal terbuka, challenge muncul. Salin signature yang sudah dipersiapkan (dari clipboard atau dokumen). Tempel ke input. Klik Verifikasi. Badge berubah hijau.
3. Total durasi flow di panggung: 10-15 detik.

Catatan: challenge expired setelah 5 menit. Generate signature dalam jendela yang sama dengan demo, atau bersiap untuk regenerate.

## Catatan Keamanan

Private key dan secret key dalam snippet ini adalah wallet demo sekali pakai. Jangan commit file ini dengan key yang terisi. Tambahkan `.env` atau `secrets.json` ke `.gitignore`. Untuk produksi, integrasi langsung dengan MetaMask `eth_signTypedData_v4` atau Phantom adapter `signMessage` adalah pilihan yang lebih aman karena private key tidak pernah meninggalkan browser pengguna.

## Threat Model — Apa yang Wallet Proof Tidak Selesaikan

Wallet ownership proof menjawab satu pertanyaan: apakah PAKD memegang private key wallet yang dideklarasikan. Tidak menjawab:

1. Apakah dana di wallet itu benar-benar milik PAKD secara hukum, bukan custodial customer.
2. Apakah dana tetap ada setelah verifikasi. Verify hanya valid pada saat tanda tangan dibuat.
3. Apakah PAKD mengontrol seluruh wallet operasional, atau hanya yang dideklarasikan.

Mitigasi yang sudah ada di PRIMA: rekonsiliasi balance otomatis berkala dan audit log. Mitigasi yang harus ditambahkan oleh OJK secara kebijakan: kewajiban re-verifikasi tiap kuartal dan deklarasi lengkap seluruh wallet operasional dalam laporan E-reporting OJK sesuai POJK 27/2024.
