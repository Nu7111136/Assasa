import hashlib
import hmac
from datetime import datetime
from zoneinfo import ZoneInfo

from jazzcash import amount_paisa, configured, hash_ok, secure_hash, txn_ref
from main import Payment, User, db
from test_signup import signup, token

PKT = ZoneInfo('Asia/Karachi')


def _hash(salt, values):
    message = salt + ''.join('&' + v for v in values)
    return hmac.new(salt.encode(), message.encode(), hashlib.sha256).hexdigest().upper()


def test_secure_hash_matches_sorted_hmac():
    fields = {'pp_Password': 'pw', 'pp_Amount': '000000000100', 'pp_MerchantID': 'MC1', 'pp_Language': 'EN', 'pp_SecureHash': 'ignore'}
    salt = 'SALT'
    expected = _hash(salt, ['000000000100', 'EN', 'MC1', 'pw'])
    assert secure_hash(fields, salt) == expected
    assert hash_ok(fields, salt, expected)
    assert not hash_ok(fields, salt, 'DEAD')


def test_amount_and_configured_flags():
    assert amount_paisa({'APP_ENV': 'staging', 'JAZZCASH_AMOUNT_PAISA': ''}) == 100
    assert amount_paisa({'APP_ENV': 'production', 'JAZZCASH_AMOUNT_PAISA': ''}) == 29900
    assert amount_paisa({'APP_ENV': 'production', 'JAZZCASH_AMOUNT_PAISA': '100'}) == 100
    assert not configured({})
    assert configured({
        'JAZZCASH_MERCHANT_ID': 'MC1',
        'JAZZCASH_PASSWORD': 'pw',
        'JAZZCASH_INTEGRITY_SALT': 'salt',
    })


def test_txn_ref_length():
    when = datetime(2026, 11, 14, 10, 30, tzinfo=PKT)
    ref = txn_ref(when, 42)
    assert ref.startswith('T20261114103000')
    assert len(ref) == 19


def test_pay_button_hidden_without_keys(client):
    signup(client)
    page = client.get('/upgrade').text
    assert 'jazzcash_pay' not in page
    assert '/billing/jazzcash/pay' not in page
    assert client.post('/billing/jazzcash/pay', data={'csrf_token': token(client, '/upgrade')}).status_code == 404


def test_pay_button_and_checkout_form(client, app):
    app.config.update(
        JAZZCASH_MERCHANT_ID='MC1',
        JAZZCASH_PASSWORD='secret',
        JAZZCASH_INTEGRITY_SALT='SALT',
        JAZZCASH_ENV='live',
        JAZZCASH_AMOUNT_PAISA='100',
        PUBLIC_BASE_URL='https://staging.rakhza.digital',
    )
    signup(client)
    page = client.get('/upgrade').text
    assert 'Pay Rs 1 with JazzCash' in page
    r = client.post('/billing/jazzcash/pay', data={'csrf_token': token(client, '/upgrade')})
    assert r.status_code == 200
    assert 'payments.jazzcash.com.pk' in r.text
    assert 'name="pp_Amount" value="000000000100"' in r.text
    assert 'name="pp_SecureHash"' in r.text
    with app.app_context():
        p = Payment.query.one()
        assert p.status == 'pending' and p.amount == 1
        assert p.tid.startswith('T')


def test_return_grants_month_on_000(client, app):
    app.config.update(
        JAZZCASH_MERCHANT_ID='MC1',
        JAZZCASH_PASSWORD='secret',
        JAZZCASH_INTEGRITY_SALT='SALT',
        JAZZCASH_AMOUNT_PAISA='100',
        PUBLIC_BASE_URL='https://staging.rakhza.digital',
        WTF_CSRF_ENABLED=True,
    )
    signup(client)
    client.post('/billing/jazzcash/pay', data={'csrf_token': token(client, '/upgrade')})
    with app.app_context():
        p = Payment.query.one()
        tid = p.tid
        uid = p.user_id
    fields = {
        'pp_TxnRefNo': tid,
        'pp_ResponseCode': '000',
        'pp_Amount': '000000000100',
        'pp_MerchantID': 'MC1',
    }
    fields['pp_SecureHash'] = secure_hash(fields, 'SALT')
    r = client.post('/billing/jazzcash/return', data=fields)
    assert r.status_code == 302
    assert r.location.endswith('/dashboard')
    with app.app_context():
        p = Payment.query.filter_by(tid=tid).one()
        u = db.session.get(User, uid)
        assert p.status == 'approved'
        assert u.paid_until is not None
    again = client.post('/billing/jazzcash/return', data=fields)
    assert again.status_code == 302
    with app.app_context():
        assert Payment.query.filter_by(tid=tid).one().status == 'approved'
        assert db.session.get(User, uid).paid_until is not None


def test_return_bad_hash_stays_pending(client, app):
    app.config.update(
        JAZZCASH_MERCHANT_ID='MC1',
        JAZZCASH_PASSWORD='secret',
        JAZZCASH_INTEGRITY_SALT='SALT',
        JAZZCASH_AMOUNT_PAISA='100',
    )
    signup(client)
    client.post('/billing/jazzcash/pay', data={'csrf_token': token(client, '/upgrade')})
    with app.app_context():
        tid = Payment.query.one().tid
    r = client.post('/billing/jazzcash/return', data={
        'pp_TxnRefNo': tid,
        'pp_ResponseCode': '000',
        'pp_SecureHash': '00' * 32,
    })
    assert r.status_code == 302
    with app.app_context():
        p = Payment.query.one()
        assert p.status == 'pending'
        assert User.query.one().paid_until is None


def test_expired_account_can_open_checkout(client, app):
    app.config.update(
        TESTER_PHONES='03001234567',
        JAZZCASH_MERCHANT_ID='MC1',
        JAZZCASH_PASSWORD='secret',
        JAZZCASH_INTEGRITY_SALT='SALT',
        JAZZCASH_AMOUNT_PAISA='100',
        PUBLIC_BASE_URL='https://staging.rakhza.digital',
    )
    signup(client)
    from test_trial import step
    for _ in range(6):
        step(client)
    r = client.post('/billing/jazzcash/pay', data={'csrf_token': token(client, '/upgrade')})
    assert r.status_code == 200
    assert 'pp_SecureHash' in r.text
