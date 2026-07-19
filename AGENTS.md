# StreamNews - notes pour les agents

Analyseur de flux RSS. Crawl un site, detecte les feeds RSS/Atom, stream la progression via WebSocket.

## Architecture

```
UI (web:3000) --HTTP--> Analyzer FastAPI:8000 --Celery/Redis--> Workers
              <--WS--   Workers --POST /api/websocket--> Web (broadcast)
                            |
                       PostgreSQL
```

| Dossier | Role |
|---------|------|
| `web/` | Express + UI + WebSocket |
| `analyzer/` | FastAPI + taches Celery |
| `scripts/` | install / init-db / dev / e2e-stack |
| `deploy/` | systemd + setup multi-Pi |
| `e2e/` | Playwright |
| `.github/workflows/` | CI + deploy SSH |

Pas de Docker.

## Homelab (IMPORTANT)

Decoupage fixe sur le cluster :

| Noeud | Role | Services |
|-------|------|----------|
| **node6.lan** | `data` | PostgreSQL + Redis uniquement |
| **node7.lan** | `app` | web + analyzer **sans worker** (UI fluide) |
| **node8.lan** (+ autres) | `worker` | Celery queues `crawl,ingest,default` |

Pipeline : crawl (pages paralleles) -> fan-out ingest feeds -> finalize.
Voir `analyzer/ARCHITECTURE.md`.

Setup :
```bash
# node6
sudo bash deploy/setup-data-node.sh
# node7
sudo DATA_HOST=node6.lan bash deploy/setup-app-node.sh
# node8
sudo DATA_HOST=node6.lan WEB_HOST=node7.lan bash deploy/setup-worker-node.sh
```

Branche de deploy actuelle : `feature/native-cicd-vps` (`DEPLOY_BRANCH`).

## Modes de lancement local

```bash
cp .env.example .env
bash scripts/install.sh && bash scripts/init-db.sh && bash scripts/dev.sh
```

## Variables d'environnement

Voir `.env.example`. Sur homelab, `.env` hors git dans `/opt/streamnews/.env`.

| Variable | Role |
|----------|------|
| `DATABASE_URL` | Postgres (souvent `node6.lan`) |
| `REDIS_URL` | Broker Celery (souvent `node6.lan`) |
| `WEB_URL` | Push WS depuis workers vers node7 |
| `ANALYZER_URL` | Proxy API cote web |
| `STREAMNEWS_ROLE` | `data` / `app` / `worker` / `all` |

## Secrets GitHub Actions

`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PATH` + var `ENABLE_DEPLOY=true`

## Pieges

1. Celery depuis `analyzer/` : `celery -A celery_worker worker`
2. Ne pas mettre de worker sur node7 (reserve UI/API)
3. Ne pas committer `.env`
4. Pi 2 : `CELERY_CONCURRENCY=1`
5. Logs : `tail -f /opt/streamnews/logs/worker.log` (ou `analyzer.log` / `web.log`)
6. Si le worker crash en boucle, regarder `logs/errors.log` (souvent import casse apres un mauvais deploy)
