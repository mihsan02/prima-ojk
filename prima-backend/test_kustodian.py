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
            [('ethereum', '0xDFd5293D8e347dFe59E90eFd55b2956a1343963d', True, None)],
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
            [('ethereum', '0xDFd5293D8e347dFe59E90eFd55b2956a1343963d', False, None)],
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
                [('ethereum', '0xDFd5293D8e347dFe59E90eFd55b2956a1343963d', True, None),
                 ('solana', '9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM', False, None)],  # wallets
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
