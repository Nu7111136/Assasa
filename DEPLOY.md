# Asasa: free tester hosting (Render + Neon)

1. **Prepare GitHub.** Review the local changes, then push them yourself to
   `Nu7111136/Assasa` when ready. Nothing has been pushed or deployed for you.
   Render reads GitHub, not this laptop. `render.yaml`, `main.py`, `wsgi.py` and
   `requirements.txt` are at the repository root; leave Render Root Directory blank.
   Do not commit `.env`, database files, actual tester phone lists, or credentials.
2. **Neon.** Sign up at https://console.neon.tech and select the Free plan.
   Create a separate project/database for this POC and choose a nearby region.
   Open **Connect**, select your database/role and copy the PostgreSQL connection
   string (pooled is fine). Keep its SSL options, including `sslmode=require`.
   It contains a password: paste it only into Render, never chat, GitHub or screenshots.
3. **Render.** Sign up at https://dashboard.render.com using GitHub. Grant access
   to `Nu7111136/Assasa`. Choose **New > Blueprint**, select that repo and main,
   and use the root `render.yaml`. Confirm the web service plan is **Free**.
   No Render database or paid disk is required: data lives in Neon.
4. **Configure prompted environment variables.** Paste the entire Neon URL into
   `DATABASE_URL` (no surrounding quotes). For `ADMIN_PHONES`, enter NZ's registered
   phone number; for `TESTER_PHONES`, enter comma-separated testers' own numbers,
   in `03XXXXXXXXX` format. Use your intended numbers, not documentation examples.
   If a list is not needed, leave it empty. Render generates `SECRET_KEY`; retain
   it across deploys so sessions stay valid. The Blueprint sets
   `PAYMENT_JAZZCASH_NUMBER=03036666758`, `APP_ENV=production`, and `COOKIE_SECURE=1`.
   Never put real phone lists in `render.yaml`. Later allowlist changes belong in
   Render > service > Environment, followed by a restart/redeploy.
5. **Deploy.** Apply the Blueprint and wait for the green deployment. Build installs
   requirements. Start runs `flask --app main upgrade-db` before Gunicorn; this
   creates missing tables and adds the legacy `paid_until` column without deleting
   users. This is a small POC migration, not a general schema migration framework.
   A startup DB error usually means a wrong URL, missing SSL options, or Neon access
   settings. Do not replace the URL with SQLite on Render: its local disk is ephemeral.
6. **Share the HTTPS link.** Open the service's `https://...onrender.com` URL.
   Sign up, confirm Next day/Reset are visible for allowlisted accounts, advance
   until Upgrade appears, and Reset. Send testers the link and `TESTERS.md`.
   Admin review is at `/admin/payments`; only allowlisted registered admins can open it.
7. **Expect free-tier pauses.** Render sleeps when idle; the first load may take
   roughly 30-50 seconds, sometimes over a minute. Neon can also pause when idle.
   Wait and refresh once; this is not an installed-app/offline mode failure.
   Free-tier limits can change: review the plan screens and do not enable paid
   services or upgrades unless you intend to pay. Internet is needed for login/data.
8. **Test safely.** This is a separate tester database, not a real billing launch.
   Use fake CNIC/address details and test passwords; phone/email/CNIC are not verified.
   Fake TIDs are test submissions, NOT proof of payment. Do not ask testers to send
   real money. Never approve a fake TID as a real payment. Approval changes the
   actual account in this test database and grants 30 days; reset does not undo it.
   Never publish database exports, logs containing personal details, or credentials.
9. **Updates.** Automatic deployment is off in this Blueprint. After reviewing and
   pushing a later commit yourself, use Render's Manual Deploy. Keep Neon credentials
   and SECRET_KEY private, back up important data, and use a separate database before
   moving beyond the POC. No external deployment was performed by this change.

## Checks / limitations

- Both `postgres://` and `postgresql://` URLs use the psycopg v3 driver.
- Gunicorn and `psycopg[binary]` are already in requirements.txt.
- SQLite regression tests cover upgrade-db and user preservation. PostgreSQL DDL
  and URL handling are tested without a server. A live PostgreSQL smoke test was
  not run: PostgreSQL/Docker were unavailable on the box. Check the first Neon
  deployment logs and complete the signup/upgrade/reset smoke test before sharing.
- Rate limiting currently uses process-local memory (one Gunicorn worker). It is
  suitable only for a limited POC, not durable distributed abuse protection.
- Sources: https://render.com/docs/blueprint-spec,
  https://render.com/docs/free, https://neon.com/docs/guides/python.
