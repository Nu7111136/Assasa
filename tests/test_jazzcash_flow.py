"""Strict JazzCash return checks, the waiting page, and the TID fallback."""
from billing import payment_kind
from jazzcash import secure_hash, verify_return
from main import Payment, User, db
from test_signup import app, client, signup, token  # noqa: F401  (fixtures)

KEYS = dict(
    JAZZCASH_MERCHANT_ID='MC1',
    JAZZCASH_PASSWORD='secret',
    JAZZCASH_INTEGRITY_SALT='SALT',
    JAZZCASH_AMOUNT_PAISA='100',
    PUBLIC_BASE_URL='https://staging.rakhza.digital',
)


def _checkout(client, app):
    app.config.update(KEYS)
    client.post('/billing/jazzcash/pay', data={'csrf_token': token(client, '/upgrade')})
    with app.app_context():
        p = Payment.query.filter_by(method='checkout').order_by(Payment.id.desc()).first()
        return p.id, p.tid


def _signed(tid, code='000', amount='000000000100', merchant='MC1', salt='SALT'):
    fields = {'pp_TxnRefNo': tid, 'pp_ResponseCode': code, 'pp_Amount': amount, 'pp_MerchantID': merchant}
    fields['pp_SecureHash'] = secure_hash(fields, salt)
    return fields


class _P:
    def __init__(self, tid='T202611141030000042', amount=1):
        self.tid, self.amount = tid, amount


def test_verify_return_outcomes():
    cfg = dict(JAZZCASH_INTEGRITY_SALT='SALT', JAZZCASH_MERCHANT_ID='MC1')
    p = _P()
    assert verify_return(_signed(p.tid), p, cfg) == ('approve', 'ok')
    assert verify_return(_signed(p.tid, code='999'), p, cfg)[0] == 'decline'
    assert verify_return(_signed(p.tid, code='157'), p, cfg)[0] == 'pending'
    assert verify_return(_signed(p.tid, amount='000000029900'), p, cfg) == ('invalid', 'amount_mismatch')
    assert verify_return(_signed(p.tid, merchant='MC2'), p, cfg) == ('invalid', 'merchant_mismatch')
    assert verify_return(_signed(p.tid, salt='OTHER'), p, cfg) == ('invalid', 'bad_hash')
    assert verify_return(_signed('T999999999999999999'), p, cfg) == ('invalid', 'ref_mismatch')
    assert verify_return(_signed(p.tid), None, cfg) == ('invalid', 'unknown_ref')
    assert verify_return(_signed(p.tid), p, dict(cfg, JAZZCASH_INTEGRITY_SALT='')) == ('invalid', 'no_salt')


def test_amount_tamper_does_not_grant(client, app):
    signup(client)
    pid, tid = _checkout(client, app)
    client.post('/billing/jazzcash/return', data=_signed(tid, amount='000000000001'))
    with app.app_context():
        assert db.session.get(Payment, pid).status == 'pending'
        assert User.query.one().paid_until is None


def test_return_works_without_session_cookie(client, app):
    """JazzCash's cross-site POST arrives without the SameSite=Lax login cookie."""
    signup(client)
    pid, tid = _checkout(client, app)
    anon = app.test_client()
    r = anon.post('/billing/jazzcash/return', data=_signed(tid))
    assert r.status_code == 303 and r.location.endswith(f'/billing/jazzcash/{pid}')
    assert 'Set-Cookie' not in r.headers  # must not replace the shop's login cookie
    with app.app_context():
        assert db.session.get(Payment, pid).status == 'approved'
        assert User.query.one().paid_until is not None
    # The shop's own browser follows the GET with its cookie and lands on Dashboard.
    assert client.get(r.location).location.endswith('/dashboard')


def test_signed_decline_marks_failed_and_offers_retry(client, app):
    signup(client)
    pid, tid = _checkout(client, app)
    r = client.post('/billing/jazzcash/return', data=_signed(tid, code='999'))
    page = client.get(r.location)
    assert page.status_code == 200
    assert 'Payment did not go through' in page.text
    assert 'Try JazzCash again' in page.text
    assert client.get(f'/billing/jazzcash/{pid}/state').json['status'] == 'failed'
    with app.app_context():
        p = db.session.get(Payment, pid)
        assert p.status == 'failed' and p.gateway_code == '999'
        assert User.query.one().paid_until is None
    # A late "success" for a ref already marked failed must not grant a month.
    client.post('/billing/jazzcash/return', data=_signed(tid))
    with app.app_context():
        assert db.session.get(Payment, pid).status == 'failed'
        assert User.query.one().paid_until is None
    assert 'not completed' in client.get('/upgrade').text
    client.get('/language/ur?page=upgrade')
    assert 'مکمل نہیں ہوئی' in client.get('/upgrade').text


def test_pending_code_shows_waiting_page(client, app):
    signup(client)
    pid, tid = _checkout(client, app)
    r = client.post('/billing/jazzcash/return', data=_signed(tid, code='157'))
    page = client.get(r.location).text
    assert 'Waiting for JazzCash' in page
    assert f'data-jc-state="/billing/jazzcash/{pid}/state"' in page
    assert client.get(f'/billing/jazzcash/{pid}/state').json == {'status': 'pending', 'done': '/dashboard'}
    with app.app_context():
        assert db.session.get(Payment, pid).gateway_code == '157'
    assert f'/billing/jazzcash/{pid}' in client.get('/upgrade').text  # "Check" link
    switched = client.get('/language/ur?page=jazzcash_wait')
    assert switched.location.endswith('/upgrade')
    assert 'JazzCash کا انتظار' in client.get(f'/billing/jazzcash/{pid}').text


def test_waiting_page_is_owner_only(client, app):
    signup(client)
    pid, _tid = _checkout(client, app)
    client.post('/logout', data={'csrf_token': token(client, '/dashboard')})
    signup(client, phone='03007654321')
    assert client.get(f'/billing/jazzcash/{pid}').status_code == 404
    assert client.get(f'/billing/jazzcash/{pid}/state').status_code == 404
    anon = app.test_client()
    assert anon.get(f'/billing/jazzcash/{pid}').status_code == 302
    assert anon.get(f'/billing/jazzcash/{pid}/state').status_code == 401


def test_return_cannot_touch_pasted_tid_rows(client, app):
    app.config.update(KEYS)
    signup(client)
    client.post('/upgrade', data={'csrf_token': token(client, '/upgrade'), 'tid': 'LIVE-12345'})
    r = client.post('/billing/jazzcash/return', data=_signed('LIVE-12345', amount='000000029900'))
    assert r.status_code == 303 and 'jc=unconfirmed' in r.location
    assert 'JazzCash did not confirm this payment' in client.get(r.location).text
    with app.app_context():
        assert Payment.query.filter_by(tid='LIVE-12345').one().status == 'pending'
        assert User.query.one().paid_until is None


def test_tid_fallback_kept_and_checkout_refs_blocked(client, app):
    app.config.update(KEYS)
    signup(client)
    page = client.get('/upgrade').text
    assert 'Pay Rs 1 with JazzCash' in page
    assert 'Or send money yourself and paste the TID' in page
    assert 'name="tid"' in page
    r = client.post('/upgrade', data={'csrf_token': token(client, '/upgrade'), 'tid': 'T202611141030000001'})
    assert r.status_code == 400
    client.post('/upgrade', data={'csrf_token': token(client, '/upgrade'), 'tid': '123456789'})
    with app.app_context():
        assert Payment.query.filter_by(tid='123456789').one().method == 'tid'


def test_admin_sees_checkouts_apart_and_approval_is_one_shot(client, app):
    app.config.update(ADMIN_PHONES='03001234567')
    signup(client)
    pid, tid = _checkout(client, app)
    client.post('/upgrade', data={'csrf_token': token(client, '/upgrade'), 'tid': '555666777'})
    office = client.get('/admin').text
    assert 'JazzCash checkouts not confirmed' in office
    assert '1 JazzCash checkouts have no confirmation yet' in office
    assert '1 receipts are waiting' in office
    review = client.get('/admin/payments').text
    assert 'JazzCash checkouts not confirmed' in review and tid in review
    # Admin found it paid in the merchant portal and approves...
    r = client.post(f'/admin/payments/{pid}/approve', data={'csrf_token': token(client, '/admin/payments')})
    assert r.status_code == 302
    with app.app_context():
        first = User.query.one().paid_until
        assert first is not None
    # ...then JazzCash's late return arrives: no second month.
    client.post('/billing/jazzcash/return', data=_signed(tid))
    with app.app_context():
        assert User.query.one().paid_until == first
    assert 'JazzCash checkouts not confirmed' not in client.get('/admin').text


def test_upgrade_db_adds_payment_columns(app):
    from sqlalchemy import inspect, text
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE payment DROP COLUMN method'))
            conn.execute(text('ALTER TABLE payment DROP COLUMN gateway_code'))
    assert app.test_cli_runner().invoke(args=['upgrade-db']).exit_code == 0
    with app.app_context():
        cols = {c['name'] for c in inspect(db.engine).get_columns('payment')}
        assert {'method', 'gateway_code'} <= cols


def test_payment_kind_infers_legacy_rows():
    class Row:
        def __init__(self, tid, method=None):
            self.tid, self.method = tid, method
    assert payment_kind(Row('T202611141030000042')) == 'checkout'
    assert payment_kind(Row('TEST-SIM-1-2-ABC')) == 'test'
    assert payment_kind(Row('123456789')) == 'tid'
    assert payment_kind(Row('123456789', 'checkout')) == 'checkout'
