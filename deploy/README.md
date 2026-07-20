# Deploy StreamNews

Scripts d'install et de mise en ligne (homelab multi-Pi ou VPS unique). **Pas de Docker.**

## Docs

| Fichier | Contenu |
|---------|---------|
| [HOMELAB.md](HOMELAB.md) | Roles node6/7/8/9/12/13, install, CD, limites |
| [../README.md](../README.md) | Install locale (SQLite / Postgres) |
| [../analyzer/ARCHITECTURE.md](../analyzer/ARCHITECTURE.md) | Pipelines Celery, backends DB |

## Scripts

| Script | Usage |
|--------|--------|
| `setup-data-node.sh` | Postgres + Redis (ex. node6) |
| `setup-app-node.sh` | web + analyzer, sans worker (ex. node7) |
| `setup-worker-node.sh` | Celery worker (ex. node8+) |
| `setup-vps.sh` | Tout-en-un sur une seule machine |
| `ensure-app-user.sh` | Cree/repare user `streamnews` + sudoers |
| `deploy.sh` | Pull + deps + restart (un noeud) |
| `deploy-fleet.sh` | Deploy parallele depuis le bastion SSH |
| `nginx-streamnews.danielcraft.fr.conf` | Vhost edge (TLS via certbot) |

Tous les `setup-*.sh` exigent :

```bash
sudo POSTGRES_PASSWORD='…' bash deploy/setup-….sh
```

Aucun mot de passe par defaut n'est injecte dans `/opt/streamnews/.env`.

## CD (rappel)

GitHub Actions → SSH `DEPLOY_HOST` (bastion, ex. node9) → `deploy-fleet.sh` → node6/7/8.
