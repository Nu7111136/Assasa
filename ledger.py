"""Simple money ledger (khata): plus / minus entries by date, running total, WhatsApp export."""
import logging
import re
from datetime import date
from urllib.parse import quote
from zoneinfo import ZoneInfo

from flask import abort, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import case, func

log = logging.getLogger('rakhza')
PKT = ZoneInfo('Asia/Karachi')
KINDS = ('plus', 'minus')
MAX_RS = 999_999_999
NOTE_MAX = 80
WA_MAX = 3500  # keep the wa.me link well under what phones and WhatsApp accept

LEDGER = {
    'en': dict(
        title='Ledger', kicker='Money book', open='Open my ledger',
        open_help='Write money in (+) and money out (−). The total stays with you.',
        total='Total', total_help='All plus minus all minus, every date.',
        add='New entry', date='Date', amount='Amount (Rs)', note='Details (optional)', col_note='Details',
        note_ph='e.g. Ali paid, rent, supplier', plus='+ Plus (money in)', minus='− Minus (money out)',
        plus_short='Plus', minus_short='Minus', day_title='Entries on', pick_day='Show this date',
        today='Today', none_day='No entries on this date.', none='No entries yet. Add your first one above.',
        show='Show full ledger', back_day='Back to one date', full='Full ledger',
        day_in='In', day_out='Out', day_net='Day total', running='Balance',
        remove='Remove', remove_ask='Remove this entry?', removed='Entry removed.',
        added_plus='Added to plus.', added_minus='Added to minus.',
        invalid='Check the entry. Amount must be a whole number above 0, and the date cannot be in the future.',
        wa_title='Send to WhatsApp', wa_phone='WhatsApp number', wa_hint='Pakistani mobile, 03XXXXXXXXX. WhatsApp opens with the ledger ready; tap Send.',
        wa_send_day='Send this date', wa_send_all='Send full ledger', wa_bad='WhatsApp number must be 03 and 9 more digits.',
        wa_head='Ledger', wa_more='… {n} earlier entries not shown', wa_from='From', rs='Rs',
        entries='entries',
    ),
    'ur': dict(
        title='کھاتہ', kicker='رقم کی کاپی', open='میرا کھاتہ کھولیں',
        open_help='آنے والی رقم (+) اور جانے والی رقم (−) لکھیں۔ کل رقم آپ کے پاس رہے گی۔',
        total='کل رقم', total_help='تمام تاریخوں کا جمع منفی نکال کر۔',
        add='نیا اندراج', date='تاریخ', amount='رقم (روپے)', note='تفصیل (اختیاری)', col_note='تفصیل',
        note_ph='مثلاً علی نے دیے، کرایہ، سپلائر', plus='+ جمع (رقم آئی)', minus='− نکالی (رقم گئی)',
        plus_short='جمع', minus_short='نکالی', day_title='اندراج بتاریخ', pick_day='یہ تاریخ دکھائیں',
        today='آج', none_day='اس تاریخ کا کوئی اندراج نہیں۔', none='ابھی کوئی اندراج نہیں۔ اوپر پہلا اندراج کریں۔',
        show='پورا کھاتہ دکھائیں', back_day='ایک تاریخ پر واپس', full='پورا کھاتہ',
        day_in='آئی', day_out='گئی', day_net='دن کا حساب', running='بقایا',
        remove='ہٹائیں', remove_ask='یہ اندراج ہٹا دیں؟', removed='اندراج ہٹا دیا گیا۔',
        added_plus='جمع میں لکھ دیا۔', added_minus='نکالی میں لکھ دیا۔',
        invalid='اندراج چیک کریں۔ رقم صفر سے زیادہ پورا عدد ہو، اور تاریخ آنے والی نہ ہو۔',
        wa_title='واٹس ایپ پر بھیجیں', wa_phone='واٹس ایپ نمبر', wa_hint='پاکستانی موبائل نمبر، 03XXXXXXXXX۔ واٹس ایپ کھاتے کے ساتھ کھلے گا، بھیجیں دبائیں۔',
        wa_send_day='یہ تاریخ بھیجیں', wa_send_all='پورا کھاتہ بھیجیں', wa_bad='واٹس ایپ نمبر 03 سے شروع اور 11 ہندسوں کا ہو۔',
        wa_head='کھاتہ', wa_more='… {n} پرانے اندراج شامل نہیں', wa_from='از', rs='روپے',
        entries='اندراج',
    ),
}


def rs(value):
    return f'{int(value):,}'


def signed(value):
    value = int(value)
    return ('+' if value >= 0 else '−') + rs(abs(value))


def parse_amount(value):
    raw = (value or '').strip().replace(',', '')
    if not re.fullmatch(r'[0-9]{1,9}', raw):
        return None
    amount = int(raw)
    return amount if 0 < amount <= MAX_RS else None


def parse_day(value, today):
    raw = (value or '').strip()
    if not raw:
        return today
    try:
        day = date.fromisoformat(raw)
    except ValueError:
        return None
    return day if date(2000, 1, 1) <= day <= today else None


def wa_number(value):
    raw = re.sub(r'[\s-]', '', value or '')
    if re.fullmatch(r'03[0-9]{9}', raw):
        return raw, '92' + raw[1:]
    if re.fullmatch(r'\+?923[0-9]{9}', raw):
        digits = raw.lstrip('+')
        return '0' + digits[2:], digits
    return None, None


def register_ledger(app, db, LedgerEntry, now):

    def copy():
        return LEDGER[getattr(g, 'lang', 'en')]

    def today():
        return now().astimezone(PKT).date()

    def shop():
        return getattr(g, 'user', None)

    def live(user):
        return LedgerEntry.query.filter_by(user_id=user.id, active=True)

    def balance(user):
        signed_sum = func.coalesce(func.sum(case(
            (LedgerEntry.kind == 'plus', LedgerEntry.amount_rs), else_=-LedgerEntry.amount_rs)), 0)
        return int(db.session.scalar(
            db.select(signed_sum).where(LedgerEntry.user_id == user.id, LedgerEntry.active.is_(True))) or 0)

    def ordered(q):
        return q.order_by(LedgerEntry.day, LedgerEntry.created_at, LedgerEntry.id).all()

    def day_sums(rows):
        plus = sum(r.amount_rs for r in rows if r.kind == 'plus')
        minus = sum(r.amount_rs for r in rows if r.kind == 'minus')
        return dict(plus=plus, minus=minus, net=plus - minus)

    def group_full(rows):
        """Date-wise groups with a running balance after every entry."""
        groups, running = [], 0
        for row in rows:
            running += row.amount_rs if row.kind == 'plus' else -row.amount_rs
            row.running = running
            if not groups or groups[-1]['day'] != row.day:
                groups.append(dict(day=row.day, rows=[]))
            groups[-1]['rows'].append(row)
        for group in groups:
            group.update(day_sums(group['rows']))
        return groups

    def day_label(day):
        return day.strftime('%d %b %Y')

    def entry_line(row, c):
        sign = '+' if row.kind == 'plus' else '−'
        note = f' {row.note}' if row.note else ''
        return f'{sign}{c["rs"]} {rs(row.amount_rs)}{note}'

    def whatsapp_text(user, rows, day, c):
        """Plain text for WhatsApp. Newest lines are kept if it gets too long; totals always stay."""
        name = user.name
        # body holds (line, is_entry) so trimming can count the entries it drops.
        if day:
            head = [f'*{c["wa_head"]}: {name}*', f'{c["date"]}: {day_label(day)}', '']
            body = [(entry_line(r, c), True) for r in rows]
            sums = day_sums(rows)
            foot = ['', f'{c["day_in"]}: {c["rs"]} {rs(sums["plus"])}',
                    f'{c["day_out"]}: {c["rs"]} {rs(sums["minus"])}',
                    f'*{c["day_net"]}: {c["rs"]} {signed(sums["net"])}*',
                    f'*{c["total"]}: {c["rs"]} {signed(balance(user))}*']
        else:
            head = [f'*{c["wa_head"]}: {name}*', c['full'], '']
            body = []
            for group in group_full(rows):
                body.append((f'_{day_label(group["day"])}_', False))
                body.extend((entry_line(r, c), True) for r in group['rows'])
                body.append((f'{c["day_net"]}: {signed(group["net"])}', False))
                body.append(('', False))
            foot = [f'*{c["total"]}: {c["rs"]} {signed(balance(user))}*']
        foot.append(f'— {c["wa_from"]} Rakhza')
        dropped = 0
        while True:
            more = [c['wa_more'].format(n=dropped), ''] if dropped else []
            text = '\n'.join(head + more + [line for line, _ in body] + foot)
            if not body or len(quote(text)) <= WA_MAX:
                return text
            _line, is_entry = body.pop(0)
            dropped += is_entry

    @app.context_processor
    def ledger_copy():
        user = shop()
        total = balance(user) if user else 0
        return dict(led=copy(), ledger_total=total, ledger_signed=signed, ledger_rs=rs)

    @app.get('/ledger')
    def ledger():
        user = shop()
        if not user:
            return redirect(url_for('login'))
        c = copy()
        now_day = today()
        full = request.args.get('view') == 'all'
        day = parse_day(request.args.get('day'), now_day) or now_day
        if full:
            groups = group_full(ordered(live(user)))
            rows, sums = [], None
        else:
            groups = []
            rows = ordered(live(user).filter_by(day=day))
            sums = day_sums(rows)
        return render_template(
            'ledger.html', heading=c['full'] if full else c['title'], full=full, day=day,
            day_text=day_label(day), today=now_day, rows=rows, sums=sums, groups=groups,
            total=balance(user), wa_phone=session.get('ledger_wa', ''),
            any_entries=live(user).limit(1).count() > 0)

    @app.post('/ledger/add')
    def ledger_add():
        user = shop()
        if not user:
            return redirect(url_for('login'))
        c = copy()
        f = request.form
        kind = f.get('kind')
        amount = parse_amount(f.get('amount'))
        day = parse_day(f.get('day'), today())
        note = (f.get('note') or '').strip()[:NOTE_MAX] or None
        if kind not in KINDS or amount is None or day is None:
            flash(c['invalid'])
            back = parse_day(f.get('day'), today())
            return redirect(url_for('ledger', day=back.isoformat() if back else None))
        db.session.add(LedgerEntry(user_id=user.id, day=day, kind=kind, amount_rs=amount,
                                   note=note, created_at=now(), active=True))
        db.session.commit()
        log.info('ledger add kind=%s user=%s', kind, user.id)
        flash(c['added_plus'] if kind == 'plus' else c['added_minus'], 'ok')
        return redirect(url_for('ledger', day=day.isoformat()))

    @app.post('/ledger/<int:eid>/remove')
    def ledger_remove(eid):
        user = shop()
        if not user:
            return redirect(url_for('login'))
        row = db.session.get(LedgerEntry, eid)
        if not row or row.user_id != user.id or not row.active:
            abort(404)
        row.active = False
        db.session.commit()
        log.info('ledger remove entry=%s user=%s', row.id, user.id)
        flash(copy()['removed'], 'ok')
        if request.form.get('view') == 'all':
            return redirect(url_for('ledger', view='all'))
        return redirect(url_for('ledger', day=row.day.isoformat()))

    @app.post('/ledger/whatsapp')
    def ledger_whatsapp():
        user = shop()
        if not user:
            return redirect(url_for('login'))
        c = copy()
        f = request.form
        full = f.get('scope') == 'all'
        day = None if full else (parse_day(f.get('day'), today()) or today())
        back = url_for('ledger', view='all') if full else url_for('ledger', day=day.isoformat())
        local, intl = wa_number(f.get('phone'))
        if not intl:
            flash(c['wa_bad'])
            return redirect(back)
        session['ledger_wa'] = local
        rows = ordered(live(user)) if full else ordered(live(user).filter_by(day=day))
        text = whatsapp_text(user, rows, day, c)
        log.info('ledger whatsapp scope=%s rows=%s user=%s', 'all' if full else 'day', len(rows), user.id)
        return redirect(f'https://wa.me/{intl}?text={quote(text)}')
