#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/load-env.sh" "$@"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

RESET=0
for arg in "$@"; do
  case "$arg" in
    --reset) RESET=1 ;;
  esac
done

if [[ "$RESET" -eq 1 ]]; then
  echo "ATTENTION: recreate complete du schema (DROP tables)."
fi

# SQLite : s'assurer que data/ existe
case "${DATABASE_URL:-}" in
  sqlite:*|sqlite+*)
    mkdir -p "$ROOT/data"
    ;;
esac

cd analyzer
STREAMNEWS_RESET_DB="$RESET" python -c \
  "from database import Database; import asyncio; asyncio.run(Database().init_db(reset=$RESET))"
echo "Base initialisee (${STREAMNEWS_ENV:-?})."
