# StreamNews sur homelab (Raspberry Pi)

## Roles (ne pas confondre)

| Noeud | Role | Crawl ? |
|-------|------|---------|
| **node6.lan** | data (Postgres + Redis) | Non |
| **node7.lan** | app (web + analyzer) | Non |
| **node8.lan** | worker Celery | Oui |

```
UI/API (node7) --> Redis+PG (node6) --> Workers (node8, …)
```

## Installation

```bash
# node6 — data
sudo bash deploy/setup-data-node.sh

# node7 — UI + API (sans worker)
sudo DATA_HOST=node6.lan bash deploy/setup-app-node.sh

# node8 — worker crawl
sudo DATA_HOST=node6.lan WEB_HOST=node7.lan bash deploy/setup-worker-node.sh
```

UI : `http://node7.lan:3000`

Ajoute d'autres workers en relancant `setup-worker-node.sh` sur d'autres Pi.

## Limites

- Pi 2 : concurrency Celery = 1
- Redis ouvert sur le LAN sans mot de passe : OK en homelab isole, pas sur Internet
