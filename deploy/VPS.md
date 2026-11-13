# Rakhza on the VPS

Domain: **rakhza.digital**  
Staging: **staging.rakhza.digital**  
VPS: **2.25.6.85**  
SSH: **root@2.25.6.85 port 2222** (home WiFi blocks outbound 22)

## DNS (at your domain registrar)

| Type | Name | Value |
|---|---|---|
| A | `@` | `2.25.6.85` |
| A | `www` | `2.25.6.85` |
| A | `staging` | `2.25.6.85` |

Wait until `ping rakhza.digital` hits that IP before bringing Caddy up, or certificates will fail.

## First boot (Ubuntu)

```sh
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
# log out and back in
git clone <this-repo> rakhza && cd rakhza/app
python3 scripts/vault.py unlock
docker compose --env-file .env.prod up -d --build
```

Health:

- https://staging.rakhza.digital/login
- https://rakhza.digital/login

CI/CD: test on staging, then press **Deploy production**. See `docs/CICD.md`.

## Data from Neon

```sh
pg_dump "$NEON_URL" --no-owner --format=custom -f neon.dump
docker compose --env-file .env.prod exec -T db pg_restore -U rakhza -d rakhza --no-owner < neon.dump
```

Restore into staging first (`-d rakhza_staging`) and click through signup, stock, and a test pay. Then restore production.

Keep Render up for 48 hours. Then turn it off.

## JazzCash

A JazzCash **Business** account is a wallet that receives TIDs. That is what the Upgrade page uses today.

Automatic Pay Now needs JazzCash **Payment Gateway** credentials (Merchant ID like `MC…`, password, integrity salt). Those are a different product. Sandbox for that gateway is often down. If you have live merchant keys, we test a Rs 1 payment on live with logging. If you only have the business wallet, shops keep sending Rs 299 and pasting the TID; you approve in Rakhza office.

## Play Store

See `docs/PLAY-STORE.md`. Android shops can already install from Chrome. A Play listing is a wrapper around https://rakhza.digital, not a second app.
