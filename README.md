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
git clone https://github.com/danielcraft57/StreamNews.git /opt/streamnews
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

- **Tests** (`.github/workflows/ci.yml`) : sur push/PR `main` - unitaires + integration + e2e
- **Mise en ligne** (`.github/workflows/deploy.yml`) : **apres Tests verts** - SSH bastion (`DEPLOY_HOST`) → flotte LAN

Pas de double run : la mise en ligne attend juste le resultat des Tests.

Secrets / variables (Settings → Actions) — **bastion SSH = `DEPLOY_HOST`** (chez nous node9 / `raspberry-9`), pas node7 :

| Type | Name | Exemple |
|------|------|---------|
| Variable | `ENABLE_DEPLOY` | `true` |
| Variable | `FLEET_HOSTS` | `node6.lan node7.lan node8.lan` |
| Variable | `FLEET_USER` | `pi` |
| Secret | `DEPLOY_HOST` | IP publique (ou hostname SSH) du **bastion** qui joignable la flotte LAN — **sans** `https://` |
| Secret | `DEPLOY_USER` | `pi` |
| Secret | `DEPLOY_SSH_KEY` | cle privee SSH |
| Secret | `DEPLOY_PATH` | `/opt/streamnews` |

Le bastion CD n'est pas forcement l'edge nginx public (ex: node12 pour `streamnews.danielcraft.fr`).

Deploy demarre seulement apres une CI `success` sur `main` (plus de 2e e2e).

Repo : https://github.com/danielcraft57/StreamNews

## Services systemd

- `streamnews-web`
- `streamnews-analyzer`
- `streamnews-worker`

```bash
sudo systemctl status streamnews-web
sudo journalctl -u streamnews-analyzer -f
```

## Homelab multi-Pi

Voir [deploy/HOMELAB.md](deploy/HOMELAB.md).

| Noeud | Role |
|-------|------|
| **node6** | Postgres + Redis |
| **node7** | web + analyzer (pas de worker) |
| **node8+** | workers Celery (crawl / ingest) |

## Licence

MIT
