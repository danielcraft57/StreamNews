# StreamNews - Homelab multi-Pi

Pas de Docker. Roles fixes sur le LAN.

## Roles

| Noeud (exemple) | Role | Services |
|-----------------|------|----------|
| **node6** | `data` | PostgreSQL + Redis |
| **node7** | `app` | web + analyzer (**sans** worker) |
| **node8+** | `worker` | Celery (`crawl`, `ingest`, `default`) + **beat** (un noeud : brief + poll RSS) |
| **node9** | bastion SSH | point d'entree CD (GitHub Actions) |
| **node12** | edge nginx | HTTPS public → proxy vers node7 |
| **node14** | Redis local-dev | broker pour le mode local PC (SQLite) |

```
Dev PC (SQLite + .env.local) ----Redis----> node14
                                    |
UI/API (node7) --> Redis+PG (node6) --> Workers (node8…)
       ^
       | proxy TLS
   edge (node12)
```

## Install prod

Les setups **refusent** de tourner sans `POSTGRES_PASSWORD` (mot de passe fort, meme valeur sur data/app/worker).

```bash
# node6 — data
sudo POSTGRES_PASSWORD='…' bash deploy/setup-data-node.sh

# node7 — UI + API
sudo DATA_HOST=node6.lan POSTGRES_PASSWORD='…' bash deploy/setup-app-node.sh

# node8 — worker
sudo DATA_HOST=node6.lan WEB_HOST=node7.lan POSTGRES_PASSWORD='…' \
  bash deploy/setup-worker-node.sh

# user/sudoers (repare si besoin, sans recreer Postgres)
sudo bash deploy/ensure-app-user.sh data   # sur node6
sudo bash deploy/ensure-app-user.sh app    # sur node7
sudo bash deploy/ensure-app-user.sh worker # sur node8
```

UI LAN : `http://node7.lan:3000`  
URL publique (si edge) : `deploy/nginx-streamnews.danielcraft.fr.conf` sur node12 + certbot.

Ne jamais committer `/opt/streamnews/.env`.

## Mode local (PC)

SQLite dans `data/` + Redis sur **node14** (fichier `.env.local`, isole de la prod).

**Windows :**
```powershell
.\scripts\install.ps1
.\scripts\init-db.ps1 -Local
.\scripts\dev.ps1 -Local
```

**Linux / macOS :**
```bash
bash scripts/install.sh
cp .env.local.example .env.local   # REDIS_URL=redis://node14.lan:6379/0
bash scripts/init-db.sh --local
bash scripts/dev.sh --local
```

## CD

GitHub Actions SSH vers le **bastion** (`DEPLOY_HOST`, ex. node9), puis `deploy/deploy-fleet.sh` deploie node6/7/8 en parallele.

Detail secrets : README → section CI/CD.

## Limites

- Pi 2 : `CELERY_CONCURRENCY=1`
- Celery beat : un seul noeud (sinon double brief / double poll RSS). Unit `streamnews-beat.service`
  - brief quotidien 06:00 UTC
  - **rechargement RSS** toutes les `FEED_REFRESH_MINUTES` (defaut **15** min)
- Redis ouvert sur le LAN sans auth : OK en lab isole, **jamais** expose Internet
- Bastion CD ≠ edge nginx (souvent node9 vs node12)

## BDD - lectures (local + prod)

Schema normalise (Alembic) : tables `rss_feeds`, `article_media` (image/video/audio),
`article_keywords`, `article_analyses`, `article_meta_norm`, `article_entities` (spaCy),
`persons` + `article_faces` (reco faciale, lib pluggable via `FACE_DETECT_BACKEND`).

| Environnement | Outil / pratique |
|---------------|------------------|
| **Local SQLite** | WAL + `cache_size` / `mmap_size` (dans `db_backend.py`), `EXPLAIN QUERY PLAN`, `ANALYZE` apres gros imports |
| **Prod Postgres** | `pg_stat_statements` (`deploy/sql/enable_pg_stat_statements.sql`), `EXPLAIN (ANALYZE, BUFFERS)`, indexes covering (migration 005), optionnel PgBouncer si beaucoup de workers |
| **Les deux** | Filtrer sur colonnes (`analysis_status`, `enrich_status`), hydrate batch (pas de N+1) |

Apres un gros crawl : `ANALYZE` (SQLite) ou laisser autovacuum (Postgres).

Visages : optionnel (`FACE_DETECT_ENABLED=0` par defaut). Backends
`face_recognition` ou `insightface` via `FACE_DETECT_BACKEND` +
`pip install -r analyzer/requirements-faces.txt`. Embeddings stockes dans
`article_faces` ; match auto vers `persons` (media NER + similarite).

Avant PR / deploy : verifier Postgres avec les tests integration
(`pytest -m integration` en CI ou `DATABASE_URL=postgresql://... pytest -m integration`).
