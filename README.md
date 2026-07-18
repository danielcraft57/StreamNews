# StreamNews

Analyseur de flux RSS. Crawl un site, detecte les feeds RSS/Atom, suit la progression en temps reel via WebSocket.

## Stack

- **web/** - Express + UI + WebSocket (port 3000)
- **analyzer/** - FastAPI + crawl RSS + taches Celery (port 8000)
- **PostgreSQL** + **Redis** (installes sur la machine, pas de Docker)

## Prerequis

- Python 3.11+
- Node.js 18+
- PostgreSQL 15+
- Redis 7+

## Installation locale

```bash
cp .env.example .env
# Adapte DATABASE_URL / REDIS_URL si besoin

# Cree user + DB Postgres (exemple)
# createuser streamnews
# createdb -O streamnews streamnews

bash scripts/install.sh
bash scripts/init-db.sh
bash scripts/dev.sh
```

UI : http://localhost:3000

## Variables d'environnement

Voir `.env.example`. Les principales :

| Variable | Role |
|----------|------|
| `DATABASE_URL` | Connexion Postgres |
| `REDIS_URL` | Broker Celery |
| `WEB_URL` | URL du web (push WebSocket depuis le worker) |
| `ANALYZER_URL` | URL de l'API analyzer (proxy cote web) |
| `PORT` | Port du service web (defaut 3000) |

## Deploy VPS (premiere fois)

Sur le serveur (Ubuntu/Debian), en root :

```bash
git clone https://github.com/loupix57/StreamNews.git /opt/streamnews
cd /opt/streamnews
bash deploy/setup-vps.sh
```

Le script installe Postgres, Redis, Node, cree l'utilisateur `streamnews`, les unites systemd, et demarre les services.

Adapte `/opt/streamnews/.env` (mots de passe, etc.).

Le user SSH de deploy doit pouvoir faire `sudo systemctl restart streamnews-*` sans mot de passe (sudoers).

## Tests

```bash
# Unitaires Python
cd analyzer
pip install -r requirements.txt -r requirements-dev.txt
pytest -q

# Unitaires Node
cd web
npm ci
npm test

# E2E Playwright (Postgres + Redis doivent tourner)
bash scripts/e2e-stack.sh
cd e2e && npm install && npx playwright install chromium && npm test
```

La CI GitHub Actions lance unitaires + e2e (services Postgres/Redis, stack complete, Chromium).

## CI/CD (GitHub Actions)

- **CI** (`.github/workflows/ci.yml`) : sur push/PR `main` - install Python/Node + smoke checks
- **Deploy** (`.github/workflows/deploy.yml`) : sur push `main` - CI puis SSH + `deploy/deploy.sh`

Secrets a creer dans le repo GitHub (Settings > Secrets and variables > Actions) :

| Secret | Exemple |
|--------|---------|
| `DEPLOY_HOST` | `203.0.113.10` |
| `DEPLOY_USER` | `streamnews` ou un user avec sudo |
| `DEPLOY_SSH_KEY` | cle privee SSH |
| `DEPLOY_PATH` | `/opt/streamnews` |

Sans ces secrets, configure aussi la variable repo `ENABLE_DEPLOY=true` (Settings > Variables) pour activer le job Deploy. Tant que ce n'est pas fait, seul le CI tests tourne.

Repo : https://github.com/loupix57/StreamNews

## Services systemd

- `streamnews-web`
- `streamnews-analyzer`
- `streamnews-worker`

```bash
sudo systemctl status streamnews-web
sudo journalctl -u streamnews-analyzer -f
```

## Suite possible

- Reverse proxy HTTPS (nginx/Caddy)
- Auth / rate limiting
- Vrais tests automatises

## Licence

MIT
