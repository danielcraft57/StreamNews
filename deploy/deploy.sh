#!/usr/bin/env bash
# Deploy sur le VPS (appele par GitHub Actions ou a la main).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Deploy StreamNews dans $ROOT"

if [[ ! -f .env ]]; then
  echo "ERREUR: .env manquant dans $ROOT"
  exit 1
fi

git fetch --all --prune
git reset --hard origin/main

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r analyzer/requirements.txt

cd web
npm ci --omit=dev
cd "$ROOT"

# shellcheck disable=SC1091
set -a
source .env
set +a

(
  cd analyzer
  python -c "from database import Database; import asyncio; asyncio.run(Database().init_db())"
)

sudo systemctl daemon-reload
sudo systemctl restart streamnews-analyzer
sudo systemctl restart streamnews-worker
sudo systemctl restart streamnews-web
sudo systemctl --no-pager --full status streamnews-analyzer || true
sudo systemctl --no-pager --full status streamnews-worker || true
sudo systemctl --no-pager --full status streamnews-web || true

echo "==> Deploy termine"
