import re
import sys
from pathlib import Path
from datetime import timedelta, timezone

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import create_app, db, User, now


@pytest.fixture
def app(tmp_path):
    app = create_app(dict(TESTING=True, SECRET_KEY='test-key-only', SQLALCHEMY_DATABASE_URI='sqlite:///' + str(tmp_path/'test.db'), RATELIMIT_ENABLED=False))
    with app.app_context():
        db.create_all()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def token(client, path='/'):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def signup(client, **changes):
    data = dict(name='Demo User', address='Fictional street', cnic='12345-1234567-1', phone='03001234567', email='', password='test-password-123', csrf_token=token(client))
    data.update(changes)
    return client.post('/', data=data)


def test_signup_trial_password_and_dashboard(client, app):
    before = now()
    r = signup(client)
    assert r.status_code == 302
    with app.app_context():
        u = User.query.one()
        assert u.cnic == '1234512345671'
        assert u.email is None
        assert u.password_hash != 'test-password-123'
        end = u.trial_ends_at.replace(tzinfo=timezone.utc)
        assert before + timedelta(days=5) <= end <= now() + timedelta(days=5)
    assert 'Days left' in client.get('/dashboard').text
    assert 'PKT' in client.get('/dashboard').text


@pytest.mark.parametrize('change', [dict(cnic='123'), dict(cnic='a'*13), dict(phone='123'),dict(phone='04001234567'), dict(email='broken'),dict(password='short'),dict(name=''),dict(address='')])
def test_invalid(client, change):
    assert signup(client, **change).status_code == 400


def test_duplicate(client, app):
    assert signup(client).status_code == 302
    assert signup(client).status_code == 409
    with app.app_context():
        assert User.query.count() == 1


def test_login_logout_and_protection(client):
    assert client.get('/dashboard').status_code == 302
    signup(client)
    assert client.get('/logout').status_code == 405
    client.post('/logout', data={'csrf_token':token(client,'/login')})
    assert client.get('/dashboard').status_code == 302
    assert client.post('/login',data=dict(phone='03001234567',password='wrong',csrf_token=token(client,'/login'))).status_code == 401
    assert client.post('/login',data=dict(phone='03001234567',password='test-password-123',csrf_token=token(client,'/login'))).status_code == 302


def test_expired(client, app):
    signup(client)
    with app.app_context():
        User.query.one().trial_ends_at = now() - timedelta(seconds=1)
        db.session.commit()
    assert 'Your trial has ended.' in client.get('/dashboard').text


def test_csrf(client):
    assert client.post('/', data={'name':'Demo'}).status_code == 400


def test_urdu_and_session(client):
    r = client.get('/language/ur', follow_redirects=True)
    assert 'lang="ur" dir="rtl"' in r.text
    assert 'شناختی کارڈ' in r.text
    assert 'dir="ltr"' in r.text
    assert 'lang="ur"' in client.get('/login').text


def test_pwa_and_privacy(client):
    assert client.get('/static/manifest.webmanifest').json['display'] == 'standalone'
    js = client.get('/sw.js').text
    assert "event.request.method !== 'GET'" in js
    assert "'/dashboard'" not in js
    for url in ('/','/login'):
        assert client.get(url).headers['Cache-Control'] == 'no-store'
    for size in (192,512):
        assert client.get(f'/static/icon-{size}.png').status_code == 200


def test_escape_customer_name(client):
    signup(client,name='<script>alert(1)</script>')
    html=client.get('/dashboard').text
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;' in html
