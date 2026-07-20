#!/usr/bin/env bash
# Lance analyzer + worker Celery + web avec hot reload (defaut en local).
# Usage: bash scripts/dev.sh --local
#        bash scripts/dev.sh --local --no-reload
#        bash scripts/dev.sh --local --skip-init

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

NO_RELOAD=0
SKIP_INIT=0
for arg in "$@"; do
  case "$arg" in
    --no-reload) NO_RELOAD=1 ;;
    --skip-init) SKIP_INIT=1 ;;
  esac
done

if [[ "$SKIP_INIT" -eq 0 ]]; then
  echo "Init DB (${STREAMNEWS_ENV:-?} / ${DATABASE_URL%%\?*} )..."
  bash scripts/init-db.sh "$@"
fi

CONCURRENCY="${CELERY_CONCURRENCY:-2}"

if [[ "$NO_RELOAD" -eq 0 ]]; then
  echo "Hot reload actif (uvicorn --reload, nodemon, watchdog Celery)."
  echo "Fichiers web/public/* : refresh navigateur."
else
  echo "Hot reload desactive (--no-reload)."
fi
echo "Demarrage analyzer (8000), worker Celery, web (3000)..."
echo "Ctrl+C pour tout arreter."

cleanup() {
  jobs -p | xargs -r kill 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [[ "$NO_RELOAD" -eq 0 ]]; then
  (
    cd analyzer
    python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-dir .
  ) &

  (
    cd analyzer
    python -m watchdog.watchmedo auto-restart \
      --directory . \
      --pattern '*.py' \
      --recursive \
      --debounce-interval 2 \
      -- python -m celery -A celery_worker worker \
      --loglevel=info --pool=solo --concurrency="$CONCURRENCY" \
      -Q crawl,ingest,default
  ) &

  (
    cd web
    npm run dev
  ) &
else
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
fi

wait
