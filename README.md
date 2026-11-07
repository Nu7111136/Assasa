# Asasa signup POC

Small Flask + SQLAlchemy server-rendered PWA, not a production identity platform.
The latest signup brief supersedes the plan's earlier OTP-only onboarding: name,
address, CNIC, phone, optional email and password; phone/password login. Every new
account gets one server-recorded 120-hour trial. Price copy: Rs 299/month after
five days, no automatic charge. Manual payment review is included; real gateway billing, inventory, OTP and
tenant memberships remain outside this signup POC.

## Run locally

Python 3.11+ (3.13 tested), from this folder:

```sh
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env  # PowerShell: Copy-Item .env.example .env
# Generate a fresh SECRET_KEY and put it in your private .env:
python -c "import secrets; print(secrets.token_hex(32))"
python -m flask --app wsgi init-db
python -m flask --app wsgi run --host 0.0.0.0 --port 5088
pytest -q
```

Open http://127.0.0.1:5088. A phone needs the computer's LAN address; PWA service
workers/installability require HTTPS or localhost. On real phones use a private
HTTPS deployment. Android: Chrome menu → Install app; iPhone: Safari Share → Add
to Home Screen. Urdu uses RTL with LTR phone/CNIC inputs. Native Urdu review is
needed before release. This is a web app installed from a browser, not a Play or
App Store native build.

`DATABASE_URL` unset: development SQLite (`instance/asasa.db`).
Postgres URL: `postgresql+psycopg://...` (also accepts `postgres://` and
`postgresql://`). Add `?sslmode=require` for Neon. Database stays outside the zip.
If SECRET_KEY is blank a random ephemeral key is used: sessions reset after a
restart. Set one stable private random key on hosting. Never use an example key.

## Integrate

- `main.py`: app factory, model, validation, login and trial calculation.
- `templates/`: bilingual signup/login/dashboard; `TEXT` catalogs are in main.py.
- `static/`: isolated navy/white UI, icons, manifest and service worker.
- Import `create_app`, or register equivalent routes/models in your larger app.
  Avoid clashing route names; namespace routes, cookie and service-worker scope
  when sharing a domain. The worker scope is the root in this standalone POC.
- User ID comes only from the signed session, not submitted dashboard IDs. Never
  use a phone or a CNIC as a tenant ID. Add business/membership tables and tenant
  authorization tests before integrating inventory.
- Werkzeug scrypt password hashes, CSRF-protected POSTs (including logout), unique
  phone DB constraint and route rate limits. Rate limiting is per-process memory
  for the POC; configure shared Redis for multi-worker production.
- Trial stored in UTC; dashboard shows PKT and ceiling days left, zero after expiry.
  Expiry enables a server-side read-only mutation guard. New mutation routes must
  be covered by entitlement tests; payment submission and logout stay available. Existing accounts never reset on login.
- No stored copy is sent to any third party. PWA caches ONLY public static assets;
  private HTML, POSTs, CNIC and dashboard are never cached. Offline page says login
  needs internet; this POC does not promise offline signup or sync.
- `init-db` creates tables, not migrations. Adopt Alembic migrations before changes
  to deployed data; backups and restore testing are mandatory.

## Free proof-of-concept hosting: Render + Neon

Checked 7 November 2026 (PKT); check current quotas at deployment:
https://render.com/docs/free and https://neon.com/faqs/free-plan-limits-and-quotas

1. NZ can place this folder in his own private repo and connect it to Render;
   no repository, remote push or deployment was performed by this delivery.
2. Create a Neon free PostgreSQL project. Keep its pooled URL private. Select a
   suitable region and enable TLS. Create only a dedicated app database role.
3. Render: Python web service, root directory = this folder, build command
   `pip install -r requirements.txt`. For this first POC, start command:
   `python -m flask --app wsgi init-db && gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1`.
   Move schema changes to an explicit release/migration step before production.
4. Set private environment variables DATABASE_URL (Neon), SECRET_KEY (random),
   COOKIE_SECURE=1. Use HTTPS. Do not put connection strings in frontend code.
5. Render free web sleeps after 15 idle minutes, with cold starts and ephemeral
   disk: **never use SQLite there**. Included instance hours, bandwidth and build
   limits apply; Render free Postgres expires after 30 days, so use Neon instead.
6. Neon free scales to zero after five idle minutes and has compute, storage,
   transfer and restore limits. Both app and DB may cold-start; no uptime promise.
   As checked: Neon lists 100 CU-hours/project/month, 1 GB storage/project and
   5 GB public transfer/project. Recheck these changing quotas before signup.
7. This is acceptable for fictional-data demos, not real CNICs or a scaled SaaS.
   Production needs paid reliability, independent backups and privacy/security review.

## Before real users (important)

Use **fictional CNIC/phone/address only** for this demo. CNIC/phone are structurally
validated but NOT verified. CNIC and address are currently ordinary DB columns,
not application-encrypted; require legal purpose/consent, retention/deletion policy,
encryption/key management, least privilege, auditing and breach procedures before
collecting real identity data. Do not log request bodies or customer records.
Add phone verification/recovery, abuse defenses, privacy/terms consent, reset and
number-change workflows, tenant isolation and subscription enforcement. PostgreSQL
support is configured but tests here use isolated SQLite; run integration tests
against a disposable PostgreSQL database before deployment. Never publish .env,
instance databases, customer screenshots or private keys. No real credentials or
customer data are included in this package.


## Trial / manual JazzCash extension (box-only update)

NZ's original `static/style.css` is retained byte-for-byte at the beginning; new
rules are appended and use his `--navy` variable. CSS version is `trial-2`, service
worker cache is `asasa-shell-trial-2`. Private pages remain network-only/no-store.

**Existing installations: back up the DB first**, then from the app directory:

```sh
python -m flask --app main upgrade-db
python -m flask --app main run --port 5005
```

`upgrade-db` adds `user.paid_until` and the new payment table without deleting users.
It is a minimal additive SQLite/Postgres POC migration, not a full Alembic system.
Use it instead of `init-db` when upgrading an existing database.

Environment settings (private `.env`, not committed/shipped):

```ini
APP_ENV=production
PAYMENT_JAZZCASH_NUMBER=03036666758
ADMIN_PHONES=
```

Set `ADMIN_PHONES` to a comma-separated allowlist of **existing registered** phone
numbers. No default admin account is created. These users must still log in with
passwords. Visit `/admin/payments`, verify the funds in JazzCash, then approve or
reject. A TID is only a claim, never automatic proof of payment. Approval grants
**30 days starting at approval time**, not from trial expiry or previous paid date.
Duplicate TIDs are rejected across all accounts; reviews are one-shot and atomic.
Rejected TIDs cannot be reused: arrange corrected payment details with the admin.
The configured destination must be checked/owned by the operator before real use.

After trial expiry, users may still view pages, submit a TID or log out. Other
logged-in mutation requests are blocked server-side with 403. Admin payment reviews
remain allowed for an authorized admin even when that admin's own trial expired.
A paid, unexpired account shows a paid-access banner and is not read-only.
No inventory screens or real gateway/automatic verification were added.

### Tester day preview

Set TESTER_PHONES to comma-separated registered phone numbers. ADMIN_PHONES also
qualify. Restart after changing allowlists. On Dashboard, Next day adds one day
to actual server time for this session; Reset returns to the real date. A TEST:
Day N strip shows the current offset. Works in all APP_ENV values; non-testers
cannot activate it. Logout clears the session. Other sessions are unaffected.

The old day picker, simulate_day query, and FAKE_TODAY clock are retired.
Preview affects entitlement display/read-only checks only. No stored trial dates
or billing records change. Payment submissions and approvals remain REAL actions
using actual server time. CSS/service-worker version: trial-4.
