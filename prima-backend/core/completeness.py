from core.pricing import kelengkapan_dari_provenance


def hitung_kelengkapan(
    entries: list[dict],
    provenance_harga: dict[str, dict | None],
    as_of: str,
) -> dict:
    def _harga_gagal(prov):
        if prov is None:
            return True
        return kelengkapan_dari_provenance(prov) == "SEBAGIAN"

    gagal_saldo = [e for e in entries if e.get("error") is not None]
    jaringan_terdampak = {
        e.get("network") for e in entries
        if (e.get("balance_native") or 0) > 0
    }
    gagal_harga = [
        net for net in sorted(jaringan_terdampak)
        if _harga_gagal(provenance_harga.get(net))
    ]

    sumber_gagal = []
    for e in gagal_saldo:
        sumber_gagal.append({
            "jenis": "saldo",
            "network": e.get("network"),
            "address": e.get("address"),
            "sebab": e.get("error"),
        })
    for net in gagal_harga:
        prov = provenance_harga.get(net)
        if prov is None:
            sebab = "provenance harga tidak tersedia"
        else:
            sebab = f"sumber={prov.get('sumber')} umur_detik={prov.get('umur_detik')}"
        sumber_gagal.append({
            "jenis": "harga", "network": net,
            "address": None, "sebab": sebab,
        })

    ada_kegagalan = bool(gagal_saldo) or bool(gagal_harga)
    semua_saldo_gagal = (len(entries) == 0
                         or len(gagal_saldo) == len(entries))

    status = "TIDAK_TERSEDIA" if semua_saldo_gagal else \
             "SEBAGIAN" if ada_kegagalan else "LENGKAP"

    return {
        "status": status,
        "sumber_gagal": sumber_gagal,
        "provenance_harga": provenance_harga,
        "as_of": as_of,
    }
