#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Cree .env et/ou .env.local si absents
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Fichier .env cree depuis .env.example"
fi
if [[ ! -f .env.local ]]; then
  cp .env.local.example .env.local
  echo "Fichier .env.local cree depuis .env.local.example"
fi

mkdir -p data

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

pip install --upgrade pip
pip install -r analyzer/requirements.txt

cd web
npm ci
cd "$ROOT"

echo "Install OK."
echo "  Local (SQLite + Redis distant) : bash scripts/init-db.sh --local && bash scripts/dev.sh --local"
echo "  Prod-like (.env Postgres)     : edite .env (remplace CHANGE_ME), puis init-db + dev.sh"
if grep -q 'CHANGE_ME' .env 2>/dev/null; then
  echo "ATTENTION: .env contient encore CHANGE_ME — a remplacer avant un usage Postgres."
fi
