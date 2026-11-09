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
    response = client.get('/dashboard')
    assert response.status_code == 302 and response.location.endswith('/upgrade')
    assert 'Upgrade your account' in client.get('/dashboard', follow_redirects=True).text


def test_csrf(client):
    assert client.post('/', data={'name':'Demo'}).status_code == 400


def test_forgot_password_resets_with_phone_and_cnic(client, app):
    signup(client)
    client.post('/logout', data={'csrf_token': token(client, '/login')})
    page = client.get('/forgot-password')
    assert page.status_code == 200
    assert 'Forgot password' in client.get('/login').text
    csrf = token(client, '/forgot-password')
    assert client.post('/forgot-password', data=dict(
        phone='03001234567', cnic='12345-1234567-1', password='new-secret-99',
        confirm='mismatch-secret', csrf_token=csrf)).status_code == 400
    assert client.post('/forgot-password', data=dict(
        phone='03001234567', cnic='99999-9999999-9', password='new-secret-99',
        confirm='new-secret-99', csrf_token=csrf)).status_code == 401
    assert client.post('/forgot-password', data=dict(
        phone='03999999999', cnic='12345-1234567-1', password='new-secret-99',
        confirm='new-secret-99', csrf_token=csrf)).status_code == 401
    ok = client.post('/forgot-password', data=dict(
        phone='03001234567', cnic='1234512345671', password='new-secret-99',
        confirm='new-secret-99', csrf_token=csrf))
    assert ok.status_code == 302 and ok.location.endswith('/login')
    assert 'Password updated' in client.get('/login').text
    assert client.post('/login', data=dict(
        phone='03001234567', password='test-password-123',
        csrf_token=token(client, '/login'))).status_code == 401
    assert client.post('/login', data=dict(
        phone='03001234567', password='new-secret-99',
        csrf_token=token(client, '/login'))).status_code == 302


def test_forgot_password_works_when_trial_expired(client, app):
    signup(client)
    with app.app_context():
        User.query.one().trial_ends_at = now() - timedelta(seconds=1)
        db.session.commit()
    assert client.get('/dashboard').location.endswith('/upgrade')
    reset = client.post('/forgot-password', data=dict(
        phone='03001234567', cnic='12345-1234567-1', password='after-expiry-1',
        confirm='after-expiry-1', csrf_token=token(client, '/forgot-password')))
    assert reset.status_code == 302 and reset.location.endswith('/login')


def test_urdu_and_session(client):
    r = client.get('/language/ur', follow_redirects=True)
    assert 'lang="ur" dir="rtl"' in r.text
    assert 'شناختی کارڈ' in r.text
    assert 'dir="ltr"' in r.text
    assert 'lang="ur"' in client.get('/login').text


def test_back_button_and_field_help(client):
    home = client.get('/').text
    login = client.get('/login').text
    forgot = client.get('/forgot-password').text
    assert 'id="back-btn"' not in home
    assert 'id="back-btn"' in login and 'Back' in login
    assert 'id="back-btn"' in forgot
    assert 'Start with 03' in login
    assert 'Dashes appear automatically' in forgot
    assert 'data-toggle="password"' in login
    ur = client.get('/language/ur?page=login', follow_redirects=True).text
    assert 'واپس' in ur
    assert 'Show' in login
    client.get('/language/en?page=login')
    signup(client)
    upgrade = client.get('/upgrade').text
    assert 'Copy number' in upgrade
    assert 'id="back-btn"' in upgrade


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
