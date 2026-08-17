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


STABLECOIN_DECIMALS = 6


def fetch_erc20_balance(address, contract_address, decimals=STABLECOIN_DECIMALS):
    """Saldo token ERC-20 dalam satuan manusiawi (mis. 1000.50 USDT).

    Memakai tag=latest agar cocok dengan state rantai yang terkonfirmasi.
    Transfer pending dikecualikan -- alasan yang sama dengan mempool BTC
    dan commitment processed di SOL: transfer belum settle tidak boleh
    ikut dihitung sebagai cadangan.

    T1.4 (D2): Etherscan memakai status "0" untuk saldo nol asli DAN untuk
    galat. Versi lama mengembalikan 0.0 untuk keduanya, sehingga alamat
    tidak valid atau rate limit terbaca sebagai "tidak punya token".
    Sekarang hanya result literal "0" yang berarti nol; sisanya dilempar.

    Sumber:
        https://docs.etherscan.io/v2/api-endpoints/accounts#get-erc20-token-account-balance-for-tokencontractaddress
    """
    api_key = os.environ.get("ETHERSCAN_API_KEY", "")
    url = (
        f"https://api.etherscan.io/v2/api"
        f"?chainid=1"
        f"&module=account"
        f"&action=tokenbalance"
        f"&contractaddress={contract_address}"
        f"&address={address}"
        f"&tag=latest"
        f"&apikey={api_key}"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data["status"] == "1":
            return int(data["result"]) / (10 ** decimals)
    except Exception as exc:
        raise RuntimeError(f"ERC-20 balance fetch failed for {address} "
                           f"contract {contract_address}: {exc}") from exc

    # status != "1". result literal "0" = saldo nol yang benar-benar
    # dilaporkan; selain itu kegagalan yang tidak boleh menyamar jadi nol.
    result = data.get("result")
    if result == "0":
        return 0.0

    cause = data.get("message") or result or "unknown Etherscan error"
    raise RuntimeError(f"ERC-20 balance fetch failed for {address} "
                       f"contract {contract_address}: {cause}")
