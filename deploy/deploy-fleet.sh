#!/usr/bin/env bash
# Deploy multi-noeuds depuis un bastion (node12) joignable par GitHub Actions.
# Usage (sur node12) :
#   bash deploy/deploy-fleet.sh
#
# Variables optionnelles :
#   FLEET_HOSTS="node6.lan node7.lan node8.lan"
#   FLEET_USER=pi
#   DEPLOY_PATH=/opt/streamnews
set -euo pipefail

FLEET_USER="${FLEET_USER:-pi}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/streamnews}"
# data -> app -> workers (ordre stable)
FLEET_HOSTS="${FLEET_HOSTS:-node6.lan node7.lan node8.lan}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "==> Fleet deploy depuis $(hostname -s) -> $FLEET_HOSTS"

failed=0
for host in $FLEET_HOSTS; do
  echo ""
  echo "---------- $host ----------"
  if ! ssh -o BatchMode=yes -o ConnectTimeout=15 \
    -o StrictHostKeyChecking=accept-new \
    "${FLEET_USER}@${host}" \
    "cd '${DEPLOY_PATH}' && bash deploy/deploy.sh"; then
    echo "ERREUR: deploy failed on $host"
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
