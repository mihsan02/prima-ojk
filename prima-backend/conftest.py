import os
import pytest

os.environ.setdefault('ADMIN_TOKEN', 'test-token-prima')

from app import app as flask_app

@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    flask_app.config['PROPAGATE_EXCEPTIONS'] = True
    with flask_app.test_client() as c:
        original_open = c.open
        def patched_open(*args, **kwargs):
            headers = dict(kwargs.get('headers') or {})
            headers['X-Admin-Token'] = os.environ.get('ADMIN_TOKEN', 'test-token-prima')
            kwargs['headers'] = headers
            return original_open(*args, **kwargs)
        c.open = patched_open
        yield c
