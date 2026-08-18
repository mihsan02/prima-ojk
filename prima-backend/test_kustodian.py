"""
Sprint 2: Kustodian CRUD test suite.
Tests auth/role enforcement (mocked DB) + endpoint contract validation.
"""
import os
import time
import json
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault('ADMIN_TOKEN', 'test-token-prima')
os.environ.setdefault('SUPABASE_JWT_SECRET', 'prima-test-jwt-secret-for-pytest-1234')

from app import app as flask_app

JWT_SECRET = os.environ['SUPABASE_JWT_SECRET']

MOCK_PROFILES = {
    'admin-001': {'role': 'super_admin', 'entity_type': None, 'entity_id': None, 'display_name': 'Super Admin'},
    'pengawas-001': {'role': 'pengawas', 'entity_type': None, 'entity_id': None, 'display_name': 'Pengawas IAKD'},
    'pakd-001': {'role': 'pakd', 'entity_type': 'PAKD', 'entity_id': 'PAKD-DEMO-001', 'display_name': 'Alpha Kripto'},
    'kustodian-001': {'role': 'kustodian', 'entity_type': 'KUSTODIAN', 'entity_id': 'KUST-001', 'display_name': 'Kustodian Test'},
}

def _mock_fetch_profile(user_id):
    return MOCK_PROFILES.get(user_id)

def _make_token(user_id='admin-001', expired=False):
    import jwt as pyjwt
    now = int(time.time())
    exp = now - 10 if expired else now + 3600
    payload = {'sub': user_id, 'email': f'{user_id}@test.com', 'aud': 'authenticated', 'iat': now, 'exp': exp}
    return pyjwt.encode(payload, JWT_SECRET, algorithm='HS256')


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    flask_app.config['PROPAGATE_EXCEPTIONS'] = True
    with flask_app.test_client() as c:
        yield c


def _make_mock_conn(query_results=None):
    """Create a mock DB connection that returns configurable results."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    if query_results:
        mock_cur.fetchone.side_effect = query_results.get('fetchone', [None])
        mock_cur.fetchall.side_effect = query_results.get('fetchall', [[]])
    else:
        mock_cur.fetchone.return_value = None
        mock_cur.fetchall.return_value = []
    return mock_conn


class TestKustodianAuth:
    def test_list_requires_auth(self, client):
        resp = client.get('/api/kustodian')
        assert resp.status_code == 401

    def test_pengawas_cannot_create(self, client):
        token = _make_token('pengawas-001')
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            resp = client.post('/api/kustodian',
                               headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                               json={'id': 'KUST-X', 'nama': 'Fail'})
            assert resp.status_code == 403

    def test_pengawas_cannot_update(self, client):
        token = _make_token('pengawas-001')
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            resp = client.put('/api/kustodian/KUST-001',
                              headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                              json={'nama': 'Nope'})
            assert resp.status_code == 403

    def test_pengawas_cannot_delete(self, client):
        token = _make_token('pengawas-001')
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            resp = client.delete('/api/kustodian/KUST-001',
                                 headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code == 403

    def test_pakd_cannot_create(self, client):
        token = _make_token('pakd-001')
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            resp = client.post('/api/kustodian',
                               headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                               json={'id': 'KUST-X', 'nama': 'Fail'})
            assert resp.status_code == 403

    def test_expired_token_rejected(self, client):
        token = _make_token('admin-001', expired=True)
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            resp = client.get('/api/kustodian',
                              headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code == 401


class TestKustodianCRUDWithMockDB:
    def test_list_returns_json_array(self, client):
        token = _make_token('admin-001')
        mock_conn = _make_mock_conn({'fetchall': [
            [('KUST-001', 'PT Kustodian Aset Prima', '2026-01-01', '2026-01-01')],
            [('PAKD-DEMO-001',)],
            [('ethereum', '0xDFd5293D8e347dFe59E90eFd55b2956a1343963d', True, None, None)],
        ]})
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile), \
             patch('app._get_db_conn', return_value=mock_conn), \
             patch('app._return_db_conn'):
            resp = client.get('/api/kustodian',
                              headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code == 200
            data = resp.get_json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]['id'] == 'KUST-001'
            assert data[0]['pakd_ids'] == ['PAKD-DEMO-001']

    def test_create_missing_fields_returns_400(self, client):
        token = _make_token('admin-001')
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            resp = client.post('/api/kustodian',
                               headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                               json={'nama': 'NoID'})
            assert resp.status_code == 400

    def test_create_success(self, client):
        token = _make_token('admin-001')
        mock_conn = _make_mock_conn({'fetchone': [None, None]})
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile), \
             patch('app._get_db_conn', return_value=mock_conn), \
             patch('app._return_db_conn'), \
             patch('app.write_audit'):
            resp = client.post('/api/kustodian',
                               headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                               json={'id': 'KUST-NEW', 'nama': 'New Kustodian', 'pakd_ids': ['PAKD-DEMO-001'], 'wallets': []})
            assert resp.status_code == 201
            data = resp.get_json()
            assert data['id'] == 'KUST-NEW'

    def test_create_duplicate_returns_409(self, client):
        token = _make_token('admin-001')
        mock_conn = _make_mock_conn({'fetchone': [('KUST-001',)]})
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile), \
             patch('app._get_db_conn', return_value=mock_conn), \
             patch('app._return_db_conn'):
            resp = client.post('/api/kustodian',
                               headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                               json={'id': 'KUST-001', 'nama': 'Dup'})
            assert resp.status_code == 409

    def test_update_not_found_returns_404(self, client):
        token = _make_token('admin-001')
        mock_conn = _make_mock_conn({'fetchone': [None]})
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile), \
             patch('app._get_db_conn', return_value=mock_conn), \
             patch('app._return_db_conn'):
            resp = client.put('/api/kustodian/KUST-NONE',
                              headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                              json={'nama': 'X'})
            assert resp.status_code == 404

    def test_delete_not_found_returns_404(self, client):
        token = _make_token('admin-001')
        mock_conn = _make_mock_conn({'fetchone': [None]})
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile), \
             patch('app._get_db_conn', return_value=mock_conn), \
             patch('app._return_db_conn'):
            resp = client.delete('/api/kustodian/KUST-NONE',
                                 headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code == 404

    def test_delete_success(self, client):
        token = _make_token('admin-001')
        mock_conn = _make_mock_conn({'fetchone': [('KUST-001',)]})
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile), \
             patch('app._get_db_conn', return_value=mock_conn), \
             patch('app._return_db_conn'), \
             patch('app.write_audit'):
            resp = client.delete('/api/kustodian/KUST-001',
                                 headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code == 200
            assert resp.get_json()['deleted'] == 'KUST-001'

    def test_wallet_uniqueness_rejected(self, client):
        token = _make_token('admin-001')
        mock_conn = _make_mock_conn({
            'fetchone': [None, ('PAKD-DEMO-001', 'PAKD', 'PAKD-DEMO-001')]
        })
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile), \
             patch('app._get_db_conn', return_value=mock_conn), \
             patch('app._return_db_conn'):
            resp = client.post('/api/kustodian',
                               headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                               json={'id': 'KUST-NEW', 'nama': 'Test',
                                     'wallets': [{'network': 'ethereum', 'address': '0x28C6c06298d514Db089934071355E5743bf21d60'}]})
            assert resp.status_code == 409

    def test_pakd_sees_only_linked(self, client):
        token = _make_token('pakd-001')
        mock_conn = _make_mock_conn({'fetchall': [
            [('KUST-001', 'Linked Kustodian', '2026-01-01', '2026-01-01')],
            [('PAKD-DEMO-001',)],
            [('ethereum', '0xDFd5293D8e347dFe59E90eFd55b2956a1343963d', False, None, None)],
        ]})
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile), \
             patch('app._get_db_conn', return_value=mock_conn), \
             patch('app._return_db_conn'):
            resp = client.get('/api/kustodian',
                              headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code == 200
            data = resp.get_json()
            assert len(data) == 1
            assert data[0]['id'] == 'KUST-001'


class TestKustodianMonitoring:
    """Sprint 4: GET /api/kustodian/<id>/monitoring dashboard endpoint."""

    def _monitoring_mock_conn(self):
        return _make_mock_conn({
            'fetchone': [
                ('KUST-001', 'PT Kustodian Aset Prima'),   # kustodian lookup
                None,                                       # _get_reported_values -> fallback ke defaults
            ],
            'fetchall': [
                [('PAKD-DEMO-001', 'Alpha Kripto Indonesia')],                        # linked PAKDs
                [('PAKD-DEMO-001', 15_000_000_000, True, 0.30, 0.70, None, 2_500_000_000)],  # latest snapshots
                [('ethereum', '0xDFd5293D8e347dFe59E90eFd55b2956a1343963d', True, None, 'PAKD-DEMO-001'),
                 ('solana', '9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM', False, None, None)],  # wallets
            ],
        })

    def _monitoring_mock_conn_tanpa_snapshot(self):
        """Salinan _monitoring_mock_conn tanpa satu pun baris snapshot.

        T2.4: PAKD tertaut tetap satu dan wallet tetap dua; yang hilang
        hanya baris reconciliation_snapshots. Bentuk tuple snapshot di
        helper lama tidak disentuh -- ia mengikuti urutan kolom SELECT.
        """
        return _make_mock_conn({
            'fetchone': [
                ('KUST-001', 'PT Kustodian Aset Prima'),   # kustodian lookup
                None,                                       # _get_reported_values -> fallback ke defaults
            ],
            'fetchall': [
                [('PAKD-DEMO-001', 'Alpha Kripto Indonesia')],                        # linked PAKDs
                [],                                                                    # latest snapshots: kosong
                [('ethereum', '0xDFd5293D8e347dFe59E90eFd55b2956a1343963d', True, None, 'PAKD-DEMO-001'),
                 ('solana', '9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM', False, None, None)],  # wallets
            ],
        })

    def test_monitoring_returns_dashboard_data(self, client):
        token = _make_token('admin-001')
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile), \
             patch('app._get_db_conn', return_value=self._monitoring_mock_conn()), \
             patch('app._return_db_conn'):
            resp = client.get('/api/kustodian/KUST-001/monitoring',
                              headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['kustodian']['id'] == 'KUST-001'
            assert data['summary']['jumlah_pakd'] == 1
            assert data['summary']['wallet_total_count'] == 2
            assert data['summary']['wallet_verified_count'] == 1
            assert data['summary']['verification_rate_pct'] == 50.0
            assert data['summary']['total_onchain_idr'] == 15_000_000_000
            # Alpha default: 7B expected at PTP -> deviasi (15B-7B)/7B
            assert data['summary']['total_expected_at_ptp_idr'] == 7_000_000_000
            assert len(data['pakd_compliance']) == 1
            p = data['pakd_compliance'][0]
            assert p['pakd_id'] == 'PAKD-DEMO-001'
            assert p['status'] == 'COMPLIANT'
            assert p['ratio_at_pakd'] == 0.30
            assert p['pakd_onchain_idr'] == 2_500_000_000
            assert p['kustodian_onchain_idr'] == 15_000_000_000
            assert len(data['wallets']) == 2

    def test_monitoring_auth_pakd_linked(self, client):
        token = _make_token('pakd-001')
        mock_conn = self._monitoring_mock_conn()
        # PAKD role: extra fetchone up-front for the link check
        mock_conn.cursor.return_value.fetchone.side_effect = [
            (1,),                                       # kustodian_pakd link exists
            ('KUST-001', 'PT Kustodian Aset Prima'),
            None,
        ]
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile), \
             patch('app._get_db_conn', return_value=mock_conn), \
             patch('app._return_db_conn'):
            resp = client.get('/api/kustodian/KUST-001/monitoring',
                              headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code == 200

    def test_monitoring_auth_pakd_unlinked(self, client):
        token = _make_token('pakd-001')
        mock_conn = _make_mock_conn({'fetchone': [None]})  # no kustodian_pakd link
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile), \
             patch('app._get_db_conn', return_value=mock_conn), \
             patch('app._return_db_conn'):
            resp = client.get('/api/kustodian/KUST-002/monitoring',
                              headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code == 403

    def test_monitoring_auth_kustodian_own_entity(self, client):
        token = _make_token('kustodian-001')
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile), \
             patch('app._get_db_conn', return_value=self._monitoring_mock_conn()), \
             patch('app._return_db_conn'):
            resp = client.get('/api/kustodian/KUST-001/monitoring',
                              headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code == 200

    def test_monitoring_auth_kustodian_other_entity(self, client):
        token = _make_token('kustodian-001')
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            resp = client.get('/api/kustodian/KUST-002/monitoring',
                              headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code == 403

    def test_monitoring_not_found(self, client):
        token = _make_token('admin-001')
        mock_conn = _make_mock_conn({'fetchone': [None]})
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile), \
             patch('app._get_db_conn', return_value=mock_conn), \
             patch('app._return_db_conn'):
            resp = client.get('/api/kustodian/KUST-999/monitoring',
                              headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code == 404

    def test_monitoring_requires_auth(self, client):
        resp = client.get('/api/kustodian/KUST-001/monitoring')
        assert resp.status_code == 401

    def _baris_pertama(self, client, mock_conn):
        """Satu panggilan endpoint monitoring, kembalikan baris pakd_compliance[0].

        D22 tidak berlaku di sini sebagai keputusan sadar: jalur ini membaca
        reconciliation_snapshots lewat koneksi yang di-mock dan tidak pernah
        menyentuh get_total_balance_idr, jadi tidak ada cache saldo maupun
        cache harga yang bisa mencemari hasilnya.
        """
        token = _make_token('admin-001')
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile), \
             patch('app._get_db_conn', return_value=mock_conn), \
             patch('app._return_db_conn'):
            resp = client.get('/api/kustodian/KUST-001/monitoring',
                              headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200, resp.status_code
        data = resp.get_json()
        assert len(data['pakd_compliance']) == 1, data['pakd_compliance']
        return data['pakd_compliance'][0]

    def test_baris_tanpa_snapshot_tak_terbedakan_dari_pelanggar(self, client):
        baris_bersnapshot = self._baris_pertama(
            client, self._monitoring_mock_conn())
        baris_tanpa_snapshot = self._baris_pertama(
            client, self._monitoring_mock_conn_tanpa_snapshot())

        # KERUGIAN. .get dipakai supaya kunci yang belum ada menghasilkan
        # None, bukan KeyError: yang diukur adalah ketiadaan pembeda, bukan
        # ketiadaan kunci.
        penanda_bersnapshot = (baris_bersnapshot.get('verdict_status'),
                               baris_bersnapshot.get('ratio_provenance'))
        penanda_tanpa_snapshot = (baris_tanpa_snapshot.get('verdict_status'),
                                  baris_tanpa_snapshot.get('ratio_provenance'))
        assert penanda_bersnapshot != penanda_tanpa_snapshot, (
            "baris tanpa data rekonsiliasi dan baris bersnapshot menerbitkan "
            f"penanda verdict yang identik: {penanda_tanpa_snapshot!r}; "
            "pembaca tidak bisa membedakan ketiadaan data dari pelanggaran")

        # Penjaga pasca-perbaikan. Tidak tercapai sebelum tambalan.
        assert baris_tanpa_snapshot['verdict_status'] == 'BELUM_DIREKONSILIASI'
        assert baris_tanpa_snapshot['ratio_provenance'] is None
        assert baris_bersnapshot['ratio_provenance'] == 'declared'

    def test_rasio_terlapor_tidak_ditandai_declared(self, client):
        baris = self._baris_pertama(client, self._monitoring_mock_conn())

        # KERUGIAN. Rasio ini dihitung dari nilai yang dilaporkan sendiri,
        # tapi payload tidak memuat apa pun yang membedakannya dari rasio
        # yang terverifikasi on-chain.
        assert 'ratio_provenance' in baris, (
            "payload baris tidak memuat penanda asal-usul rasio; rasio "
            f"terlapor dan rasio terverifikasi tampak sama: {sorted(baris)!r}")

        # Penjaga pasca-perbaikan.
        assert baris['ratio_provenance'] == 'declared'


class TestDeviasiWithCustody:
    """Deviasi must count the PAKD's prorated custody share as on-chain assets."""

    def test_perfect_30_70_placement_has_zero_deviation(self):
        import app as app_mod
        total, dev = app_mod.deviasi_with_custody(3_000_000_000, 7_000_000_000, 10_000_000_000)
        assert total == 10_000_000_000
        assert dev == 0

    def test_missing_custody_share_shows_deficit(self):
        import app as app_mod
        total, dev = app_mod.deviasi_with_custody(3_000_000_000, 0, 10_000_000_000)
        assert total == 3_000_000_000
        assert round(dev, 2) == -70.0

    def test_zero_dilaporkan_yields_zero(self):
        import app as app_mod
        total, dev = app_mod.deviasi_with_custody(1_000, 2_000, 0)
        assert dev == 0

    def test_none_inputs_are_safe(self):
        import app as app_mod
        total, dev = app_mod.deviasi_with_custody(None, None, 5_000)
        assert total == 0
        assert dev == -100.0


class TestKustodianOnchainResilient:
    """A transient zero balance fetch must not zero a PAKD's custody porsi."""

    def _reset(self):
        """Bersihkan HANYA _KUST_ONCHAIN_LKG. Pengecualian yang dibenarkan.

        D39: kelas ini sengaja tidak membersihkan BALANCE_CACHE,
        PRICE_CACHE, maupun JUPITER_PRICE_CACHE. Setiap tes di kelas ini
        mem-patch get_total_balance_idr secara utuh, atau mem-patch
        _get_kustodian_onchain_resilient yang membungkusnya, sehingga tak
        satu pun jalur produksi yang membaca ketiga cache itu pernah
        dieksekusi. Membersihkannya hanya akan menambah gerak tanpa
        mengubah hasil, dan menyamarkan bahwa isolasi kelas ini bersandar
        pada patch, bukan pada keadaan cache. _KUST_ONCHAIN_LKG berbeda:
        ia dibaca dan ditulis oleh _get_kustodian_onchain_resilient
        sendiri, di luar jangkauan patch, jadi ia WAJIB dibersihkan.
        """
        import app as app_mod
        app_mod._KUST_ONCHAIN_LKG.clear()

    def test_empty_wallets_return_zero(self):
        import app as app_mod
        self._reset()
        # D30: kembaliannya kini dict, jadi totalnya dibaca lewat kunci.
        hasil = app_mod._get_kustodian_onchain_resilient('KUST-X', [])
        assert hasil['total_idr'] == 0
        assert hasil['sumber_total'] == 'tanpa_wallet'

    def test_retry_recovers_transient_zero(self):
        import app as app_mod
        from unittest.mock import patch as _patch
        self._reset()
        with _patch.object(app_mod, 'get_total_balance_idr',
                           side_effect=[{'total_idr': 0}, {'total_idr': 1_420_000_000}]), \
             _patch.object(app_mod.time, 'sleep'):
            val = app_mod._get_kustodian_onchain_resilient('KUST-001', [{'network': 'ethereum', 'address': '0xabc'}])
        # D30: kontrak berubah dari int menjadi dict; nilai yang diuji sama.
        assert val['total_idr'] == 1_420_000_000

    def test_last_known_good_used_when_fetch_stays_zero(self):
        import app as app_mod
        from unittest.mock import patch as _patch
        self._reset()
        # D30: nilai LKG kini dict, bukan int; indeks 0 tetap timestamp.
        app_mod._KUST_ONCHAIN_LKG['KUST-001'] = (app_mod.time.time(), {
            'total_idr': 1_420_000_000, 'entries': [], 'provenance_harga': {}})
        with _patch.object(app_mod, 'get_total_balance_idr', return_value={'total_idr': 0}), \
             _patch.object(app_mod.time, 'sleep'):
            val = app_mod._get_kustodian_onchain_resilient('KUST-001', [{'network': 'ethereum', 'address': '0xabc'}])
        # D30: kontrak berubah dari int menjadi dict; nilai yang diuji sama.
        assert val['total_idr'] == 1_420_000_000
        assert val['sumber_total'] == 'lkg'

    def test_genuine_zero_without_lkg_stays_zero(self):
        import app as app_mod
        from unittest.mock import patch as _patch
        self._reset()
        with _patch.object(app_mod, 'get_total_balance_idr', return_value={'total_idr': 0}), \
             _patch.object(app_mod.time, 'sleep'):
            val = app_mod._get_kustodian_onchain_resilient('KUST-002', [{'network': 'ethereum', 'address': '0xdead'}])
        # D30: kontrak berubah dari int menjadi dict; nilai yang diuji sama.
        assert val['total_idr'] == 0
        assert val['sumber_total'] == 'gagal'

    # ---- D34/D35: nol kustodian yang tidak terukur tidak boleh tersaji
    # sebagai angka nol yang setara dengan nol hasil pengukuran. ----

    _REPORTED = {"customer_at_pakd_idr": 30_000_000_000,
                 "customer_at_ptp_idr": 70_000_000_000,
                 "proprietary_idr": 0}

    def test_kustodian_onchain_none_saat_gagal(self):
        import app as app_mod
        from unittest.mock import patch as _patch
        self._reset()
        GAGAL = {"total_idr": 0.0, "entries": [], "sumber_total": "gagal",
                 "provenance_harga": {"ethereum": None},
                 "lkg_umur_detik": None}
        with _patch.object(app_mod, "_get_kustodian_data_for_pakd",
                           return_value=(["KUST-001"],
                                         {"KUST-001": [{"network": "ethereum",
                                                        "address": "0xabc"}]})), \
             _patch.object(app_mod, "_get_reported_values",
                           return_value=dict(self._REPORTED)), \
             _patch.object(app_mod, "_get_kustodian_onchain_resilient",
                           return_value=GAGAL) as m:
            hasil = app_mod.compute_30_70_compliance(
                "PAKD-001", 0, as_of="2026-08-18T04:00:00+00:00")
        assert m.call_count == 1, (
            "premis batal: cabang berkustodian seharusnya memanggil "
            f"_get_kustodian_onchain_resilient sekali. call_count={m.call_count}")

        # KERUGIAN. Pengukuran yang gagal tersaji sebagai angka nol,
        # tidak terbedakan dari kustodian yang benar-benar kosong.
        assert hasil.get("kustodian_onchain_idr") is None, (
            "total kustodian yang gagal terukur tersaji sebagai "
            f"{hasil.get('kustodian_onchain_idr')!r}, bukan None")

        # Penjaga pasca-perbaikan. Hanya nilai yang dikembalikan yang
        # bercabang; sisa payload tetap utuh dan numerik.
        assert hasil["has_kustodian"] is True
        assert isinstance(hasil["ratio_at_pakd"], (int, float))
        assert isinstance(hasil["ratio_at_ptp"], (int, float))
        assert hasil["ratio_at_pakd"] is not None
        assert hasil["ratio_at_ptp"] is not None

    def test_kustodian_onchain_none_tanpa_kustodian(self):
        import app as app_mod
        from unittest.mock import patch as _patch
        self._reset()
        with _patch.object(app_mod, "_get_kustodian_data_for_pakd",
                           return_value=([], {})):
            hasil = app_mod.compute_30_70_compliance(
                "PAKD-002", 0, as_of="2026-08-18T04:00:00+00:00")

        # KERUGIAN. PAKD tanpa kustodian sama sekali juga menerbitkan
        # nol, seolah porsi PTP-nya telah diukur dan hasilnya nol.
        assert hasil.get("kustodian_onchain_idr") is None, (
            "PAKD tanpa kustodian tersaji sebagai "
            f"{hasil.get('kustodian_onchain_idr')!r}, bukan None")

        # Penjaga pasca-perbaikan.
        assert hasil["has_kustodian"] is False
        assert hasil["ratio_at_pakd"] == 1.0

    def test_kustodian_onchain_angka_saat_live(self):
        """TES KONTROL. Tanpa ini, perbaikan yang selalu None akan lulus."""
        import app as app_mod
        from unittest.mock import patch as _patch
        self._reset()
        TOTAL = 1_420_000_000.4
        LIVE = {"total_idr": TOTAL, "entries": [], "sumber_total": "live",
                "provenance_harga": {"ethereum": "coingecko"},
                "lkg_umur_detik": None}
        with _patch.object(app_mod, "_get_kustodian_data_for_pakd",
                           return_value=(["KUST-001"],
                                         {"KUST-001": [{"network": "ethereum",
                                                        "address": "0xabc"}]})), \
             _patch.object(app_mod, "_get_reported_values",
                           return_value=dict(self._REPORTED)), \
             _patch.object(app_mod, "_get_kustodian_onchain_resilient",
                           return_value=LIVE) as m:
            hasil = app_mod.compute_30_70_compliance(
                "PAKD-001", 0, as_of="2026-08-18T04:00:00+00:00")
        assert m.call_count == 1, (
            "premis batal: cabang berkustodian seharusnya memanggil "
            f"_get_kustodian_onchain_resilient sekali. call_count={m.call_count}")

        nilai = hasil["kustodian_onchain_idr"]
        assert nilai is not None
        assert isinstance(nilai, (int, float))
        assert nilai == round(TOTAL)
        assert hasil["has_kustodian"] is True
