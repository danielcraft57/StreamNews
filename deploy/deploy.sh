#!/usr/bin/env bash
# Deploy sur un noeud (appele par GitHub Actions ou a la main).
# Respecte STREAMNEWS_ROLE dans .env : data | app | worker | all
#
# A lancer en tant que pi (ou root) depuis la flotte : git/pip/npm passent
# en utilisateur streamnews, systemctl reste avec le sudo de pi.
# Toujours possible en streamnews si sudoers.d/streamnews-deploy est en place.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_USER="${DEPLOY_APP_USER:-streamnews}"
ME="$(id -un)"

echo "==> Deploy StreamNews dans $ROOT (user=$ME)"

if [[ ! -f .env ]]; then
  echo "ERREUR: .env manquant dans $ROOT"
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

ROLE="${STREAMNEWS_ROLE:-all}"
BRANCH="${DEPLOY_BRANCH:-main}"

# Ancien .env data copie depuis .env.example (ROLE=all) sans units app/worker
if [[ "$ROLE" == "all" ]] && ! systemctl list-unit-files 2>/dev/null | grep -q '^streamnews-'; then
  echo "WARN: STREAMNEWS_ROLE=all mais aucun unit streamnews -> role=data"
  ROLE=data
fi

# Commandes fichier (repo owned by streamnews).
# Toujours re-source .env dans le sous-shell : bash -lc / sudo -u droppent l'env.
as_app() {
  local inner="cd \"$ROOT\" && set -a && source .env && set +a && $*"
  if [[ "$ME" == "$APP_USER" ]]; then
    bash -lc "$inner"
  else
    sudo -u "$APP_USER" bash -lc "$inner"
  fi
}

# systemctl : pi/root ont le sudo large ; streamnews a le sudoers restreint
sys() {
  if [[ "$ME" == "root" ]]; then
    systemctl "$@"
  else
    sudo -n systemctl "$@"
  fi
}

echo "==> git fetch/reset origin/${BRANCH} (as $APP_USER)"
as_app "git -c safe.directory=$ROOT fetch --all --prune"
as_app "git -c safe.directory=$ROOT reset --hard origin/${BRANCH}"

case "$ROLE" in
  data)
    echo "Role=data : schema/deps seulement (Postgres/Redis geres par apt)."
    as_app '
      if [[ -d .venv ]]; then
        source .venv/bin/activate
        pip install -q -r analyzer/requirements.txt
        cd analyzer
        python -c "from database import Database; import asyncio; asyncio.run(Database().init_db())"
      else
        echo "WARN: .venv absent, skip pip/init_db"
      fi
    '
    ;;
  worker)
    as_app '
      if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
      source .venv/bin/activate
      pip install --upgrade pip
      pip install -r analyzer/requirements.txt
    '
    sys daemon-reload
    sys restart streamnews-worker
    sys status streamnews-worker || true
    ;;
  app|all)
    as_app '
      if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
      source .venv/bin/activate
      pip install --upgrade pip
      pip install -r analyzer/requirements.txt
      ( cd web && npm ci --omit=dev )
      ( cd analyzer && python -c "from database import Database; import asyncio; asyncio.run(Database().init_db())" )
    '
    sys daemon-reload
    if [[ "$ROLE" == "all" ]] || systemctl list-unit-files | grep -q streamnews-analyzer; then
      sys restart streamnews-analyzer || true
    fi
    if systemctl list-unit-files | grep -q streamnews-worker; then
      sys restart streamnews-worker || true
    fi
    if systemctl list-unit-files | grep -q streamnews-web; then
      sys restart streamnews-web || true
    fi
    sys status streamnews-analyzer 2>/dev/null || true
    sys status streamnews-worker 2>/dev/null || true
    sys status streamnews-web 2>/dev/null || true
    ;;
  *)
    echo "STREAMNEWS_ROLE inconnu: $ROLE (data|app|worker|all)"
    exit 1
    ;;
esac

echo "==> Deploy termine (role=$ROLE)"
