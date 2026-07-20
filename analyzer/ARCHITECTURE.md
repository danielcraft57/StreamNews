# Architecture StreamNews (analyzer)

## Patterns

| Pattern | Ou | Role |
|---------|-----|------|
| **Domain models** | `models/` | Contrats Pydantic (Feed, Article, CrawlResult) |
| **Services** | `services/` | CrawlService, IngestService, EnrichService |
| **Repository** | `database.py` + `db_backend.py` | Postgres (asyncpg) ou SQLite (aiosqlite) |
| **Pipeline + Fan-out/Fan-in** | `tasks/` | crawl → group(ingest) → finalize (Celery chord) |
| **Queues** | `crawl`, `ingest`, `default` | Specialisation workers |
| **Bounded concurrency** | `CRAWL_CONCURRENCY` | Semaphore asyncio sur pages (defaut 3) |
| **Logging** | `logging_config.py` + `logs/` | Fichiers rotatifs + `errors.log` |

## Backend DB

Choisi via `DATABASE_URL` (sinon defaut SQLite local, **sans** mot de passe en dur) :

| URL | Backend | Usage |
|-----|---------|--------|
| `postgresql://…` | asyncpg | Prod / CI / homelab |
| `sqlite:///./data/streamnews.db` | aiosqlite | Dev local (fichier sous `data/`, ignore git) |

`db_backend.py` adapte les placeholders `$1` et casts `::jsonb` pour SQLite.

Charge l'env avec `scripts/load-env.sh` (`--local` → `.env.local`).

## Flux

```
POST /analyze
    → crawl_site (queue crawl)
         → pages en parallele (semaphore)
         → persist feeds/pages
         → chord:
              ingest_feed x N  (queue ingest)
              → finalize_analysis (WS UI)
```

Enrichissement article : taches `enrich_*` sur queue `ingest`.

## Logs

Dossier `logs/` (ou `LOG_DIR`) :

| Fichier | Source |
|---------|--------|
| `analyzer.log` | FastAPI |
| `worker.log` | Celery |
| `web.log` | Express |
| `errors.log` | WARNING+ |

```bash
tail -f /opt/streamnews/logs/worker.log
# local :
tail -f logs/analyzer.log
```

## Lancer un worker

```bash
cd analyzer
celery -A celery_worker worker -Q crawl,ingest,default --concurrency=1
```
