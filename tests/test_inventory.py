from datetime import timedelta
from decimal import Decimal

from main import Item, StockMove, User, db, now
from test_signup import signup, token


def csrf(client, path='/stock'):
    return token(client, path)


def pick_trade(client, trade='kiryana'):
    return client.post('/stock/trade', data={'trade': trade, 'csrf_token': csrf(client, '/stock')})


def add_item(client, **changes):
    data = dict(name='Sugar', category='Rice', qty='10', unit='kg', min_qty='2',
                buy_rs='80', sell_rs='100', csrf_token=csrf(client, '/stock'))
    data.update(changes)
    return client.post('/stock/new', data=data)


def test_stock_login_and_expired_redirect(client, app):
    assert client.get('/stock').status_code == 302
    signup(client)
    assert client.get('/stock').status_code == 200
    assert 'What do you sell?' in client.get('/stock').text
    with app.app_context():
        User.query.one().trial_ends_at = now() - timedelta(seconds=1)
        db.session.commit()
    ended = client.get('/stock')
    assert ended.status_code == 302 and ended.location.endswith('/upgrade')


def test_trade_add_in_out_low_used_remove(client, app):
    signup(client)
    dash = client.get('/dashboard').text
    assert 'Open my stock' in dash
    assert 'Like your notebook' in dash
    assert dash.find('class="trial paid-top"') < dash.find('<h1>Your dashboard</h1>')
    assert dash.find('Days left in your trial') < dash.find('Welcome')
    assert pick_trade(client).status_code == 302
    page = client.get('/stock').text
    assert 'Inventory' in page
    assert 'Add item' in page
    assert 'inventory_form' not in page
    blank = client.post('/stock/new', data={'blank': '1', 'csrf_token': csrf(client)})
    assert blank.status_code == 302 and 'focus=' in (blank.location or '')
    grid = client.get(blank.location).text
    assert 'class="cell-name"' in grid
    assert 'name="unit"' in grid
    assert 'Box' in grid and 'Litre' in grid and 'Piece' in grid
    assert 'step-btn plus' in grid and 'step-btn minus' in grid
    assert 'step-form' in grid
    assert 'inputmode="decimal"' not in grid
    assert grid.find('stock-table-wrap') < grid.find('stock-add-btn')
    assert '>Item</th>' in grid and '>Type</th>' in grid and '>Qty</th>' in grid and '>Price</th>' in grid
    assert 'cell-price' in grid
    assert 'barcode' not in grid.lower() and 'SKU' not in grid
    with app.app_context():
        blank_id = Item.query.filter_by(name='New item').one().id
    assert client.post(
        f'/stock/{blank_id}/in',
        data={'qty': '1', 'name': 'Milk', 'unit': 'litre', 'csrf_token': csrf(client)},
    ).status_code == 302
    with app.app_context():
        milk = db.session.get(Item, blank_id)
        assert milk.name == 'Milk'
        assert milk.unit == 'litre'
        assert Decimal(str(milk.qty)) == Decimal('1')
    assert add_item(client, qty='3', sell_rs='100').status_code == 302
    grid = client.get('/stock').text
    assert 'Sugar' in grid
    assert grid.find('Milk') < grid.find('Sugar')
    xhr = client.post(
        f'/stock/{blank_id}/in',
        data={'qty': '1', 'csrf_token': csrf(client), 'quiet': '1'},
        headers={'X-Requested-With': 'fetch'},
    )
    assert xhr.status_code == 200
    payload = xhr.get_json()
    assert payload['ok'] is True and payload['qty'] == '2'
    with app.app_context():
        sugar = Item.query.filter_by(name='Sugar').one()
        assert sugar.unit == 'kg'
        assert Decimal(str(sugar.qty)) == Decimal('3')
        iid = sugar.id
    assert client.post(f'/stock/{iid}/out', data={'qty': '1', 'csrf_token': csrf(client)}).status_code == 302
    assert client.post(f'/stock/{iid}/in', data={'qty': '5', 'csrf_token': csrf(client)}).status_code == 302
    with app.app_context():
        item = db.session.get(Item, iid)
        assert Decimal(str(item.qty)) == Decimal('7')
        kinds = {row.kind for row in StockMove.query.all()}
        assert kinds == {'open', 'out', 'in'}
    client.post(f'/stock/{iid}/row', data={'name': 'Sugar', 'unit': 'box', 'sell_rs': '120', 'csrf_token': csrf(client)})
    with app.app_context():
        saved = db.session.get(Item, iid)
        assert saved.unit == 'box'
        assert saved.sell_rs == 120
    client.post(f'/stock/{iid}/out', data={'qty': '6', 'csrf_token': csrf(client)})
    assert 'Running low' in client.get('/stock').text or 'is-low' in client.get('/stock').text
    client.post(f'/stock/{iid}/out', data={'qty': '1', 'csrf_token': csrf(client)})
    empty = client.get('/stock').text
    assert 'Finished' in empty or 'is-out' in empty
    blocked = client.post(f'/stock/{iid}/out', data={'qty': '1', 'csrf_token': csrf(client)}, follow_redirects=True)
    assert 'You do not have that many' in blocked.text
    assert client.post(f'/stock/{iid}/remove', data={'csrf_token': csrf(client, f'/stock/{iid}')}).status_code == 302
    after = client.get('/stock').text
    assert 'Sugar' not in after


def test_other_shop_cannot_touch_item(client, app):
    signup(client)
    pick_trade(client)
    add_item(client)
    with app.app_context():
        iid = Item.query.one().id
    other = app.test_client()
    signup(other, phone='03111234567')
    pick_trade(other)
    assert other.get(f'/stock/{iid}').status_code == 404
    assert other.post(f'/stock/{iid}/out', data={'qty': '1', 'csrf_token': csrf(other)}).status_code == 404


def test_piece_rejects_fraction_and_set_count(client, app):
    signup(client)
    pick_trade(client, 'clothes')
    assert add_item(client, name='Shirt', qty='4', unit='piece', min_qty='1', category='').status_code == 302
    with app.app_context():
        iid = Item.query.one().id
    bad = client.post('/stock/new', data=dict(
        name='Bad', qty='1.5', unit='piece', min_qty='1', csrf_token=csrf(client, '/stock')))
    assert bad.status_code == 400
    assert client.post(f'/stock/{iid}/count', data={'qty': '9', 'csrf_token': csrf(client, f'/stock/{iid}')}).status_code == 302
    with app.app_context():
        assert Decimal(str(db.session.get(Item, iid).qty)) == Decimal('9')
        assert StockMove.query.filter_by(kind='set').count() == 1


def test_urdu_stock_and_keyboard(client):
    signup(client)
    pick_trade(client)
    client.get('/language/ur?page=inventory')
    assert client.get('/stock/new').status_code == 302
    client.post('/stock/new', data={'blank': '1', 'csrf_token': csrf(client)})
    page = client.get('/stock').text
    assert 'مال' in page
    assert 'آئٹم شامل' in page
    assert 'تعداد' in page and 'قسم' in page and 'قیمت' in page
    assert 'data-kb="ur"' in page
    assert 'id="ur-kb"' in page
    assert 'cell-qty' in page
    assert 'lang="en" dir="ltr"' in page
    assert 'inputmode="decimal"' not in page
    assert 'barcode' not in page.lower()
