import os
import time
import pytest
from unittest.mock import patch

os.environ.setdefault('ADMIN_TOKEN', 'test-token-prima')
os.environ.setdefault('SUPABASE_JWT_SECRET', 'prima-test-jwt-secret-for-pytest-1234')

from app import app as flask_app

# T3.5: isolasi test dari pakd_data.json lokal (di-gitignore, tidak ada di
# checkout bersih). Tanpa ini, load_pakd() fallback membaca file kosong/tidak
# ada di CI, menyebabkan StopIteration di test yang mencari PAKD_ID tetap
# (test_d49_verdict_consistency.py, test_final_failsafe.py). Lihat D80.
import tempfile
import json as _json
import app as _app_mod

_tmp_dir = tempfile.mkdtemp()
_app_mod.DATA_FILE = os.path.join(_tmp_dir, "pakd_data.json")
with open(_app_mod.DATA_FILE, "w") as _f:
    _json.dump([dict(p) for p in _app_mod.PAKD_DEFAULT], _f)

_TEST_SUPER_ADMIN_PROFILE = {
    'role': 'super_admin',
    'entity_type': None,
    'entity_id': None,
    'display_name': 'Test Super Admin'
}

def _mock_profile(user_id):
    return _TEST_SUPER_ADMIN_PROFILE


def _make_test_jwt():
    """Buat test JWT token untuk super_admin (dipakai di semua existing tests)."""
    import jwt
    secret = os.environ['SUPABASE_JWT_SECRET']
    now = int(time.time())
    payload = {
        'sub': 'test-super-admin-001',
        'email': 'test-admin@prima.ojk.go.id',
        'aud': 'authenticated',
        'iat': now,
        'exp': now + 3600,
    }
    return jwt.encode(payload, secret, algorithm='HS256')


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    flask_app.config['PROPAGATE_EXCEPTIONS'] = True
    test_jwt = _make_test_jwt()
    with flask_app.test_client() as c:
        original_open = c.open
        def patched_open(*args, **kwargs):
            headers = dict(kwargs.get('headers') or {})
            headers['X-Admin-Token'] = os.environ.get('ADMIN_TOKEN', 'test-token-prima')
            # Inject JWT Bearer untuk require_auth endpoints (backward compat)
            if 'Authorization' not in headers:
                headers['Authorization'] = 'Bearer ' + test_jwt
            kwargs['headers'] = headers
            return original_open(*args, **kwargs)
        c.open = patched_open
        with patch('auth._fetch_user_profile', side_effect=_mock_profile):
            yield c
