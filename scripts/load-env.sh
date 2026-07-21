#!/usr/bin/env bash
# Charge .env.local (mode local) ou .env (prod / defaut).
# Usage: source scripts/load-env.sh [--local]
#        STREAMNEWS_ENV=local source scripts/load-env.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

USE_LOCAL=0
for arg in "$@"; do
  case "$arg" in
    --local|-l) USE_LOCAL=1 ;;
  esac
done

if [[ "${STREAMNEWS_ENV:-}" == "local" ]]; then
  USE_LOCAL=1
fi

ENV_FILE=".env"
if [[ "$USE_LOCAL" -eq 1 ]]; then
  ENV_FILE=".env.local"
  if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f .env.local.example ]]; then
      cp .env.local.example .env.local
      echo "Fichier .env.local cree depuis .env.local.example"
    else
      echo "Fichier .env.local manquant. Copie .env.local.example vers .env.local."
      return 1 2>/dev/null || exit 1
    fi
  fi
elif [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "Fichier .env cree depuis .env.example"
  else
    echo "Fichier .env manquant."
    return 1 2>/dev/null || exit 1
  fi
fi

# shellcheck disable=SC1090
set -a
# shellcheck disable=SC1091
source "$ENV_FILE"
set +a

echo "Env charge: $ENV_FILE (STREAMNEWS_ENV=${STREAMNEWS_ENV:-?})"

if [[ "$USE_LOCAL" -eq 0 ]]; then
  if [[ "${POSTGRES_PASSWORD:-}" == "CHANGE_ME" ]] || [[ "${DATABASE_URL:-}" == *CHANGE_ME* ]]; then
    echo "ATTENTION: Postgres non configure (CHANGE_ME dans .env)."
  fi
fi
