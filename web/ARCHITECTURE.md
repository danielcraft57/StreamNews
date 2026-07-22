# Architecture frontend StreamNews

## Objectif

Sortir du monolithe `public/app.js` (~2500 lignes) vers une architecture en couches,
avec des composants **Material Web (MD3)** themes StreamNews (ink / teal / amber).

## Couches

```
public/
  css/
    tokens.css          # design tokens MD3 → palette StreamNews
    layout.css          # shell (sidebar, panes)
  vendor/
    material.js         # bundle @material/web (esbuild)
  js/
    main.js             # bootstrap
    core/
      bus.js            # EventBus pub/sub
      state.js          # etat applicatif (single source of truth)
    models/             # donnees pures (pas de DOM)
      article.js
      site.js
      settings.js
      job.js
    services/           # IO uniquement
      api.js            # fetch REST
      storage.js        # localStorage
      realtime.js       # WebSocket
    views/              # rendu DOM
      feed-view.js
      reader-view.js
      sources-view.js
      jobs-view.js
      settings-view.js
      modal-view.js
    ui/                 # wrappers Material + helpers
      theme.js
      toast.js
    utils/
      dom.js
      time.js
  app.legacy.js         # orchestrateur (migration progressive)
```

## Flux

```
UI (views/Material) → EventBus / handlers → services → models → state → views.render()
                                              ↑
                                         WebSocket
```

## Material

Composants utilises : `md-filled-button`, `md-outlined-button`, `md-dialog`,
`md-outlined-text-field`, `md-switch`, `md-filter-chip`, `md-linear-progress`,
`md-icon-button`, `md-checkbox`.

Theme via CSS custom properties `--md-sys-color-*` mappees sur les tokens StreamNews.

## Migration

1. Extraire utils + models + services (fait)
2. Brancher Material sur modal / reglages / CTA Sources (fait)
3. Views Feed + Reader + chips Material (fait)
4. Views Sources + Jobs + recherche Ctrl+K (fait)
5. Remplacer progressivement le reste de `app.js` (orchestrateur)

## Build

```bash
cd web
npm run build:material
```
