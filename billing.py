"""Manual JazzCash verification and trial entitlements. No payment API claims."""
import logging
import math
import os
import re
import secrets
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
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


def is_test_tid(tid):
    return str(tid or '').upper().startswith('TEST-SIM-')


def shop_bucket(user, at_time):
    if is_paid_at(user.paid_until, at_time) or remaining_seconds(user.trial_ends_at, at_time) > 0:
        return 'active'
    if user.paid_until:
        return 'left'
    return 'unpaid'


def period_bounds(kind='month', date_from='', date_to='', at=None):
    """PKT-inclusive window. Presets run from the period start through `at` (now)."""
    now_local = pkt(at) or pkt(datetime.now(timezone.utc))
    kind = (kind or 'month').lower()
    if kind == 'custom' and date_from and date_to:
        try:
            start_d = date.fromisoformat(date_from)
            end_d = date.fromisoformat(date_to)
        except ValueError:
            kind = 'month'
        else:
            if start_d > end_d:
                start_d, end_d = end_d, start_d
            start = datetime.combine(start_d, time.min, tzinfo=PKT)
            end = datetime.combine(end_d, time(23, 59, 59), tzinfo=PKT)
            return start.astimezone(timezone.utc), end.astimezone(timezone.utc), 'custom'
    month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if kind == 'year':
        start_local = now_local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif kind == '3m':
        start_local = pkt(add_calendar_months(month_start, -2)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif kind == '6m':
        start_local = pkt(add_calendar_months(month_start, -5)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif kind in ('12m', 'year12'):
        start_local = pkt(add_calendar_months(month_start, -11)).replace(hour=0, minute=0, second=0, microsecond=0)
        kind = '12m'
    else:
        start_local = month_start
        kind = 'month'
    return start_local.astimezone(timezone.utc), now_local.astimezone(timezone.utc), kind


def register_billing(app, db, User, Payment, now, ReconNote=None):
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
            allowed.update({'admin_home', 'admin_payments', 'review_payment', 'admin_recon'})
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

    def _admin_gate():
        if not g.user:
            return redirect(url_for('login'))
        if not g.is_admin:
            abort(403)
        return None

    def _payments_in_window(start, end):
        rows = db.session.query(Payment, User).join(User, Payment.user_id == User.id).order_by(Payment.id.desc()).all()
        out = []
        for payment, owner in rows:
            created = utc(payment.created_at)
            if created and start <= created <= end:
                out.append((payment, owner))
        return out

    def _money_split(rows):
        pending = live = test = 0
        n_pending = n_approved = n_rejected = n_test = n_live = 0
        for payment, _owner in rows:
            amount = payment.amount or 0
            test_row = is_test_tid(payment.tid)
            if payment.status == 'pending':
                pending += amount
                n_pending += 1
            elif payment.status == 'approved':
                n_approved += 1
                if test_row:
                    test += amount
                    n_test += 1
                else:
                    live += amount
                    n_live += 1
            elif payment.status == 'rejected':
                n_rejected += 1
        return dict(pending=pending, live=live, test=test, n_pending=n_pending,
                    n_approved=n_approved, n_rejected=n_rejected, n_test=n_test, n_live=n_live)

    @app.get('/admin')
    def admin_home():
        gate = _admin_gate()
        if gate:
            return gate
        at = now()
        start, end, kind = period_bounds(request.args.get('range', 'month'),
                                         request.args.get('from', ''), request.args.get('to', ''), at)
        shops = User.query.order_by(User.id.desc()).all()
        buckets = {'active': 0, 'left': 0, 'unpaid': 0}
        shop_rows = []
        for shop in shops:
            bucket = shop_bucket(shop, at)
            buckets[bucket] += 1
            shop_rows.append(dict(
                name=shop.name, phone=shop.phone, bucket=bucket,
                trial=pkt_label(shop.trial_ends_at), paid=pkt_label(shop.paid_until),
            ))
        period_rows = _payments_in_window(start, end)
        money = _money_split(period_rows)
        pending_rows = db.session.query(Payment, User).join(User, Payment.user_id == User.id).filter(
            Payment.status == 'pending').order_by(Payment.id).all()
        recon = None
        if ReconNote is not None:
            recon = ReconNote.query.order_by(ReconNote.id.desc()).first()
        wallet = db.session.scalar(db.select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == 'approved', Payment.tid.startswith('TEST-SIM-'))) or 0
        log.info('admin home user=%s range=%s shops=%s pending=%s', g.user.id, kind, len(shops), money['n_pending'])
        return render_template(
            'admin.html', shops=shop_rows, buckets=buckets, registered=len(shops),
            money=money, period_rows=period_rows, pending_rows=pending_rows,
            range_kind=kind, range_start=pkt_label(start), range_end=pkt_label(end),
            date_from=pkt(start).date().isoformat(), date_to=pkt(end).date().isoformat(),
            recon=recon, wallet=wallet, is_test_tid=is_test_tid, pkt_label=pkt_label,
        )

    @app.post('/admin/recon')
    def admin_recon():
        gate = _admin_gate()
        if gate:
            return gate
        if ReconNote is None:
            abort(404)
        raw = (request.form.get('jazzcash_rs') or '').strip()
        if not re.fullmatch(r'[0-9]{1,9}', raw):
            flash('JazzCash رقم صرف ہندسوں میں لکھیں۔' if g.lang == 'ur' else 'Enter the JazzCash amount in numbers only.')
            return redirect(url_for('admin_home'))
        start, end, _kind = period_bounds(request.form.get('range', 'month'),
                                          request.form.get('from', ''), request.form.get('to', ''), now())
        db.session.add(ReconNote(period_from=start, period_to=end, jazzcash_rs=int(raw),
                                 created_at=now(), created_by=g.user.id))
        db.session.commit()
        log.info('recon note user=%s rs=%s', g.user.id, raw)
        flash('JazzCash رقم محفوظ ہو گئی۔' if g.lang == 'ur' else 'Saved the amount you saw in JazzCash.', 'ok')
        return redirect(url_for('admin_home', **{'range': request.form.get('range', 'month'),
                                                 'from': request.form.get('from', ''),
                                                 'to': request.form.get('to', '')}))

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
        if request.form.get('next') == 'office':
            return redirect(url_for('admin_home'))
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
                if 'trade' not in cols:
                    column_type = User.__table__.c.trade.type.compile(dialect=db.engine.dialect)
                    conn.execute(text(f'ALTER TABLE "user" ADD COLUMN trade {column_type}'))
        if inspector.has_table('item'):
            item_cols = {c['name'] for c in inspector.get_columns('item')}
            if 'notebook_id' not in item_cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE item ADD COLUMN notebook_id INTEGER'))
        db.create_all()
        for user in User.query.filter(User.paid_until.isnot(None), User.billing_day.is_(None)):
            local = pkt(user.paid_until)
            if local:
                user.billing_day = local.day
        db.session.commit()
        import main as asasa_main
        from inventory import upgrade_notebook_schema
        upgrade_notebook_schema(db, User, asasa_main.Item, asasa_main.Notebook, now)
        print('POC billing schema ready. Existing data preserved.')
