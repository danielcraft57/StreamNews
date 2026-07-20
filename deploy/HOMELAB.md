# StreamNews - Homelab multi-Pi

Pas de Docker. Roles fixes sur le LAN.

## Roles

| Noeud (exemple) | Role | Services |
|-----------------|------|----------|
| **node6** | `data` | PostgreSQL + Redis |
| **node7** | `app` | web + analyzer (**sans** worker) |
| **node8+** | `worker` | Celery (`crawl`, `ingest`, `default`) |
| **node9** | bastion SSH | point d'entree CD (GitHub Actions) |
| **node12** | edge nginx | HTTPS public → proxy vers node7 |
| **node13** | Redis local-dev | broker pour le mode SQLite sur ton PC |

```
Dev PC (SQLite) ----Redis----> node13
                     |
UI/API (node7) --> Redis+PG (node6) --> Workers (node8…)
       ^
       | proxy TLS
   edge (node12)  https://…
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

Voir le README racine : SQLite dans `data/` + Redis sur node13.

```bash
cp .env.local.example .env.local
# adapte REDIS_URL si ton Redis n'est pas node13.lan
bash scripts/install.sh
bash scripts/init-db.sh --local
bash scripts/dev.sh --local
```

## CD

GitHub Actions SSH vers le **bastion** (`DEPLOY_HOST`, ex. node9), puis `deploy/deploy-fleet.sh` deploie node6/7/8 en parallele.

Detail secrets : README → section CI/CD.

## Limites

- Pi 2 : `CELERY_CONCURRENCY=1`
- Redis ouvert sur le LAN sans auth : OK en lab isole, **jamais** expose Internet
- Bastion CD ≠ edge nginx (souvent node9 vs node12)
