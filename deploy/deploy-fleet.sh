#!/usr/bin/env bash
# Deploy multi-noeuds depuis le bastion SSH (secret DEPLOY_HOST, ex: node9).
# Usage (sur le bastion) :
#   bash deploy/deploy-fleet.sh
#
# Variables optionnelles :
#   FLEET_HOSTS="node6.lan node7.lan node8.lan"
#   FLEET_USER=pi
#   DEPLOY_PATH=/opt/streamnews
#
# Les noeuds app/worker partent en parallele apres le noeud data (1er de FLEET_HOSTS).
# L'edge nginx public (ex: node12) est un autre role : reload ici seulement si le
# vhost StreamNews est present sur CE bastion.
set -euo pipefail

FLEET_USER="${FLEET_USER:-pi}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/streamnews}"
FLEET_HOSTS="${FLEET_HOSTS:-node6.lan node7.lan node8.lan}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "==> Fleet deploy depuis $(hostname -s) -> $FLEET_HOSTS"

LOG_DIR="$(mktemp -d)"
trap 'rm -rf "$LOG_DIR"' EXIT

deploy_one() {
  local host="$1"
  local log="$2"
  (
    set +e
    echo "==> debut deploy $host"
    ssh -o BatchMode=yes -o ConnectTimeout=15 \
      -o StrictHostKeyChecking=accept-new \
      "${FLEET_USER}@${host}" \
      "set -euo pipefail
       cd \"${DEPLOY_PATH}\"
       # Pull avant exec (sinon on lance encore l'ancien deploy.sh)
       BRANCH=\"\${DEPLOY_BRANCH:-main}\"
       sudo -u streamnews git -c safe.directory=${DEPLOY_PATH} fetch --all --prune
       sudo -u streamnews git -c safe.directory=${DEPLOY_PATH} reset --hard \"origin/\${BRANCH}\"
       export DEPLOY_BRANCH=\"\${BRANCH}\"
       bash deploy/deploy.sh"
    ec=$?
    if [[ "$ec" -ne 0 ]]; then
      echo "ERREUR: deploy failed on $host (exit $ec)"
    else
      echo "==> fin deploy $host OK"
    fi
    exit "$ec"
  ) >"$log" 2>&1
}

declare -a HOSTS_ARR=()
for host in $FLEET_HOSTS; do
  HOSTS_ARR+=("$host")
done

if [[ ${#HOSTS_ARR[@]} -eq 0 ]]; then
  echo "ERREUR: FLEET_HOSTS vide"
  exit 1
fi

# Premier hote = data (convention FLEET_HOSTS) : migrations avant le reste.
DATA_HOST="${HOSTS_ARR[0]}"
echo "==> phase data (migrations) : $DATA_HOST"
set +e
deploy_one "$DATA_HOST" "$LOG_DIR/${DATA_HOST}.log"
data_ec=$?
set -e
echo ""
echo "========== $DATA_HOST =========="
cat "$LOG_DIR/${DATA_HOST}.log"
if [[ "$data_ec" -ne 0 ]]; then
  echo "==> Fleet deploy termine AVEC ERREURS (data)"
  exit 1
fi

declare -a PIDS=()
declare -a REST_HOSTS=()
for host in "${HOSTS_ARR[@]:1}"; do
  REST_HOSTS+=("$host")
  log="$LOG_DIR/${host}.log"
  deploy_one "$host" "$log" &
  PIDS+=($!)
  echo "lance: $host (pid ${PIDS[-1]})"
done

failed=0
for i in "${!PIDS[@]}"; do
  host="${REST_HOSTS[$i]}"
  pid="${PIDS[$i]}"
  set +e
  wait "$pid"
  ec=$?
  set -e
  echo ""
  echo "========== $host =========="
  cat "$LOG_DIR/${host}.log"
  if [[ "$ec" -ne 0 ]]; then
    failed=1
  fi
done

# Recharge nginx local si le vhost StreamNews est present (bastion edge)
if [[ -f /etc/nginx/sites-enabled/streamnews.danielcraft.fr ]]; then
  echo ""
  echo "---------- nginx (local) ----------"
  if [[ -d "$ROOT/.git" ]]; then
    BRANCH="${DEPLOY_BRANCH:-main}"
    git -C "$ROOT" fetch origin || true
    git -C "$ROOT" checkout "$BRANCH" 2>/dev/null || true
    git -C "$ROOT" reset --hard "origin/${BRANCH}" 2>/dev/null || true
    if [[ -f "$ROOT/deploy/nginx-streamnews.danielcraft.fr.conf" ]]; then
      sudo cp "$ROOT/deploy/nginx-streamnews.danielcraft.fr.conf" \
        /etc/nginx/sites-available/streamnews.danielcraft.fr.bootstrap 2>/dev/null || true
      # Ne pas ecraser le vhost certbot : juste tester / reload
    fi
  fi
  sudo nginx -t && sudo systemctl reload nginx
  echo "nginx reloaded"
fi

if [[ "$failed" -ne 0 ]]; then
  echo "==> Fleet deploy termine AVEC ERREURS"
  exit 1
fi
echo "==> Fleet deploy OK"
