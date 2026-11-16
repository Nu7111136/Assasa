"""JazzCash server notification (IPN) and the status-inquiry sweep."""
from datetime import timedelta
from pathlib import Path

from jazzcash import inquiry_fields, ipn_reply, read_inquiry, secure_hash
from main import Payment, User, db, now
from test_jazzcash_flow import KEYS, _checkout, _signed, _P
from test_signup import app, client, signup, token  # noqa: F401  (fixtures)

ROOT = Path(__file__).resolve().parents[1]


def _sweep(app, post, at=None):
    with app.app_context():
        return app.extensions['rakhza_jazzcash_sweep'](post=post, at=at)


def _age(app, pid, minutes):
    with app.app_context():
        p = db.session.get(Payment, pid)
        p.created_at = now() - timedelta(minutes=minutes)
        db.session.commit()


def _answer(tid, pay_code='121', status='Completed', amount='000000000100', code='000', salt='SALT'):
    resp = {'pp_ResponseCode': code, 'pp_TxnRefNo': tid, 'pp_PaymentResponseCode': pay_code,
            'pp_Status': status, 'pp_Amount': amount}
    resp['pp_SecureHash'] = secure_hash(resp, salt)
    return resp


# ---- IPN -------------------------------------------------------------------

def test_ipn_is_off_without_keys(client):
    assert client.post('/billing/jazzcash/ipn', data={'pp_TxnRefNo': 'x'}).status_code == 404


def test_ipn_form_grants_month_without_browser(client, app):
    signup(client)
    pid, tid = _checkout(client, app)
    jc = app.test_client()  # JazzCash's server: no cookie, no CSRF token
    r = jc.post('/billing/jazzcash/ipn', data=_signed(tid))
    assert r.status_code == 200
    assert r.json['pp_ResponseCode'] == '000'
    assert r.json['pp_SecureHash'] == ipn_reply(KEYS, True)['pp_SecureHash']
    assert 'Set-Cookie' not in r.headers
    with app.app_context():
        assert db.session.get(Payment, pid).status == 'approved'
        first = User.query.one().paid_until
        assert first is not None
    # JazzCash retries the IPN, and the browser return lands too: still one month.
    jc.post('/billing/jazzcash/ipn', data=_signed(tid))
    client.post('/billing/jazzcash/return', data=_signed(tid))
    with app.app_context():
        assert User.query.one().paid_until == first
    # The shop's waiting page now moves straight to Dashboard.
    assert client.get(f'/billing/jazzcash/{pid}').location.endswith('/dashboard')


def test_ipn_accepts_json(client, app):
    signup(client)
    pid, tid = _checkout(client, app)
    r = app.test_client().post('/billing/jazzcash/ipn', json=_signed(tid))
    assert r.status_code == 200 and r.json['pp_ResponseCode'] == '000'
    with app.app_context():
        assert db.session.get(Payment, pid).status == 'approved'


def test_ipn_rejects_forgery_and_decline_marks_failed(client, app):
    signup(client)
    pid, tid = _checkout(client, app)
    jc = app.test_client()
    forged = _signed(tid, salt='GUESS')
    r = jc.post('/billing/jazzcash/ipn', data=forged)
    assert r.status_code == 400 and r.json['pp_ResponseCode'] == '199'
    assert jc.post('/billing/jazzcash/ipn', data=_signed('T000000000000000000')).status_code == 400
    with app.app_context():
        assert db.session.get(Payment, pid).status == 'pending'
    r = jc.post('/billing/jazzcash/ipn', data=_signed(tid, code='999'))
    assert r.status_code == 200
    with app.app_context():
        p = db.session.get(Payment, pid)
        assert p.status == 'failed' and p.gateway_code == '999'
        assert User.query.one().paid_until is None


# ---- inquiry reader -------------------------------------------------------------

def test_inquiry_request_is_signed():
    fields = inquiry_fields(KEYS, 'T202611141030000042')
    assert fields['pp_MerchantID'] == 'MC1' and fields['pp_TxnRefNo'] == 'T202611141030000042'
    assert fields['pp_SecureHash'] == secure_hash(fields, 'SALT')


def test_read_inquiry_outcomes():
    p = _P()
    cfg = KEYS
    assert read_inquiry(_answer(p.tid), p, cfg)[0] == 'approve'
    assert read_inquiry(_answer(p.tid, pay_code='000', status=''), p, cfg)[0] == 'approve'
    assert read_inquiry(_answer(p.tid, pay_code='', status='Pending'), p, cfg)[0] == 'pending'
    assert read_inquiry(_answer(p.tid, pay_code='157', status=''), p, cfg)[0] == 'pending'
    assert read_inquiry(_answer(p.tid, pay_code='', status='Failed'), p, cfg)[0] == 'decline'
    assert read_inquiry(_answer(p.tid, amount='000000029900'), p, cfg) == ('invalid', 'amount_mismatch')
    assert read_inquiry(_answer(p.tid, salt='OTHER'), p, cfg) == ('invalid', 'bad_hash')
    assert read_inquiry(_answer(p.tid, code='110'), p, cfg)[0] == 'invalid'
    assert read_inquiry(_answer('T999999999999999999'), p, cfg) == ('invalid', 'ref_mismatch')
    assert read_inquiry('nope', p, cfg)[0] == 'invalid'
    unsigned = {'pp_ResponseCode': '000', 'pp_PaymentResponseCode': '121'}
    assert read_inquiry(unsigned, p, cfg)[0] == 'approve'  # we called JazzCash over TLS


# ---- sweep ----------------------------------------------------------------------

def test_sweep_skips_without_keys(app):
    assert _sweep(app, post=lambda *a: 1 / 0) == dict(
        checked=0, approved=0, failed=0, expired=0, waiting=0, errors=0, skipped=1)


def test_sweep_approves_paid_checkout(client, app):
    signup(client)
    pid, tid = _checkout(client, app)
    calls = []

    def fake_post(url, payload):
        calls.append((url, payload))
        return _answer(payload['pp_TxnRefNo'])

    assert _sweep(app, fake_post)['checked'] == 0  # too fresh: give the return/IPN a chance
    _age(app, pid, 10)
    counts = _sweep(app, fake_post)
    assert counts['checked'] == 1 and counts['approved'] == 1
    url, payload = calls[0]
    assert url.endswith('/ApplicationAPI/API/PaymentInquiry/Inquire')
    assert payload['pp_TxnRefNo'] == tid and payload['pp_SecureHash']
    with app.app_context():
        assert db.session.get(Payment, pid).status == 'approved'
        first = User.query.one().paid_until
        assert first is not None
    # Next round: nothing pending, nothing granted twice.
    assert _sweep(app, fake_post)['checked'] == 0
    with app.app_context():
        assert User.query.one().paid_until == first


def test_sweep_waits_then_expires_abandoned_checkout(client, app):
    signup(client)
    pid, _tid = _checkout(client, app)
    not_found = lambda url, payload: {'pp_ResponseCode': '110', 'pp_ResponseMessage': 'not found'}
    _age(app, pid, 30)
    assert _sweep(app, not_found)['waiting'] == 1
    with app.app_context():
        assert db.session.get(Payment, pid).status == 'pending'
    _age(app, pid, (3 + 1) * 60 + 5)
    assert _sweep(app, not_found)['expired'] == 1
    with app.app_context():
        p = db.session.get(Payment, pid)
        assert p.status == 'failed' and p.gateway_code == 'expired'
        assert User.query.one().paid_until is None


def test_sweep_never_expires_on_suspicious_answer_or_network_error(client, app):
    signup(client)
    pid, tid = _checkout(client, app)
    _age(app, pid, 6 * 60)
    wrong_amount = lambda url, payload: _answer(tid, amount='000000000001')
    assert _sweep(app, wrong_amount)['waiting'] == 1

    def down(url, payload):
        raise TimeoutError('jazzcash slow')

    assert _sweep(app, down)['errors'] == 1
    with app.app_context():
        assert db.session.get(Payment, pid).status == 'pending'
        assert User.query.one().paid_until is None


def test_sweep_marks_clear_failure_and_ignores_tid_rows(client, app):
    signup(client)
    pid, tid = _checkout(client, app)
    client.post('/upgrade', data={'csrf_token': token(client, '/upgrade'), 'tid': '987654321'})
    with app.app_context():
        for p in Payment.query.all():
            p.created_at = now() - timedelta(minutes=10)
        db.session.commit()
    seen = []

    def failed(url, payload):
        seen.append(payload['pp_TxnRefNo'])
        return _answer(payload['pp_TxnRefNo'], pay_code='', status='Failed')

    assert _sweep(app, failed)['failed'] == 1
    assert seen == [tid]  # pasted TIDs are never sent to JazzCash
    with app.app_context():
        assert db.session.get(Payment, pid).status == 'failed'
        assert Payment.query.filter_by(tid='987654321').one().status == 'pending'


def test_sweep_cli_runs_once(app):
    result = app.test_cli_runner().invoke(args=['jazzcash-sweep'])
    assert result.exit_code == 0


def test_compose_runs_a_sweep_per_environment():
    compose = (ROOT / 'compose.yaml').read_text(encoding='utf-8')
    update = (ROOT / 'deploy' / 'update.sh').read_text(encoding='utf-8')
    assert 'sweep_prod:' in compose and 'sweep_staging:' in compose
    assert compose.count('"jazzcash-sweep", "--loop", "300"') == 2
    assert 'web_staging sweep_staging' in update and 'web_prod sweep_prod' in update
