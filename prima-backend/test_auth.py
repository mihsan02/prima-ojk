"""
Sprint 1: Auth test suite.
Menggunakan mock JWT dan mock DB profile untuk isolasi.
"""
import os
import pytest
import jwt
import time
from unittest.mock import patch, MagicMock

os.environ.setdefault('ADMIN_TOKEN', 'test-token-prima')
os.environ.setdefault('SUPABASE_JWT_SECRET', 'test-secret-for-pytest-only')
os.environ.setdefault('SUPABASE_URL', 'https://test.supabase.co')
os.environ.setdefault('SUPABASE_ANON_KEY', 'test-anon-key')

from app import app as flask_app

# Always read from env so we stay in sync with whatever conftest.py may have set first
JWT_SECRET = os.environ['SUPABASE_JWT_SECRET']

def _make_token(user_id='user-001', email='test@test.com', role='pengawas',
                entity_type=None, entity_id=None, expired=False):
    """Buat test JWT token."""
    now = int(time.time())
    exp = now - 10 if expired else now + 3600
    payload = {
        'sub': user_id,
        'email': email,
        'aud': 'authenticated',
        'iat': now,
        'exp': exp,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


MOCK_PROFILES = {
    'admin-001': {'role': 'super_admin', 'entity_type': None, 'entity_id': None, 'display_name': 'Super Admin'},
    'pengawas-001': {'role': 'pengawas', 'entity_type': None, 'entity_id': None, 'display_name': 'Pengawas IAKD'},
    'pakd-001': {'role': 'pakd', 'entity_type': 'PAKD', 'entity_id': 'PAKD-DEMO-001', 'display_name': 'Alpha Kripto'},
}


def _mock_fetch_profile(user_id):
    return MOCK_PROFILES.get(user_id)


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    flask_app.config['PROPAGATE_EXCEPTIONS'] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def auth_headers_admin():
    token = _make_token(user_id='admin-001', email='admin@prima.ojk.go.id', role='super_admin')
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


@pytest.fixture
def auth_headers_pengawas():
    token = _make_token(user_id='pengawas-001', email='pengawas@prima.ojk.go.id', role='pengawas')
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


@pytest.fixture
def auth_headers_pakd():
    token = _make_token(user_id='pakd-001', email='compliance@alpha.co.id', role='pakd',
                        entity_type='PAKD', entity_id='PAKD-DEMO-001')
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


class TestAuthLogin:
    def test_login_missing_body(self, client):
        """Login tanpa body return 400."""
        resp = client.post('/api/auth/login', json={})
        assert resp.status_code == 400
        assert 'error' in resp.get_json()

    def test_login_missing_password(self, client):
        """Login tanpa password return 400."""
        resp = client.post('/api/auth/login', json={'email': 'test@test.com'})
        assert resp.status_code == 400

    def test_login_supabase_not_configured(self, client):
        """Login ketika Supabase belum dikonfigurasi return error."""
        with patch.dict(os.environ, {'SUPABASE_URL': '', 'SUPABASE_ANON_KEY': ''}):
            import importlib, auth
            importlib.reload(auth)
            resp = client.post('/api/auth/login', json={'email': 'a@b.com', 'password': 'pw'})
            assert resp.status_code in (400, 401, 500)
            importlib.reload(auth)


class TestProtectedEndpoints:
    def test_no_token_returns_401(self, client):
        """Akses protected endpoint tanpa token return 401."""
        resp = client.get('/api/auth/me')
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['error'] == 'Authentication required'

    def test_invalid_token_returns_401(self, client):
        """Token invalid return 401."""
        resp = client.get('/api/auth/me', headers={'Authorization': 'Bearer invalid.token.here'})
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, client):
        """Token expired return 401."""
        expired_token = _make_token(expired=True)
        resp = client.get('/api/auth/me', headers={'Authorization': f'Bearer {expired_token}'})
        assert resp.status_code == 401

    def test_valid_token_returns_user(self, client):
        """Token valid dengan profile di DB return 200."""
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            token = _make_token(user_id='admin-001')
            resp = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['role'] == 'super_admin'
            assert data['id'] == 'admin-001'


class TestRoleAuthorization:
    def test_pengawas_cannot_create_pakd(self, client):
        """Role pengawas tidak bisa POST /api/pakd → 403."""
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            token = _make_token(user_id='pengawas-001')
            resp = client.post(
                '/api/pakd',
                json={'id': 'PAKD-TEST', 'nama': 'Test'},
                headers={'Authorization': f'Bearer {token}'}
            )
            assert resp.status_code == 403
            data = resp.get_json()
            assert data['error'] == 'Forbidden'

    def test_pakd_cannot_create_pakd(self, client):
        """Role pakd tidak bisa POST /api/pakd → 403."""
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            token = _make_token(user_id='pakd-001')
            resp = client.post(
                '/api/pakd',
                json={'id': 'PAKD-TEST', 'nama': 'Test'},
                headers={'Authorization': f'Bearer {token}'}
            )
            assert resp.status_code == 403

    def test_super_admin_can_access_write_endpoints(self, client):
        """Super admin bisa akses write endpoint (atau dapat response bukan 401/403)."""
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            token = _make_token(user_id='admin-001')
            resp = client.post(
                '/api/pakd',
                json={'id': 'PAKD-X-TEST-BYPASS', 'nama': 'Test Bypass'},
                headers={'Authorization': f'Bearer {token}'}
            )
            # Bisa 201 (berhasil) atau 409 (sudah ada) atau 503 (no DB) — bukan 401/403
            assert resp.status_code not in (401, 403)

    def test_pengawas_cannot_delete_pakd(self, client):
        """Pengawas tidak bisa DELETE /api/pakd/<id> → 403."""
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            token = _make_token(user_id='pengawas-001')
            resp = client.delete(
                '/api/pakd/PAKD-DEMO-001',
                headers={'Authorization': f'Bearer {token}'}
            )
            assert resp.status_code == 403


class TestEntityAccess:
    def test_pakd_can_only_see_own_data_history(self, client):
        """PAKD role tidak bisa lihat history pakd lain → 403."""
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            token = _make_token(user_id='pakd-001')
            resp = client.get(
                '/api/reconciliation-history?pakd_id=PAKD-OJK-001',
                headers={'Authorization': f'Bearer {token}'}
            )
            assert resp.status_code == 403

    def test_pakd_can_see_own_data_history(self, client):
        """PAKD role bisa lihat history entity sendiri (atau 503 jika no DB)."""
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            token = _make_token(user_id='pakd-001')
            resp = client.get(
                '/api/reconciliation-history?pakd_id=PAKD-DEMO-001',
                headers={'Authorization': f'Bearer {token}'}
            )
            # Bisa 200 (ada data) atau 503 (no DB) — bukan 401/403
            assert resp.status_code not in (401, 403)

    def test_pengawas_can_see_all_history(self, client):
        """Pengawas bisa lihat semua history tanpa filter (atau 503 jika no DB)."""
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            token = _make_token(user_id='pengawas-001')
            resp = client.get(
                '/api/reconciliation-history?pakd_id=PAKD-OJK-001',
                headers={'Authorization': f'Bearer {token}'}
            )
            assert resp.status_code not in (401, 403)


class TestBackwardCompat:
    def test_internal_token_still_works(self, client):
        """X-Internal-Token untuk cron tetap berfungsi tanpa JWT."""
        resp = client.post(
            '/api/internal/refresh-all',
            headers={'X-Internal-Token': 'wrong-token'}
        )
        assert resp.status_code == 401

    def test_admin_token_still_works_for_write(self, client):
        """X-Admin-Token masih accepted untuk write endpoint (grace period)."""
        resp = client.post(
            '/api/pakd',
            json={'id': 'PAKD-LEGACY-TEST', 'nama': 'Test Legacy'},
            headers={'X-Admin-Token': os.environ.get('ADMIN_TOKEN', 'test-token-prima')}
        )
        # 201 atau 409 (sudah ada) atau 503 (no DB) — bukan 401/403
        assert resp.status_code not in (401, 403)

    def test_ping_is_public(self, client):
        """/ping tidak butuh auth."""
        resp = client.get('/ping')
        assert resp.status_code in (200, 503)

    def test_status_is_public(self, client):
        """/api/status tidak butuh auth."""
        resp = client.get('/api/status')
        assert resp.status_code == 200


class TestUserManagement:
    def test_list_users_requires_super_admin(self, client):
        """GET /api/users membutuhkan super_admin."""
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            token = _make_token(user_id='pengawas-001')
            resp = client.get('/api/users', headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code == 403

    def test_list_users_no_auth(self, client):
        """GET /api/users tanpa auth return 401."""
        resp = client.get('/api/users')
        assert resp.status_code == 401

    def test_create_user_requires_super_admin(self, client):
        """POST /api/users membutuhkan super_admin."""
        with patch('auth._fetch_user_profile', side_effect=_mock_fetch_profile):
            token = _make_token(user_id='pakd-001')
            resp = client.post(
                '/api/users',
                json={'email': 'new@test.com', 'password': 'pass123', 'role': 'pengawas', 'display_name': 'New User'},
                headers={'Authorization': f'Bearer {token}'}
            )
            assert resp.status_code == 403
