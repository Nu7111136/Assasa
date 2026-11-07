"""Manual JazzCash verification and trial entitlements. No payment API claims."""
import os
import re
from datetime import datetime, timedelta, timezone
from flask import g, session, request, redirect, url_for, render_template, flash, abort
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def register_billing(app, db, User, Payment, now):
    app.extensions['asasa_payment'] = Payment
    app.config.setdefault('APP_ENV', os.getenv('APP_ENV', 'production'))
    app.config.setdefault('FAKE_TODAY', os.getenv('FAKE_TODAY', ''))
    app.config.setdefault('PAYMENT_JAZZCASH_NUMBER', os.getenv('PAYMENT_JAZZCASH_NUMBER', '03036666758'))
    app.config.setdefault('TESTER_PHONES', os.getenv('TESTER_PHONES', ''))
    app.config.setdefault('ADMIN_PHONES', os.getenv('ADMIN_PHONES', ''))

    @app.before_request
    def entitlement():
        g.user = db.session.get(User, session.get('user_id')) if session.get('user_id') else None
        g.dev = app.config['APP_ENV'] == 'dev'
        testers = {x.strip() for x in (app.config['TESTER_PHONES'] + ',' + app.config['ADMIN_PHONES']).split(',') if x.strip()}
        g.is_tester = bool(g.user and g.user.phone in testers)
        if not g.is_tester:
            session.pop('tester_day', None)
            session.pop('tester_real', None)
        g.test_mode = g.is_tester and 'tester_day' in session
        if not g.dev:
            session.pop('simulate_day', None)
        if g.user and g.dev and request.endpoint == 'dashboard' and 'simulate_day' in request.args:
            v = request.args['simulate_day']
            if not re.fullmatch(r'[0-7]', v):
                abort(400)
            session['simulate_day'] = int(v)
        effective = now()
        if g.user and g.dev:
            if 'simulate_day' in session:
                effective = utc(g.user.created_at) + timedelta(days=session['simulate_day'])
            elif app.config['FAKE_TODAY']:
                try:
                    effective = datetime.fromisoformat(app.config['FAKE_TODAY'].replace('Z', '+00:00'))
                    effective = utc(effective)
                except ValueError:
                    abort(400, 'FAKE_TODAY must be an ISO date/time')
        if g.is_tester and session.get('tester_real'):
            effective = now()
        if g.test_mode:
            effective = utc(g.user.created_at) + timedelta(days=session['tester_day'])
        g.effective = effective
        g.is_admin = bool(g.user and g.user.phone in {x.strip() for x in app.config['ADMIN_PHONES'].split(',') if x.strip()})
        g.paid = bool(g.user and g.user.paid_until and utc(g.user.paid_until) > effective)
        remaining = (utc(g.user.trial_ends_at) - effective).total_seconds() if g.user else 0
        import math
        g.trial_days = max(0, math.ceil(remaining / 86400))
        g.readonly = bool(g.user and not g.paid and remaining <= 0)
        # Fail closed for future inventory/profile mutation endpoints too.
        # Payment submission and logout remain usable after expiry; admin reviews
        # are administrative operations, not the admin's own stock mutations.
        allowed = {'upgrade', 'logout', 'login', 'review_payment', 'test_mode'}
        if g.readonly and request.method not in ('GET', 'HEAD', 'OPTIONS') and request.endpoint not in allowed:
            abort(403, 'Read-only: upgrade to continue')

    @app.context_processor
    def billing_context():
        return dict(account=getattr(g,'user',None), readonly=getattr(g,'readonly',False),
                    is_admin=getattr(g,'is_admin',False), paid=getattr(g,'paid',False),
                    trial_days=getattr(g,'trial_days',0), dev=getattr(g,'dev',False),
                    is_tester=getattr(g,'is_tester',False), test_mode=getattr(g,'test_mode',False), tester_day=session.get('tester_day',0),
                    simulated_day=session.get('simulate_day',0), jazzcash=app.config['PAYMENT_JAZZCASH_NUMBER'])

    @app.post('/test-mode')
    def test_mode():
        if not g.is_tester:
            abort(403)
        choice = request.form.get('day', '')
        if choice == 'real':
            session.pop('tester_day', None)
            session['tester_real'] = True
            # Real date also resets the older dev picker in this session.
            session.pop('simulate_day', None)
        elif choice == 'on':
            session.pop('tester_real', None)
            session['tester_day'] = 0
        elif re.fullmatch(r'[0-7]', choice):
            session.pop('tester_real', None)
            session['tester_day'] = int(choice)
        else:
            abort(400)
        return redirect(url_for('dashboard'))

    @app.route('/upgrade', methods=['GET', 'POST'])
    def upgrade():
        if not g.user:
            return redirect(url_for('login'))
        if request.method == 'POST':
            tid = request.form.get('tid','').strip().upper()
            if not re.fullmatch(r'[A-Z0-9-]{5,64}', tid):
                flash('درست ٹرانزیکشن آئی ڈی درج کریں۔' if g.lang=='ur' else 'Enter a valid transaction ID (5–64 letters, digits or hyphens).')
                return render_template('upgrade.html', payments=[]), 400
            db.session.add(Payment(user_id=g.user.id, tid=tid, created_at=now(), amount=299))
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('یہ آئی ڈی پہلے جمع ہو چکی ہے۔' if g.lang=='ur' else 'This transaction ID has already been submitted.')
                return redirect(url_for('upgrade'))
            return redirect(url_for('upgrade'))
        payments = Payment.query.filter_by(user_id=g.user.id).order_by(Payment.id.desc()).all()
        return render_template('upgrade.html', payments=payments)

    @app.get('/admin/payments')
    def admin_payments():
        if not g.user: return redirect(url_for('login'))
        if not g.is_admin: abort(403)
        rows = db.session.query(Payment, User).join(User, Payment.user_id == User.id).filter(Payment.status=='pending').order_by(Payment.id).all()
        return render_template('payments.html', rows=rows)

    @app.post('/admin/payments/<int:pid>/<action>')
    def review_payment(pid, action):
        if not g.user or not g.is_admin: abort(403)
        if action not in ('approve','reject'): abort(404)
        # Atomic status claim: repeated/concurrent approvals cannot grant twice.
        status = 'approved' if action == 'approve' else 'rejected'
        changed = Payment.query.filter_by(id=pid,status='pending').update(dict(status=status,reviewed_at=now(),reviewed_by=g.user.id))
        if changed != 1:
            db.session.rollback()
            abort(409, 'Payment already reviewed or not found')
        payment = db.session.get(Payment,pid)
        if action == 'approve':
            owner = db.session.get(User,payment.user_id)
            owner.paid_until = now() + timedelta(days=30)
        db.session.commit()
        return redirect(url_for('admin_payments'))

    @app.cli.command('upgrade-db')
    def upgrade_db():
        """POC additive upgrade: preserve existing users, add paid_until/payment table."""
        inspector = inspect(db.engine)
        if inspector.has_table('user') and 'paid_until' not in {c['name'] for c in inspector.get_columns('user')}:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE "user" ADD COLUMN paid_until TIMESTAMP'))
        db.create_all()
        print('POC billing schema ready. Existing data preserved.')
