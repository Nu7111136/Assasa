import logging
import math
from datetime import datetime, timedelta, timezone
from billing import pkt, remaining_seconds, utc
from main import db, User, Payment, now
from test_signup import signup, token


def step(client, action='next'):
    return client.post('/test-mode',data={'action':action,'csrf_token':token(client,'/login')})


def test_banner_days(client,app):
    app.config['TESTER_PHONES']='03001234567'
    signup(client)
    for n in range(8):
        page=client.get('/dashboard',follow_redirects=True)
        assert page.status_code==200
        if n>=5:
            assert 'Trial ended, pay to continue' not in page.text
            assert 'Upgrade your account' in page.text
        else:
            assert f'{5-n} '+('day left' if n==4 else 'days left') in page.text
        assert 'Upgrade Now' in page.text
        assert step(client).status_code==302
    upgrade=client.get('/upgrade').text
    assert 'Trial ended, pay to continue' not in upgrade
    assert 'Upgrade Now' in upgrade
    client.get('/language/ur')
    assert '\u0627\u06af\u0644\u0627 \u062f\u0646' in client.get('/dashboard',follow_redirects=True).text
    assert step(client,'reset').status_code==302
    assert 'TEST: Day' not in client.get('/dashboard').text


def test_legacy_simulation_ignored(client,app):
    app.config.update(APP_ENV='dev',FAKE_TODAY='2099-01-01')
    signup(client)
    with client.session_transaction() as s:s['simulate_day']=7
    page=client.get('/dashboard?simulate_day=7')
    assert '5 days left' in page.text
    assert 'tester-buttons' not in page.text
    with client.session_transaction() as s: assert 'simulate_day' not in s


def test_expiry_redirects_mutation_but_allows_payment(client,app):
    app.config['TESTER_PHONES']='03001234567'
    signup(client)
    for _ in range(6):step(client)
    response=client.post('/',data={'csrf_token':token(client,'/upgrade')})
    assert response.status_code==303 and response.location.endswith('/upgrade')
    r=client.post('/upgrade',data={'tid':'TEST-TID-12345','csrf_token':token(client,'/upgrade')})
    assert r.status_code==302
    assert 'pending' in client.get('/upgrade').text
    assert step(client,'reset').status_code==302
    assert '5 days left' in client.get('/dashboard').text


def test_payment_approval_permissions_and_repeated_review(client,app):
    signup(client)
    assert client.get('/admin/payments').status_code==403
    assert client.post('/upgrade',data={'tid':'1234567890','csrf_token':token(client,'/upgrade')}).status_code==302
    with app.app_context():
        p=Payment.query.one();pid=p.id
        assert p.status=='pending'
        assert User.query.one().paid_until is None
    csrf=token(client,'/upgrade')
    assert client.post(f'/admin/payments/{pid}/approve',data={'csrf_token':csrf}).status_code==403
    app.config['ADMIN_PHONES']='03001234567'
    assert '1234567890' in client.get('/admin/payments').text
    before=now()
    assert client.post(f'/admin/payments/{pid}/approve',data={'csrf_token':csrf}).status_code==302
    with app.app_context():
        u=User.query.one();end=utc(u.paid_until)
        assert u.billing_day in (pkt(before).day, pkt(now()).day)
        assert now()+timedelta(days=27) < end < now()+timedelta(days=32)
        assert Payment.query.one().status=='approved'
    paid_page=client.get('/dashboard').text
    assert client.post(f'/admin/payments/{pid}/approve',data={'csrf_token':csrf}).status_code==409
    assert 'Paid access active' in paid_page
    assert 'Paid until (PKT)' in paid_page
    assert 'Days left in your trial' not in paid_page


def test_reject_duplicates_and_validation(client,app):
    signup(client)
    def submit(tid):return client.post('/upgrade',data={'tid':tid,'csrf_token':token(client,'/upgrade')})
    assert submit('<script>').status_code==400
    assert submit('TID-12345').status_code==302
    assert submit('TID-12345').status_code==302
    with app.app_context():assert Payment.query.count()==1
    app.config['ADMIN_PHONES']='03001234567'
    assert client.post('/admin/payments/1/reject',data={'csrf_token':token(client,'/upgrade')}).status_code==302
    with app.app_context():
        assert User.query.one().paid_until is None
        assert Payment.query.one().status=='rejected'
    assert client.post('/admin/payments/1/approve').status_code==400


def test_other_users_payments_private(client,app):
    signup(client)
    client.post('/upgrade',data={'tid':'PRIVATE-TID','csrf_token':token(client,'/upgrade')})
    client.post('/logout',data={'csrf_token':token(client,'/login')})
    signup(client,phone='03111234567')
    assert 'PRIVATE-TID' not in client.get('/upgrade').text
    assert client.get('/admin/payments').status_code==403


def test_simulate_payment_fills_test_wallet(client,app):
    signup(client)
    assert client.post('/upgrade/simulate', data={'csrf_token': token(client, '/upgrade')}).status_code == 403
    app.config['TESTER_PHONES'] = '03001234567'
    app.config['ADMIN_PHONES'] = '03001234567'
    for _ in range(6):
        step(client)
    ok = client.post('/upgrade/simulate', data={'csrf_token': token(client, '/upgrade')})
    assert ok.status_code == 302 and ok.location.endswith('/dashboard')
    paid_page = client.get('/dashboard').text
    assert 'Paid access active' in paid_page
    assert 'Paid until (PKT)' in paid_page
    assert 'Days left in your trial' not in paid_page
    assert 'Your trial has ended' not in paid_page
    admin = client.get('/admin/payments')
    assert 'Rs 299' in admin.text
    with app.app_context():
        p = Payment.query.one()
        assert p.status == 'approved' and p.amount == 299 and p.tid.startswith('TEST-SIM-')


def test_css_preserved():
    from pathlib import Path
    p=Path(__file__).resolve().parents[1]
    css=(p/'static/style.css').read_text()
    assert '--navy:#0949b7' in css
    assert 'background:hsla(229, 59%, 87%, 0.298)' in css
    assert 'var(--navy)' in css.split('/* Trial/payment extension')[1]


def test_paid_expiry(client,app):
    signup(client)
    with app.app_context():
        u=User.query.one()
        u.trial_ends_at=now()-timedelta(days=1)
        u.paid_until=now()+timedelta(days=1)
        db.session.commit()
    paid_page=client.get('/dashboard').text
    assert 'Paid access active' in paid_page
    assert 'Paid until (PKT)' in paid_page
    assert 'Days left in your trial' not in paid_page
    assert 'Your trial has ended' not in paid_page
    assert 'Trial ends (PKT)' not in paid_page
    assert 'Then Rs 299/month' not in paid_page
    with app.app_context():
        User.query.one().paid_until=now()-timedelta(seconds=1)
        db.session.commit()
    expired=client.get('/dashboard',follow_redirects=True).text
    assert 'Trial ended, pay to continue' not in expired
    assert 'Upgrade Now' in expired
    assert 'Upgrade your account' in expired


def test_upgrade_cli_preserves_legacy_users(tmp_path):
    import sqlite3
    from main import create_app
    path=tmp_path/'legacy.db'
    conn=sqlite3.connect(path)
    conn.execute('CREATE TABLE user (id INTEGER PRIMARY KEY, name VARCHAR(120), address VARCHAR(500), cnic VARCHAR(13), phone VARCHAR(11), email VARCHAR(254), password_hash VARCHAR(256), created_at TIMESTAMP, trial_ends_at TIMESTAMP)')
    conn.execute("INSERT INTO user (id,name,phone) VALUES (1,'Legacy Demo','03001112223')")
    conn.commit();conn.close()
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(path)})
    assert app.test_cli_runner().invoke(args=['upgrade-db']).exit_code==0
    assert app.test_cli_runner().invoke(args=['upgrade-db']).exit_code==0
    with app.app_context():
        assert db.session.get(User,1).name=='Legacy Demo'
        assert db.session.get(User,1).paid_until is None
        assert Payment.query.count()==0


def test_allowlisted_steps_and_billing_unchanged(client,app):
    app.config.update(APP_ENV='production',TESTER_PHONES='03001234567')
    signup(client)
    with app.app_context():
        u=User.query.one(); original=(u.created_at,u.trial_ends_at,u.paid_until)
    html=client.get('/dashboard').text
    assert 'Next day' in html and 'Reset' in html
    assert '<select' not in html and 'Test mode' not in html
    for n in range(1,9):
        assert step(client).status_code==302
        assert f'TEST: Day {n}' in client.get('/dashboard',follow_redirects=True).text
    assert 'TEST: Day 8' in client.get('/upgrade').text
    assert step(client,'reset').status_code==302
    assert '5 days left' in client.get('/dashboard').text
    assert 'TEST: Day' not in client.get('/dashboard').text
    with app.app_context():
        u=User.query.one(); assert original==(u.created_at,u.trial_ends_at,u.paid_until)
        assert Payment.query.count()==0
    assert step(client,'on').status_code==400
    assert client.post('/test-mode',data={'action':'next'}).status_code==400


def test_non_tester_and_session_isolation(client,app):
    app.config['TESTER_PHONES']='03001234567'
    signup(client)
    for _ in range(7):step(client)
    other=app.test_client()
    signup(other,phone='03111234567')
    with other.session_transaction() as s:s['tester_day']=7
    html=other.get('/dashboard').text
    assert '5 days left' in html
    assert 'tester-buttons' not in html and 'TEST: Day' not in html
    assert step(other).status_code==403
    ended=client.get('/dashboard',follow_redirects=True).text
    assert 'Trial ended, pay to continue' not in ended
    assert 'Upgrade Now' in ended
    # Same account in a different browser does not inherit simulation.
    another=app.test_client()
    with client.session_transaction() as s: uid=s['user_id']
    with another.session_transaction() as s:s['user_id']=uid
    assert '5 days left' in another.get('/dashboard').text
    app.config['TESTER_PHONES']=''
    assert '5 days left' in client.get('/dashboard').text
    with client.session_transaction() as s:assert 'tester_day' not in s


def test_admin_qualifies_in_dev_and_uses_real_offset(client,app):
    app.config.update(APP_ENV='dev',FAKE_TODAY='2099-01-01',ADMIN_PHONES='03001234567')
    signup(client)
    with app.app_context():
        u=User.query.one();u.created_at=now()-timedelta(days=2);u.trial_ends_at=now()+timedelta(days=3);db.session.commit()
    assert 'tester-buttons' in client.get('/dashboard').text
    assert step(client).status_code==302
    assert '2 days left' in client.get('/dashboard').text
    assert step(client,'reset').status_code==302
    assert '3 days left' in client.get('/dashboard').text


def test_expired_redirects_and_upgrade_controls(client,app):
    app.config['TESTER_PHONES']='03001234567'
    signup(client)
    for n in range(1,7):
        response=step(client)
        assert response.location.endswith('/upgrade' if n>=5 else '/dashboard')
    for path in ('/dashboard','/','/missing','/admin/payments','/stock'):
        response=client.get(path)
        assert response.status_code==302 and response.location.endswith('/upgrade')
    upgrade=client.get('/upgrade')
    assert upgrade.status_code==200
    assert 'Next day' in upgrade.text and 'Reset' in upgrade.text and 'TEST: Day 6' in upgrade.text
    assert client.get('/login').status_code==200
    assert client.get('/static/style.css').status_code==200
    assert client.get('/sw.js').status_code==200
    assert client.get('/language/ur?page=upgrade',follow_redirects=True).status_code==200
    assert step(client,'reset').location.endswith('/dashboard')
    assert client.get('/dashboard').status_code==200
    assert client.post('/logout',data={'csrf_token':token(client,'/login')}).location.endswith('/login')


def test_real_expiry_admin_access_and_paid_simulation(client,app):
    signup(client)
    with app.app_context():
        User.query.one().trial_ends_at=now()-timedelta(days=1)
        db.session.commit()
    assert client.get('/dashboard').location.endswith('/upgrade')
    app.config['ADMIN_PHONES']='03001234567'
    assert client.get('/admin/payments').status_code==200
    assert client.post('/admin/payments/999/approve',data={'csrf_token':token(client,'/upgrade')}).status_code==409
    # Reset cannot revive a genuinely expired trial.
    assert step(client,'reset').location.endswith('/upgrade')
    with app.app_context():
        User.query.one().paid_until=now()+timedelta(days=2)
        db.session.commit()
    assert step(client).location.endswith('/dashboard')
    assert 'Paid access active' in client.get('/dashboard').text
    assert step(client).location.endswith('/upgrade')
    assert client.get('/admin/payments').status_code==200


def test_paid_calendar_month_expires_on_tester_clock(client, app):
    app.config['TESTER_PHONES']='03001234567'
    signup(client)
    for _ in range(6):
        step(client)
    assert client.post('/upgrade/simulate', data={'csrf_token': token(client, '/upgrade')}).status_code == 302
    assert step(client, 'reset').location.endswith('/dashboard')
    with app.app_context():
        u = User.query.one()
        end = utc(u.paid_until)
        assert u.billing_day
        days = math.ceil((end - now()).total_seconds() / 86400)
    for _ in range(max(days, 1) - 1):
        assert step(client).location.endswith('/dashboard')
    assert step(client).location.endswith('/upgrade')
    assert 'Upgrade your account' in client.get('/upgrade').text


def test_remaining_seconds_naive_aware_and_missing():
    aware = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 11, 10, 12, 0)
    later = datetime(2026, 11, 15, 12, 0)
    assert remaining_seconds(None, aware) == 0
    assert remaining_seconds(aware, None) == 0
    assert remaining_seconds(naive, aware) == 0
    assert remaining_seconds(aware, naive) == 0
    assert remaining_seconds(later, naive) == 5 * 86400
    assert utc(None) is None
    assert utc(naive).tzinfo is timezone.utc
    assert utc(aware) is aware


def test_naive_expired_trial_renders_upgrade(client, app, caplog):
    caplog.set_level(logging.INFO, logger='rakhza')
    signup(client)
    with app.app_context():
        u = User.query.one()
        u.trial_ends_at = datetime(2020, 1, 1, 0, 0, 0)
        db.session.commit()
    dashboard = client.get('/dashboard')
    assert dashboard.status_code == 302 and dashboard.location.endswith('/upgrade')
    upgrade = client.get('/upgrade')
    assert upgrade.status_code == 200
    assert 'Upgrade your account' in upgrade.text
    assert 'Upgrade Now' in upgrade.text
    assert 'trial expired, redirecting to upgrade' in caplog.text
    assert 'GET /upgrade -> 200' in caplog.text


def test_expired_logout_and_anonymous_access(client,app):
    assert client.get('/login').status_code==200
    signup(client)
    with app.app_context():
        User.query.one().trial_ends_at=now()-timedelta(seconds=1)
        db.session.commit()
    response=client.post('/logout',data={'csrf_token':token(client,'/upgrade')})
    assert response.location.endswith('/login')
    assert client.get('/login').status_code==200
    assert client.get('/dashboard').location.endswith('/login')
