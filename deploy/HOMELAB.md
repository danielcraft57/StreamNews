# StreamNews sur homelab (Raspberry Pi)

## Idee

Celery permet de **repartir le crawl RSS** sur plusieurs Pi :

```
UI / API (node7)  -->  Redis queue (node6)  -->  Workers Celery (node7, node8, ...)
                         |
                    Postgres (node6)
```

- **1 analyse** = 1 tache Celery
- Plusieurs workers = plusieurs sites (ou pages) traites en parallele
- Tous ecrivent dans le meme Postgres et poussent les events WS vers le web (`WEB_URL`)

## Decoupage recommande (node6 + node7)

| Noeud | Role | Services |
|-------|------|----------|
| **node6.lan** | data | PostgreSQL + Redis |
| **node7.lan** | app | web :3000 + analyzer :8000 + 1 worker |
| node8+ (optionnel) | worker | Celery seulement |

node6 est deja prevu comme storage dans CryptoCluster : ca colle.

## Installation

Sur **node6** :
```bash
sudo LAN_CIDR=192.168.1.0/24 bash deploy/setup-data-node.sh
```

Sur **node7** :
```bash
sudo DATA_HOST=node6.lan bash deploy/setup-app-node.sh
```

UI : `http://node7.lan:3000` (ou l'IP de node7).

### Ajouter un worker sur un autre Pi (ex: node8)

```bash
sudo DATA_HOST=node6.lan WEB_HOST=node7.lan bash deploy/setup-worker-node.sh
```

Tu peux repeter sur node8, node12, etc. Chaque worker tape la meme queue Redis.

## Variables cles

Sur les noeuds app/worker, `.env` doit pointer vers node6 :

```bash
DATABASE_URL=postgresql://streamnews:CHANGEME@node6.lan:5432/streamnews
REDIS_URL=redis://node6.lan:6379/0
WEB_URL=http://node7.lan:3000
STREAMNEWS_ROLE=app   # ou worker
```

## Limites Pi 2 / Pi 3

- Pi 2 (~1 Go) : **ne mets pas** Postgres+Redis+app+plusieurs crawls sur la meme machine.
- Concurrency Celery : garde `--concurrency=1` sur Pi 2 (defaut des scripts).
- Un crawl agressif (200 pages) reste lourd : mieux vaut plusieurs workers que plus de concurrency sur un seul Pi.

## Deploy CI

Pour l'instant le workflow Deploy SSH cible **un** `DEPLOY_HOST`. Options :

1. Deploy manuel sur chaque noeud : `bash deploy/deploy.sh`
2. Plus tard : matrice GitHub Actions (app + workers) avec plusieurs secrets

Variable `ENABLE_DEPLOY=true` + secrets `DEPLOY_*` inchanges pour le noeud app (node7).
