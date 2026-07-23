# StreamNews — refonte UX/UI (brief)

Branche: `feature/ux-ui-refonte`  
Sources: transcripts TikTok UX (`Videos/tiktokUX/transcripts`) + audit de l'UI actuelle (`web/public/index.html`).

## Probleme actuel

L'UI etait une grosse page unique: fond violet degrade, cartes blanches, CTA partout. Ca ressemblait a un template admin 2019, pas a un outil de lecture + analyse RSS.

## Direction visuelle

| Token | Valeur | Role |
|-------|--------|------|
| Ink | `#0B1F33` | texte, chrome, marque |
| Teal | `#0D9488` | action principale, etat actif |
| Amber | `#D97706` | tags NLP / entites |
| Surface | `#F4F6F8` / blanc | fonds et panneaux |
| Radius | 6px | coins (pas de pills full) |

On sort volontairement du violet degrade. Pas de look "journal dense", pas de cream + serif terracotta.

## Principes tires des transcripts

1. **Sidebar par intention** (pas par feature): Lire / Analyser / Compte. Max 7 items niveau 1. Le Feed en haut = action a valoriser.
2. **Systeme 1 vs 2**: scan + ouvrir un article = zero reflexion. Supprimer une source = friction volontaire.
3. **Loi de Fitts**: gros CTA principal ("Ajouter une source", "Analyser"). Delete petit et loin.
4. **Aha moment**: une URL → premier article enrichi en quelques secondes. Victoire avant les reglages.
5. **Feedback + next step**: apres un crawl, confirmer l'impact ET proposer "Lire le premier article".
6. **Celebration asymetrique**: premiere source = moment fort (modal victoire). Les reloads suivants = toast discret.
7. **Recherche copilote**: suggestions, actions rapides, contexte. Jamais un mur "0 resultat".
8. **Simplifier = hierarchiser**, pas tout enlever. Options avancees du crawl cachees dans le modal.

## Maquettes

| Fichier | Ecran | Idee |
|---------|-------|------|
| `maquette-01-console-feed-lecteur.png` | Feed + lecteur | Split view, NLP dans le flux de lecture |
| `maquette-02-onboarding-aha.png` | Onboarding | Une action, une victoire rapide |
| `maquette-03-recherche-copilote.png` | Recherche | Spotlight + actions + contexte |
| `maquette-04-source-victoire.png` | Detail source | Celebration + CTA suivant apres crawl |
| `maquette-05-favoris.png` | Favoris | Meme shell que le Feed, filtre local |
| `maquette-06-sources.html` (+ png si dispo) | Sources | Liste en lignes + gros CTA Ajouter |
| `maquette-07-modal-ajout-source.png` | Modal ajout | URL seule, options avancees, progress live |
| `maquette-08-jobs.png` | Jobs | File crawl / enrich / NLP + detail |
| `maquette-09-reglages.png` | Reglages | Prefs locales, delete loin du CTA |

## Implementation (app)

Dans `web/public/` : sidebar Lire/Analyser/Compte, Feed+lecteur, Favoris (localStorage),
Sources (liste + modal Ajouter), Jobs (file locale), Reglages (prefs locales).
Ajout source = modal (pas de formulaire enfoui dans la page).

## Parcours cible (v1)

1. Arrivee → Feed (ou empty Sources) → **Ajouter une source** (modal)
2. Progress live dans le modal → confirmation + CTA "Lire le premier article"
3. Split lecteur (resume IA, entites / mots-cles)
4. Cmd/Ctrl+K pour chercher / ajouter une source
5. Sidebar: Feed | Favoris | Sources | Jobs | Reglages

## Hors scope pour l'instant

Auth multi-user, dark mode force, redesign backend. Rewrite React non prioritaire :
architecture ES modules + Material Web en place (`web/ARCHITECTURE.md`).
