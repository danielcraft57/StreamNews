#!/usr/bin/env bash
# Setup noeud APP (web + analyzer UNIQUEMENT, pas de worker) - ex: node7.lan
# Usage:
#   sudo DATA_HOST=node6.lan bash deploy/setup-app-node.sh
set -euo pipefail

APP_DIR="${DEPLOY_PATH:-/opt/streamnews}"
APP_USER="${DEPLOY_APP_USER:-streamnews}"
REPO_URL="${REPO_URL:-https://github.com/loupix57/StreamNews.git}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-feature/native-cicd-vps}"
DATA_HOST="${DATA_HOST:-node6.lan}"
PG_PASSWORD="${POSTGRES_PASSWORD:-streamnews123}"

echo "==> Setup APP node (UI+API only) -> $APP_DIR (data=$DATA_HOST)"

apt-get update
apt-get install -y python3 python3-venv python3-pip git curl

if ! command -v node &>/dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
  apt-get install -y nodejs
fi

if [[ ! -d "$APP_DIR/.git" ]]; then
  mkdir -p "$(dirname "$APP_DIR")"
  git clone --branch "$DEPLOY_BRANCH" "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" fetch origin
  git -C "$APP_DIR" checkout "$DEPLOY_BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$DEPLOY_BRANCH"
fi

if ! id "$APP_USER" &>/dev/null; then
  useradd --system --home-dir "$APP_DIR" --shell /bin/bash "$APP_USER"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
mkdir -p "$APP_DIR/logs"
chown "$APP_USER:$APP_USER" "$APP_DIR/logs"

LOCAL_IP="$(hostname -I | awk '{print $1}')"

cat > "$APP_DIR/.env" <<EOF
POSTGRES_DB=streamnews
POSTGRES_USER=streamnews
POSTGRES_PASSWORD=$PG_PASSWORD
DATABASE_URL=postgresql://streamnews:${PG_PASSWORD}@${DATA_HOST}:5432/streamnews
REDIS_URL=redis://${DATA_HOST}:6379/0
WEB_URL=http://${LOCAL_IP}:3000
ANALYZER_URL=http://127.0.0.1:8000
PORT=3000
NODE_ENV=production
STREAMNEWS_ROLE=app
EOF
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"

sudo -u "$APP_USER" bash -lc "cd $APP_DIR && bash scripts/install.sh && bash scripts/init-db.sh"

cp "$APP_DIR/deploy/streamnews-web.service" /etc/systemd/system/
cp "$APP_DIR/deploy/streamnews-analyzer.service" /etc/systemd/system/

if [[ "$APP_DIR" != "/opt/streamnews" ]]; then
  sed -i "s|/opt/streamnews|$APP_DIR|g" /etc/systemd/system/streamnews-*.service
fi

# Pas de worker sur le noeud app (UI reste fluide)
systemctl disable --now streamnews-worker 2>/dev/null || true
rm -f /etc/systemd/system/streamnews-worker.service

systemctl daemon-reload
systemctl enable --now streamnews-analyzer streamnews-web

cat > /etc/sudoers.d/streamnews-deploy <<EOF
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl daemon-reload
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart streamnews-analyzer
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart streamnews-web
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl status streamnews-analyzer
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl status streamnews-web
EOF
chmod 440 /etc/sudoers.d/streamnews-deploy

echo "==> APP node pret (sans worker). UI: http://${LOCAL_IP}:3000"
echo "    Workers: sudo DATA_HOST=$DATA_HOST WEB_HOST=$(hostname -s).lan bash deploy/setup-worker-node.sh"
