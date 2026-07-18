#!/usr/bin/env bash
# Demarre fixture mock + stack StreamNews pour les e2e, puis rend la main.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export DATABASE_URL="${DATABASE_URL:-postgresql://streamnews:streamnews123@localhost:5432/streamnews}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export WEB_URL="${WEB_URL:-http://127.0.0.1:3000}"
export ANALYZER_URL="${ANALYZER_URL:-http://127.0.0.1:8000}"
export PORT="${PORT:-3000}"

LOG_DIR="${LOG_DIR:-/tmp/streamnews-e2e}"
mkdir -p "$LOG_DIR"
PIDS_FILE="$LOG_DIR/pids"
: > "$PIDS_FILE"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "==> Fixture mock site :8765"
python3 -m http.server 8765 --directory "$ROOT/e2e/fixtures/mock-site" \
  > "$LOG_DIR/fixture.log" 2>&1 &
echo $! >> "$PIDS_FILE"

echo "==> Init DB"
(
  cd analyzer
  python -c "from database import Database; import asyncio; asyncio.run(Database().init_db())"
)

echo "==> Analyzer :8000"
(
  cd analyzer
  python main.py
) > "$LOG_DIR/analyzer.log" 2>&1 &
echo $! >> "$PIDS_FILE"

echo "==> Celery worker"
(
  cd analyzer
  python -m celery -A celery_worker worker --loglevel=info --concurrency=1
) > "$LOG_DIR/celery.log" 2>&1 &
echo $! >> "$PIDS_FILE"

echo "==> Web :3000"
(
  cd web
  node server.js
) > "$LOG_DIR/web.log" 2>&1 &
echo $! >> "$PIDS_FILE"

echo "==> Attente healthchecks"
for i in $(seq 1 90); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null \
    && curl -sf http://127.0.0.1:3000/api/health >/dev/null \
    && curl -sf http://127.0.0.1:8765/ >/dev/null; then
    echo "Stack e2e prete (PIDs dans $PIDS_FILE)"
    exit 0
  fi
  sleep 1
done

echo "Timeout demarrage stack e2e"
tail -n 80 "$LOG_DIR"/*.log || true
exit 1
