from flask import Flask, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

ETHERSCAN_API_KEY = "8AXPII6ETF898NUAQ13396JN15SPNRA4JE"

PAKD_DATA = [
    {
        "id": "PAKD-OJK-001",
        "nama": "PT Indodax Nasional Indonesia",
        "eth_wallet": "0x0681d8db095565fe8a346fa0277bffde9c0edbbf",
        "aset_dilaporkan_idr": 9814800000000
    },
    {
        "id": "PAKD-OJK-002", 
        "nama": "PT Tokocrypto",
        "eth_wallet": "0x2b5634c42055806a59e9107ed44d43c426e58258",
        "aset_dilaporkan_idr": 3421000000000
    }
]

ETH_TO_IDR = 50000000

def get_eth_balance(wallet):
    url = f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=balance&address={wallet}&tag=latest&apikey={ETHERSCAN_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data["status"] == "1":
            return int(data["result"]) / 1e18
        return 0
    except:
        return 0

@app.route("/api/status")
def status():
    return jsonify({"status": "ok", "sistem": "PRIMA", "versi": "1.0"})

@app.route("/api/reconciliation")
def reconciliation():
    hasil = []
    for pakd in PAKD_DATA:
        eth_balance = get_eth_balance(pakd["eth_wallet"])
        aset_onchain_idr = eth_balance * ETH_TO_IDR
        aset_dilaporkan = pakd["aset_dilaporkan_idr"]
        
        if aset_dilaporkan > 0:
            deviasi_pct = abs(aset_onchain_idr - aset_dilaporkan) / aset_dilaporkan * 100
        else:
            deviasi_pct = 0

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

if __name__ == "__main__":
    app.run(debug=True, port=5000)
