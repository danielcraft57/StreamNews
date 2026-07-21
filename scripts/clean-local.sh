#!/usr/bin/env bash
# Nettoyage fichiers locaux (hors git). Ne touche pas aux .env.
# Usage: bash scripts/clean-local.sh [--keep-db]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

KEEP_DB=0
for arg in "$@"; do
  case "$arg" in
    --keep-db) KEEP_DB=1 ;;
  esac
done

echo "[clean] caches pytest / mypy / ruff..."
for d in .pytest_cache analyzer/.pytest_cache analyzer/.pytest_tmp .mypy_cache .ruff_cache; do
  if [[ -d "$d" ]]; then
    rm -rf "$d"
    echo "  supprime $d"
  fi
done

if [[ "$KEEP_DB" -eq 0 ]]; then
  echo "[clean] base SQLite locale..."
  rm -f data/streamnews.db data/streamnews.db-wal data/streamnews.db-shm 2>/dev/null || true
fi

echo "[clean] logs (garde .gitkeep)..."
find logs -maxdepth 1 -name '*.log' -type f -exec truncate -s 0 {} \; 2>/dev/null || true

echo "Nettoyage termine."
