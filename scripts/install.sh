#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Fichier .env cree depuis .env.example"
fi

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

pip install --upgrade pip
pip install -r analyzer/requirements.txt

cd web
npm ci
cd "$ROOT"

echo "Install OK. Ensuite: bash scripts/init-db.sh puis bash scripts/dev.sh"
