# StreamNews - Analyseur de Flux RSS

Une application Docker Swarm qui analyse automatiquement les sites web pour détecter et récupérer les flux RSS en temps réel.

## 🚀 Fonctionnalités

- **Analyse automatique** : Crawl intelligent des sites web
- **Détection RSS** : Identification automatique des flux RSS/Atom
- **Streaming temps réel** : Suivi en direct de l'avancement via WebSocket
- **Interface moderne** : Interface web responsive et intuitive
- **Scalabilité** : Architecture microservices avec Docker Swarm
- **Persistance** : Stockage PostgreSQL des résultats

## 🏗️ Architecture

L'application est composée de plusieurs services :

- **Web** : Interface utilisateur (Node.js + Express + WebSocket)
- **Analyzer** : Service d'analyse des sites (Python + FastAPI)
- **Worker** : Traitement des tâches en arrière-plan (Celery)
- **PostgreSQL** : Base de données pour les résultats
- **Redis** : Queue de tâches et cache

## 📋 Prérequis

- Docker et Docker Compose
- Docker Swarm activé
- Au moins 4GB de RAM disponible

## 🛠️ Installation et Démarrage

### 1. Initialiser Docker Swarm

```bash
docker swarm init
```

### 2. Déployer l'application

```bash
# Déployer la stack
docker stack deploy -c docker-stack.yml streamnews

# Vérifier le déploiement
docker stack services streamnews
```

### 3. Accéder à l'application

Ouvre ton navigateur sur : http://localhost:3000

## 🎯 Utilisation

### Analyser un site

1. Saisis l'URL du site à analyser
2. Configure le nombre maximum de pages (25-200)
3. Définis la profondeur de crawl (2-5 niveaux)
4. Clique sur "Lancer l'analyse"

### Suivi en temps réel

- **Barre de progression** : Suit l'avancement page par page
- **Logs en direct** : Voir chaque page analysée
- **Flux RSS détectés** : Apparition en temps réel
- **Statut de l'analyse** : En cours, terminé, ou erreur

### Consulter les résultats

- **Liste des sites** : Tous les sites analysés
- **Détails par site** : Flux RSS trouvés, pages analysées
- **Historique** : Conserve tous les résultats

## 🔧 Configuration

### Variables d'environnement

```bash
# Base de données
DATABASE_URL=postgresql://streamnews:streamnews123@postgres:5432/streamnews

# Redis
REDIS_URL=redis://redis:6379

# Service web
WEB_URL=http://web:3000
```

### Scaling des services

```bash
# Augmenter le nombre de workers
docker service scale streamnews_worker=5

# Augmenter les analyseurs
docker service scale streamnews_analyzer=3
```

## 📊 Monitoring

### Vérifier l'état des services

```bash
# Services actifs
docker service ls

# Logs d'un service
docker service logs streamnews_web

# Métriques
docker stats
```

### Logs en temps réel

```bash
# Tous les services
docker service logs -f streamnews_web
docker service logs -f streamnews_analyzer
docker service logs -f streamnews_worker
```

## 🐛 Dépannage

### Problèmes courants

1. **Service ne démarre pas**
   ```bash
   docker service logs streamnews_web
   ```

2. **Base de données inaccessible**
   ```bash
   docker service logs streamnews_postgres
   ```

3. **WebSocket ne fonctionne pas**
   - Vérifier que le port 3000 est accessible
   - Contrôler les logs du service web

### Redémarrage d'un service

```bash
docker service update --force streamnews_web
```

## 🔒 Sécurité

- **HTTPS** : Configure un reverse proxy pour la production
- **Authentification** : À implémenter selon tes besoins
- **Rate limiting** : Limite les requêtes par IP
- **Validation** : Toutes les URLs sont validées

## 📈 Performance

### Optimisations recommandées

- **Workers** : Ajuste le nombre selon la charge
- **Base de données** : Index sur les colonnes fréquemment utilisées
- **Cache** : Utilise Redis pour les résultats fréquents
- **Réseau** : Optimise la bande passante pour le crawling

### Métriques de performance

- **Pages par minute** : 50-100 pages selon la complexité
- **Mémoire** : ~512MB par worker
- **CPU** : Utilisation modérée, pics lors du parsing

## 🤝 Contribution

1. Fork le projet
2. Crée une branche feature
3. Commit tes changements
4. Push vers la branche
5. Ouvre une Pull Request

## 📄 Licence

MIT License - Voir le fichier LICENSE pour plus de détails.

## 🆘 Support

Pour toute question ou problème :

1. Consulte les logs des services
2. Vérifie la documentation
3. Ouvre une issue sur GitHub

---

**StreamNews** - Analyse intelligent des flux RSS avec Docker Swarm 🚀 