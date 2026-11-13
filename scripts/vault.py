#!/usr/bin/env python3
"""Password-protected secrets vault for Rakhza.

One master password encrypts staging + production env files.
Plaintext stays on this machine only. The encrypted vault can live in git.

  python scripts/vault.py init      copy the example into secrets/rakhza.env
  python scripts/vault.py lock      encrypt secrets/rakhza.env -> secrets/rakhza.vault
  python scripts/vault.py unlock    write .env.staging and .env.prod (gitignored)
  python scripts/vault.py status    show whether the vault and env files exist

Unlock on the VPS with the same password, or set RAKHZA_VAULT_PASSWORD.
Never commit secrets/rakhza.env, .env.staging, or .env.prod.
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRETS = ROOT / 'secrets'
PLAIN = SECRETS / 'rakhza.env'
EXAMPLE = SECRETS / 'rakhza.env.example'
VAULT = SECRETS / 'rakhza.vault'
STAGING_OUT = ROOT / '.env.staging'
PROD_OUT = ROOT / '.env.prod'
MAGIC = b'RAKHZA1'
SALT_LEN = 16


def _fernet(password: str, salt: bytes):
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    import base64
    kdf = Scrypt(salt=salt, length=32, n=2 ** 14, r=8, p=1)
    key = base64.urlsafe_b64encode(kdf.derive(password.encode('utf-8')))
    return Fernet(key)


def _password(confirm: bool = False) -> str:
    env = os.environ.get('RAKHZA_VAULT_PASSWORD', '').strip()
    if env:
        return env
    first = getpass.getpass('Vault password: ')
    if not first:
        sys.exit('Password is empty.')
    if confirm:
        again = getpass.getpass('Type it again: ')
        if first != again:
            sys.exit('Passwords do not match.')
    return first


def _split_envs(text: str) -> dict[str, str]:
    """Split a vault plaintext into staging / production blocks."""
    blocks = {'staging': [], 'production': [], 'shared': []}
    current = 'shared'
    for line in text.splitlines():
        stripped = line.strip().upper().replace(' ', '')
        if stripped in ('#=====STAGING=====', '#---STAGING---', '[STAGING]'):
            current = 'staging'
            continue
        if stripped in ('#=====PRODUCTION=====', '#---PRODUCTION---', '[PRODUCTION]'):
            current = 'production'
            continue
        blocks[current].append(line)
    shared = '\n'.join(blocks['shared']).strip()
    out = {}
    for name in ('staging', 'production'):
        body = '\n'.join(blocks[name]).strip()
        parts = [p for p in (shared, body) if p]
        out[name] = '\n'.join(parts) + ('\n' if parts else '')
    return out


def cmd_init() -> None:
    SECRETS.mkdir(exist_ok=True)
    if PLAIN.exists():
        print(f'Already exists: {PLAIN}')
        return
    if not EXAMPLE.exists():
        sys.exit(f'Missing {EXAMPLE}')
    PLAIN.write_text(EXAMPLE.read_text(encoding='utf-8'), encoding='utf-8')
    print(f'Wrote {PLAIN}')
    print('Fill in the values, then run: python scripts/vault.py lock')


def cmd_lock() -> None:
    if not PLAIN.exists():
        sys.exit(f'Missing {PLAIN}. Run: python scripts/vault.py init')
    password = _password(confirm=not os.environ.get('RAKHZA_VAULT_PASSWORD'))
    salt = os.urandom(SALT_LEN)
    token = _fernet(password, salt).encrypt(PLAIN.read_bytes())
    VAULT.write_bytes(MAGIC + salt + token)
    print(f'Encrypted {PLAIN} -> {VAULT} ({VAULT.stat().st_size} bytes)')
    print('Keep the password somewhere you will not lose it. There is no recovery.')


def cmd_unlock() -> None:
    if not VAULT.exists():
        sys.exit(f'Missing {VAULT}. Run lock first, or copy the vault onto this machine.')
    raw = VAULT.read_bytes()
    if not raw.startswith(MAGIC):
        sys.exit('Not a Rakhza vault file.')
    salt = raw[len(MAGIC):len(MAGIC) + SALT_LEN]
    token = raw[len(MAGIC) + SALT_LEN:]
    password = _password()
    try:
        plain = _fernet(password, salt).decrypt(token).decode('utf-8')
    except Exception:
        sys.exit('Wrong password, or the vault file is damaged.')
    parts = _split_envs(plain)
    STAGING_OUT.write_text(parts['staging'], encoding='utf-8')
    PROD_OUT.write_text(parts['production'], encoding='utf-8')
    print(f'Wrote {STAGING_OUT}')
    print(f'Wrote {PROD_OUT}')


def cmd_status() -> None:
    checks = [
        ('example', EXAMPLE),
        ('plaintext (gitignored)', PLAIN),
        ('encrypted vault', VAULT),
        ('.env.staging (gitignored)', STAGING_OUT),
        ('.env.prod (gitignored)', PROD_OUT),
    ]
    for label, path in checks:
        mark = 'yes' if path.exists() else 'no'
        print(f'{mark:3}  {label:28} {path}')


def main() -> None:
    cmd = (sys.argv[1] if len(sys.argv) > 1 else 'status').lower()
    if cmd in ('-h', '--help', 'help'):
        print(__doc__)
        return
    actions = {
        'init': cmd_init,
        'lock': cmd_lock,
        'unlock': cmd_unlock,
        'status': cmd_status,
    }
    if cmd not in actions:
        sys.exit(f'Unknown command {cmd!r}. Try: init, lock, unlock, status')
    actions[cmd]()


if __name__ == '__main__':
    main()
