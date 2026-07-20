#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/load-env.sh" "$@"

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

echo "Init DB (${STREAMNEWS_ENV:-?} / ${DATABASE_URL%%\?*} )..."
bash scripts/init-db.sh "$@"

CONCURRENCY="${CELERY_CONCURRENCY:-2}"

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
  python -m celery -A celery_worker worker --loglevel=info --concurrency="$CONCURRENCY" \
    -Q crawl,ingest,default
) &

(
  cd web
  npm start
) &

wait
