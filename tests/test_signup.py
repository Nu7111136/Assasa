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


PIN = '135790'


def signup(client, **changes):
    data = dict(name='Demo User', phone='03001234567', password=PIN, confirm=PIN, trade='kiryana', csrf_token=token(client))
    data.update(changes)
    if 'password' in changes and 'confirm' not in changes:
        data['confirm'] = changes['password']
    return client.post('/', data=data)


def test_signup_trial_password_and_dashboard(client, app):
    before = now()
    r = signup(client)
    assert r.status_code == 302
    home = client.get('/').text
    assert 'biz-grid' in home
    assert 'Other' in home
    assert 'type="checkbox"' in home and 'name="trade"' in home
    assert 'type="radio"' not in home
    assert 'id="cnic"' not in home and 'id="address"' not in home and 'id="email"' not in home
    assert '/static/trades/plumber.jpg' in home
    assert '/static/trades/other.jpg' in home
    assert '/static/trades/sports.jpg' in home
    assert '/static/trades/books.jpg' in home
    assert '/static/trades/hardware.jpg' in home
    assert '/static/trades/stitching.jpg' in home
    with app.app_context():
        u = User.query.one()
        assert u.trade == 'kiryana'
        assert u.cnic == ''
        assert u.address == ''
        assert u.email is None
        assert u.password_hash != PIN
        end = u.trial_ends_at.replace(tzinfo=timezone.utc)
        assert before + timedelta(days=5) <= end <= now() + timedelta(days=5)
    assert 'Days left' in client.get('/dashboard').text
    assert 'PKT' in client.get('/dashboard').text


@pytest.mark.parametrize('change', [dict(phone='123'),dict(phone='04001234567'),dict(password='short'),dict(password='12345'),dict(password='1234567'),dict(name=''),dict(confirm='000000'),dict(trade=''),dict(trade='spaceship')])
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
    assert client.post('/login',data=dict(phone='03001234567',password='123456',csrf_token=token(client,'/login'))).status_code == 401
    assert client.post('/login',data=dict(phone='03001234567',password=PIN,csrf_token=token(client,'/login'))).status_code == 302


def test_old_password_hash_needs_mpin_reset(client, app):
    from werkzeug.security import generate_password_hash
    signup(client)
    with app.app_context():
        User.query.one().password_hash = generate_password_hash('old-password-123')
        db.session.commit()
    client.post('/logout', data={'csrf_token': token(client, '/login')})
    assert client.post('/login', data=dict(
        phone='03001234567', password='old-password-123',
        csrf_token=token(client, '/login'))).status_code == 401
    assert client.post('/login', data=dict(
        phone='03001234567', password=PIN,
        csrf_token=token(client, '/login'))).status_code == 401


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


def test_forgot_password_points_to_office(client, app):
    signup(client)
    client.post('/logout', data={'csrf_token': token(client, '/login')})
    page = client.get('/forgot-password')
    assert page.status_code == 200
    assert 'Forgot MPIN' in client.get('/login').text
    assert 'Rakhza office will set a new MPIN' in page.text
    assert 'id="cnic"' not in page.text
    assert 'id="password"' not in page.text
    assert client.post('/forgot-password').status_code == 405
    assert client.post('/login', data=dict(
        phone='03001234567', password=PIN,
        csrf_token=token(client, '/login'))).status_code == 302


def test_forgot_password_works_when_trial_expired(client, app):
    signup(client)
    with app.app_context():
        User.query.one().trial_ends_at = now() - timedelta(seconds=1)
        db.session.commit()
    assert client.get('/dashboard').location.endswith('/upgrade')
    page = client.get('/forgot-password')
    assert page.status_code == 200
    assert 'Rakhza office will set a new MPIN' in page.text


def test_urdu_and_session(client):
    r = client.get('/language/ur', follow_redirects=True)
    assert 'lang="ur" dir="rtl"' in r.text
    assert 'فون نمبر' in r.text
    assert 'dir="ltr"' in r.text
    assert 'lang="ur"' in client.get('/login').text


def test_keyboard_follows_screen_language(client):
    en = client.get('/').text
    assert 'id="ur-kb"' not in en
    assert 'data-kb="ur"' not in en
    assert 'id="name" name="name"' in en and 'lang="en"' in en
    assert 'lang="en" inputmode="tel"' in en
    login = client.get('/login').text
    assert 'id="ur-kb"' not in login
    assert 'id="password"' in login and 'lang="en"' in login
    assert '>MPIN</label>' in login
    assert 'class="mpin"' in login and 'inputmode="numeric"' in login
    assert 'pattern="[0-9]{6}"' in login
    assert 'id="confirm"' not in login

    ur = client.get('/language/ur', follow_redirects=True).text
    assert 'دیگر' in ur
    assert 'پلمبر' in ur
    assert 'id="ur-kb"' in ur
    assert 'data-kb="ur"' in ur
    assert 'inputmode="none"' in ur
    assert 'lang="ur" dir="rtl" inputmode="none" data-kb="ur"' in ur
    assert 'lang="en" inputmode="tel"' in ur
    assert 'id="cnic"' not in ur and 'id="email"' not in ur
    assert 'ہارڈویئر' in ur and 'سلائی' in ur and 'کھیل' in ur and 'کتابیں' in ur
    ur_login = client.get('/login').text
    assert 'id="ur-kb"' in ur_login
    assert 'data-kb="ur"' not in ur_login
    assert 'id="password"' in ur_login and 'lang="en"' in ur_login
    assert 'ایم پن' in ur_login
    assert 'class="mpin"' in ur_login
    client.get('/language/en?page=signup')
    signup(client)
    upgrade = client.get('/upgrade').text
    assert 'id="tid"' in upgrade and 'lang="en"' in upgrade
    assert 'id="ur-kb"' not in upgrade
    assert 'data-kb="ur"' not in upgrade


def test_back_button_and_field_help(client):
    home = client.get('/').text
    login = client.get('/login').text
    forgot = client.get('/forgot-password').text
    assert 'id="back-btn"' not in home
    assert 'id="back-btn"' in login and 'Back' in login
    assert 'id="back-btn"' in forgot
    assert 'Start with 03' in login
    assert 'Rakhza office will set a new MPIN' in forgot
    assert 'data-toggle="password"' in login
    assert '>MPIN</label>' in home and 'class="mpin"' in home
    assert 'id="confirm"' in home and 'id="confirm"' not in forgot
    assert 'Six numbers, like JazzCash' in home
    assert 'Forgot MPIN?' in login
    assert 'Password' not in home and 'Password' not in login and 'Password' not in forgot
    ur = client.get('/language/ur?page=login', follow_redirects=True).text
    assert 'واپس' in ur
    assert 'Show' in login
    client.get('/language/en?page=login')
    signup(client)
    upgrade = client.get('/upgrade').text
    if (client.application.config.get('PAYMENT_JAZZCASH_NUMBER') or '').strip():
        assert 'Copy number' in upgrade
    else:
        assert 'Receive number is not set' in upgrade
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
