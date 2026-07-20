#!/usr/bin/env bash
# Cree/repare l'utilisateur streamnews + sudoers deploy (idempotent).
# Usage (en root/sudo), selon le role du noeud :
#   sudo bash deploy/ensure-app-user.sh data
#   sudo bash deploy/ensure-app-user.sh app
#   sudo bash deploy/ensure-app-user.sh worker
#
# Ne touche PAS a Postgres/Redis ni au code : juste user, droits, sudoers.
set -euo pipefail

ROLE="${1:-}"
APP_DIR="${DEPLOY_PATH:-/opt/streamnews}"
APP_USER="${DEPLOY_APP_USER:-streamnews}"

if [[ -z "$ROLE" || ! "$ROLE" =~ ^(data|app|worker)$ ]]; then
  echo "Usage: sudo bash deploy/ensure-app-user.sh {data|app|worker}"
  exit 1
fi

echo "==> ensure user=$APP_USER dir=$APP_DIR role=$ROLE"

if ! id "$APP_USER" &>/dev/null; then
  useradd --system --home-dir "$APP_DIR" --shell /bin/bash "$APP_USER"
  echo "    user cree"
else
  echo "    user existe"
fi

if [[ -d "$APP_DIR" ]]; then
  mkdir -p "$APP_DIR/logs"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
  echo "    chown $APP_DIR"
else
  echo "WARN: $APP_DIR absent (clone le repo avant)"
fi

# Corrige ROLE dans .env si present
if [[ -f "$APP_DIR/.env" ]]; then
  if grep -q '^STREAMNEWS_ROLE=' "$APP_DIR/.env"; then
    sed -i "s|^STREAMNEWS_ROLE=.*|STREAMNEWS_ROLE=$ROLE|" "$APP_DIR/.env"
  else
    echo "STREAMNEWS_ROLE=$ROLE" >> "$APP_DIR/.env"
  fi
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
  echo "    STREAMNEWS_ROLE=$ROLE"
fi

SUDOERS=/etc/sudoers.d/streamnews-deploy
case "$ROLE" in
  data)
    # data n'a pas besoin de systemctl app ; fichier minimal (git via pi)
    cat > "$SUDOERS" <<EOF
# StreamNews data node - pas de services app
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl daemon-reload
EOF
    ;;
  app)
    cat > "$SUDOERS" <<EOF
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl daemon-reload
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart streamnews-analyzer
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart streamnews-web
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl status streamnews-analyzer
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl status streamnews-web
EOF
    ;;
  worker)
    cat > "$SUDOERS" <<EOF
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl daemon-reload
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart streamnews-worker
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl status streamnews-worker
EOF
    ;;
esac
chmod 440 "$SUDOERS"
visudo -cf "$SUDOERS"
echo "==> OK ($SUDOERS)"
