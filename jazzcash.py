"""JazzCash hosted checkout (HMAC + form fields). No network I/O."""
from __future__ import annotations

import hmac
import hashlib
import os
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

PKT = ZoneInfo('Asia/Karachi')
CHECKOUT_URL = {
    'sandbox': 'https://sandbox.jazzcash.com.pk/CustomerPortal/transactionmanagement/merchantform/',
    'live': 'https://payments.jazzcash.com.pk/CustomerPortal/transactionmanagement/merchantform/',
}


def configured(config=None) -> bool:
    src = config if config is not None else os.environ
    get = src.get if hasattr(src, 'get') else lambda k, d='': src[k] if k in src else d
    return bool(
        (get('JAZZCASH_MERCHANT_ID') or '').strip()
        and (get('JAZZCASH_PASSWORD') or '').strip()
        and (get('JAZZCASH_INTEGRITY_SALT') or '').strip()
    )


def amount_paisa(config) -> int:
    raw = (config.get('JAZZCASH_AMOUNT_PAISA') or '').strip()
    if raw.isdigit():
        return int(raw)
    env = (config.get('APP_ENV') or 'production').strip().lower()
    return 100 if env == 'staging' else 29900


def checkout_url(config) -> str:
    env = (config.get('JAZZCASH_ENV') or 'live').strip().lower()
    return CHECKOUT_URL['sandbox'] if env == 'sandbox' else CHECKOUT_URL['live']


def public_base(config, request) -> str:
    explicit = (config.get('PUBLIC_BASE_URL') or '').strip().rstrip('/')
    if explicit:
        return explicit
    return (request.url_root or '').rstrip('/')


def secure_hash(fields: dict, salt: str) -> str:
    """JazzCash HMAC: salt + '&' + sorted nonempty values, key = salt."""
    parts = []
    for key in sorted(fields):
        if key == 'pp_SecureHash':
            continue
        value = fields[key]
        if value is None or str(value) == '':
            continue
        parts.append(str(value))
    message = salt + ''.join('&' + p for p in parts)
    return hmac.new(salt.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest().upper()


def hash_ok(fields: dict, salt: str, given: str) -> bool:
    expected = secure_hash(fields, salt)
    return hmac.compare_digest(expected, (given or '').strip().upper())


SUCCESS_CODE = '000'
# Codes JazzCash uses for "not finished yet" (customer still approving, voucher
# awaiting cash). Keep the row pending; the status page keeps waiting.
# Confirm this list against the integration guide that comes with live keys.
PENDING_CODES = frozenset({'124', '157'})
TXN_REF_RE = re.compile(r'T[0-9]{18}')


def verify_return(posted: dict, payment, config) -> tuple[str, str]:
    """Decide what a JazzCash return/notification means for `payment`.

    Returns (outcome, reason). outcome is one of:
      'approve'  signed, our merchant, our ref, exact amount, code 000
      'decline'  signed and ours, but JazzCash says it did not go through
      'pending'  signed and ours, JazzCash says still in progress
      'invalid'  anything we cannot trust; change nothing
    """
    salt = (config.get('JAZZCASH_INTEGRITY_SALT') or '').strip()
    if payment is None:
        return 'invalid', 'unknown_ref'
    if not salt:
        return 'invalid', 'no_salt'
    if not hash_ok(posted, salt, posted.get('pp_SecureHash', '')):
        return 'invalid', 'bad_hash'
    if (posted.get('pp_TxnRefNo') or '').strip() != payment.tid:
        return 'invalid', 'ref_mismatch'
    merchant = (config.get('JAZZCASH_MERCHANT_ID') or '').strip()
    if (posted.get('pp_MerchantID') or '').strip() != merchant:
        return 'invalid', 'merchant_mismatch'
    code = (posted.get('pp_ResponseCode') or '').strip()
    if code == SUCCESS_CODE:
        raw = (posted.get('pp_Amount') or '').strip()
        if not raw.isdigit() or int(raw) != int(payment.amount or 0) * 100:
            return 'invalid', 'amount_mismatch'
        return 'approve', 'ok'
    if code in PENDING_CODES:
        return 'pending', 'in_progress'
    if code:
        return 'decline', 'declined'
    return 'invalid', 'no_code'


def txn_ref(when: datetime, user_id: int) -> str:
    stamp = when.astimezone(PKT).strftime('%Y%m%d%H%M%S')
    return f'T{stamp}{int(user_id) % 10000:04d}'


def checkout_fields(config, *, user_id: int, when: datetime, return_url: str, amount_paisa_value: int) -> dict:
    salt = config['JAZZCASH_INTEGRITY_SALT'].strip()
    local = when.astimezone(PKT)
    expiry = local + timedelta(hours=3)
    padded = str(int(amount_paisa_value)).zfill(12)
    fields = {
        'pp_Version': '1.1',
        'pp_TxnType': 'MWALLET',
        'pp_Language': 'EN',
        'pp_MerchantID': config['JAZZCASH_MERCHANT_ID'].strip(),
        'pp_Password': config['JAZZCASH_PASSWORD'].strip(),
        'pp_TxnRefNo': txn_ref(when, user_id),
        'pp_Amount': padded,
        'pp_TxnCurrency': 'PKR',
        'pp_TxnDateTime': local.strftime('%Y%m%d%H%M%S'),
        'pp_BillReference': f'rakhza-{user_id}',
        'pp_Description': 'Rakhza month',
        'pp_TxnExpiryDateTime': expiry.strftime('%Y%m%d%H%M%S'),
        'pp_ReturnURL': return_url,
        'pp_BankID': '',
        'pp_ProductID': '',
        'pp_SubMerchantID': '',
    }
    fields['pp_SecureHash'] = secure_hash(fields, salt)
    return fields


def return_url_for(config, request) -> str:
    return urljoin(public_base(config, request) + '/', 'billing/jazzcash/return')
