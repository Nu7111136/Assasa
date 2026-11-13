from datetime import datetime, timedelta

from billing import PKT, is_test_tid, period_bounds, pkt, shop_bucket
from main import Payment, ReconNote, User, db, now
from test_signup import signup, token


def login(client, phone='03001234567'):
    return client.post('/login', data=dict(
        phone=phone, password='135790', csrf_token=token(client, '/login')))


def logout(client):
    client.post('/logout', data={'csrf_token': token(client, '/login')})


class Shop:
    def __init__(self, trial_ends_at=None, paid_until=None):
        self.trial_ends_at = trial_ends_at
        self.paid_until = paid_until


def test_is_test_tid_and_shop_buckets():
    assert is_test_tid('TEST-SIM-1')
    assert is_test_tid('test-sim-abc')
    assert not is_test_tid('121212')
    assert not is_test_tid('LIVE-OK-99999')
    at = now()
    assert shop_bucket(Shop(at + timedelta(days=2), None), at) == 'active'
    assert shop_bucket(Shop(at - timedelta(days=1), at + timedelta(days=10)), at) == 'active'
    assert shop_bucket(Shop(at - timedelta(days=1), at - timedelta(days=1)), at) == 'left'
    assert shop_bucket(Shop(at - timedelta(days=1), None), at) == 'unpaid'


def test_period_bounds_month_3m_and_custom():
    at = datetime(2026, 11, 10, 15, 0, tzinfo=PKT)
    start, end, kind = period_bounds('month', at=at)
    assert kind == 'month'
    assert pkt(start).date().isoformat() == '2026-11-01'
    assert pkt(end).date().isoformat() == '2026-11-10'
    start, _end, kind = period_bounds('3m', at=at)
    assert kind == '3m' and pkt(start).date().isoformat() == '2026-09-01'
    start, end, kind = period_bounds('custom', '2026-02-10', '2026-02-01', at)
    assert kind == 'custom'
    assert pkt(start).date().isoformat() == '2026-02-01'
    assert pkt(end).hour == 23 and pkt(end).day == 10
    _start, _end, kind = period_bounds('custom', 'nope', 'still-no', at)
    assert kind == 'month'


def test_office_is_admin_only(client, app):
    signup(client)
    assert client.get('/admin').status_code == 403
    assert client.post('/admin/recon', data={
        'jazzcash_rs': '299', 'csrf_token': token(client, '/upgrade')}).status_code == 403
    with app.app_context():
        User.query.one().trial_ends_at = now() - timedelta(days=1)
        db.session.commit()
    expired = client.get('/admin')
    assert expired.status_code == 302 and expired.location.endswith('/upgrade')
    logout(client)
    guest = client.get('/admin')
    assert guest.status_code == 302 and guest.location.endswith('/login')


def test_office_counts_money_window_recon_and_language(client, app):
    app.config['ADMIN_PHONES'] = '03001234567'
    app.config['TESTER_PHONES'] = '03001234567'
    signup(client)

    logout(client)
    signup(client, phone='03111234567', cnic='11111-1111111-1', name='Left Shop')
    with app.app_context():
        u = User.query.filter_by(phone='03111234567').one()
        u.trial_ends_at = now() - timedelta(days=10)
        u.paid_until = now() - timedelta(days=1)
        u.billing_day = 1
        db.session.commit()

    logout(client)
    signup(client, phone='03221234567', cnic='22222-2222222-2', name='Never Paid')
    with app.app_context():
        u = User.query.filter_by(phone='03221234567').one()
        u.trial_ends_at = now() - timedelta(days=2)
        db.session.commit()

    logout(client)
    signup(client, phone='03331234567', cnic='33333-3333333-3', name='Paid Shop')
    with app.app_context():
        u = User.query.filter_by(phone='03331234567').one()
        u.trial_ends_at = now() - timedelta(days=2)
        u.paid_until = now() + timedelta(days=10)
        u.billing_day = 10
        db.session.commit()

    logout(client)
    assert login(client).status_code == 302
    with app.app_context():
        admin = User.query.filter_by(phone='03001234567').one()
        left = User.query.filter_by(phone='03111234567').one()
        db.session.add(Payment(user_id=left.id, tid='121212', created_at=now(), amount=299))
        db.session.add(Payment(user_id=admin.id, tid='TEST-SIM-ADMIN-1', created_at=now(),
                               amount=299, status='approved'))
        db.session.add(Payment(user_id=admin.id, tid='LIVE-OK-99999', created_at=now(),
                               amount=299, status='approved'))
        db.session.add(Payment(user_id=admin.id, tid='OLD-LIVE-88888',
                               created_at=now() - timedelta(days=100),
                               amount=299, status='approved'))
        db.session.commit()

    office = client.get('/admin')
    assert office.status_code == 200
    text = office.text
    assert 'How the shops are doing' in text
    assert 'Rakhza office' in text
    assert '<span class="n">4</span>' in text
    assert 'Left Shop' in text and 'Left membership' in text
    assert 'Never Paid' in text and 'Trial ended, never paid' in text
    assert 'Paid Shop' in text and 'Active' in text
    assert '121212' in text
    assert 'TEST-SIM-ADMIN-1' in text
    assert 'LIVE-OK-99999' in text
    assert 'OLD-LIVE-88888' not in text
    assert 'Looks like real JazzCash' in text
    assert 'All-time test wallet' in text
    assert 'Rs 299' in text

    payments = client.get('/admin/payments')
    assert payments.status_code == 200
    assert '121212' in payments.text
    assert 'TEST-SIM-ADMIN-1' not in payments.text
    assert 'Rs 299' in payments.text

    six = client.get('/admin?range=6m').text
    assert 'OLD-LIVE-88888' in six
    empty = client.get('/admin?range=custom&from=2020-01-01&to=2020-01-02').text
    assert 'OLD-LIVE-88888' not in empty
    assert 'No receipts in this window' in empty

    saved = client.post('/admin/recon', data={
        'csrf_token': token(client, '/admin'), 'jazzcash_rs': '598',
        'range': 'month', 'from': '', 'to': ''})
    assert saved.status_code == 302 and '/admin' in saved.location
    ticked = client.get('/admin').text
    assert 'Last tick' in ticked and 'Rs 598' in ticked
    with app.app_context():
        note = ReconNote.query.one()
        assert note.jazzcash_rs == 598 and note.created_by == User.query.filter_by(phone='03001234567').one().id

    bad = client.post('/admin/recon', data={
        'csrf_token': token(client, '/admin'), 'jazzcash_rs': 'nope'}, follow_redirects=True)
    assert 'numbers only' in bad.text

    ur = client.get('/language/ur?page=admin_home', follow_redirects=True)
    assert ur.status_code == 200
    assert 'رکھزا دفتر' in ur.text
    assert 'رجسٹرڈ' in ur.text
    assert 'رکنیت چھوڑ دی' in ur.text

    with app.app_context():
        pid = Payment.query.filter_by(tid='121212').one().id
    stay = client.post(f'/admin/payments/{pid}/approve', data={
        'csrf_token': token(client, '/admin'), 'next': 'office'})
    assert stay.status_code == 302 and stay.location.endswith('/admin')
    assert '121212' not in client.get('/admin/payments').text

    client.get('/language/en?page=admin_home')
    sim = client.post('/upgrade/simulate', data={'csrf_token': token(client, '/upgrade')})
    assert sim.status_code == 302
    wallet_page = client.get('/admin').text
    assert 'All-time test wallet' in wallet_page
    assert 'Rs 598' in wallet_page or 'Rs 299' in wallet_page


def test_expired_admin_can_open_office(client, app):
    app.config['ADMIN_PHONES'] = '03001234567'
    signup(client)
    with app.app_context():
        User.query.one().trial_ends_at = now() - timedelta(days=1)
        db.session.commit()
    assert client.get('/dashboard').location.endswith('/upgrade')
    office = client.get('/admin')
    assert office.status_code == 200
    assert 'How the shops are doing' in office.text
    assert client.get('/admin/payments').status_code == 200
