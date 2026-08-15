"""Lapisan akuisisi data on-chain.

Dipisah dari app.py pada T1.1 (D1). Aturan modul ini: fetcher TIDAK
mengembalikan nilai sentinel saat gagal. Kegagalan dilempar sebagai
RuntimeError dengan pesan yang menyebut sumbernya, supaya pemanggil
tidak pernah salah membaca kegagalan jaringan sebagai saldo nol.
"""

import os

import requests


def get_eth_balance(address):
    """Saldo ETH native dalam satuan ETH.

    Melempar RuntimeError kalau saldo tidak bisa dipastikan. Satu-satunya
    nilai nol yang dikembalikan adalah nol yang benar-benar dilaporkan
    Etherscan, bukan nol karena gagal.
    """
    api_key = os.environ.get("ETHERSCAN_API_KEY", "")
    url = (f"https://api.etherscan.io/v2/api?chainid=1&module=account"
           f"&action=balance&address={address}&tag=latest&apikey={api_key}")
    try:
        data = requests.get(url, timeout=10).json()
        if data["status"] == "1":
            return int(data["result"]) / 1e18
    except Exception as exc:
        raise RuntimeError(f"ETH balance fetch failed for {address}: {exc}") from exc

    # status != "1". Etherscan memakai status "0" untuk galat DAN untuk
    # sebagian balasan sah; result literal "0" berarti saldo nol asli.
    result = data.get("result")
    if result == "0":
        return 0.0

    cause = data.get("message") or result or "unknown Etherscan error"
    raise RuntimeError(f"ETH balance fetch failed for {address}: {cause}")
