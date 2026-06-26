import os
import hmac
import functools
import jwt
from flask import request, jsonify, g

# ES256 public key dari Supabase JWKS (manual construction, cross-version compatible)
_es256_public_key = None
_es256_key_fetched = False

def _get_es256_public_key():
    global _es256_public_key, _es256_key_fetched
    if _es256_key_fetched:
        return _es256_public_key
    _es256_key_fetched = True
    try:
        import json, base64
        from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicNumbers, SECP256R1
        # 1. Coba dari env var (production: JWKS fetch dari Render gagal)
        jwk_env = os.environ.get('SUPABASE_JWT_JWK', '')
        if jwk_env:
            key_data = json.loads(jwk_env)
        else:
            # 2. Fallback: fetch dari Supabase JWKS endpoint
            import urllib.request
            url = _supabase_url()
            if not url:
                return None
            jwks_url = f"{url.rstrip('/')}/auth/v1/jwks"
            print(f"[AUTH] Fetching JWKS from: {jwks_url}", flush=True)
            req = urllib.request.Request(
                    jwks_url,
                    headers={"apikey": _anon_key()}
                )
            resp = urllib.request.urlopen(req, timeout=5)
            jwks = json.loads(resp.read())
            key_data = None
            for k in jwks.get('keys', []):
                if k.get('alg') == 'ES256' and k.get('kty') == 'EC':
                    key_data = k
                    break
            if not key_data:
                return None
        x_bytes = base64.urlsafe_b64decode(key_data['x'] + '==')
        y_bytes = base64.urlsafe_b64decode(key_data['y'] + '==')
        numbers = EllipticCurvePublicNumbers(
            x=int.from_bytes(x_bytes, 'big'),
            y=int.from_bytes(y_bytes, 'big'),
            curve=SECP256R1()
        )
        _es256_public_key = numbers.public_key()
        print(f"[AUTH] ES256 public key loaded", flush=True)
        return _es256_public_key
    except Exception as e:
        print(f"[AUTH] ES256 key load failed: {e}", flush=True)
    return None

def _jwt_secret():
    return os.environ.get('SUPABASE_JWT_SECRET', '')

def _supabase_url():
    return os.environ.get('SUPABASE_URL', '')

def _anon_key():
    return os.environ.get('SUPABASE_ANON_KEY', '')

def _service_role_key():
    return os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')

_USER_PROFILE_CACHE = {}   # {user_id: (cached_at, profile_dict)}
_PROFILE_CACHE_TTL = 300   # 5 menit

import time as _time_module


def get_current_user():
    """Extract dan validate JWT dari Authorization header.
    Return dict {id, email, role, entity_type, entity_id} atau None.
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None

    token = auth_header[7:]
    secret = _jwt_secret()
    if not secret:
        return None

    try:
        # ES256 via manual JWKS key, fallback HS256
        payload = None
        es256_key = _get_es256_public_key()
        if es256_key:
            try:
                payload = jwt.decode(
                    token,
                    es256_key,
                    algorithms=['ES256'],
                    audience='authenticated'
                )
            except (jwt.InvalidTokenError, ValueError, Exception) as e:
                print(f"[AUTH] ES256 decode failed: {e}", flush=True)
                pass  # fallback ke HS256
        if payload is None:
            payload = jwt.decode(
                token,
                secret,
                algorithms=['HS256'],
                audience='authenticated'
            )
        user_id = payload.get('sub')
        if not user_id:
            return None

        profile = _fetch_user_profile(user_id)
        if not profile:
            return None

        return {
            'id': user_id,
            'email': payload.get('email', ''),
            'role': profile['role'],
            'entity_type': profile.get('entity_type'),
            'entity_id': profile.get('entity_id'),
            'display_name': profile.get('display_name', '')
        }
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def _fetch_user_profile(user_id):
    """Fetch user profile dari DB. Cache 5 menit per user."""
    now = _time_module.time()
    cached = _USER_PROFILE_CACHE.get(user_id)
    if cached and (now - cached[0]) < _PROFILE_CACHE_TTL:
        return cached[1]

    from app import _get_db_conn, _return_db_conn
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT role, entity_type, entity_id, display_name "
            "FROM user_profiles WHERE id = %s",
            (str(user_id),)
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        profile = {
            'role': row[0],
            'entity_type': row[1],
            'entity_id': row[2],
            'display_name': row[3]
        }
        _USER_PROFILE_CACHE[user_id] = (now, profile)
        return profile
    except Exception as e:
        print(f"[AUTH] Profile fetch error: {e}", flush=True)
        return None
    finally:
        _return_db_conn(conn)


def invalidate_user_cache(user_id):
    """Hapus cache profil user (panggil setelah update profil)."""
    _USER_PROFILE_CACHE.pop(str(user_id), None)


def _testing_admin_fallback():
    """Dalam TESTING mode, terima X-Admin-Token sebagai super_admin.
    Memungkinkan existing tests berjalan tanpa JWT.
    """
    from flask import current_app
    if not current_app.config.get('TESTING'):
        return None
    expected = os.environ.get('ADMIN_TOKEN')
    if not expected:
        return None
    token = request.headers.get('X-Admin-Token', '')
    if token and hmac.compare_digest(token, expected):
        return {
            'id': 'test-super-admin',
            'email': 'test@prima.ojk.go.id',
            'role': 'super_admin',
            'entity_type': None,
            'entity_id': None,
            'display_name': 'Test Admin'
        }
    return None


def require_auth(f):
    """Decorator: endpoint membutuhkan valid JWT. Inject g.current_user."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user() or _testing_admin_fallback()
        if not user:
            return jsonify({'error': 'Authentication required'}), 401
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def require_role(*allowed_roles):
    """Decorator: endpoint membutuhkan role tertentu.
    Usage: @require_role('super_admin', 'pengawas')
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user() or _testing_admin_fallback()
            if not user:
                return jsonify({'error': 'Authentication required'}), 401
            if user['role'] not in allowed_roles:
                return jsonify({
                    'error': 'Forbidden',
                    'message': f"Role '{user['role']}' tidak memiliki akses ke endpoint ini"
                }), 403
            g.current_user = user
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_super_admin_or_token(f):
    """Dual-auth decorator untuk PAKD write endpoints.
    Accepts JWT super_admin ATAU legacy X-Admin-Token.
    Grace period: Sprint 4 akan enforce JWT only.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        # Coba JWT dulu
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            user = get_current_user()
            if user:
                if user['role'] != 'super_admin':
                    return jsonify({
                        'error': 'Forbidden',
                        'message': f"Role '{user['role']}' tidak memiliki akses ke endpoint ini"
                    }), 403
                g.current_user = user
                return f(*args, **kwargs)

        # Fallback ke X-Admin-Token (backward compat)
        expected = os.environ.get('ADMIN_TOKEN')
        if expected:
            token = request.headers.get('X-Admin-Token', '')
            if token and hmac.compare_digest(token, expected):
                g.current_user = {
                    'id': 'system',
                    'email': 'system',
                    'role': 'super_admin',
                    'entity_type': None,
                    'entity_id': None,
                    'display_name': 'System'
                }
                return f(*args, **kwargs)

        return jsonify({'error': 'Authentication required'}), 401
    return decorated


def require_entity_access(entity_param='pakd_id'):
    """Decorator: PAKD/Kustodian hanya bisa akses entity sendiri.
    Pengawas dan Super Admin bypass filter ini.
    Usage: @require_entity_access('pakd_id')
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({'error': 'Authentication required'}), 401
            g.current_user = user

            if user['role'] in ('pengawas', 'super_admin'):
                return f(*args, **kwargs)

            requested_entity = (
                kwargs.get(entity_param)
                or request.args.get(entity_param)
                or (request.get_json(silent=True) or {}).get(entity_param)
            )
            if requested_entity and requested_entity != user['entity_id']:
                return jsonify({
                    'error': 'Forbidden',
                    'message': 'Anda hanya dapat mengakses data entity sendiri'
                }), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


def login_user(email, password):
    """Login via Supabase Auth REST API.
    Return {access_token, user, profile} atau {error}.
    """
    url = _supabase_url()
    anon_key = _anon_key()
    if not url or not anon_key:
        return {'error': 'Supabase belum dikonfigurasi. Set SUPABASE_URL dan SUPABASE_ANON_KEY.'}

    import requests as req
    try:
        resp = req.post(
            f"{url}/auth/v1/token?grant_type=password",
            json={"email": email, "password": password},
            headers={
                "apikey": anon_key,
                "Content-Type": "application/json"
            },
            timeout=10
        )
    except Exception as e:
        return {'error': f'Koneksi ke Supabase gagal: {str(e)}'}

    if resp.status_code != 200:
        return {'error': 'Email atau password salah'}

    data = resp.json()
    access_token = data.get('access_token')
    user_id = data.get('user', {}).get('id')

    profile = _fetch_user_profile(user_id)
    if not profile:
        return {'error': 'User profile tidak ditemukan. Hubungi admin.'}

    return {
        'access_token': access_token,
        'refresh_token': data.get('refresh_token'),
        'expires_in': data.get('expires_in'),
        'user': {
            'id': user_id,
            'email': email,
            'role': profile['role'],
            'entity_type': profile.get('entity_type'),
            'entity_id': profile.get('entity_id'),
            'display_name': profile.get('display_name')
        }
    }


def create_supabase_user(email, password, display_name, role, entity_type=None, entity_id=None):
    """Create user via Supabase Auth Admin API + insert user_profiles.
    Hanya bisa dipanggil dari backend dengan SERVICE_ROLE_KEY.
    """
    url = _supabase_url()
    svc_key = _service_role_key()
    if not url or not svc_key:
        return {'error': 'SUPABASE_URL dan SUPABASE_SERVICE_ROLE_KEY wajib diset'}

    import requests as req

    # 1. Create Supabase auth user
    resp = req.post(
        f"{url}/auth/v1/admin/users",
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"display_name": display_name}
        },
        headers={
            "Authorization": f"Bearer {svc_key}",
            "apikey": svc_key,
            "Content-Type": "application/json"
        },
        timeout=15
    )

    if resp.status_code not in (200, 201):
        err = resp.json().get('message', resp.text)
        return {'error': f'Gagal create Supabase user: {err}'}

    user_id = resp.json().get('id')
    if not user_id:
        return {'error': 'Supabase user created tapi ID tidak ada di response'}

    # 2. Insert user_profiles
    from app import _get_db_conn, _return_db_conn
    conn = _get_db_conn()
    if not conn:
        return {'error': 'Database tidak tersedia'}
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO user_profiles (id, role, entity_type, entity_id, display_name)
               VALUES (%s, %s, %s, %s, %s)""",
            (user_id, role, entity_type, entity_id, display_name)
        )
        conn.commit()
        cur.close()
        return {
            'id': user_id,
            'email': email,
            'role': role,
            'entity_type': entity_type,
            'entity_id': entity_id,
            'display_name': display_name
        }
    except Exception as e:
        conn.rollback()
        return {'error': f'User dibuat di Supabase tapi gagal simpan profil: {str(e)}'}
    finally:
        _return_db_conn(conn)


def delete_supabase_user(user_id):
    """Delete user via Supabase Auth Admin API (CASCADE ke user_profiles via FK)."""
    url = _supabase_url()
    svc_key = _service_role_key()
    if not url or not svc_key:
        return {'error': 'SUPABASE_URL dan SUPABASE_SERVICE_ROLE_KEY wajib diset'}

    import requests as req
    resp = req.delete(
        f"{url}/auth/v1/admin/users/{user_id}",
        headers={
            "Authorization": f"Bearer {svc_key}",
            "apikey": svc_key,
        },
        timeout=10
    )
    if resp.status_code not in (200, 204):
        err = resp.json().get('message', resp.text) if resp.text else 'Unknown error'
        return {'error': f'Gagal hapus user: {err}'}

    invalidate_user_cache(user_id)
    return {'deleted': user_id}
