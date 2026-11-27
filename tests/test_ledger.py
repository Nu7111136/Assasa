"""Ledger: plus / minus entries by date, running total, WhatsApp export."""
from datetime import date, timedelta
from urllib.parse import unquote

from main import LedgerEntry, User, db, now
from ledger import PKT, parse_amount, wa_number
from test_signup import app, client, signup, token  # noqa: F401  (fixtures)


def money(v):
    return f'Rs <bdi lang="en" dir="ltr">{v}</bdi>'


def today():
    return now().astimezone(PKT).date()


def add(client, kind='plus', amount='500', day=None, note=''):
    data = dict(kind=kind, amount=amount, note=note, csrf_token=token(client, '/ledger'))
    if day is not None:
        data['day'] = day.isoformat() if isinstance(day, date) else day
    return client.post('/ledger/add', data=data)


def test_ledger_needs_login_and_active_account(client, app):
    assert client.get('/ledger').status_code == 302
    signup(client)
    page = client.get('/ledger')
    assert page.status_code == 200 and 'Ledger' in page.text and money('+0') in page.text
    with app.app_context():
        User.query.one().trial_ends_at = now() - timedelta(seconds=1)
        db.session.commit()
    ended = client.get('/ledger')
    assert ended.status_code == 302 and ended.location.endswith('/upgrade')


def test_plus_minus_and_total_kept(client, app):
    signup(client)
    assert add(client, 'plus', '1,500', note='Ali paid').status_code == 302
    add(client, 'minus', '400', note='Rent')
    add(client, 'minus', '2000', note='Supplier')
    page = client.get('/ledger').text
    assert money('−900') in page  # 1500 - 400 - 2000
    assert 'Ali paid' in page and 'Rent' in page
    assert '+1,500' in page and '−2,400' in page  # day in / out
    dash = client.get('/dashboard').text
    assert 'Open my ledger' in dash and money('−900') in dash
    with app.app_context():
        assert LedgerEntry.query.count() == 3


def test_entries_are_kept_per_date(client):
    signup(client)
    t = today()
    y = t - timedelta(days=1)
    add(client, 'plus', '100', day=y, note='yesterday-in')
    add(client, 'plus', '700', day=t, note='today-in')
    on_y = client.get(f'/ledger?day={y.isoformat()}').text
    assert 'yesterday-in' in on_y and 'today-in' not in on_y
    on_t = client.get('/ledger').text
    assert 'today-in' in on_t and 'yesterday-in' not in on_t
    assert money('+800') in on_t  # total is all dates


def test_full_ledger_is_date_wise_with_running_balance(client):
    signup(client)
    t = today()
    add(client, 'plus', '300', day=t, note='third')
    add(client, 'plus', '1000', day=t - timedelta(days=5), note='first')
    add(client, 'minus', '200', day=t - timedelta(days=2), note='second')
    full = client.get('/ledger?view=all').text
    assert full.index('first') < full.index('second') < full.index('third')
    assert '+1,000' in full and '+800' in full and '+1,100' in full  # running balance
    assert full.rindex(money('+1,100')) > full.index('third')  # total at the end
    assert 'Send full ledger' in full


def test_bad_entries_rejected(client, app):
    signup(client)
    for amount in ('0', '-5', 'abc', '', '1.5', '9999999999'):
        add(client, 'plus', amount)
    add(client, 'other', '50')
    add(client, 'plus', '50', day=today() + timedelta(days=1))
    with app.app_context():
        assert LedgerEntry.query.count() == 0
    assert parse_amount('1,234') == 1234 and parse_amount('0') is None


def test_remove_entry_changes_total_and_is_owner_only(client, app):
    signup(client)
    add(client, 'plus', '900')
    add(client, 'plus', '100')
    with app.app_context():
        first = LedgerEntry.query.order_by(LedgerEntry.id).first().id
    r = client.post(f'/ledger/{first}/remove', data={'csrf_token': token(client, '/ledger')})
    assert r.status_code == 302
    assert money('+100') in client.get('/ledger').text
    client.post('/logout', data={'csrf_token': token(client, '/dashboard')})
    signup(client, phone='03007654321')
    with app.app_context():
        other = LedgerEntry.query.filter_by(active=True).first().id
    assert client.post(f'/ledger/{other}/remove', data={'csrf_token': token(client, '/ledger')}).status_code == 404
    assert money('+0') in client.get('/ledger').text  # never sees another shop's entries


def test_whatsapp_export_day_and_full(client):
    signup(client)
    t = today()
    add(client, 'plus', '1200', day=t, note='Ali paid')
    add(client, 'minus', '200', day=t - timedelta(days=1), note='Tea')
    data = dict(phone='0300 1112223', scope='day', day=t.isoformat(), csrf_token=token(client, '/ledger'))
    r = client.post('/ledger/whatsapp', data=data)
    assert r.status_code == 302 and r.location.startswith('https://wa.me/923001112223?text=')
    text = unquote(r.location.split('text=', 1)[1])
    assert 'Ali paid' in text and 'Tea' not in text
    assert 'Day total: Rs +1,200' in text and 'Total: Rs +1,000' in text
    assert 'value="03001112223"' in client.get('/ledger').text  # number remembered
    data.update(scope='all', csrf_token=token(client, '/ledger'))
    text = unquote(client.post('/ledger/whatsapp', data=data).location.split('text=', 1)[1])
    assert text.index('Tea') < text.index('Ali paid') and 'Total: Rs +1,000' in text


def test_whatsapp_bad_number_and_long_ledger(client):
    signup(client)
    bad = client.post('/ledger/whatsapp', data=dict(phone='12345', scope='day', csrf_token=token(client, '/ledger')))
    assert bad.status_code == 302 and 'wa.me' not in bad.location
    assert 'WhatsApp number must be' in client.get(bad.location).text
    for i in range(150):
        add(client, 'plus', '10', note=f'sale number {i:03d}')
    r = client.post('/ledger/whatsapp', data=dict(phone='03001112223', scope='all', csrf_token=token(client, '/ledger')))
    assert len(r.location) < 4200
    text = unquote(r.location.split('text=', 1)[1])
    assert 'earlier entries not shown' in text and 'sale number 149' in text and 'Total: Rs +1,500' in text
    assert wa_number('+923001112223') == ('03001112223', '923001112223')


def test_urdu_ledger_and_tab(client):
    signup(client)
    client.get('/language/ur?page=ledger')
    page = client.get('/ledger').text
    assert 'کھاتہ' in page and 'dir="rtl"' in page and 'data-kb="ur"' in page
    assert 'href="/ledger"' in client.get('/stock').text
