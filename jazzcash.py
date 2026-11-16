"""JazzCash hosted checkout (HMAC + form fields), notification replies and status inquiry.

Only `inquire()` touches the network, and its transport can be swapped for tests.
"""
from __future__ import annotations

import hmac
import hashlib
import json
import os
import re
import urllib.request
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
    expiry = local + timedelta(hours=CHECKOUT_HOURS)
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


# ---- Notification (IPN) reply ----------------------------------------------

def ipn_reply(config, ok: bool) -> dict:
    """Signed acknowledgement JazzCash expects back from the notification URL."""
    salt = (config.get('JAZZCASH_INTEGRITY_SALT') or '').strip()
    body = {
        'pp_ResponseCode': '000' if ok else '199',
        'pp_ResponseMessage': 'IPN received successfully' if ok else 'IPN rejected',
    }
    body['pp_SecureHash'] = secure_hash(body, salt) if salt else ''
    return body


# ---- Status inquiry ----------------------------------------------------------

INQUIRY_URL = {
    'sandbox': 'https://sandbox.jazzcash.com.pk/ApplicationAPI/API/PaymentInquiry/Inquire',
    'live': 'https://payments.jazzcash.com.pk/ApplicationAPI/API/PaymentInquiry/Inquire',
}
# pp_ResponseCode on an inquiry says whether the *inquiry* worked; the payment's
# own outcome is pp_PaymentResponseCode / pp_Status. Confirm these against the
# integration guide that comes with the live keys.
INQUIRY_OK = '000'
PAID_CODES = frozenset({'000', '121'})
PAID_STATUSES = frozenset({'completed', 'success', 'paid'})
FAILED_STATUSES = frozenset({'failed', 'reversed', 'rejected', 'expired', 'cancelled', 'canceled'})
# A checkout link is valid for CHECKOUT_HOURS (pp_TxnExpiryDateTime).
CHECKOUT_HOURS = 3


def inquiry_url(config) -> str:
    env = (config.get('JAZZCASH_ENV') or 'live').strip().lower()
    return INQUIRY_URL['sandbox'] if env == 'sandbox' else INQUIRY_URL['live']


def inquiry_fields(config, tid: str) -> dict:
    fields = {
        'pp_TxnRefNo': tid,
        'pp_MerchantID': config['JAZZCASH_MERCHANT_ID'].strip(),
        'pp_Password': config['JAZZCASH_PASSWORD'].strip(),
    }
    fields['pp_SecureHash'] = secure_hash(fields, config['JAZZCASH_INTEGRITY_SALT'].strip())
    return fields


def http_post_json(url: str, payload: dict, timeout: float = 20) -> dict:
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST',
                                 headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https host)
        return json.loads(resp.read().decode('utf-8') or '{}')


def inquire(config, tid: str, post=None) -> dict:
    """Ask JazzCash what happened to `tid`. `post(url, payload) -> dict` is injectable."""
    return (post or http_post_json)(inquiry_url(config), inquiry_fields(config, tid))


def read_inquiry(resp: dict, payment, config) -> tuple[str, str]:
    """Map an inquiry answer to approve / decline / pending / invalid (same words as verify_return)."""
    if not isinstance(resp, dict):
        return 'invalid', 'not_json'
    salt = (config.get('JAZZCASH_INTEGRITY_SALT') or '').strip()
    given = (resp.get('pp_SecureHash') or '').strip()
    if given and not hash_ok(resp, salt, given):
        return 'invalid', 'bad_hash'
    code = str(resp.get('pp_ResponseCode') or '').strip()
    if code != INQUIRY_OK:
        # Includes "no such transaction" (the shop never got as far as paying).
        # The sweep expires those by age; never fail on a code we did not verify.
        return 'invalid', f'inquiry_{code or "blank"}'
    ref = str(resp.get('pp_TxnRefNo') or payment.tid).strip()
    if ref != payment.tid:
        return 'invalid', 'ref_mismatch'
    pay_code = str(resp.get('pp_PaymentResponseCode') or '').strip()
    status = str(resp.get('pp_Status') or '').strip().lower()
    if pay_code in PAID_CODES or status in PAID_STATUSES:
        raw = str(resp.get('pp_Amount') or '').strip()
        if raw and (not raw.isdigit() or int(raw) != int(payment.amount or 0) * 100):
            return 'invalid', 'amount_mismatch'
        return 'approve', pay_code or status
    if pay_code in PENDING_CODES or status in ('pending', 'initiated', 'in process', ''):
        return 'pending', pay_code or status or 'unknown'
    if status in FAILED_STATUSES or pay_code:
        return 'decline', pay_code or status
    return 'pending', 'unknown'
