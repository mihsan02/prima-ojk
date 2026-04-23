import requests

ETHERSCAN_API_KEY = "8AXPII6ETF898NUAQ13396JN15SPNRA4JE"
SOLSCAN_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjcmVhdGVkQXQiOjE3NzY5MTI2NTU4MTIsImVtYWlsIjoibXVoYW1tYWRpaHNhbnVkaW4wMkBnbWFpbC5jb20iLCJhY3Rpb24iOiJ0b2tlbi1hcGkiLCJhcGlWZXJzaW9uIjoidjIiLCJpYXQiOjE3NzY5MTI2NTV9.5RGxPPdZOlZIy4IfZ7KzmW6A_zWllhpMe9y1lXxQmtw "

def test_etherscan():
    wallet = "0x0681d8db095565fe8a346fa0277bffde9c0edbbf"
    url = f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=balance&address={wallet}&tag=latest&apikey={ETHERSCAN_API_KEY}"
    response = requests.get(url)
    data = response.json()
    print("Etherscan:", data)

def test_solana():
    address = "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"
    url = "https://api.mainnet-beta.solana.com"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [address]
    }
    response = requests.post(url, json=payload)
    print("Solana RPC status:", response.status_code)
    print("Solana RPC:", response.json())

test_etherscan()
test_solana()
