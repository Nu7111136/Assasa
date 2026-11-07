import math
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()
db = SQLAlchemy()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])

TEXT = {
'en': dict(signup='Create your account', name='Name', address='Address', cnic='CNIC', phone='Phone', email='Email (optional)', password='Password', submit='Start free trial', login='Log in', logout='Log out', dashboard='Your dashboard', trial='5 days free. No payment needed now.', price='Then Rs 299/month. No automatic charges.', have='Already registered?', new='New to Asasa?', days='Days left in your trial', ends='Trial ends (PKT)', expired='Your trial has ended.', welcome='Welcome', invalid='Please check your details. Name and address are required, CNIC must have 13 digits, phone must be 03XXXXXXXXX, email must be valid if supplied, and password must contain 8–128 characters.', duplicate='This phone is already registered. Please log in.', denied='Incorrect phone or password.', privacy='POC: use fictional details only. CNIC and phone are not verified.', install='Install: Android → browser menu → Install app. iPhone → Share → Add to Home Screen.', offline='You are offline. Connect to the internet to sign up or log in.'),
'ur': dict(signup='اپنا اکاؤنٹ بنائیں', name='نام', address='پتہ', cnic='شناختی کارڈ نمبر', phone='فون نمبر', email='ای میل (اختیاری)', password='پاس ورڈ', submit='مفت آزمائش شروع کریں', login='لاگ ان', logout='لاگ آؤٹ', dashboard='آپ کا ڈیش بورڈ', trial='پانچ دن مفت۔ ابھی ادائیگی کی ضرورت نہیں۔', price='اس کے بعد 299 روپے ماہانہ۔ خودکار ادائیگی نہیں ہوگی۔', have='پہلے سے اکاؤنٹ ہے؟', new='نیا اکاؤنٹ بنائیں؟', days='آزمائش کے باقی دن', ends='آزمائش کا اختتام (پاکستان وقت)', expired='آپ کی آزمائش ختم ہو گئی ہے۔', welcome='خوش آمدید', invalid='معلومات درست کریں۔ نام اور پتہ ضروری ہیں، شناختی نمبر 13 ہندسوں کا، فون 03 سے شروع ہونے والا 11 ہندسوں کا اور پاس ورڈ 8 سے 128 حروف کا ہونا چاہیے۔ ای میل دیں تو درست لکھیں۔', duplicate='یہ فون پہلے سے رجسٹرڈ ہے۔ لاگ ان کریں۔', denied='فون نمبر یا پاس ورڈ درست نہیں۔', privacy='یہ ابتدائی نمونہ ہے۔ صرف فرضی معلومات استعمال کریں۔ شناختی کارڈ اور فون کی تصدیق نہیں ہوتی۔', install='اینڈرائیڈ: براؤزر مینو سے ایپ انسٹال کریں۔ آئی فون: شیئر سے ہوم اسکرین پر شامل کریں۔', offline='انٹرنیٹ بند ہے۔ رجسٹریشن یا لاگ ان کے لیے انٹرنیٹ سے جڑیں۔')}


def now():
    return datetime.now(timezone.utc)


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
    trial_ends_at = db.Column(db.DateTime(timezone=True), nullable=False)


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tid = db.Column(db.String(64), nullable=False, unique=True)
    amount = db.Column(db.Integer, nullable=False, default=299)
    status = db.Column(db.String(12), nullable=False, default='pending')
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    reviewed_at = db.Column(db.DateTime(timezone=True))
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'))


def create_app(config=None):
    app = Flask(__name__)
    uri = os.getenv('DATABASE_URL', 'sqlite:///asasa.db')
    if uri.startswith(('postgres://', 'postgresql://')):
        uri = 'postgresql+psycopg://' + uri.split('://', 1)[1]
    app.config.update(SECRET_KEY=os.getenv('SECRET_KEY') or os.urandom(32), SQLALCHEMY_DATABASE_URI=uri,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE') == '1', MAX_CONTENT_LENGTH=16384,
                      RATELIMIT_STORAGE_URI=os.getenv('RATELIMIT_STORAGE_URI', 'memory://'))
    if config:
        app.config.update(config)
    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    @app.before_request
    def language():
        g.lang = session.get('lang', 'en')
        g.t = TEXT[g.lang]

    @app.context_processor
    def context():
        return dict(t=g.t, lang=g.lang)

    @app.after_request
    def headers(r):
        if request.endpoint != 'static':
            r.headers['Cache-Control'] = 'no-store'
        r.headers['X-Content-Type-Options'] = 'nosniff'
        r.headers['X-Frame-Options'] = 'DENY'
        r.headers['Referrer-Policy'] = 'same-origin'
        return r

    @app.get('/language/<lang>')
    def switch_language(lang):
        if lang in TEXT:
            session['lang'] = lang
        page = request.args.get('page', 'signup')
        return redirect(url_for(page if page in ('signup', 'login', 'dashboard', 'upgrade', 'admin_payments') else 'signup'))

    @app.route('/', methods=['GET', 'POST'])
    @limiter.limit('10 per minute', methods=['POST'])
    def signup():
        if request.method == 'POST':
            f = request.form
            name, address = f.get('name', '').strip(), f.get('address', '').strip()
            cnic = f.get('cnic', '').replace('-', '').strip()
            phone, email = f.get('phone', '').strip(), f.get('email', '').strip()
            password = f.get('password', '')
            valid = (0 < len(name) <= 120 and 0 < len(address) <= 500 and
                     re.fullmatch(r'[0-9]{13}', cnic) and re.fullmatch(r'03[0-9]{9}', phone) and
                     (not email or (len(email) <= 254 and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email))) and
                     8 <= len(password) <= 128)
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
            return redirect(url_for('dashboard'))
        return render_template('auth.html', mode='signup')

    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit('10 per minute', methods=['POST'])
    def login():
        if request.method == 'POST':
            phone, password = request.form.get('phone', '').strip(), request.form.get('password', '')
            user = db.session.scalar(db.select(User).where(User.phone == phone))
            # Always run a password check, even for an unknown phone.
            fallback = app.config.get('_DUMMY_HASH')
            if not fallback:
                fallback = generate_password_hash('unused-placeholder')
                app.config['_DUMMY_HASH'] = fallback
            ok = check_password_hash(user.password_hash if user else fallback, password[:129])
            if not user or not ok or len(password) > 128:
                flash(g.t['denied'])
                return render_template('auth.html', mode='login'), 401
            lang = g.lang
            session.clear()
            session.update(user_id=user.id, lang=lang)
            return redirect(url_for('dashboard'))
        return render_template('auth.html', mode='login')

    @app.get('/dashboard')
    def dashboard():
        user = db.session.get(User, session.get('user_id')) if session.get('user_id') else None
        if not user:
            return redirect(url_for('login'))
        end = user.trial_ends_at
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
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

    from billing import register_billing
    register_billing(app, db, User, Payment, now)
    return app

# Allows the requested `flask --app main run` command.
app = create_app()
