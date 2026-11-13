#!/bin/bash
# Rebuild one environment on this VPS. Env files in /opt/rakhza stay untouched.
set -euo pipefail
cd /opt/rakhza
case "${1:-}" in
  staging) svc=web_staging ;;
  production|prod) svc=web_prod ;;
  *) echo "usage: $0 staging|production" >&2; exit 1 ;;
esac
docker compose --env-file .env.prod up -d --build db redis caddy "$svc"
docker compose --env-file .env.prod ps
