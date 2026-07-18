# StreamNews - notes pour les agents

Analyseur de flux RSS. Crawl un site, detecte les feeds RSS/Atom, stream la progression via WebSocket.

## Architecture

```
UI (web:3000) --HTTP--> Analyzer FastAPI:8000 --Celery/Redis--> Worker
              <--WS--   Worker --POST /api/websocket--> Web (broadcast)
                            |
                       PostgreSQL
```

| Dossier | Role |
|---------|------|
| `web/` | Express + UI statique + WebSocket |
| `analyzer/` | FastAPI, crawl RSS, taches Celery (`celery_worker.py`) |
| `scripts/` | install / init-db / dev local |
| `deploy/` | systemd + setup VPS + deploy.sh |
| `.github/workflows/` | CI + deploy SSH |

Pas de Docker. Postgres et Redis tournent sur la machine hote.

## Modes de lancement

**Local :**
```bash
cp .env.example .env
bash scripts/install.sh
bash scripts/init-db.sh
bash scripts/dev.sh
```

**VPS (premiere fois) :**
```bash
sudo bash deploy/setup-vps.sh
```

**VPS (deploys suivants) :** push sur `main` -> GitHub Actions -> `deploy/deploy.sh`

## Variables d'environnement

Voir `.env.example`.

| Variable | Qui l'utilise | Defaut |
|----------|---------------|--------|
| `DATABASE_URL` | analyzer | `postgresql://streamnews:streamnews123@localhost:5432/streamnews` |
| `REDIS_URL` | analyzer / celery | `redis://localhost:6379/0` |
| `WEB_URL` | celery (push WS) | `http://localhost:3000` |
| `ANALYZER_URL` | web (proxy API) | `http://localhost:8000` |
| `PORT` | web | `3000` |

Sur le VPS, `.env` est hors git (`/opt/streamnews/.env`), charge via `EnvironmentFile=` dans systemd.

## Secrets GitHub Actions

`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PATH`

## Etat du projet

Prototype. Fonctionne en grande partie, mais :

- Pas d'auth / rate limit / HTTPS
- Table `pages` prevue mais peu/pas remplie pendant le crawl
- `cleanup_old_analyses` encore un stub
- Redis = broker Celery seulement
- Scripts `build`/`test` dans `web/package.json` sans config derriere

## Pieges a eviter

1. Celery se lance depuis `analyzer/` : `celery -A celery_worker worker`
2. `asyncpg` est requis par `database.py`
3. Ne pas reintroduire Docker sans raison
4. Ne pas committer `.env`

## Style du repo

- Explications simples, francais OK pour la doc
- Pas de refactors massifs hors sujet
- Corriger boot / deps / env avant d'ajouter des features
