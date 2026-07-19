#!/usr/bin/env bash
# Setup initial du VPS (a lancer UNE fois en root ou avec sudo).
# Usage: sudo bash deploy/setup-vps.sh
set -euo pipefail

APP_DIR="${DEPLOY_PATH:-/opt/streamnews}"
APP_USER="${DEPLOY_APP_USER:-streamnews}"
REPO_URL="${REPO_URL:-https://github.com/loupix57/StreamNews.git}"

echo "==> Setup VPS StreamNews -> $APP_DIR (user $APP_USER)"

apt-get update
apt-get install -y \
  python3 python3-venv python3-pip postgresql postgresql-contrib redis-server git curl \
  build-essential python3-dev \
  libxml2-dev libxslt1-dev zlib1g-dev

if ! command -v node &>/dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
  apt-get install -y nodejs
fi

systemctl enable --now postgresql redis-server

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='streamnews'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE USER streamnews WITH PASSWORD 'streamnews123';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='streamnews'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE DATABASE streamnews OWNER streamnews;"

if [[ ! -d "$APP_DIR/.git" ]]; then
  mkdir -p "$(dirname "$APP_DIR")"
  git clone "$REPO_URL" "$APP_DIR"
fi

if ! id "$APP_USER" &>/dev/null; then
  useradd --system --home-dir "$APP_DIR" --shell /bin/bash "$APP_USER"
fi

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  sed -i 's|NODE_ENV=development|NODE_ENV=production|' "$APP_DIR/.env"
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
  echo "Fichier .env cree. Adapte les mots de passe si besoin."
fi

sudo -u "$APP_USER" bash -lc "cd $APP_DIR && bash scripts/install.sh && bash scripts/init-db.sh"

cp "$APP_DIR/deploy/streamnews-web.service" /etc/systemd/system/
cp "$APP_DIR/deploy/streamnews-analyzer.service" /etc/systemd/system/
cp "$APP_DIR/deploy/streamnews-worker.service" /etc/systemd/system/

# Adapter WorkingDirectory si DEPLOY_PATH != /opt/streamnews
if [[ "$APP_DIR" != "/opt/streamnews" ]]; then
  sed -i "s|/opt/streamnews|$APP_DIR|g" /etc/systemd/system/streamnews-*.service
fi

systemctl daemon-reload
systemctl enable --now streamnews-analyzer streamnews-worker streamnews-web

# Sudo sans mot de passe pour les restarts (deploy CI)
cat > /etc/sudoers.d/streamnews-deploy <<EOF
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl daemon-reload
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart streamnews-analyzer
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart streamnews-worker
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart streamnews-web
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl status streamnews-analyzer
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl status streamnews-worker
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl status streamnews-web
EOF
chmod 440 /etc/sudoers.d/streamnews-deploy

echo "==> Setup termine. UI sur le port 3000."
echo "Secrets GitHub a configurer: DEPLOY_HOST, DEPLOY_USER=$APP_USER, DEPLOY_SSH_KEY, DEPLOY_PATH=$APP_DIR"
