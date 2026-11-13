# Play Store for Rakhza

## What shops have today (PWA)

On Android Chrome, open https://rakhza.digital → menu → **Install app**.
That puts Rakhza on the home screen. It looks like an app. No Google account
review, no $25 fee, no waiting. Staging uses https://staging.rakhza.digital
the same way.

iPhone: Safari → Share → Add to Home Screen.

## What “Play Store now” means

A listing on Google Play so a shop can search **Rakhza**, tap Install, and get
the same site inside a thin Android wrapper (Trusted Web Activity / TWA).

That needs:

1. A Google Play Console account — **US $25 once**
2. Package name, e.g. `digital.rakhza.app`
3. Signing key (keep in the vault)
4. Bubblewrap/TWA build that opens `https://rakhza.digital`
5. Store screenshots, short description, privacy policy URL
6. Google review — often a few days, sometimes longer
7. Every later change to the wrapper is a new Play release (website changes
   go live without a store update)

It is still the Flask PWA. It is not a Kotlin rewrite.

## When to do it

Do it when you want shops to find Rakhza inside Play, or when they do not
trust “Install from Chrome”.

Do the VPS + HTTPS + paying shops first. Play will not help if
rakhza.digital is down or still on Render.

Say **yes, Play Store now** if you want the TWA wrapper in this move.
Say **later** if Chrome install is enough for testers.
