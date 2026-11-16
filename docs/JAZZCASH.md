# JazzCash for Rakhza

Two different JazzCash products get mixed up. Only one is in the app today.

| | JazzCash Business (what you have) | JazzCash Payment Gateway |
|---|---|---|
| What it is | A merchant/business **wallet number** | Hosted checkout + IPN APIs |
| Shop action | Send Rs 299, paste TID | Tap Pay, JazzCash page opens |
| Proof | You look in the JazzCash app | Signed callback, response `000` |
| Credentials | The receive number | Merchant ID `MC…`, password, integrity salt |
| Sandbox | None | sandbox.jazzcash.com.pk — often broken |

Automatic “Pay Rs 299 and the month opens by itself” needs the **Payment Gateway**.
A business account does not include those keys. Sandbox being dead is common;
it does not mean live gateway will fail.

## Hosted checkout (staging)

When `JAZZCASH_MERCHANT_ID`, `JAZZCASH_PASSWORD`, and `JAZZCASH_INTEGRITY_SALT`
are set, `/upgrade` shows **Pay with JazzCash**. The shop is sent to JazzCash
hosted checkout. A signed return to `/billing/jazzcash/return` with code `000`
calls `grant_month()`. Staging amount is **Rs 1** (`JAZZCASH_AMOUNT_PAISA=100`).
TID paste stays for agents and failed callbacks.

## What we do

1. Keep the current TID + Rakhza office approve/reject flow on the business number.
2. Hosted checkout on staging with live PG keys (sandbox skipped).
3. First live PG test is **Rs 1**, with logs, on https://staging.rakhza.digital.

Do not paste Merchant password or integrity salt into GitHub or chat.
Put them in `secrets/rakhza.env` and lock the vault.

## How a checkout is settled

Every payment row has a `method`: `tid` (pasted receipt), `checkout`
(gateway), or `test` (tester button). Older rows are inferred from the ID.

The return at `/billing/jazzcash/return` changes a row only when **all** hold:
signature valid with our salt, `pp_MerchantID` is ours, `pp_TxnRefNo` is a
`checkout` row, and for success `pp_Amount` equals the amount we sent.

| JazzCash says | Row becomes | Shop sees |
|---|---|---|
| `000` | approved, one month granted | Dashboard |
| `124` / `157` (still in progress) | stays pending | Waiting page, polls every few seconds |
| any other signed code | failed, no month | "Did not go through", Try again / paste TID |
| unsigned, wrong amount/merchant/ref | unchanged | Waiting page or Upgrade notice |

`pending -> approved/failed/rejected` is a one-shot update shared by the
return and the office Approve button, so a month is never granted twice.

The return is a cross-site POST, so the login cookie (SameSite=Lax) is not
sent. The handler never reads or writes the session; it redirects to
`/billing/jazzcash/<id>`, and that GET carries the cookie.

Rakhza office lists unconfirmed checkouts separately from pasted TIDs. Approve
one only after finding that reference paid in the JazzCash merchant portal.
The TID paste form stays on Upgrade for agents and failed checkouts.

Still to do: server-to-server IPN listener and a status-inquiry job, so a
checkout settles even if the shop's browser never comes back.
