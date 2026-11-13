# Staging then production

```
push to main
    → tests
    → deploy staging.rakhza.digital
you click through the shop on staging
    → GitHub → Actions → Deploy production → Run workflow
    → rakhza.digital
```

Production never deploys itself. You press the button after staging looks right.

## Two jobs

| Workflow | When | Where |
|---|---|---|
| **Test** | every push / pull request | GitHub runner only |
| **Deploy staging** | push to `main`, or Run workflow | `staging.rakhza.digital` |
| **Deploy production** | **Run workflow only** | `rakhza.digital` |

Same VPS, two Docker services (`web_staging`, `web_prod`). Vault env files on the server are not overwritten.

## One GitHub secret

Repo → Settings → Secrets and variables → Actions → New repository secret:

- Name: `VPS_SSH_KEY`
- Value: the full private key from `C:\Users\DELL\.ssh\id_ed25519_rakhza` (the `-----BEGIN` block)

Optional later: Settings → Environments → `production` → required reviewers, so the prod button needs a second click.

## First time

1. Add `VPS_SSH_KEY`.
2. Point DNS (see `deploy/VPS.md`).
3. Push these workflow files to `main`.
4. Staging deploys. Open https://staging.rakhza.digital/login
5. When that is good, run **Deploy production**.
