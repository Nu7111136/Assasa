"""Manual JazzCash verification and trial entitlements. No payment API claims."""
import logging
import math
import os
import re
import secrets
from calendar import monthrange
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

from flask import g, session, request, redirect, url_for, render_template, flash, abort
from sqlalchemy import func, inspect, text
from sqlalchemy.exc import IntegrityError

log = logging.getLogger('asasa')
PKT = ZoneInfo('Asia/Karachi')


def utc(value):
    if value is None:
        return None
    if getattr(value, 'tzinfo', None) is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def pkt(value):
    value = utc(value)
    return None if value is None else value.astimezone(PKT)


def pkt_label(value):
    local = pkt(value)
    return '' if local is None else local.strftime('%d %b %Y, %H:%M PKT')


def add_calendar_months(when, months=1, billing_day=None):
    """Same PKT clock time next month(s). Missing days (31, leap 29) clamp to month end."""
    local = pkt(when)
    if local is None:
        return None
    anchor = billing_day if billing_day else local.day
    if not isinstance(anchor, int) or not 1 <= anchor <= 31:
        anchor = local.day
    month_index = local.month - 1 + months
    year = local.year + month_index // 12
    month = month_index % 12 + 1
    day = min(anchor, monthrange(year, month)[1])
    return local.replace(year=year, month=month, day=day).astimezone(timezone.utc)


def grant_month(user, at):
    """One PKT calendar month. Stacks from paid_until when still active; else starts at `at`."""
    at = utc(at)
    active = user.paid_until and utc(user.paid_until) > at
    if active:
        anchor = user.billing_day or pkt(user.paid_until).day
        user.billing_day = anchor
        user.paid_until = add_calendar_months(user.paid_until, 1, anchor)
    else:
        anchor = pkt(at).day
        user.billing_day = anchor
        user.paid_until = add_calendar_months(at, 1, anchor)
    return user.paid_until


def remaining_seconds(trial_ends_at, effective):
    end, when = utc(trial_ends_at), utc(effective)
    if end is None or when is None:
        return 0
    return (end - when).total_seconds()


def is_paid_at(paid_until, at_time):
    end, when = utc(paid_until), utc(at_time)
    return bool(end and when and end > when)


def register_billing(app, db, User, Payment, now):
    app.extensions['asasa_payment'] = Payment
    app.config.setdefault('APP_ENV', os.getenv('APP_ENV', 'production'))
    app.config.setdefault('PAYMENT_JAZZCASH_NUMBER', os.getenv('PAYMENT_JAZZCASH_NUMBER', '').strip())
    app.config.setdefault('TESTER_PHONES', os.getenv('TESTER_PHONES', ''))
    app.config.setdefault('ADMIN_PHONES', os.getenv('ADMIN_PHONES', ''))

    @app.before_request
    def entitlement():
        g.user = db.session.get(User, session.get('user_id')) if session.get('user_id') else None
        testers = {x.strip() for x in (app.config['TESTER_PHONES'] + ',' + app.config['ADMIN_PHONES']).split(',') if x.strip()}
        g.is_tester = bool(g.user and g.user.phone in testers)
        # Retire the old picker/dev-clock state, including pre-upgrade sessions.
        for key in ('simulate_day', 'tester_real'):
            session.pop(key, None)
        if not g.is_tester:
            session.pop('tester_day', None)
        g.test_mode = g.is_tester and session.get('tester_day', 0) > 0
        effective = now()
        if g.test_mode:
            effective += timedelta(days=session['tester_day'])
        g.effective = effective
        g.is_admin = bool(g.user and g.user.phone in {x.strip() for x in app.config['ADMIN_PHONES'].split(',') if x.strip()})
        g.paid = bool(g.user and is_paid_at(g.user.paid_until, effective))
        remaining = remaining_seconds(g.user.trial_ends_at, effective) if g.user else 0
        g.trial_days = max(0, math.ceil(remaining / 86400))
        g.readonly = bool(g.user and not g.paid and remaining <= 0)
        # Expired accounts are routed to payment, not a read-only dashboard.
        # Static/PWA assets and language switching must still work on Upgrade.
        allowed = {'upgrade', 'logout', 'login', 'forgot_password', 'test_mode', 'simulate_payment', 'static', 'sw', 'switch_language'}
        if g.is_admin:
            allowed.update({'admin_payments', 'review_payment'})
        if g.user:
            log.debug(
                'entitlement user=%s remaining_s=%.0f trial_days=%s readonly=%s paid=%s tester_day=%s endpoint=%s',
                g.user.id, remaining, g.trial_days, g.readonly, g.paid,
                session.get('tester_day', 0), request.endpoint,
            )
        if g.readonly and request.endpoint not in allowed:
            log.info(
                'trial expired, redirecting to upgrade user=%s from=%s tester_day=%s',
                g.user.id, request.endpoint, session.get('tester_day', 0),
            )
            return redirect(url_for('upgrade'), code=303 if request.method == 'POST' else 302)

    @app.context_processor
    def billing_context():
        user = getattr(g, 'user', None)
        return dict(account=user, readonly=getattr(g,'readonly',False),
                    is_admin=getattr(g,'is_admin',False), paid=getattr(g,'paid',False),
                    trial_days=getattr(g,'trial_days',0),
                    is_tester=getattr(g,'is_tester',False), test_mode=getattr(g,'test_mode',False), tester_day=session.get('tester_day',0),
                    jazzcash=app.config['PAYMENT_JAZZCASH_NUMBER'],
                    paid_end=pkt_label(user.paid_until) if user else '')

    @app.post('/test-mode')
    def test_mode():
        if not g.is_tester:
            abort(403)
        action = request.form.get('action', '')
        if action == 'next':
            session['tester_day'] = session.get('tester_day', 0) + 1
        elif action == 'reset':
            session.pop('tester_day', None)
        else:
            abort(400)
        effective = now() + timedelta(days=session.get('tester_day', 0))
        paid = is_paid_at(g.user.paid_until, effective)
        expired = not paid and remaining_seconds(g.user.trial_ends_at, effective) <= 0
        log.info(
            'test-mode action=%s user=%s tester_day=%s expired=%s',
            action, g.user.id, session.get('tester_day', 0), expired,
        )
        return redirect(url_for('upgrade' if expired else 'dashboard'))

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
                log.info('payment duplicate user=%s tid=%s', g.user.id, tid)
                flash('یہ آئی ڈی پہلے جمع ہو چکی ہے۔' if g.lang=='ur' else 'This transaction ID has already been submitted.')
                return redirect(url_for('upgrade'))
            log.info('payment submitted user=%s tid=%s', g.user.id, tid)
            return redirect(url_for('upgrade'))
        payments = Payment.query.filter_by(user_id=g.user.id).order_by(Payment.id.desc()).all()
        log.debug('upgrade page user=%s payments=%s readonly=%s', g.user.id, len(payments), g.readonly)
        return render_template('upgrade.html', payments=payments)

    @app.post('/upgrade/simulate')
    def simulate_payment():
        if not g.user:
            return redirect(url_for('login'))
        if not g.is_tester:
            abort(403)
        tid = f"TEST-SIM-{g.user.id}-{now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3).upper()}"
        payment = Payment(user_id=g.user.id, tid=tid, created_at=now(), amount=299,
                          status='approved', reviewed_at=now(), reviewed_by=g.user.id)
        db.session.add(payment)
        grant_month(g.user, now())
        db.session.commit()
        log.info('simulate payment user=%s tid=%s paid_until=%s billing_day=%s',
                 g.user.id, tid, g.user.paid_until, g.user.billing_day)
        flash('ٹیسٹ ادائیگی ہو گئی۔ ایک مہینہ کھل گیا، ٹیسٹ والیٹ میں 299 روپے شامل ہیں۔' if g.lang == 'ur'
              else 'Test payment recorded. One month is active and Rs 299 was added to the test wallet.', 'ok')
        return redirect(url_for('dashboard'))

    @app.get('/admin/payments')
    def admin_payments():
        if not g.user: return redirect(url_for('login'))
        if not g.is_admin: abort(403)
        rows = db.session.query(Payment, User).join(User, Payment.user_id == User.id).filter(Payment.status=='pending').order_by(Payment.id).all()
        wallet = db.session.scalar(db.select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == 'approved')) or 0
        return render_template('payments.html', rows=rows, wallet=wallet)

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
            grant_month(owner, now())
        db.session.commit()
        log.info('payment %s pid=%s user=%s by=%s', action, pid, payment.user_id, g.user.id)
        return redirect(url_for('admin_payments'))

    @app.cli.command('upgrade-db')
    def upgrade_db():
        """POC additive upgrade: preserve existing users, add paid_until/billing_day/payment table."""
        inspector = inspect(db.engine)
        if inspector.has_table('user'):
            cols = {c['name'] for c in inspector.get_columns('user')}
            with db.engine.begin() as conn:
                if 'paid_until' not in cols:
                    column_type = User.__table__.c.paid_until.type.compile(dialect=db.engine.dialect)
                    conn.execute(text(f'ALTER TABLE "user" ADD COLUMN paid_until {column_type}'))
                if 'billing_day' not in cols:
                    column_type = User.__table__.c.billing_day.type.compile(dialect=db.engine.dialect)
                    conn.execute(text(f'ALTER TABLE "user" ADD COLUMN billing_day {column_type}'))
        db.create_all()
        for user in User.query.filter(User.paid_until.isnot(None), User.billing_day.is_(None)):
            local = pkt(user.paid_until)
            if local:
                user.billing_day = local.day
        db.session.commit()
        print('POC billing schema ready. Existing data preserved.')
