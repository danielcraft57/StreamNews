#!/usr/bin/env bash
# Setup noeud WORKER Celery seulement (crawl / traitement RSS).
# Usage:
#   sudo DATA_HOST=node6.lan WEB_HOST=node7.lan bash deploy/setup-worker-node.sh
#
# Tu peux lancer ca sur node8, node9, etc. pour paralleler les analyses.
set -euo pipefail

APP_DIR="${DEPLOY_PATH:-/opt/streamnews}"
APP_USER="${DEPLOY_APP_USER:-streamnews}"
REPO_URL="${REPO_URL:-https://github.com/loupix57/StreamNews.git}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-feature/native-cicd-vps}"
DATA_HOST="${DATA_HOST:-node6.lan}"
WEB_HOST="${WEB_HOST:-node7.lan}"
PG_PASSWORD="${POSTGRES_PASSWORD:-streamnews123}"
CONCURRENCY="${CELERY_CONCURRENCY:-1}"

echo "==> Setup WORKER node StreamNews -> $APP_DIR"
echo "    Redis/PG: $DATA_HOST | WebSocket push: $WEB_HOST"

apt-get update
apt-get install -y python3 python3-venv python3-pip git

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

cat > "$APP_DIR/.env" <<EOF
DATABASE_URL=postgresql://streamnews:${PG_PASSWORD}@${DATA_HOST}:5432/streamnews
REDIS_URL=redis://${DATA_HOST}:6379/0
WEB_URL=http://${WEB_HOST}:3000
NODE_ENV=production
STREAMNEWS_ROLE=worker
CELERY_CONCURRENCY=$CONCURRENCY
EOF
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"

sudo -u "$APP_USER" bash -lc "
  cd $APP_DIR
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -q -r analyzer/requirements.txt
"

# Unit worker avec concurrency configurable
cat > /etc/systemd/system/streamnews-worker.service <<EOF
[Unit]
Description=StreamNews Celery Worker
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR/analyzer
EnvironmentFile=$APP_DIR/.env
Environment=PATH=$APP_DIR/.venv/bin:/usr/bin
ExecStart=$APP_DIR/.venv/bin/python -m celery -A celery_worker worker --loglevel=info --concurrency=${CONCURRENCY} -Q crawl,ingest,default
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now streamnews-worker

cat > /etc/sudoers.d/streamnews-deploy <<EOF
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl daemon-reload
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart streamnews-worker
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl status streamnews-worker
EOF
chmod 440 /etc/sudoers.d/streamnews-deploy

echo "==> WORKER pret sur $(hostname). Il consomme la queue Redis de $DATA_HOST."
