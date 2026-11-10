"""Shop stock for people who keep a notebook. No SKU, barcode, rack or ERP jargon."""
from decimal import Decimal, InvalidOperation
import re

from flask import abort, flash, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func, inspect, text

log = None

TRADES = (
    'kiryana', 'food', 'clothes', 'tailor', 'stitching', 'plumber',
    'carpenter', 'hardware', 'sports', 'books', 'other')
UNITS = ('piece', 'box', 'kg', 'litre', 'packet', 'meter')
WHOLE_UNITS = frozenset({'piece', 'box', 'packet'})
DEFAULT_UNIT = dict(
    kiryana='kg', food='kg', clothes='piece', tailor='meter', stitching='piece',
    plumber='piece', carpenter='piece', hardware='piece', sports='piece',
    books='piece', other='piece')
MAX_ITEMS = 300
MAX_NOTEBOOKS = 3
KINDS = frozenset({'in', 'out', 'open', 'set'})
TRADE_MARK = dict(
    kiryana='🛒', food='🍽', clothes='👗', tailor='🧵', stitching='🪡',
    plumber='🪠', carpenter='🪚', hardware='🔧', sports='🏏', books='📚',
    other='📦')
NB_FIRST = {
    'en': dict(
        plumber='Workshop', carpenter='Workshop', hardware='Shop',
        kiryana='Shop', clothes='Shop', tailor='Shop', stitching='Shop',
        food='Kitchen', sports='Shop', books='Shop', other='Stock'),
    'ur': dict(
        plumber='ورکشاپ', carpenter='ورکشاپ', hardware='دکان',
        kiryana='دکان', clothes='دکان', tailor='دکان', stitching='دکان',
        food='باورچی خانہ', sports='دکان', books='دکان', other='شمار'),
}
NB_EXTRA = {
    'en': ('Site A', 'Site B'),
    'ur': ('سائٹ اے', 'سائٹ بی'),
}
TEMPLATES = {
    'en': dict(
        kiryana=('Sugar', 'Flour', 'Rice', 'Oil'),
        food=('Chicken', 'Rice', 'Onion', 'Tomato'),
        clothes=('Shirt', 'Trouser', 'Dupatta', 'Shawl'),
        tailor=('Cotton', 'Lawn', 'Silk', 'Linen'),
        plumber=('PVC pipe', 'Thread tape', 'Elbow', 'Tap'),
        carpenter=('Plywood sheet', 'Screw', 'Hinge', 'Nail'),
        stitching=('Thread', 'Needle', 'Button', 'Zip'),
        hardware=('Screw', 'Paint', 'Brush', 'Lock'),
        sports=('Football', 'Bat', 'Gloves', 'Shoes'),
        books=('Notebook', 'Pen', 'Textbook', 'Bag'),
        other=('Notebook', 'Pen', 'Tape', 'Box'),
    ),
    'ur': dict(
        kiryana=('چینی', 'آٹا', 'چاول', 'تیل'),
        food=('چکن', 'چاول', 'پیاز', 'ٹماٹر'),
        clothes=('قمیض', 'پاجامہ', 'دوپٹہ', 'شال'),
        tailor=('سوتی کپڑا', 'لان', 'ریشم', 'لینن'),
        plumber=('پی وی سی پائپ', 'ٹیپ', 'ایلبو', 'نل'),
        carpenter=('پلائی ووڈ', 'پیچ', 'کنڈا', 'کیل'),
        stitching=('دھاگا', 'سوئی', 'بٹن', 'زپ'),
        hardware=('پیچ', 'پینٹ', 'برش', 'تالہ'),
        sports=('فٹبال', 'بیٹ', 'دستانے', 'جوتے'),
        books=('کاپی', 'قلم', 'کتاب', 'بیگ'),
        other=('کاپی', 'قلم', 'ٹیپ', 'ڈبہ'),
    ),
}

INV_NEW_EN = 'New item'
INV_NEW_UR = 'نیا آئٹم'


def _template_names():
    mapping = {
        INV_NEW_EN: {'en': INV_NEW_EN, 'ur': INV_NEW_UR},
        INV_NEW_UR: {'en': INV_NEW_EN, 'ur': INV_NEW_UR},
    }
    for trade in TRADES:
        for en_name, ur_name in zip(TEMPLATES['en'][trade], TEMPLATES['ur'][trade]):
            mapping[en_name] = {'en': en_name, 'ur': ur_name}
            mapping[ur_name] = {'en': en_name, 'ur': ur_name}
    return mapping


NAME_MAP = _template_names()

INV = {
    'en': dict(
        title='Inventory', notebook='Like your notebook',
        pick='What do you sell?',
        pick_help='Tap the closest one. You can change this later.',
        kiryana='Small shop / kiryana', food='Food', clothes='Clothes',
        tailor='Tailor', stitching='Stitching', plumber='Plumber', carpenter='Carpenter',
        hardware='Hardware shop', sports='Sports', books='Books', other='Other',
        open='Open my stock',
        open_help='Add what you keep in the shop. Tap when stock comes in or goes out.',
        add='Add item', add_more='Add more', name='Item name', new_row='New item',
        col_item='Product', col_unit='Unit', col_type='Unit', col_qty='Qty', col_price='Price',
        toast_seed='We put a few items in your inventory. Add and subtract them yourself.',
        nb_new='New inventory', nb_limit='This plan includes 3 inventories. Pay to add another.',
        nb_remove='Delete inventory', nb_ask='Remove this inventory and every item in it?',
        nb_last='Keep at least one inventory.', nb_removed='Inventory removed.',
        site_mark='📍',
        total_items='Total items', need_stock='Need stock', value='Stock value',
        search_ph='Search item', home='Home', tab_stock='Stock',
        stock_in_btn='Stock in', stock_out_btn='Stock out',
        pick_in='Tap the item that came in', pick_out='Tap the item that went out',
        min_mark='Low · min', rs='Rs',
        piece_short='pcs', box_short='box', kg_short='kg', litre_short='L', packet_short='pkt', meter_short='m',
        hint_name='The name you say in the shop. Sugar, pipe, shirt…',
        group='Group (optional)', hint_group='Like rice, or tools. You can leave this empty.',
        qty='How many now', unit='How you count it',
        piece='Piece', box='Box', kg='Kg', litre='Litre', packet='Packet', meter='Meter',
        buy='Buy price, Rs (optional)', sell='Sell price, Rs (optional)',
        minq='Warn me when below', hint_min='We will mark it as running low.',
        save='Save item', came='Came in', went='Sold or used',
        how_in='How many came in?', how_out='How many sold or used?',
        save_in='Add to stock', save_out='Take from stock',
        other_in='Other amount in', other_out='Other amount out',
        not_enough='You do not have that many.',
        low='Running low', empty='Finished', used='Most used', all='All items',
        find='Find an item', none='No items yet. Tap Add item. Type the name on the new row.',
        none_low='Nothing is running low. Good.',
        none_used='As you sell or use items, the ones you use most will show here.',
        none_find='No item with that name.',
        remove='Remove this item', removed='Item removed from your stock.',
        saved='Item saved.', added='Item added.',
        in_ok='Added to stock.', out_ok='Taken from stock.',
        counted='Count saved.',
        count='How many are here now?', set_count='Save this count',
        change_trade='Change shop type',
        you_sell='Your shop type',
        items='Items',
        invalid='Please check the item. Name is required. Numbers must be 0 or more.',
        full='You already have 300 items. Remove one you no longer keep.',
        low_flash='This item is running low.',
        empty_flash='This item is finished.',
        recent='Last changes',
        one='1',
    ),
    'ur': dict(
        title='شمار', notebook='جیسا آپ کی کاپی',
        pick='آپ کیا بیچتے ہیں؟',
        pick_help='قریب ترین آپشن دبائیں۔ بعد میں بدل سکتے ہیں۔',
        kiryana='کریانہ / چھوٹی دکان', food='کھانا', clothes='کپڑے',
        tailor='درزی', stitching='سلائی', plumber='پلمبر', carpenter='بڑھئی',
        hardware='ہارڈویئر', sports='کھیل', books='کتابیں', other='دیگر',
        open='میرا مال کھولیں',
        open_help='دکان کا سامان لکھیں۔ مال آئے یا جائے تو دبائیں۔',
        add='فہرست میں شامل کریں', add_more='اور شامل کریں', name='آئٹم کا نام', new_row='نیا آئٹم',
        col_item='آئٹم', col_unit='اکائی', col_type='اکائی', col_qty='تعداد', col_price='قیمت',
        toast_seed='کچھ آئٹم ہم نے انوینٹری میں ڈال دیے ہیں۔ خود سے جمع تفریق کریں۔',
        nb_new='نیا شمار', nb_limit='اس پلان میں 3 انوینٹری ہیں۔ ایک اور کے لیے ادائیگی کریں۔',
        nb_remove='شمار ہٹائیں', nb_ask='یہ شمار اور اس کے تمام آئٹم ہٹائیں؟',
        nb_last='کم از کم ایک شمار رکھیں۔', nb_removed='شمار ہٹ گیا۔',
        site_mark='📍',
        total_items='کل آئٹم', need_stock='مال چاہیے', value='مال کی قیمت',
        search_ph='آئٹم تلاش کریں', home='گھر', tab_stock='شمار',
        stock_in_btn='مال آیا', stock_out_btn='مال گیا',
        pick_in='جو مال آیا وہ دبائیں', pick_out='جو مال گیا وہ دبائیں',
        min_mark='کم · حد', rs='روپے',
        piece_short='عدد', box_short='ڈبہ', kg_short='کلو', litre_short='لیٹر', packet_short='پیکٹ', meter_short='میٹر',
        hint_name='وہی نام جو دکان میں بولتے ہیں۔ چینی، پائپ، قمیض…',
        group='گروپ (اختیاری)', hint_group='جیسے چاول، یا اوزار۔ خالی چھوڑ سکتے ہیں۔',
        qty='اب کتنے ہیں', unit='کس طرح گنتے ہیں',
        piece='عدد', box='ڈبہ', kg='کلو', litre='لیٹر', packet='پیکٹ', meter='میٹر',
        buy='خرید قیمت، روپے (اختیاری)', sell='فروخت قیمت، روپے (اختیاری)',
        minq='اس سے کم ہوں تو بتائیں', hint_min='کم مال پر نشان لگے گا۔',
        save='آئٹم محفوظ کریں', came='مال آیا', went='بک گیا / استعمال',
        how_in='کتنے آئے؟', how_out='کتنے گئے؟',
        save_in='مال میں شامل کریں', save_out='مال سے نکالیں',
        other_in='اور مقدار اندر', other_out='اور مقدار باہر',
        not_enough='اتنے پاس نہیں ہیں۔',
        low='مال کم ہے', empty='ختم', used='سب سے زیادہ استعمال', all='سب آئٹم',
        find='آئٹم تلاش کریں', none='ابھی کوئی آئٹم نہیں۔ فہرست میں شامل کریں دبائیں اور قطار میں نام لکھیں۔',
        none_low='کوئی چیز کم نہیں۔ ٹھیک ہے۔',
        none_used='جب آپ بیچیں یا استعمال کریں، سب سے زیادہ استعمال یہاں نظر آئے گا۔',
        none_find='اس نام کا آئٹم نہیں۔',
        remove='یہ آئٹم ہٹائیں', removed='آئٹم مال سے ہٹ گیا۔',
        saved='آئٹم محفوظ ہو گیا۔', added='آئٹم شامل ہو گیا۔',
        in_ok='مال میں شامل ہو گیا۔', out_ok='مال سے نکل گیا۔',
        counted='گنتی محفوظ ہو گئی۔',
        count='اب یہاں کتنے ہیں؟', set_count='یہ گنتی محفوظ کریں',
        change_trade='دکان کی قسم بدلیں',
        you_sell='آپ کی دکان',
        items='آئٹم',
        invalid='آئٹم چیک کریں۔ نام ضروری ہے۔ نمبر صفر یا اس سے زیادہ ہوں۔',
        full='300 آئٹم ہو چکے۔ جو نہیں رکھتے اسے ہٹائیں۔',
        low_flash='یہ آئٹم کم رہ گیا ہے۔',
        empty_flash='یہ آئٹم ختم ہو گیا ہے۔',
        recent='آخری تبدیلیاں',
        one='1',
    ),
}


def as_qty(value):
    if value is None:
        return Decimal('0')
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal('0')


def qty_label(value):
    q = as_qty(value)
    if q == q.to_integral_value():
        return str(int(q))
    text = format(q.normalize(), 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text or '0'


def parse_qty(value, allow_zero=False, whole=False):
    raw = (value or '').strip().replace(',', '')
    if not re.fullmatch(r'[0-9]{1,9}(\.[0-9]{1,3})?', raw):
        return None
    q = Decimal(raw)
    if whole and q != q.to_integral_value():
        return None
    if q < 0 or (q == 0 and not allow_zero):
        return None
    return q


def parse_rs(value):
    raw = (value or '').strip()
    if not raw:
        return None
    if not re.fullmatch(r'[0-9]{1,7}', raw):
        return False
    return int(raw)


def stock_status(item):
    qty, floor = as_qty(item.qty), as_qty(item.min_qty)
    if qty <= 0:
        return 'out'
    if qty <= floor:
        return 'low'
    return 'ok'


def first_notebook_name(trade, lang):
    names = NB_FIRST.get(lang) or NB_FIRST['en']
    return names.get(trade) or names['other']


def extra_notebook_name(index, lang):
    names = NB_EXTRA.get(lang) or NB_EXTRA['en']
    if index < 0:
        index = 0
    if index >= len(names):
        return names[-1]
    return names[index]


def show_item_name(name, lang):
    pack = NAME_MAP.get(name or '')
    if not pack:
        return name
    return pack.get(lang) or name


def label_notebooks(books, trade, lang):
    for index, nb in enumerate(books):
        if index == 0:
            nb.label = first_notebook_name(trade, lang)
        else:
            nb.label = extra_notebook_name(index - 1, lang)
    return books


def seed_first_notebook(db, Notebook, Item, StockMove, now, user, lang):
    """Create the first notebook. Seed 4 template items at qty 10 when the book is empty."""
    if not user or not user.trade:
        return False
    existing = Notebook.query.filter_by(user_id=user.id, active=True).order_by(Notebook.id).first()
    if existing:
        return False
    lang = lang if lang in TEMPLATES else 'en'
    at = now()
    nb = Notebook(user_id=user.id, name=first_notebook_name(user.trade, lang), created_at=at, active=True)
    db.session.add(nb)
    db.session.flush()
    orphans = Item.query.filter_by(user_id=user.id).filter(Item.notebook_id.is_(None)).all()
    if orphans:
        for item in orphans:
            item.notebook_id = nb.id
        db.session.commit()
        return False
    unit = DEFAULT_UNIT.get(user.trade, 'piece')
    names = TEMPLATES[lang].get(user.trade) or TEMPLATES[lang]['other']
    for name in names:
        item = Item(
            user_id=user.id, notebook_id=nb.id, name=name, category=None,
            qty=Decimal('10'), unit=unit, min_qty=Decimal('2'),
            active=True, created_at=at)
        db.session.add(item)
        db.session.flush()
        db.session.add(StockMove(
            user_id=user.id, item_id=item.id, kind='open', qty=Decimal('10'),
            qty_before=Decimal('0'), qty_after=Decimal('10'), created_at=at))
    db.session.commit()
    flash(INV[lang]['toast_seed'], 'ok')
    return True


def upgrade_notebook_schema(db, User, Item, Notebook, now_fn):
    inspector = inspect(db.engine)
    if inspector.has_table('item'):
        cols = {c['name'] for c in inspector.get_columns('item')}
        if 'notebook_id' not in cols:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE item ADD COLUMN notebook_id INTEGER'))
    db.create_all()
    for user in User.query.all():
        books = Notebook.query.filter_by(user_id=user.id, active=True).order_by(Notebook.id).all()
        items = Item.query.filter_by(user_id=user.id).all()
        if books:
            first = books[0]
            for item in items:
                if not item.notebook_id:
                    item.notebook_id = first.id
            continue
        if not items and not user.trade:
            continue
        nb = Notebook(
            user_id=user.id, name=first_notebook_name(user.trade or 'other', 'en'),
            created_at=now_fn(), active=True)
        db.session.add(nb)
        db.session.flush()
        for item in items:
            item.notebook_id = nb.id
    db.session.commit()


def register_inventory(app, db, User, Item, StockMove, Notebook, now):
    global log
    import logging
    log = logging.getLogger('asasa')

    def inv():
        return INV[getattr(g, 'lang', 'en')]

    def shop():
        return getattr(g, 'user', None)

    def own_item(iid):
        user = shop()
        item = db.session.get(Item, iid)
        if not user or not item or item.user_id != user.id or not item.active:
            abort(404)
        return item

    def own_notebook(nid):
        user = shop()
        nb = db.session.get(Notebook, nid)
        if not user or not nb or nb.user_id != user.id or not nb.active:
            abort(404)
        return nb

    def notebooks_of(user):
        return Notebook.query.filter_by(user_id=user.id, active=True).order_by(Notebook.id).all()

    def current_notebook(user):
        books = notebooks_of(user)
        if not books:
            return None, books
        want = request.args.get('nb', type=int)
        if want is None:
            raw = request.form.get('nb')
            want = int(raw) if raw and str(raw).isdigit() else None
        for nb in books:
            if nb.id == want:
                return nb, books
        return books[0], books

    def decorate(item, used_map=None):
        copy = inv()
        item.qty_label = qty_label(item.qty)
        item.min_label = qty_label(item.min_qty)
        item.status = stock_status(item)
        item.used_qty = used_map.get(item.id, Decimal('0')) if used_map is not None else Decimal('0')
        item.used_label = qty_label(item.used_qty)
        item.unit_short = copy.get(f'{item.unit}_short', copy.get(item.unit, item.unit))
        item.price_label = f"{copy['rs']} {item.sell_rs:,}" if item.sell_rs else '—'
        shown = show_item_name(item.name, getattr(g, 'lang', 'en'))
        item.show_name = '' if shown in (copy['new_row'], INV_NEW_EN, INV_NEW_UR) else shown
        return item

    def used_totals(user_id):
        rows = db.session.execute(
            db.select(StockMove.item_id, func.coalesce(func.sum(StockMove.qty), 0))
            .where(StockMove.user_id == user_id, StockMove.kind == 'out')
            .group_by(StockMove.item_id)
        ).all()
        return {item_id: as_qty(total) for item_id, total in rows}

    def apply_move(item, kind, amount, at):
        before = as_qty(item.qty)
        if kind == 'in':
            after = before + amount
            logged = amount
        elif kind == 'out':
            if amount > before:
                return None
            after = before - amount
            logged = amount
        elif kind == 'set':
            after = amount
            logged = abs(after - before)
        elif kind == 'open':
            after = amount
            logged = amount
        else:
            return None
        item.qty = after
        db.session.add(StockMove(
            user_id=item.user_id, item_id=item.id, kind=kind, qty=logged,
            qty_before=before, qty_after=after, created_at=at))
        return after

    def flash_level(item, copy):
        status = stock_status(item)
        if status == 'out':
            flash(copy['empty_flash'])
        elif status == 'low':
            flash(copy['low_flash'])

    @app.context_processor
    def inventory_copy():
        user = shop()
        low_n = 0
        item_n = 0
        if user:
            q = Item.query.filter_by(user_id=user.id, active=True)
            item_n = q.count()
            low_n = q.filter(Item.qty <= Item.min_qty).count()
        return dict(inv=inv(), trades=TRADES, units=UNITS, stock_low_n=low_n, stock_item_n=item_n)

    @app.get('/stock')
    def inventory():
        user = shop()
        if not user:
            return redirect(url_for('login'))
        copy = inv()
        if not user.trade:
            return render_template('inventory_trade.html', heading=copy['pick'])
        seed_first_notebook(db, Notebook, Item, StockMove, now, user, getattr(g, 'lang', 'en'))
        notebook, books = current_notebook(user)
        if not notebook:
            return render_template('inventory_trade.html', heading=copy['pick'])
        view = (request.args.get('view') or 'all').lower()
        if view not in ('all', 'low', 'used'):
            view = 'all'
        find = (request.args.get('q') or '').strip()[:40]
        find_safe = re.sub(r'[%_\\]', '', find)
        q = Item.query.filter_by(user_id=user.id, notebook_id=notebook.id, active=True)
        if find_safe:
            q = q.filter(Item.name.ilike(f'%{find_safe}%'))
        used_map = used_totals(user.id)
        all_items = [decorate(row, used_map) for row in q.order_by(Item.id).all()]
        live = Item.query.filter_by(user_id=user.id, notebook_id=notebook.id, active=True).all()
        low_n = sum(1 for row in live if stock_status(row) in ('low', 'out'))
        item_n = len(live)
        value_rs = 0
        for row in live:
            if row.sell_rs:
                value_rs += int(as_qty(row.qty) * Decimal(row.sell_rs))
        items = all_items
        if view == 'low':
            items = [row for row in all_items if row.status in ('low', 'out')]
        elif view == 'used':
            items = [row for row in all_items if row.used_qty > 0]
            items.sort(key=lambda row: (-row.used_qty, row.name.lower()))
        empty = ''
        if not items:
            if find_safe:
                empty = copy['none_find']
            elif view == 'low':
                empty = copy['none_low']
            elif view == 'used':
                empty = copy['none_used']
            else:
                empty = copy['none']
        focus_id = request.args.get('focus', type=int)
        first_id = books[0].id if books else None
        label_notebooks(books, user.trade, getattr(g, 'lang', 'en'))
        return render_template(
            'inventory.html', heading=copy['title'], items=items, view=view, find=find,
            empty=empty, low_n=low_n, item_n=item_n, value_rs=value_rs,
            trade=user.trade, default_unit=DEFAULT_UNIT.get(user.trade, 'piece'), shop=user,
            focus_id=focus_id, notebook=notebook, notebooks=books,
            trade_mark=TRADE_MARK.get(user.trade, '📦'), first_nb_id=first_id,
            nb_room=len(books) < MAX_NOTEBOOKS)

    @app.post('/stock/trade')
    def inventory_trade():
        user = shop()
        if not user:
            return redirect(url_for('login'))
        trade = (request.form.getlist('trade')[0] if request.form.getlist('trade') else request.form.get('trade') or '').strip()
        if trade not in TRADES:
            flash(inv()['invalid'])
            return redirect(url_for('inventory'))
        user.trade = trade
        db.session.commit()
        seed_first_notebook(db, Notebook, Item, StockMove, now, user, getattr(g, 'lang', 'en'))
        log.info('stock trade user=%s trade=%s', user.id, trade)
        return redirect(url_for('inventory'))

    @app.post('/stock/notebooks/new')
    def notebook_new():
        user = shop()
        if not user:
            return redirect(url_for('login'))
        if not user.trade:
            return redirect(url_for('inventory'))
        copy = inv()
        books = notebooks_of(user)
        if len(books) >= MAX_NOTEBOOKS:
            flash(copy['nb_limit'])
            return redirect(url_for('upgrade'))
        lang = getattr(g, 'lang', 'en')
        nb = Notebook(
            user_id=user.id, name=extra_notebook_name(len(books) - 1, lang),
            created_at=now(), active=True)
        db.session.add(nb)
        db.session.commit()
        log.info('stock notebook user=%s nb=%s', user.id, nb.id)
        return redirect(url_for('inventory', nb=nb.id))

    @app.post('/stock/notebooks/<int:nid>/remove')
    def notebook_remove(nid):
        user = shop()
        if not user:
            return redirect(url_for('login'))
        copy = inv()
        nb = own_notebook(nid)
        books = notebooks_of(user)
        if len(books) <= 1:
            flash(copy['nb_last'])
            if wants_xhr():
                return jsonify(ok=False, error=copy['nb_last']), 400
            return redirect(url_for('inventory', nb=nb.id))
        nb.active = False
        for item in Item.query.filter_by(user_id=user.id, notebook_id=nb.id, active=True):
            item.active = False
        db.session.commit()
        log.info('stock notebook remove user=%s nb=%s', user.id, nb.id)
        remain = notebooks_of(user)
        go = remain[0].id if remain else None
        if wants_xhr():
            return jsonify(ok=True, id=nb.id, next=go)
        flash(copy['nb_removed'], 'ok')
        return redirect(url_for('inventory', nb=go) if go else url_for('inventory'))

    @app.route('/stock/new', methods=['GET', 'POST'])
    def inventory_new():
        user = shop()
        if not user:
            return redirect(url_for('login'))
        if not user.trade:
            return redirect(url_for('inventory'))
        copy = inv()
        notebook, _books = current_notebook(user)
        if not notebook:
            return redirect(url_for('inventory'))
        if request.method != 'POST':
            return redirect(url_for('inventory', nb=notebook.id))
        if Item.query.filter_by(user_id=user.id, active=True).count() >= MAX_ITEMS:
            flash(copy['full'])
            return redirect(url_for('inventory', nb=notebook.id))
        if request.form.get('blank'):
            item = Item(
                user_id=user.id, notebook_id=notebook.id, name=copy['new_row'], category=None,
                qty=0, unit=DEFAULT_UNIT.get(user.trade, 'piece'), min_qty=2,
                active=True, created_at=now())
            db.session.add(item)
            db.session.commit()
            log.info('stock row user=%s item=%s nb=%s', user.id, item.id, notebook.id)
            return redirect(url_for('inventory', nb=notebook.id, focus=item.id))
        item, extra = item_from_form(user, None, copy)
        if item is None:
            flash(extra)
            return redirect(url_for('inventory', nb=notebook.id)) if request.form.get('from_grid') else (
                render_template('inventory_form.html', heading=copy['add'], item=None, form=request.form,
                                default_unit=DEFAULT_UNIT.get(user.trade, 'piece')), 400)
        item.notebook_id = notebook.id
        db.session.add(item)
        db.session.flush()
        if extra > 0:
            apply_move(item, 'open', extra, now())
        db.session.commit()
        log.info('stock add item=%s user=%s nb=%s', item.id, user.id, notebook.id)
        return redirect(url_for('inventory', nb=notebook.id, focus=item.id))

    @app.route('/stock/<int:iid>', methods=['GET', 'POST'])
    def inventory_item(iid):
        user = shop()
        if not user:
            return redirect(url_for('login'))
        item = own_item(iid)
        copy = inv()
        if request.method == 'POST':
            saved, extra = item_from_form(user, item, copy)
            if saved is None:
                flash(extra)
                moves = StockMove.query.filter_by(item_id=item.id).order_by(StockMove.id.desc()).limit(8).all()
                return render_template('inventory_item.html', heading=item.name, item=decorate(item), moves=moves,
                                       form=request.form), 400
            db.session.commit()
            log.info('stock edit item=%s user=%s', item.id, user.id)
            if request.form.get('from_grid'):
                return redirect(url_for('inventory', nb=item.notebook_id, focus=item.id))
            flash(copy['saved'], 'ok')
            return redirect(url_for('inventory_item', iid=item.id))
        moves = StockMove.query.filter_by(item_id=item.id).order_by(StockMove.id.desc()).limit(8).all()
        for row in moves:
            row.qty_label = qty_label(row.qty)
            row.before_label = qty_label(row.qty_before)
            row.after_label = qty_label(row.qty_after)
        return render_template('inventory_item.html', heading=item.name, item=decorate(item), moves=moves, form=None)

    @app.get('/stock/pick')
    def stock_pick():
        user = shop()
        if not user:
            return redirect(url_for('login'))
        if not user.trade:
            return redirect(url_for('inventory'))
        kind = 'in' if request.args.get('kind') == 'in' else 'out'
        copy = inv()
        items = [decorate(row) for row in Item.query.filter_by(user_id=user.id, active=True).order_by(Item.name)]
        heading = copy['pick_in'] if kind == 'in' else copy['pick_out']
        return render_template('inventory_pick.html', heading=heading, items=items, kind=kind)

    @app.get('/stock/<int:iid>/move')
    def stock_move(iid):
        user = shop()
        if not user:
            return redirect(url_for('login'))
        item = own_item(iid)
        kind = 'in' if request.args.get('kind') == 'in' else 'out'
        copy = inv()
        heading = copy['how_in'] if kind == 'in' else copy['how_out']
        return render_template('inventory_move.html', heading=heading, item=decorate(item), kind=kind)

    def apply_row_fields(item, copy):
        name = (request.form.get('name') or '').strip() or copy['new_row']
        if len(name) > 80:
            return False
        unit = (request.form.get('unit') or '').strip()
        item.name = name
        if unit in UNITS:
            item.unit = unit
        if 'sell_rs' in request.form:
            sell = parse_rs(request.form.get('sell_rs'))
            if sell is False:
                return False
            item.sell_rs = sell
        return True

    def wants_xhr():
        return request.headers.get('X-Requested-With') in ('fetch', 'XMLHttpRequest')

    def item_json(item, copy, **extra):
        decorate(item)
        payload = dict(
            ok=True, id=item.id, qty=item.qty_label, status=item.status,
            name='' if item.name == copy['new_row'] else item.name,
            unit=item.unit, unit_label=copy.get(item.unit, item.unit),
            price='' if not item.sell_rs else str(item.sell_rs),
            price_label=item.price_label,
        )
        payload.update(extra)
        return jsonify(payload)

    @app.post('/stock/<int:iid>/row')
    def stock_row(iid):
        user = shop()
        if not user:
            return redirect(url_for('login'))
        item = own_item(iid)
        copy = inv()
        if not apply_row_fields(item, copy):
            if wants_xhr():
                return item_json(item, copy, ok=False, error=copy['invalid']), 400
            flash(copy['invalid'])
            return redirect(url_for('inventory', nb=item.notebook_id))
        db.session.commit()
        log.info('stock row save item=%s user=%s', item.id, user.id)
        if wants_xhr():
            return item_json(item, copy)
        return redirect(url_for('inventory', nb=item.notebook_id))

    @app.post('/stock/<int:iid>/in')
    def stock_in(iid):
        return mutate(iid, 'in')

    @app.post('/stock/<int:iid>/out')
    def stock_out(iid):
        return mutate(iid, 'out')

    @app.post('/stock/<int:iid>/count')
    def stock_count(iid):
        return mutate(iid, 'set')

    @app.post('/stock/<int:iid>/remove')
    def stock_remove(iid):
        user = shop()
        if not user:
            return redirect(url_for('login'))
        item = own_item(iid)
        item.active = False
        db.session.commit()
        log.info('stock remove item=%s user=%s', item.id, user.id)
        if wants_xhr():
            return jsonify(ok=True, id=item.id)
        flash(inv()['removed'], 'ok')
        return redirect(url_for('inventory', nb=item.notebook_id))

    def mutate(iid, kind):
        user = shop()
        if not user:
            return redirect(url_for('login'))
        item = own_item(iid)
        copy = inv()
        apply_row_fields(item, copy)
        whole = item.unit in WHOLE_UNITS
        allow_zero = kind == 'set'
        amount = parse_qty(request.form.get('qty'), allow_zero=allow_zero, whole=whole)
        if amount is None or kind not in KINDS:
            if wants_xhr():
                return item_json(item, copy, ok=False, error=copy['invalid']), 400
            flash(copy['invalid'])
            return redirect(request.referrer if request.referrer else url_for('inventory', nb=item.notebook_id))
        after = apply_move(item, kind, amount, now())
        if after is None:
            if wants_xhr():
                return item_json(item, copy, ok=False, error=copy['not_enough']), 409
            flash(copy['not_enough'])
            return redirect(url_for('inventory', nb=item.notebook_id))
        db.session.commit()
        log.info('stock %s item=%s user=%s', kind, item.id, user.id)
        if wants_xhr():
            return item_json(item, copy)
        quiet = request.form.get('quiet')
        if not quiet:
            if kind == 'in':
                flash(copy['in_ok'], 'ok')
            elif kind == 'out':
                flash(copy['out_ok'], 'ok')
            else:
                flash(copy['counted'], 'ok')
        flash_level(item, copy)
        return redirect(url_for('inventory', nb=item.notebook_id))

    def item_from_form(user, item, copy):
        f = request.form
        name = (f.get('name') or '').strip()
        category = (f.get('category') or '').strip()
        unit = (f.get('unit') or '').strip()
        if unit not in UNITS:
            unit = DEFAULT_UNIT.get(user.trade, 'piece')
        whole = unit in WHOLE_UNITS
        min_raw = (f.get('min_qty') or '').strip()
        minq = Decimal('2') if not min_raw else parse_qty(min_raw, allow_zero=True, whole=whole)
        buy = parse_rs(f.get('buy_rs'))
        sell = parse_rs(f.get('sell_rs'))
        if item is None:
            qty_raw = (f.get('qty') or '').strip()
            qty = Decimal('0') if not qty_raw else parse_qty(qty_raw, allow_zero=True, whole=whole)
        else:
            qty = as_qty(item.qty)
        if not (0 < len(name) <= 80) or len(category) > 40 or qty is None or minq is None or buy is False or sell is False:
            return None, copy['invalid']
        if item is None:
            item = Item(user_id=user.id, created_at=now(), active=True, qty=0)
            notebook, _books = current_notebook(user)
            if notebook:
                item.notebook_id = notebook.id
        item.name = name
        item.category = category or None
        item.unit = unit
        item.min_qty = minq
        item.buy_rs = buy
        item.sell_rs = sell
        return item, qty
