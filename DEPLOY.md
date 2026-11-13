# Rakhza: VPS hosting (staging + production)

Render + Neon was the tester host. Live hosting is the VPS at **2.25.6.85**
with Docker: **https://rakhza.digital** (prod) and
**https://staging.rakhza.digital** (testers).

Full runbook: `deploy/VPS.md`. Secrets: `secrets/README.md`.
JazzCash: `docs/JAZZCASH.md`. Play Store: `docs/PLAY-STORE.md`.

1. **DNS.** Point `rakhza.digital`, `www.rakhza.digital`, and
   `staging.rakhza.digital` A records to `2.25.6.85`.
2. **Vault.** Copy `secrets/rakhza.env.example` to `secrets/rakhza.env`,
   fill values, then `python scripts/vault.py lock`. Unlock on the VPS
   before `docker compose`. Never commit the plaintext.
3. **VPS.** Install Docker. Clone the repo. Unlock the vault.
   `docker compose --env-file .env.prod up -d --build`.
4. **Database.** Staging and production are two Postgres databases on the
   same server (`rakhza` and `rakhza_staging`). Dump Neon into staging
   first, smoke-test, then production.
5. **JazzCash.** The business wallet number is `PAYMENT_JAZZCASH_NUMBER`.
   Automatic Pay Now needs Payment Gateway merchant keys, which a business
   account does not include. Keep TID review until those keys exist.
6. **Android.** Chrome → Install app on the HTTPS URL. Play Store is a
   later TWA wrapper of rakhza.digital, not a second codebase.

`render.yaml` remains for the old tester service until cutover is done.
Do not commit `.env`, vault plaintext, phone lists, or JazzCash keys.
