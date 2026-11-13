# Rakhza vault

One password encrypts staging and production secrets. The encrypted file
`secrets/rakhza.vault` can go in git. The plaintext must not.

## On your laptop

```bat
cd app
python -m pip install cryptography
python scripts/vault.py init
notepad secrets\rakhza.env
python scripts/vault.py lock
```

Type a long password you can remember. It is the only way to open the vault.
Do not reuse a JazzCash MPIN.

Generate two different `SECRET_KEY` values:

```bat
python -c "import secrets; print(secrets.token_hex(32))"
```

## On the VPS

```sh
python scripts/vault.py unlock
docker compose up -d --build
```

Unlock writes `.env.staging` and `.env.prod` next to `compose.yaml`.
Those files are gitignored.

## Password

Tell the operator the vault password in person or in this private chat once.
Do not put it in GitHub, Render, Discord, or a screenshot.
