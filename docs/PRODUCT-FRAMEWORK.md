# Rakhza product framework

Audience: small shopkeepers in Pakistan who have no POS and no digital inventory (food stalls, cloth shops, plumbers, carpenters, kiryana, tailors). The app must stay simple: large buttons, EN/Urdu, no jargon.

Two roles:

| Role | Who | What they see |
|---|---|---|
| Shop owner | Each signed-up phone | Trial, pay Rs 299 / calendar month, then inventory (later orders if paid) |
| Platform admin | `ADMIN_PHONES` (you) | Users, payments, reconciliation, test wallet |

One phone = one shop for now. No staff logins yet.

Work in this order. Do not start the next slice until the current one is reviewed.

---

## 1. Golden Upgrade Now — **done**

The banner button **Upgrade Now** / **ابھی اپ گریڈ کریں** is a gold button (gold fill, dark royal text), same family as the gold CTAs on login/signup.

## 2. Hide “trial ended” when upgrade is the action — **done**

When the trial is over and the shop is unpaid, the banner must not say **Trial ended, pay to continue**. Keep **Upgrade Now** (gold) and the Upgrade page. Paid shops keep **Paid access active**. Active trials keep “N days left”.

## 3. Admin portal (platform, not the shop) — **done**

Admin-only home at `/admin` (**Rakhza office** / **رکھزا دفتر**). `/admin/payments` stays as the pending queue.

Counts (real PKT clock, not tester Next day):

- **Registered** — every signup.
- **Active** — trial still running **or** `paid_until` in the future.
- **Left membership** — had paid access that has now expired (not people who only finished a free trial).
- **Trial ended, never paid** — no `paid_until`, trial over.

Payments board:

- List: TID, amount, status, shop phone/name, sent at (PKT).
- Totals for **this month**, **3 months**, **6 months**, **12 months**, **custom from–to**.
- Split: pending vs live-looking approved vs `TEST-SIM-…` test money. All-time test wallet stays on the page.
- Reconciliation: type the amount you saw in JazzCash for that window (manual tick). Test money is kept separate on purpose.

## 4. Inventory (core product, trial + paid) — **done**

Built for people who count stock in a notebook.

Shop picks a **trade** at signup (pictured rows with a square checkbox, including Other). First inventory is seeded with 4 template items at qty 10.

- Food, Clothes, Plumber, Carpenter, Small shop / kiryana, Tailor, Stitching, Hardware shop, Sports, Books, Other

The Rs 299 plan includes **3 inventories** (Workshop / Shop plus Site A and Site B). A 4th asks the shop to pay.

Grid columns: Product, Unit, Price, Qty. Native unit dropdown. No barcode, no scanner.

Available during **trial and paid**. This is why they stay.

## 5. Orders (premium only)

If `paid_until` is in the future: track jobs/orders (customer name/phone, what they asked, status new → doing → done). Fits tailors, plumbers, food takeaway. Unpaid / expired shops see Upgrade, not the order book.

---

## Decisions

- Inventory is the product; billing is the gate; admin is your control room.
- Keep Flask + SQLAlchemy, bilingual PWA, JazzCash receive number in the vault.
- Virtual **Pay Rs 299 (test)** stays on staging until JazzCash Payment Gateway live keys exist.
- JazzCash hosted checkout is a later billing slice, not mixed into inventory.

## Later (not in 1–5)

JazzCash Pay Now API, staff accounts, barcode, multi-shop, native stores.
