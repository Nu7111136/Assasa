"""Play JazzCash's part for testing: send a signed IPN for a checkout reference.

Use with DUMMY keys on staging (or locally) before real JazzCash keys exist.
The salt is read from JAZZCASH_INTEGRITY_SALT or typed at a hidden prompt, so it
never lands in shell history. Never point this at production with real keys.

  python scripts/jazzcash_fake.py --base https://staging.rakhza.digital \
      --ref T202611161200000007 --merchant MCFAKE01 --code 000 --rupees 1
"""
import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jazzcash import secure_hash  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', required=True, help='e.g. https://staging.rakhza.digital or http://127.0.0.1:5088')
    ap.add_argument('--ref', required=True, help='checkout reference (T + 18 digits) from Upgrade / Rakhza office')
    ap.add_argument('--merchant', required=True, help='the JAZZCASH_MERCHANT_ID the server uses')
    ap.add_argument('--code', default='000', help='000 = paid, 157 = still pending, 999 = failed')
    ap.add_argument('--rupees', type=int, default=1, help='amount the checkout was for (staging: 1)')
    args = ap.parse_args()
    if 'rakhza.digital' in args.base and 'staging' not in args.base:
        sys.exit('Refusing to fake a payment on production.')
    salt = os.environ.get('JAZZCASH_INTEGRITY_SALT') or getpass.getpass('Integrity salt (hidden): ')
    fields = {
        'pp_TxnRefNo': args.ref,
        'pp_ResponseCode': args.code,
        'pp_ResponseMessage': 'fake for testing',
        'pp_Amount': str(args.rupees * 100).zfill(12),
        'pp_MerchantID': args.merchant,
    }
    fields['pp_SecureHash'] = secure_hash(fields, salt)
    req = urllib.request.Request(args.base.rstrip('/') + '/billing/jazzcash/ipn',
                                 data=json.dumps(fields).encode(), method='POST',
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            print(resp.status, resp.read().decode())
    except urllib.error.HTTPError as err:
        print(err.code, err.read().decode())
        sys.exit(1)


if __name__ == '__main__':
    main()
