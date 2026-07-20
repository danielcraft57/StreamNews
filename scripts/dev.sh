#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Fichier .env manquant. Copie .env.example vers .env puis relance."
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

if [[ ! -d .venv ]]; then
  echo "venv absent. Lance d'abord: bash scripts/install.sh"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [[ ! -d web/node_modules ]]; then
  echo "node_modules absent. Lance d'abord: bash scripts/install.sh"
  exit 1
fi

echo "Installation des dependances OK. Init DB..."
bash scripts/init-db.sh

echo "Demarrage analyzer (8000), worker Celery, web (3000)..."
echo "Ctrl+C pour tout arreter."

cleanup() {
  jobs -p | xargs -r kill 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(
  cd analyzer
  python main.py
) &

(
  cd analyzer
  python -m celery -A celery_worker worker --loglevel=info --concurrency=2 \
    -Q crawl,ingest,default
) &

(
  cd web
  npm start
) &

wait
