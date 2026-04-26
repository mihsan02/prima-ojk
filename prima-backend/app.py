from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import requests
import os
import json
from datetime import datetime
import re

app = Flask(__name__)
CORS(app)

ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
DATA_FILE = os.path.join(os.path.dirname(__file__), 'pakd_data.json')
AUDIT_FILE = os.path.join(os.path.dirname(__file__), 'audit_log.json')

WALLET_RE = re.compile(r'^0x[0-9a-fA-F]{40}$')

PAKD_DEFAULT = [
    {"id": "PAKD-OJK-001", "nama": "PT Indodax Nasional Indonesia", "wallets": ["0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"], "aset_dilaporkan": 9814800000},
    {"id": "PAKD-OJK-002", "nama": "PT Tokocrypto", "wallets": ["0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe"], "aset_dilaporkan": 3421000000}
]


def get_eth_price_idr():
    """Returns (price_idr: int, is_fallback: bool)."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=idr"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return 39_910_503, True
        data = response.json()
        return data["ethereum"]["idr"], False
    except Exception:
        return 39_910_503, True


def _migrate_record(p):
    """Migrate legacy eth_wallet string field to wallets array."""
    if "eth_wallet" in p and "wallets" not in p:
        p = dict(p)
        p["wallets"] = [p.pop("eth_wallet")]
    return p


def load_pakd():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            if data:
                return [_migrate_record(p) for p in data]
    except Exception:
        pass
    return list(PAKD_DEFAULT)


def save_pakd(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def write_audit(action, detail):
    try:
        logs = []
        if os.path.exists(AUDIT_FILE):
            with open(AUDIT_FILE, 'r') as f:
                logs = json.load(f)
        logs.insert(0, {"waktu": datetime.now().strftime("%d %b %Y, %H:%M"), "aksi": action, "detail": detail})
        logs = logs[:50]
        with open(AUDIT_FILE, 'w') as f:
            json.dump(logs, f, indent=2)
    except Exception:
        pass


def get_eth_balance(wallet_address):
    url = (
        f"https://api.etherscan.io/v2/api?chainid=1&module=account"
        f"&action=balance&address={wallet_address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
    )
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data["status"] == "1":
            return int(data["result"]) / 1e18
        return 0
    except Exception:
        return 0


def get_total_eth_balance(wallets):
    """Sum ETH balance across all wallet addresses for a PAKD."""
    return sum(get_eth_balance(w) for w in wallets)


def init_data():
    """Write seed data to pakd_data.json if the file is missing or empty."""
    try:
        if not os.path.exists(DATA_FILE):
            save_pakd(list(PAKD_DEFAULT))
            return
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        if not data:
            save_pakd(list(PAKD_DEFAULT))
    except Exception:
        save_pakd(list(PAKD_DEFAULT))


@app.route('/')
def index():
    response = send_from_directory('../prima-frontend', 'PRIMA Dashboard Standalone.html')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    return response


@app.route('/api/status')
def status():
    try:
        return jsonify({"status": "ok", "sistem": "PRIMA", "versi": "1.0"})
    except Exception as e:
        return jsonify({"status": "error", "message": "Status check gagal", "detail": str(e)}), 500


@app.route('/api/reconciliation')
def reconciliation():
    try:
        eth_price, harga_fallback = get_eth_price_idr()
        pakd_list = load_pakd()
        hasil = []
        for pakd in pakd_list:
            wallets = pakd["wallets"]
            eth_balance = get_total_eth_balance(wallets)
            aset_onchain_idr = eth_balance * eth_price
            aset_dilaporkan = pakd["aset_dilaporkan"]
            if aset_dilaporkan > 0:
                selisih = aset_onchain_idr - aset_dilaporkan
                deviasi_pct = selisih / aset_dilaporkan * 100
            else:
                selisih = 0
                deviasi_pct = 0
            surplus = aset_onchain_idr >= aset_dilaporkan
            if surplus:
                status_rec = "Aman"
            else:
                deficit_pct = abs(deviasi_pct)
                if deficit_pct < 5:
                    status_rec = "Aman"
                elif deficit_pct < 15:
                    status_rec = "Deviasi"
                else:
                    status_rec = "Kritis"
            hasil.append({
                "id": pakd["id"],
                "nama": pakd["nama"],
                "wallets": wallets,
                "wallet_count": len(wallets),
                "aset_onchain_idr": round(aset_onchain_idr),
                "aset_dilaporkan_idr": aset_dilaporkan,
                "deviasi_pct": round(deviasi_pct, 2),
                "surplus": surplus,
                "status": status_rec,
                "eth_balance": round(eth_balance, 4)
            })
        write_audit("REKONSILIASI", f"{len(hasil)} PAKD direkonsiliasi, harga ETH: Rp {eth_price:,}")
        return jsonify({
            "data": hasil,
            "total_pakd": len(hasil),
            "eth_price_idr": eth_price,
            "harga_fallback": harga_fallback
        })
    except Exception as e:
        return jsonify({"status": "error", "message": "Rekonsiliasi gagal", "detail": str(e)}), 500


@app.route('/api/stress-test')
def stress_test():
    try:
        eth_price, harga_fallback = get_eth_price_idr()
        pakd_list = load_pakd()
        skenario = {
            "mild":     {"label": "Mild (-30%)",     "penurunan": 0.30},
            "moderate": {"label": "Moderate (-55%)", "penurunan": 0.55},
            "severe":   {"label": "Severe (-80%)",   "penurunan": 0.80}
        }
        hasil = {}
        for key, s in skenario.items():
            lulus = 0
            gagal = 0
            eth_price_stressed = eth_price * (1 - s["penurunan"])
            for pakd in pakd_list:
                eth_balance = get_total_eth_balance(pakd["wallets"])
                aset_onchain_stressed = eth_balance * eth_price_stressed
                aset_dilaporkan = pakd["aset_dilaporkan"]
                if aset_dilaporkan > 0:
                    rasio = aset_onchain_stressed / aset_dilaporkan
                else:
                    rasio = 0
                if rasio >= 0.80:
                    lulus += 1
                else:
                    gagal += 1
            hasil[key] = {
                "label": s["label"],
                "lulus": lulus,
                "gagal": gagal,
                "total": len(pakd_list),
                "eth_price_stressed": round(eth_price_stressed)
            }
        write_audit("STRESS TEST", f"Stress test dijalankan untuk {len(pakd_list)} PAKD")
        return jsonify({"data": hasil, "eth_price_idr": eth_price, "harga_fallback": harga_fallback})
    except Exception as e:
        return jsonify({"status": "error", "message": "Stress test gagal", "detail": str(e)}), 500


@app.route('/api/input-manual', methods=['POST'])
def input_manual():
    try:
        body = request.get_json(silent=True)
        if not body:
            return jsonify({"status": "error", "message": "Request body tidak valid atau bukan JSON"}), 400

        nama = body.get('nama', '').strip() if isinstance(body.get('nama'), str) else ''
        pakd_id = body.get('id', '').strip() if isinstance(body.get('id'), str) else ''
        aset = body.get('aset_dilaporkan', None)

        # Accept wallets array; fall back to wrapping legacy eth_wallet string
        raw_wallets = body.get('wallets')
        if raw_wallets is None and 'eth_wallet' in body:
            eth_wallet = body.get('eth_wallet')
            raw_wallets = [eth_wallet] if isinstance(eth_wallet, str) else []

        if not nama:
            return jsonify({"status": "error", "message": "Field 'nama' wajib diisi"}), 400
        if not pakd_id:
            return jsonify({"status": "error", "message": "Field 'id' wajib diisi"}), 400
        if not isinstance(raw_wallets, list) or len(raw_wallets) < 1:
            return jsonify({"status": "error", "message": "Field 'wallets' wajib berupa array dengan minimal 1 alamat"}), 400
        for w in raw_wallets:
            if not isinstance(w, str) or not WALLET_RE.match(w):
                return jsonify({"status": "error", "message": f"Wallet '{w}' tidak valid. Harus berformat 0x diikuti 40 karakter hex"}), 400
        if aset is None or not isinstance(aset, (int, float)) or aset <= 0:
            return jsonify({"status": "error", "message": "Field 'aset_dilaporkan' harus berupa angka positif"}), 400

        pakd_list = load_pakd()
        for p in pakd_list:
            if p['id'] == pakd_id:
                return jsonify({"status": "error", "message": f"ID {pakd_id} sudah terdaftar"}), 400

        entry = {"id": pakd_id, "nama": nama, "wallets": raw_wallets, "aset_dilaporkan": int(aset)}
        pakd_list.append(entry)
        save_pakd(pakd_list)
        write_audit("INPUT MANUAL", f"{nama} ({pakd_id}) ditambahkan oleh OJK")
        return jsonify({"success": True, "message": f"{nama} berhasil ditambahkan", "data": entry})
    except Exception as e:
        return jsonify({"status": "error", "message": "Input manual gagal", "detail": str(e)}), 500


@app.route('/api/audit-log')
def audit_log():
    try:
        if not os.path.exists(AUDIT_FILE):
            return jsonify({"data": []})
        with open(AUDIT_FILE, 'r') as f:
            logs = json.load(f)
        return jsonify({"data": logs})
    except Exception as e:
        return jsonify({"status": "error", "message": "Gagal memuat audit log", "detail": str(e)}), 500


if __name__ == '__main__':
    init_data()
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug, port=5000)
