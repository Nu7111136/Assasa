#!/bin/bash
# Rebuild one environment on this VPS. Env files in /opt/rakhza stay untouched.
set -euo pipefail
cd /opt/rakhza
case "${1:-}" in
  staging) svc="web_staging sweep_staging" ;;
  production|prod) svc="web_prod sweep_prod" ;;
  *) echo "usage: $0 staging|production" >&2; exit 1 ;;
esac
# $svc is intentionally unquoted: it holds the web service and its sweep worker.
docker compose --env-file .env.prod up -d --build db redis caddy $svc
docker compose --env-file .env.prod ps
