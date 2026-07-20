# StreamNews

**Version 0.2.0**

Analyseur de flux RSS. Crawl un site, detecte les feeds RSS/Atom, suit la progression en temps reel via WebSocket.

## Stack

| Piece | Role |
|-------|------|
| `web/` | Express + UI + WebSocket (port 3000) |
| `analyzer/` | FastAPI + crawl RSS + Celery (port 8000) |
| DB | **Postgres** (prod / CI) ou **SQLite** (dev local) |
| Redis | Broker Celery (homelab node6, ou node13 en local) |

Pas de Docker.

## Prerequis

- Python 3.11+, Node.js 18+
- Redis accessible (local ou LAN)
- Postgres 15+ **seulement** en mode prod / CI (le mode local utilise SQLite)

## Installation locale

Deux modes (fichiers d'env **non** versionnes) :

| Mode | Fichier | DB | Redis |
|------|---------|-----|-------|
| **Local** | `.env.local` | SQLite (`data/streamnews.db`) | ex. `node13.lan` |
| **Prod-like** | `.env` | Postgres | localhost ou homelab |

```bash
bash scripts/install.sh

# Local (SQLite + Redis distant)
cp .env.local.example .env.local   # si pas deja cree par install.sh
# adapte REDIS_URL si besoin
bash scripts/init-db.sh --local
bash scripts/dev.sh --local

# Postgres local
cp .env.example .env
# Remplace TOUS les CHANGE_ME, cree user/db Postgres
bash scripts/init-db.sh
bash scripts/dev.sh
```

UI : http://localhost:3000

Modeles versionnes (sans secrets) : `.env.example`, `.env.local.example`.

### Scripts

| Script | Role |
|--------|------|
| `scripts/install.sh` | venv + deps Python/Node + cree les .env d'exemple |
| `scripts/load-env.sh` | charge `.env.local` (`--local`) ou `.env` |
| `scripts/init-db.sh` | cree le schema (`--local`, `--reset`) |
| `scripts/dev.sh` | lance analyzer + worker + web |
| `scripts/e2e-stack.sh` | stack pour Playwright (CI / Postgres local) |

## Variables d'environnement

| Variable | Role |
|----------|------|
| `STREAMNEWS_ENV` | `local` ou `production` |
| `DATABASE_URL` | `postgresql://…` ou `sqlite:///./data/streamnews.db` |
| `REDIS_URL` | Broker Celery |
| `WEB_URL` | URL web (push WebSocket depuis workers) |
| `ANALYZER_URL` | API analyzer (proxy cote web) |
| `STREAMNEWS_ROLE` | `all` / `data` / `app` / `worker` |
| `PORT` | Port web (defaut 3000) |
| `POSTGRES_PASSWORD` | Obligatoire sur les scripts `deploy/setup-*.sh` |

## Secrets (important)

Ne committe **jamais** :

- `.env`, `.env.local`
- `data/*.db` (et fichiers `-wal` / `-shm`)
- cles SSH, certificats, mots de passe reels

Les setups homelab / VPS exigent `POSTGRES_PASSWORD=…` en argument : plus de defaut `streamnews123` en prod.

Le mot de passe `streamnews123` n'existe que dans la **CI GitHub** (Postgres ephemere) et `scripts/e2e-stack.sh`.

## Architecture analyzer

Voir [analyzer/ARCHITECTURE.md](analyzer/ARCHITECTURE.md) (services, queues, SQLite/Postgres).

## Homelab multi-Pi

Detail : [deploy/HOMELAB.md](deploy/HOMELAB.md) — index deploy : [deploy/README.md](deploy/README.md).

| Noeud | Role |
|-------|------|
| **node6** | Postgres + Redis (`data`) |
| **node7** | web + analyzer (`app`, pas de worker) |
| **node8+** | workers Celery |
| **node9** | bastion SSH (CD) |
| **node12** | edge nginx / TLS public |
| **node13** | Redis pour le mode local PC |

## Deploy VPS all-in-one

```bash
git clone https://github.com/danielcraft57/StreamNews.git /opt/streamnews
cd /opt/streamnews
sudo POSTGRES_PASSWORD='ton-mot-de-passe-fort' bash deploy/setup-vps.sh
```

Adapte ensuite `/opt/streamnews/.env` si besoin.

## Tests

```bash
cd analyzer && pip install -r requirements.txt -r requirements-dev.txt && pytest -q
cd web && npm ci && npm test

# E2E (Postgres + Redis locaux requis)
bash scripts/e2e-stack.sh
cd e2e && npm install && npx playwright install chromium && npm test
```

## CI/CD (GitHub Actions)

- **Tests** : push/PR `main`
- **Mise en ligne** : apres Tests OK → SSH bastion (`DEPLOY_HOST`) → flotte LAN en parallele

| Type | Name | Exemple |
|------|------|---------|
| Variable | `ENABLE_DEPLOY` | `true` |
| Variable | `FLEET_HOSTS` | `node6.lan node7.lan node8.lan` |
| Variable | `FLEET_USER` | `pi` |
| Secret | `DEPLOY_HOST` | IP/hostname du **bastion** (ex. node9), sans `https://` |
| Secret | `DEPLOY_USER` | `pi` |
| Secret | `DEPLOY_SSH_KEY` | cle privee SSH |
| Secret | `DEPLOY_PATH` | `/opt/streamnews` |

## Services systemd

`streamnews-web`, `streamnews-analyzer`, `streamnews-worker`

```bash
sudo systemctl status streamnews-web
sudo journalctl -u streamnews-analyzer -f
```

## Licence

MIT
