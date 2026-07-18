#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Fichier .env manquant."
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

cd analyzer
python -c "from database import Database; import asyncio; asyncio.run(Database().init_db())"
echo "Base initialisee."
