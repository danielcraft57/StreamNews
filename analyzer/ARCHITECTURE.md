# Architecture StreamNews (analyzer)

## Patterns

| Pattern | Ou | Role |
|---------|-----|------|
| **Domain models** | `models/` | Contrats Pydantic (Feed, Article, CrawlResult) |
| **Services** | `services/` | CrawlService (IO web), IngestService (parse RSS) |
| **Repository** | `database.py` | Postgres asyncpg |
| **Pipeline + Fan-out/Fan-in** | `tasks/` | crawl -> group(ingest) -> finalize (Celery chord) |
| **Queues** | `crawl`, `ingest`, `default` | Specialisation workers |
| **Bounded concurrency** | `CRAWL_CONCURRENCY` | Semaphore asyncio sur pages (defaut 3) |

## Flux

```
POST /analyze
    -> crawl_site (queue crawl)
         -> pages en parallele (semaphore)
         -> persist feeds/pages
         -> chord:
              ingest_feed x N  (queue ingest, N workers possibles)
              -> finalize_analysis (WS UI)
```

## Gains

- Pages crawllees en parallele sur un meme Pi (sans exploser la RAM)
- Chaque flux RSS ingere sur un worker different si plusieurs Pi
- UI notifiee une fois le fan-in termine

## Lancer un worker

```bash
cd analyzer
celery -A celery_worker worker -Q crawl,ingest,default --concurrency=1
```
