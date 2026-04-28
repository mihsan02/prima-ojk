from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import requests
import os
import json
import tempfile
from datetime import datetime
import re
import time

app = Flask(__name__)
CORS(app)

SATOSHI_PER_BTC = 100_000_000
PRICE_CACHE     = {}
BALANCE_CACHE   = {}
PRICE_TTL       = 60
BALANCE_TTL     = 30

ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
DATA_FILE  = os.path.join(os.path.dirname(__file__), "pakd_data.json")
AUDIT_FILE = os.path.join(os.path.dirname(__file__), "audit_log.json")

WALLET_RE = {
    "ethereum": re.compile(r"^0x[0-9a-fA-F]{40}$"),
    "bitcoin":  re.compile(r"^(bc1[a-zA-Z0-9]{6,87}|[13][a-km-zA-HJ-NP-Z0-9]{25,34})$"),
    "solana":   re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$"),
}
SUPPORTED_NETWORKS = set(WALLET_RE.keys())

PAKD_DEFAULT = [
    {
        "id": "PAKD-OJK-001",
        "nama": "PT Indodax Nasional Indonesia",
        "wallets": [
            {"network": "ethereum", "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
             "verified": False, "verified_at": None}
        ],
        "aset_dilaporkan": 9814800000
    },
    {
        "id": "PAKD-OJK-002",
        "nama": "PT Tokocrypto",
        "wallets": [
            {"network": "ethereum", "address": "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
             "verified": False, "verified_at": None}
        ],
        "aset_dilaporkan": 3421000000
    }
]


# ---------------------------------------------------------------------------
# Data helpers (Day 1 — unchanged)
# ---------------------------------------------------------------------------

def _normalize_wallet_entry(w, default_network="ethereum"):
    if isinstance(w, str):
        return {"network": default_network, "address": w, "verified": False, "verified_at": None}
    if isinstance(w, dict):
        return {
            "network":     w.get("network", default_network),
            "address":     w.get("address", ""),
            "verified":    w.get("verified", False),
            "verified_at": w.get("verified_at", None),
        }
    return None


def _migrate_record(p):
    p = dict(p)
    if "eth_wallet" in p and "wallets" not in p:
        eth_addr = p.pop("eth_wallet")
        p["wallets"] = [{"network": "ethereum", "address": eth_addr, "verified": False, "verified_at": None}]
        return p
    if "wallets" in p and isinstance(p["wallets"], list):
        normalized = []
        for w in p["wallets"]:
            entry = _normalize_wallet_entry(w, default_network="ethereum")
            if entry:
                normalized.append(entry)
        p["wallets"] = normalized
    return p


def load_pakd():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
            if data:
                return [_migrate_record(p) for p in data]
    except Exception:
        pass
    return [dict(p) for p in PAKD_DEFAULT]


def save_pakd(data):
    dir_ = os.path.dirname(DATA_FILE) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, DATA_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_audit(action, detail):
    try:
        logs = []
        if os.path.exists(AUDIT_FILE):
            with open(AUDIT_FILE, "r") as f:
                logs = json.load(f)
        logs.insert(0, {"waktu": datetime.now().strftime("%d %b %Y, %H:%M"), "aksi": action, "detail": detail})
        logs = logs[:50]
        dir_ = os.path.dirname(AUDIT_FILE) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(logs, f, indent=2)
        os.replace(tmp_path, AUDIT_FILE)
    except Exception:
        pass


def validate_wallet_address(network, address):
    if network not in SUPPORTED_NETWORKS:
        return False, f"Network '{network}' tidak didukung. Pilih: {', '.join(sorted(SUPPORTED_NETWORKS))}"
    if not WALLET_RE[network].match(address):
        return False, f"Alamat '{address}' tidak valid untuk network {network}"
    return True, None


# ---------------------------------------------------------------------------
# Ethereum fetchers (Day 1 — unchanged)
# ---------------------------------------------------------------------------

def get_eth_price_idr():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=idr"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return 39_910_503, True
        return resp.json()["ethereum"]["idr"], False
    except Exception:
        return 39_910_503, True


def get_eth_balance(address):
    url = (f"https://api.etherscan.io/v2/api?chainid=1&module=account"
           f"&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}")
    try:
        data = requests.get(url, timeout=10).json()
        if data["status"] == "1":
            return int(data["result"]) / 1e18
        return 0
    except Exception:
        return 0


def get_total_eth_balance(wallets):
    total = 0
    for w in wallets:
        if isinstance(w, dict) and w.get("network") == "ethereum":
            total += get_eth_balance(w["address"])
        elif isinstance(w, str):
            total += get_eth_balance(w)
    return total


# ---------------------------------------------------------------------------
# Cache helpers (Day 2)
# ---------------------------------------------------------------------------

def get_cached_price(network, fetch_fn):
    """
    Return cached price for network. Calls fetch_fn only when cache is
    cold or older than PRICE_TTL seconds. Protects against CoinGecko
    rate limits during back-to-back reconciliations.
    """
    now = time.time()
    if network in PRICE_CACHE:
        cached_at, price = PRICE_CACHE[network]
        if now - cached_at < PRICE_TTL:
            return price
    price = fetch_fn()
    PRICE_CACHE[network] = (now, price)
    return price


def get_cached_balance(network, address, fetch_fn):
    """
    Return cached balance for (network, address). Calls fetch_fn only
    when cache is cold or older than BALANCE_TTL seconds.
    """
    now = time.time()
    key = (network, address)
    if key in BALANCE_CACHE:
        cached_at, balance = BALANCE_CACHE[key]
        if now - cached_at < BALANCE_TTL:
            return balance
    balance = fetch_fn()
    BALANCE_CACHE[key] = (now, balance)
    return balance


# ---------------------------------------------------------------------------
# Bitcoin fetchers (Day 2)
# ---------------------------------------------------------------------------

def fetch_btc_balance(address):
    """
    Fetch confirmed BTC balance from Blockstream Esplora public API.
    Returns float in BTC.

    Uses chain_stats only — mempool (unconfirmed) transactions are
    excluded because they cannot be counted as settled regulatory reserve.

    Source: https://github.com/Blockstream/esplora/blob/master/API.md
    """
    url = f"https://blockstream.info/api/address/{address}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    funded = data["chain_stats"]["funded_txo_sum"]
    spent  = data["chain_stats"]["spent_txo_sum"]
    return (funded - spent) / SATOSHI_PER_BTC


def fetch_btc_price_idr():
    """
    Fetch current BTC/IDR price from CoinGecko public API.
    Returns float (IDR per 1 BTC).
    """
    url = "https://api.coingecko.com/api/v3/simple/price"
    resp = requests.get(url, params={"ids": "bitcoin", "vs_currencies": "idr"}, timeout=10)
    resp.raise_for_status()
    return float(resp.json()["bitcoin"]["idr"])


# ---------------------------------------------------------------------------
# Unified multi-network balance fetcher (Day 2)
# ---------------------------------------------------------------------------

def get_total_balance_idr(wallets, eth_price_idr=None, btc_price_idr=None):
    """
    Fetch on-chain balance for all wallets across Ethereum and Bitcoin.
    Solana wallets are recorded with balance=0 and a note (Day 3 scope).

    Returns dict:
      total_idr       : float  — combined IDR value all networks
      eth_balance_idr : float  — ETH wallets subtotal in IDR
      btc_balance_idr : float  — BTC wallets subtotal in IDR
      breakdown       : list   — per-wallet detail
    """
    # Fetch prices once; injected values used in tests / stress-test caller
    if eth_price_idr is None:
        try:
            eth_price_idr = get_cached_price(
                "ethereum",
                lambda: get_eth_price_idr()[0]   # unwrap (price, fallback) tuple
            )
        except Exception:
            eth_price_idr = 39_910_503            # fallback same as get_eth_price_idr

    if btc_price_idr is None:
        try:
            btc_price_idr = get_cached_price("bitcoin", fetch_btc_price_idr)
        except Exception:
            btc_price_idr = 0.0

    total_idr     = 0.0
    eth_total_idr = 0.0
    btc_total_idr = 0.0
    breakdown     = []

    for wallet in wallets:
        network  = wallet.get("network", "ethereum")
        address  = wallet.get("address", "")
        verified = wallet.get("verified", False)

        entry = {
            "network":        network,
            "address":        address,
            "balance_native": 0.0,
            "native_unit":    "",
            "balance_idr":    0.0,
            "verified":       verified,
            "error":          None,
        }

        if network == "ethereum":
            entry["native_unit"] = "ETH"
            try:
                bal = get_cached_balance(
                    network, address,
                    lambda a=address: get_eth_balance(a)
                )
                entry["balance_native"] = bal
                entry["balance_idr"]    = bal * eth_price_idr
                eth_total_idr          += entry["balance_idr"]
            except Exception as e:
                entry["error"] = f"ETH fetch error: {e}"

        elif network == "bitcoin":
            entry["native_unit"] = "BTC"
            try:
                bal = get_cached_balance(
                    network, address,
                    lambda a=address: fetch_btc_balance(a)
                )
                entry["balance_native"] = round(bal, 8)
                entry["balance_idr"]    = bal * btc_price_idr
                btc_total_idr          += entry["balance_idr"]
            except Exception as e:
                entry["error"] = f"BTC fetch error: {e}"

        else:
            # Solana — Day 3
            entry["native_unit"] = "SOL"
            entry["error"]       = "Solana support: Day 3"

        total_idr += entry["balance_idr"]
        breakdown.append(entry)

    return {
        "total_idr":       total_idr,
        "eth_balance_idr": eth_total_idr,
        "btc_balance_idr": btc_total_idr,
        "breakdown":       breakdown,
    }


# ---------------------------------------------------------------------------
# Data init
# ---------------------------------------------------------------------------

def init_data():
    try:
        if not os.path.exists(DATA_FILE):
            save_pakd([dict(p) for p in PAKD_DEFAULT])
            return
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
        if not data:
            save_pakd([dict(p) for p in PAKD_DEFAULT])
    except Exception:
        save_pakd([dict(p) for p in PAKD_DEFAULT])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    resp = send_from_directory("../prima-frontend", "PRIMA Dashboard Standalone.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/api/status")
def status():
    return jsonify({"status": "ok", "sistem": "PRIMA", "versi": "1.2-multichain-btc"})


@app.route("/api/reconciliation")
def reconciliation():
    try:
        pakd_list = load_pakd()
        hasil = []

        for pakd in pakd_list:
            wallets = pakd["wallets"]

            # Day 2: use unified multi-network fetcher
            balance_result  = get_total_balance_idr(wallets)
            aset_onchain_idr = balance_result["total_idr"]
            aset_dilaporkan  = pakd["aset_dilaporkan"]

            if aset_dilaporkan > 0:
                selisih    = aset_onchain_idr - aset_dilaporkan
                deviasi_pct = selisih / aset_dilaporkan * 100
            else:
                selisih    = 0
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
                "id":                  pakd["id"],
                "nama":                pakd["nama"],
                "wallets":             wallets,
                "wallet_count":        len(wallets),
                "aset_onchain_idr":    round(aset_onchain_idr),
                "eth_balance_idr":     round(balance_result["eth_balance_idr"]),
                "btc_balance_idr":     round(balance_result["btc_balance_idr"]),
                "aset_dilaporkan_idr": aset_dilaporkan,
                "deviasi_pct":         round(deviasi_pct, 2),
                "surplus":             surplus,
                "status":              status_rec,
                "breakdown":           balance_result["breakdown"],
            })

        write_audit("REKONSILIASI", f"{len(hasil)} PAKD direkonsiliasi (multi-chain: ETH+BTC)")
        return jsonify({"data": hasil, "total_pakd": len(hasil)})

    except Exception as e:
        return jsonify({"status": "error", "message": "Rekonsiliasi gagal", "detail": str(e)}), 500


@app.route("/api/stress-test")
def stress_test():
    try:
        eth_price, harga_fallback = get_eth_price_idr()
        pakd_list = load_pakd()
        skenario = {
            "mild":     {"label": "Mild (-30%)",     "penurunan": 0.30},
            "moderate": {"label": "Moderate (-55%)", "penurunan": 0.55},
            "severe":   {"label": "Severe (-80%)",   "penurunan": 0.80},
        }
        hasil = {}
        for key, s in skenario.items():
            lulus = gagal = 0
            eth_price_stressed = eth_price * (1 - s["penurunan"])
            for pakd in pakd_list:
                # Day 2: pass stressed ETH price; BTC stress coming Day 4
                balance_result = get_total_balance_idr(
                    pakd["wallets"],
                    eth_price_idr=eth_price_stressed,
                    btc_price_idr=None   # BTC stressed separately in Day 4
                )
                aset_onchain_stressed = balance_result["total_idr"]
                aset_dilaporkan = pakd["aset_dilaporkan"]
                rasio = aset_onchain_stressed / aset_dilaporkan if aset_dilaporkan > 0 else 0
                if rasio >= 0.80:
                    lulus += 1
                else:
                    gagal += 1
            hasil[key] = {
                "label": s["label"], "lulus": lulus, "gagal": gagal,
                "total": len(pakd_list), "eth_price_stressed": round(eth_price_stressed)
            }
        write_audit("STRESS TEST", f"Stress test dijalankan untuk {len(pakd_list)} PAKD")
        return jsonify({"data": hasil, "eth_price_idr": eth_price, "harga_fallback": harga_fallback})
    except Exception as e:
        return jsonify({"status": "error", "message": "Stress test gagal", "detail": str(e)}), 500


@app.route("/api/input-manual", methods=["POST"])
def input_manual():
    try:
        body = request.get_json(silent=True)
        if not body:
            return jsonify({"status": "error", "message": "Request body tidak valid atau bukan JSON"}), 400
        nama    = body.get("nama", "").strip() if isinstance(body.get("nama"), str) else ""
        pakd_id = body.get("id", "").strip()   if isinstance(body.get("id"), str)   else ""
        aset    = body.get("aset_dilaporkan", None)
        if not nama:
            return jsonify({"status": "error", "message": "Field nama wajib diisi"}), 400
        if not pakd_id:
            return jsonify({"status": "error", "message": "Field id wajib diisi"}), 400
        if aset is None or not isinstance(aset, (int, float)) or aset <= 0:
            return jsonify({"status": "error", "message": "Field aset_dilaporkan harus berupa angka positif"}), 400
        raw_wallets = body.get("wallets")
        if raw_wallets is None and "eth_wallet" in body:
            eth_addr = body.get("eth_wallet")
            raw_wallets = [{"network": "ethereum", "address": eth_addr}] if isinstance(eth_addr, str) else []
        if not isinstance(raw_wallets, list) or len(raw_wallets) < 1:
            return jsonify({"status": "error", "message": "Field wallets wajib berupa array minimal 1 entry"}), 400
        canonical_wallets = []
        for w in raw_wallets:
            entry = _normalize_wallet_entry(w, default_network="ethereum")
            if not entry or not entry.get("address"):
                return jsonify({"status": "error", "message": "Setiap wallet entry harus punya field address"}), 400
            ok, err = validate_wallet_address(entry["network"], entry["address"])
            if not ok:
                return jsonify({"status": "error", "message": err}), 400
            canonical_wallets.append(entry)
        pakd_list = load_pakd()
        for p in pakd_list:
            if p["id"] == pakd_id:
                return jsonify({"status": "error", "message": f"ID {pakd_id} sudah terdaftar"}), 400
        new_entry = {"id": pakd_id, "nama": nama, "wallets": canonical_wallets, "aset_dilaporkan": int(aset)}
        pakd_list.append(new_entry)
        save_pakd(pakd_list)
        write_audit("INPUT MANUAL", f"{nama} ({pakd_id}) ditambahkan oleh OJK")
        return jsonify({"success": True, "message": f"{nama} berhasil ditambahkan", "data": new_entry})
    except Exception as e:
        return jsonify({"status": "error", "message": "Input manual gagal", "detail": str(e)}), 500


@app.route("/api/audit-log")
def audit_log():
    try:
        if not os.path.exists(AUDIT_FILE):
            return jsonify({"data": []})
        with open(AUDIT_FILE, "r") as f:
            logs = json.load(f)
        return jsonify({"data": logs})
    except Exception as e:
        return jsonify({"status": "error", "message": "Gagal memuat audit log", "detail": str(e)}), 500


if __name__ == "__main__":
    init_data()
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug, port=5000)
