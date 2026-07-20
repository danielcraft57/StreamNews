#!/usr/bin/env bash
# Deploy sur un noeud (appele par GitHub Actions ou a la main).
# Respecte STREAMNEWS_ROLE dans .env : data | app | worker | all
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Deploy StreamNews dans $ROOT"

if [[ ! -f .env ]]; then
  echo "ERREUR: .env manquant dans $ROOT"
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

ROLE="${STREAMNEWS_ROLE:-all}"
BRANCH="${DEPLOY_BRANCH:-main}"

# Repo owned by streamnews, deploy souvent lance en pi -> safe.directory
git -c "safe.directory=$ROOT" fetch --all --prune
git -c "safe.directory=$ROOT" reset --hard "origin/${BRANCH}"

case "$ROLE" in
  data)
    echo "Role=data : pas de restart app (Postgres/Redis geres par apt/systemd)."
    if [[ -d .venv ]]; then
      # shellcheck disable=SC1091
      source .venv/bin/activate
      pip install -q -r analyzer/requirements.txt
      (
        cd analyzer
        python -c "from database import Database; import asyncio; asyncio.run(Database().init_db())"
      )
    fi
    ;;
  worker)
    if [[ ! -d .venv ]]; then
      python3 -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r analyzer/requirements.txt
    sudo systemctl daemon-reload
    sudo systemctl restart streamnews-worker
    sudo systemctl --no-pager --full status streamnews-worker || true
    ;;
  app|all)
    if [[ ! -d .venv ]]; then
      python3 -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r analyzer/requirements.txt
    (
      cd web
      npm ci --omit=dev
    )
    (
      cd analyzer
      python -c "from database import Database; import asyncio; asyncio.run(Database().init_db())"
    )
    sudo systemctl daemon-reload
    if [[ "$ROLE" == "all" ]] || systemctl list-unit-files | grep -q streamnews-analyzer; then
      sudo systemctl restart streamnews-analyzer || true
    fi
    if systemctl list-unit-files | grep -q streamnews-worker; then
      sudo systemctl restart streamnews-worker || true
    fi
    if systemctl list-unit-files | grep -q streamnews-web; then
      sudo systemctl restart streamnews-web || true
    fi
    sudo systemctl --no-pager --full status streamnews-analyzer streamnews-worker streamnews-web 2>/dev/null || true
    ;;
  *)
    echo "STREAMNEWS_ROLE inconnu: $ROLE (data|app|worker|all)"
    exit 1
    ;;
esac

echo "==> Deploy termine (role=$ROLE)"
