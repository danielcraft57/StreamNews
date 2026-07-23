# StreamNews

**Version 0.5.1**

Console de veille RSS : crawl un site, detecte les feeds, suit l'avancement en live (WebSocket), puis analyse le corpus pour **tendances**, **radar d'idees**, **watchlist**, **briefs** et **fiches opportunite**.

## Stack

| Piece | Role |
|-------|------|
| `web/` | Express + console UI + WebSocket (port 3000) |
| `analyzer/` | FastAPI + crawl/ingest RSS + Celery (port 8000) |
| DB | **Postgres** (prod / CI) ou **SQLite** (dev local) |
| Redis | Broker Celery (homelab data, ou Redis distant en local) |

Pas de Docker.

## Fonctionnalites (0.5)

| Zone | Contenu |
|------|---------|
| **Feed / Sources / Jobs** | Lecture, favoris, ajout de source, suivi crawl / enrich / NLP |
| **Tendances** | Top mots-cles / entites / YAKE, fenetre 7–90 j, filtre par **collection** |
| **Radar idees** | Signaux SaaS/IT (intents + themes), score decompose, pack RSS, fiches |
| **Watchlist** | Mots-cles suivis + alertes de volume |
| **Brief** | Quotidien (auto / cron) et hebdo |
| **Collections** | Groupes thematiques de sources → filtre Radar / Tendances |
| **Fiches idee** | Notes + export Markdown / Notion / Linear (liens prefill) |
| **Poll RSS** | Celery beat recharge les flux (`FEED_REFRESH_MINUTES`, defaut 15) |

## Prerequis

- Python 3.11+, Node.js 18+
- Redis accessible
- Postgres 15+ pour prod / CI (le mode local utilise SQLite)

## Installation locale

Deux modes (fichiers d'env **non** versionnes) :

| Mode | Fichier | DB | Redis |
|------|---------|-----|-------|
| **Local** | `.env.local` | SQLite (`data/streamnews.db`) | `node14.lan` (exemple) |
| **Prod / prod-like** | `.env` | Postgres | localhost ou `node6.lan` |

### Windows (PowerShell)

```powershell
.\scripts\install.ps1
.\scripts\init-db.ps1 -Local
.\scripts\dev.ps1 -Local
```

Hot reload par defaut : analyzer (`uvicorn --reload`), web (`nodemon`), worker Celery (`watchdog`).
Sous Windows, Celery tourne avec `--pool=solo` (obligatoire).

Pour le poll RSS / brief auto en local, lance aussi le **beat** (cwd `analyzer/`) :

```powershell
.\.venv\Scripts\python.exe -m celery -A celery_worker beat --loglevel=info
```

### Linux / macOS (bash)

```bash
bash scripts/install.sh
bash scripts/init-db.sh --local
bash scripts/dev.sh --local
# optionnel : celery -A celery_worker beat --loglevel=info  (depuis analyzer/)
```

### Prod-like (Postgres)

```bash
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
| `scripts/install.ps1` / `install.sh` | venv + deps Python/Node + cree les .env d'exemple |
| `scripts/init-db.ps1` / `init-db.sh` | schema Alembic (`-Local` / `--local`, `-Reset` / `--reset`) |
| `scripts/dev.ps1` / `dev.sh` | analyzer + worker + web |
| `scripts/e2e-stack.sh` | stack Playwright (CI / Postgres local) |
| `scripts/clean-local.ps1` / `clean-local.sh` | caches + logs + SQLite locale |

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
| `FEED_REFRESH_MINUTES` | Intervalle poll RSS via beat (defaut 15, min 5) |
| `POSTGRES_PASSWORD` | Obligatoire sur les scripts `deploy/setup-*.sh` |

## Secrets (important)

Ne committe **jamais** :

- `.env`, `.env.local`
- `data/*.db` (et fichiers `-wal` / `-shm`)
- cles SSH, certificats, mots de passe reels

Les setups homelab / VPS exigent `POSTGRES_PASSWORD=…` en argument.

Le mot de passe `streamnews123` n'existe que dans la **CI GitHub** (Postgres ephemere) et comme defaut de `scripts/e2e-stack.sh`.

## Architecture

- Analyzer : [analyzer/ARCHITECTURE.md](analyzer/ARCHITECTURE.md) (services, queues, SQLite/Postgres)
- Frontend : [web/ARCHITECTURE.md](web/ARCHITECTURE.md) (modules `js/`, Material Web)
- Homelab : [deploy/HOMELAB.md](deploy/HOMELAB.md) — index deploy : [deploy/README.md](deploy/README.md)

| Noeud (exemple) | Role |
|-----------------|------|
| **node6** | Postgres + Redis (`data`) |
| **node7** | web + analyzer (`app`, pas de worker) |
| **node8+** | workers Celery + **un** beat |
| **node9** | bastion SSH (CD, secret `DEPLOY_HOST`) |
| **node12** | edge nginx / TLS public |
| **node14** | Redis pour le mode local PC (SQLite) |

## Deploy VPS all-in-one

```bash
git clone https://github.com/danielcraft57/StreamNews.git /opt/streamnews
cd /opt/streamnews
sudo POSTGRES_PASSWORD='ton-mot-de-passe-fort' bash deploy/setup-vps.sh
```

## Tests

```bash
cd analyzer && pip install -r requirements.txt -r requirements-dev.txt
pytest -q -m "not integration"   # unit
pytest -q -m integration         # Postgres (DATABASE_URL)

cd web && npm ci && npm test

# E2E (Postgres + Redis locaux requis)
bash scripts/e2e-stack.sh
cd e2e && npm install && npx playwright install chromium && npm test
```

## CI/CD (GitHub Actions)

- **Tests** : push/PR `main` (pytest unit + integration, npm, Playwright)
- **Mise en ligne** : apres Tests OK → SSH bastion (`DEPLOY_HOST`) → flotte LAN

| Type | Name | Exemple |
|------|------|---------|
| Variable | `ENABLE_DEPLOY` | `true` |
| Variable | `FLEET_HOSTS` | `node6.lan node7.lan node8.lan` |
| Variable | `FLEET_USER` | `pi` |
| Secret | `DEPLOY_HOST` | bastion (ex. node9), sans `https://` |
| Secret | `DEPLOY_USER` | `pi` |
| Secret | `DEPLOY_SSH_KEY` | cle privee SSH |
| Secret | `DEPLOY_PATH` | `/opt/streamnews` |

## Services systemd

`streamnews-web`, `streamnews-analyzer`, `streamnews-worker`, `streamnews-beat`

```bash
sudo systemctl status streamnews-web streamnews-beat
sudo journalctl -u streamnews-analyzer -f
```

## Licence

MIT
