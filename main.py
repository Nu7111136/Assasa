import hmac
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash, check_password_hash

from billing import register_billing, utc
from inventory import register_inventory

load_dotenv()
db = SQLAlchemy()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])

TEXT = {
'en': dict(signup='Create your account', name='Name', address='Address', cnic='CNIC', phone='Phone', email='Email (optional)', password='MPIN', submit='Start free trial', login='Log in', logout='Log out', dashboard='Your dashboard', trial='5 days free. No payment needed now.', price='Then Rs 299/month. No automatic charges.', have='Already registered?', new='New to Asasa?', days='Days left in your trial', ends='Trial ends (PKT)', expired='Your trial has ended.', paid_until_label='Paid until (PKT)', paid_help='Pay again by this date to keep the next month. The day stays the same each month, or the last day if that month is shorter.', welcome='Welcome', invalid='Please check your details. Name and address are required, CNIC must have 13 digits, phone must be 03XXXXXXXXX, email must be valid if supplied, and MPIN must be 6 numbers.', duplicate='This phone is already registered. Please log in.', denied='Incorrect phone or MPIN.', forgot='Forgot MPIN?', forgot_title='Reset your MPIN', forgot_help='Enter the phone and CNIC you used at signup, then choose 6 new numbers.', forgot_submit='Save new MPIN', forgot_denied='Phone or CNIC does not match our records.', forgot_ok='MPIN updated. Log in with your new MPIN.', confirm='Type MPIN again', mismatch='Both MPINs must be the same 6 numbers.', back='Back', copy_number='Copy number', copied='Copied', show_pass='Show', hide_pass='Hide', hint_name='Write your name as people know you.', hint_address='Shop or home address is fine.', hint_cnic='13 numbers from your ID card. Dashes appear automatically.', hint_phone='Your mobile number. Start with 03, 11 digits in total.', hint_email='Optional. You can leave this empty.', hint_password='Six numbers, like JazzCash. Do not use your JazzCash MPIN. Do not tell anyone.', hint_confirm='Type the same six numbers again.', hint_tid='Copy the ID from your JazzCash receipt. Never type your PIN here.', privacy='POC: use fictional details only. CNIC and phone are not verified.', install='Install: Android → browser menu → Install app. iPhone → Share → Add to Home Screen.', offline='You are offline. Connect to the internet to sign up or log in.'),
'ur': dict(signup='اپنا اکاؤنٹ بنائیں', name='نام', address='پتہ', cnic='شناختی کارڈ نمبر', phone='فون نمبر', email='ای میل (اختیاری)', password='ایم پن', submit='مفت آزمائش شروع کریں', login='لاگ ان', logout='لاگ آؤٹ', dashboard='آپ کا ڈیش بورڈ', trial='پانچ دن مفت۔ ابھی ادائیگی کی ضرورت نہیں۔', price='اس کے بعد 299 روپے ماہانہ۔ خودکار ادائیگی نہیں ہوگی۔', have='پہلے سے اکاؤنٹ ہے؟', new='نیا اکاؤنٹ بنائیں؟', days='آزمائش کے باقی دن', ends='آزمائش کا اختتام (پاکستان وقت)', expired='آپ کی آزمائش ختم ہو گئی ہے۔', paid_until_label='ادائیگی کی میعاد (پاکستان وقت)', paid_help='اگلے مہینے کے لیے اس تاریخ تک دوبارہ ادا کریں۔ تاریخ ہر مہینے وہی رہتی ہے، چھوٹے مہینے میں آخری دن۔', welcome='خوش آمدید', invalid='معلومات درست کریں۔ نام اور پتہ ضروری ہیں، شناختی نمبر 13 ہندسوں کا، فون 03 سے شروع ہونے والا 11 ہندسوں کا اور ایم پن چھ ہندسوں کا ہونا چاہیے۔ ای میل دیں تو درست لکھیں۔', duplicate='یہ فون پہلے سے رجسٹرڈ ہے۔ لاگ ان کریں۔', denied='فون نمبر یا ایم پن درست نہیں۔', forgot='ایم پن بھول گئے؟', forgot_title='ایم پن تبدیل کریں', forgot_help='رجسٹریشن والا فون اور شناختی نمبر درج کریں، پھر چھ نئے نمبر چنیں۔', forgot_submit='نیا ایم پن محفوظ کریں', forgot_denied='فون نمبر یا شناختی نمبر درست نہیں۔', forgot_ok='ایم پن بدل گیا۔ نئے ایم پن سے لاگ ان کریں۔', confirm='ایم پن دوبارہ لکھیں', mismatch='دونوں ایم پن ایک جیسے چھ ہندسے ہوں۔', back='واپس', copy_number='نمبر کاپی کریں', copied='کاپی ہو گیا', show_pass='دکھائیں', hide_pass='چھپائیں', hint_name='وہ نام لکھیں جس سے لوگ آپ کو جانتے ہیں۔', hint_address='دکان یا گھر کا پتہ کافی ہے۔', hint_cnic='شناختی کارڈ کے 13 ہندسے۔ ڈیش خود لگ جائیں گے۔', hint_phone='آپ کا موبائل نمبر۔ 03 سے شروع، کل 11 ہندسے۔', hint_email='اختیاری ہے۔ خالی چھوڑ سکتے ہیں۔', hint_password='چھ نمبر، JazzCash کی طرح۔ اپنا JazzCash ایم پن یہاں نہ رکھیں۔ کسی کو نہ بتائیں۔', hint_confirm='وہی چھ نمبر دوبارہ لکھیں تاکہ غلطی نہ ہو۔', hint_tid='JazzCash رسید سے آئی ڈی نقل کریں۔ پن یہاں نہ لکھیں۔', privacy='یہ ابتدائی نمونہ ہے۔ صرف فرضی معلومات استعمال کریں۔ شناختی کارڈ اور فون کی تصدیق نہیں ہوتی۔', install='اینڈرائیڈ: براؤزر مینو سے ایپ انسٹال کریں۔ آئی فون: شیئر سے ہوم اسکرین پر شامل کریں۔', offline='انٹرنیٹ بند ہے۔ رجسٹریشن یا لاگ ان کے لیے انٹرنیٹ سے جڑیں۔')}


log = logging.getLogger('asasa')


def now():
    return datetime.now(timezone.utc)


def is_mpin(value):
    return bool(re.fullmatch(r'[0-9]{6}', value or ''))


def configure_logging(app):
    """Stdout logs for local terminal and Render → Logs. LOG_LEVEL=INFO|DEBUG."""
    allowed = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
    level_name = (os.getenv('LOG_LEVEL') or 'INFO').upper()
    if app.config.get('TESTING') and 'LOG_LEVEL' not in os.environ:
        level_name = 'WARNING'
    if level_name not in allowed:
        level_name = 'INFO'
    level = getattr(logging, level_name)
    app.config['LOG_LEVEL'] = level_name
    log.setLevel(level)
    log.propagate = False
    if not any(isinstance(handler, logging.StreamHandler) for handler in log.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [asasa] %(message)s'))
        handler.setLevel(level)
        log.addHandler(handler)
    else:
        for handler in log.handlers:
            handler.setLevel(level)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(500), nullable=False)
    cnic = db.Column(db.String(13), nullable=False)
    phone = db.Column(db.String(11), unique=True, nullable=False)
    email = db.Column(db.String(254))
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    paid_until = db.Column(db.DateTime(timezone=True))
    billing_day = db.Column(db.Integer)
    trial_ends_at = db.Column(db.DateTime(timezone=True), nullable=False)
    trade = db.Column(db.String(16))


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tid = db.Column(db.String(64), nullable=False, unique=True)
    amount = db.Column(db.Integer, nullable=False, default=299)
    status = db.Column(db.String(12), nullable=False, default='pending')
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    reviewed_at = db.Column(db.DateTime(timezone=True))
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'))


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    category = db.Column(db.String(40))
    qty = db.Column(db.Numeric(12, 3), nullable=False, default=0)
    unit = db.Column(db.String(12), nullable=False, default='piece')
    buy_rs = db.Column(db.Integer)
    sell_rs = db.Column(db.Integer)
    min_qty = db.Column(db.Numeric(12, 3), nullable=False, default=2)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)


class StockMove(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False, index=True)
    kind = db.Column(db.String(8), nullable=False)
    qty = db.Column(db.Numeric(12, 3), nullable=False)
    qty_before = db.Column(db.Numeric(12, 3), nullable=False)
    qty_after = db.Column(db.Numeric(12, 3), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)


class ReconNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    period_from = db.Column(db.DateTime(timezone=True), nullable=False)
    period_to = db.Column(db.DateTime(timezone=True), nullable=False)
    jazzcash_rs = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))


def database_uri(value):
    """Use psycopg v3 for standard Neon/legacy PostgreSQL URLs."""
    uri = (value or '').strip() or 'sqlite:///asasa.db'
    if uri.startswith(('postgres://', 'postgresql://')):
        uri = 'postgresql+psycopg://' + uri.split('://', 1)[1]
    return uri


def create_app(config=None):
    app = Flask(__name__)
    uri = database_uri(os.getenv('DATABASE_URL'))
    app.config.update(SECRET_KEY=os.getenv('SECRET_KEY') or os.urandom(32), SQLALCHEMY_DATABASE_URI=uri,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE') == '1', MAX_CONTENT_LENGTH=16384,
                      RATELIMIT_STORAGE_URI=os.getenv('RATELIMIT_STORAGE_URI', 'memory://'))
    if config:
        app.config.update(config)
    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    configure_logging(app)

    @app.before_request
    def language():
        g.lang = session.get('lang', 'en')
        g.t = TEXT[g.lang]

    @app.context_processor
    def context():
        dest = {
            'login': 'signup',
            'forgot_password': 'login',
            'upgrade': 'dashboard',
            'admin_home': 'dashboard',
            'admin_payments': 'admin_home',
            'inventory': 'dashboard',
            'inventory_new': 'inventory',
            'inventory_item': 'inventory',
            'stock_move': 'inventory',
            'stock_pick': 'inventory',
        }.get(request.endpoint)
        return dict(t=g.t, lang=g.lang, back_href=url_for(dest) if dest else '')

    @app.after_request
    def headers(r):
        if request.endpoint != 'static':
            r.headers['Cache-Control'] = 'no-store'
        r.headers['X-Content-Type-Options'] = 'nosniff'
        r.headers['X-Frame-Options'] = 'DENY'
        r.headers['Referrer-Policy'] = 'same-origin'
        return r

    @app.after_request
    def log_request(r):
        path = request.path
        quiet = path.startswith('/static/') or path == '/sw.js'
        line = '%s %s -> %s user=%s readonly=%s trial_days=%s paid=%s'
        args = (request.method, path, r.status_code,
                getattr(getattr(g, 'user', None), 'id', None),
                getattr(g, 'readonly', None), getattr(g, 'trial_days', None),
                getattr(g, 'paid', None))
        if quiet:
            log.debug(line, *args)
        else:
            log.info(line, *args)
        return r

    @app.errorhandler(Exception)
    def unhandled(err):
        if isinstance(err, HTTPException):
            if err.code >= 500:
                log.exception('HTTP %s on %s %s', err.code, request.method, request.path)
            else:
                log.info('HTTP %s on %s %s', err.code, request.method, request.path)
            return err
        log.exception('Unhandled error on %s %s', request.method, request.path)
        if app.debug or app.config.get('TESTING'):
            raise err
        return ('Internal Server Error', 500)

    @app.get('/language/<lang>')
    def switch_language(lang):
        if lang in TEXT:
            session['lang'] = lang
        page = request.args.get('page', 'signup')
        allowed = ('signup', 'login', 'forgot_password', 'dashboard', 'upgrade', 'admin_home', 'admin_payments',
                   'inventory', 'inventory_new', 'inventory_item', 'stock_move', 'stock_pick')
        return redirect(url_for(page if page in allowed else 'signup'))

    @app.route('/', methods=['GET', 'POST'])
    @limiter.limit('10 per minute', methods=['POST'])
    def signup():
        if request.method == 'POST':
            f = request.form
            name, address = f.get('name', '').strip(), f.get('address', '').strip()
            cnic = f.get('cnic', '').replace('-', '').strip()
            phone, email = f.get('phone', '').strip(), f.get('email', '').strip()
            password = f.get('password', '')
            confirm = f.get('confirm', '')
            valid = (0 < len(name) <= 120 and 0 < len(address) <= 500 and
                     re.fullmatch(r'[0-9]{13}', cnic) and re.fullmatch(r'03[0-9]{9}', phone) and
                     (not email or (len(email) <= 254 and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email))) and
                     is_mpin(password) and password == confirm)
            if not valid:
                flash(g.t['invalid'])
                return render_template('auth.html', mode='signup'), 400
            start = now()
            user = User(name=name, address=address, cnic=cnic, phone=phone, email=email or None,
                        password_hash=generate_password_hash(password), created_at=start,
                        trial_ends_at=start + timedelta(days=5))
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash(g.t['duplicate'])
                return render_template('auth.html', mode='signup'), 409
            lang = g.lang
            session.clear()
            session.update(user_id=user.id, lang=lang)
            log.info('signup ok user=%s', user.id)
            return redirect(url_for('dashboard'))
        return render_template('auth.html', mode='signup')

    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit('10 per minute', methods=['POST'])
    def login():
        if request.method == 'POST':
            phone, password = request.form.get('phone', '').strip(), request.form.get('password', '')
            user = db.session.scalar(db.select(User).where(User.phone == phone))
            # Always run a hash check, even for an unknown phone.
            fallback = app.config.get('_DUMMY_HASH')
            if not fallback:
                fallback = generate_password_hash('000000')
                app.config['_DUMMY_HASH'] = fallback
            ok = check_password_hash(user.password_hash if user else fallback, password)
            if not user or not ok or not is_mpin(password):
                log.info('login failed')
                flash(g.t['denied'])
                return render_template('auth.html', mode='login'), 401
            lang = g.lang
            session.clear()
            session.update(user_id=user.id, lang=lang)
            log.info('login ok user=%s', user.id)
            return redirect(url_for('dashboard'))
        return render_template('auth.html', mode='login')

    @app.route('/forgot-password', methods=['GET', 'POST'])
    @limiter.limit('5 per minute', methods=['POST'])
    def forgot_password():
        if request.method == 'POST':
            f = request.form
            phone = f.get('phone', '').strip()
            cnic = f.get('cnic', '').replace('-', '').strip()
            password, confirm = f.get('password', ''), f.get('confirm', '')
            user = db.session.scalar(db.select(User).where(User.phone == phone))
            dummy = '0' * 13
            stored = user.cnic if user and len(user.cnic or '') == 13 else dummy
            submitted = cnic if len(cnic) == 13 else dummy
            matched = hmac.compare_digest(stored, submitted)
            identity_ok = bool(user) and matched and bool(re.fullmatch(r'03[0-9]{9}', phone)) and len(cnic) == 13
            if not (is_mpin(password) and password == confirm):
                flash(g.t['mismatch'])
                return render_template('auth.html', mode='forgot'), 400
            if not identity_ok:
                flash(g.t['forgot_denied'])
                return render_template('auth.html', mode='forgot'), 401
            user.password_hash = generate_password_hash(password)
            db.session.commit()
            log.info('mpin reset user=%s', user.id)
            flash(g.t['forgot_ok'], 'ok')
            return redirect(url_for('login'))
        return render_template('auth.html', mode='forgot')

    @app.get('/dashboard')
    def dashboard():
        user = db.session.get(User, session.get('user_id')) if session.get('user_id') else None
        if not user:
            return redirect(url_for('login'))
        end = utc(user.trial_ends_at) or now()
        days = g.trial_days
        return render_template('dashboard.html', user=user, days=days,
                               end=end.astimezone(ZoneInfo('Asia/Karachi')).strftime('%d %b %Y, %H:%M PKT'))

    @app.post('/logout')
    def logout():
        lang = g.lang
        session.clear()
        session['lang'] = lang
        return redirect(url_for('login'))

    @app.get('/sw.js')
    def sw():
        return send_from_directory(app.static_folder, 'sw.js', mimetype='application/javascript')

    @app.cli.command('init-db')
    def init_db():
        """Create initial POC tables. Use migrations for production upgrades."""
        db.create_all()
        print('Database initialized.')

    register_billing(app, db, User, Payment, now, ReconNote)
    register_inventory(app, db, User, Item, StockMove, now)
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    db_kind = 'postgres' if 'postgres' in db_uri else 'sqlite'
    log.info('Asasa started log_level=%s db=%s', app.config['LOG_LEVEL'], db_kind)
    return app

# Allows the requested `flask --app main run` command.
app = create_app()
