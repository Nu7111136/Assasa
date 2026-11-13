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

## What we do

1. Keep the current TID + Rakhza office approve/reject flow on the business number.
2. If JazzCash later issues live PG keys, add hosted checkout and skip sandbox.
3. First live PG test is **Rs 1**, with logs, on staging hostname if JazzCash
   will whitelist it, otherwise a one-shop live test you watch.

Do not paste Merchant password or integrity salt into GitHub or chat.
Put them in `secrets/rakhza.env` and lock the vault.
