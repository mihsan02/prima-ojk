from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import requests
import os

app = Flask(__name__)
CORS(app)

ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
ETH_TO_IDR = 50000000

PAKD_DATA = [
    {
        "id": "PAKD-OJK-001",
        "nama": "PT Indodax Nasional Indonesia",
        "eth_wallet": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        "aset_dilaporkan": 9814800000
    },
    {
        "id": "PAKD-OJK-002",
        "nama": "PT Tokocrypto",
        "eth_wallet": "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
        "aset_dilaporkan": 3421000000
    }
]

def get_eth_balance(wallet_address):
    url = f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=balance&address={wallet_address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data["status"] == "1":
            return int(data["result"]) / 1e18
        return 0
    except:
        return 0

@app.route('/api/status')
def status():
    return jsonify({"status": "ok", "sistem": "PRIMA", "versi": "1.0"})

@app.route('/api/reconciliation')
def reconciliation():
    hasil = []
    for pakd in PAKD_DATA:
        eth_balance = get_eth_balance(pakd["eth_wallet"])
        aset_onchain_idr = eth_balance * ETH_TO_IDR
        aset_dilaporkan = pakd["aset_dilaporkan"]
        if aset_dilaporkan > 0:
            deviasi_pct = abs(aset_onchain_idr - aset_dilaporkan) / aset_dilaporkan * 100
        else:
            deviasi_pct = 100
        if deviasi_pct < 5:
            status_rec = "Aman"
        elif deviasi_pct < 15:
            status_rec = "Deviasi"
        else:
            status_rec = "Kritis"
        hasil.append({
            "id": pakd["id"],
            "nama": pakd["nama"],
            "aset_onchain_idr": round(aset_onchain_idr),
            "aset_dilaporkan_idr": aset_dilaporkan,
            "deviasi_pct": round(deviasi_pct, 2),
            "status": status_rec,
            "eth_balance": round(eth_balance, 4)
        })
    return jsonify({"data": hasil, "total_pakd": len(hasil)})

@app.route('/')
def index():
    return send_from_directory('../prima-frontend', 'index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
