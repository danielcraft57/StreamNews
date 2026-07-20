#!/usr/bin/env bash
# Setup noeud DATA (Postgres + Redis) - ex: node6.lan
# Usage: sudo bash deploy/setup-data-node.sh
set -euo pipefail

APP_DIR="${DEPLOY_PATH:-/opt/streamnews}"
APP_USER="${DEPLOY_APP_USER:-streamnews}"
REPO_URL="${REPO_URL:-https://github.com/loupix57/StreamNews.git}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
PG_PASSWORD="${POSTGRES_PASSWORD:-streamnews123}"
# Reseau LAN autorise a joindre Postgres/Redis (adapte si besoin)
LAN_CIDR="${LAN_CIDR:-192.168.1.0/24}"

echo "==> Setup DATA node StreamNews -> $APP_DIR"
echo "    LAN autorise: $LAN_CIDR"

apt-get update
apt-get install -y postgresql postgresql-contrib redis-server git python3 python3-venv python3-pip

systemctl enable --now postgresql redis-server

# --- PostgreSQL : ecoute LAN ---
PG_CONF="$(ls /etc/postgresql/*/main/postgresql.conf | head -1)"
PG_HBA="$(ls /etc/postgresql/*/main/pg_hba.conf | head -1)"
sed -i "s/^#\\?listen_addresses.*/listen_addresses = '*'/" "$PG_CONF"
if ! grep -q "streamnews-lan" "$PG_HBA"; then
  echo "# streamnews-lan" >> "$PG_HBA"
  echo "host    streamnews    streamnews    $LAN_CIDR    md5" >> "$PG_HBA"
fi
systemctl restart postgresql

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='streamnews'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE USER streamnews WITH PASSWORD '$PG_PASSWORD';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='streamnews'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE DATABASE streamnews OWNER streamnews;"

# --- Redis : ecoute LAN ---
if grep -qE '^bind ' /etc/redis/redis.conf; then
  sed -i 's/^bind .*/bind 0.0.0.0/' /etc/redis/redis.conf
else
  echo 'bind 0.0.0.0' >> /etc/redis/redis.conf
fi
sed -i 's/^protected-mode yes/protected-mode no/' /etc/redis/redis.conf || true
systemctl restart redis-server

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

if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  # Sur le noeud data, URLs locales
  sed -i 's|NODE_ENV=development|NODE_ENV=production|' "$APP_DIR/.env"
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
fi

# Init schema depuis ce noeud (localhost)
sudo -u "$APP_USER" bash -lc "
  cd $APP_DIR
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -q -r analyzer/requirements.txt
  export DATABASE_URL=postgresql://streamnews:${PG_PASSWORD}@localhost:5432/streamnews
  bash scripts/init-db.sh
"

echo "==> DATA node pret."
HOST_IP="$(hostname -I | awk '{print $1}')"
echo "    DATABASE_URL=postgresql://streamnews:***@${HOST_IP}:5432/streamnews"
echo "    REDIS_URL=redis://${HOST_IP}:6379/0"
echo "    Prochaine etape: setup-app-node.sh sur node7 (et setup-worker-node.sh sur d'autres Pi)"
