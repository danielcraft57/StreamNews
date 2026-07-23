import { escapeHtml, escapeAttr } from '../utils/dom.js';
import { highlightMatch } from '../services/search.js';

/**
 * Palette Ctrl+K — actions + resultats articles / sources.
 */
export function renderSearchPalette({
    query = '',
    articles = [],
    sites = [],
    actions = [],
    searching = false,
    searchSource = '',
} = {}) {
    const q = String(query || '').trim();
    const qLow = q.toLowerCase();

    const articleHits = (articles || []).slice(0, 12);
    const siteHits = qLow
        ? (sites || [])
            .filter((s) => {
                const hay = `${s.title || s.name || ''} ${s.url || ''}`.toLowerCase();
                return hay.includes(qLow);
            })
            .slice(0, 4)
        : [];

    const allActions = actions.length ? actions : defaultActions();
    let visibleActions = allActions.filter((a) => (
        !qLow
        || a.label.toLowerCase().includes(qLow)
        || a.keywords?.some((k) => k.includes(qLow))
    ));
    if (qLow && !visibleActions.length) {
        visibleActions = allActions.slice(0, 3);
    }

    const actionButtons = visibleActions.map((a, i) => `
            <button type="button" class="search-hit${i === 0 && !articleHits.length && !siteHits.length ? ' is-active' : ''}" data-search-action="${escapeAttr(a.id)}">
                <span class="search-hit-icon"><i class="fas ${escapeAttr(a.icon)}"></i></span>
                <span class="search-hit-body">
                    <strong>${escapeHtml(a.label)}</strong>
                    ${a.hint ? `<span class="pane-sub">${escapeHtml(a.hint)}</span>` : ''}
                </span>
                ${a.kbd ? `<kbd>${escapeHtml(a.kbd)}</kbd>` : ''}
            </button>
        `).join('');

    const articlesBlock = articleHits.length
        ? `
            <div class="search-palette-section">Articles${searchSource === 'api' ? ' · BDD' : (searchSource === 'local' ? ' · local' : '')}</div>
            ${articleHits.map((a, i) => `
                <button type="button" class="search-hit${i === 0 ? ' is-active' : ''}" data-search-article="${a.id}">
                    <span class="search-hit-icon"><i class="fas fa-newspaper"></i></span>
                    <span class="search-hit-body">
                        <strong>${highlightMatch(a.title || 'Sans titre', q)}</strong>
                        <span class="pane-sub">${escapeHtml(a.source || a._siteLabel || 'Source')}</span>
                    </span>
                </button>
            `).join('')}`
        : '';

    const sitesBlock = siteHits.length
        ? `
            <div class="search-palette-section">Sources</div>
            ${siteHits.map((s) => `
                <button type="button" class="search-hit" data-search-site="${s.id}">
                    <span class="search-hit-icon"><i class="fas fa-rss"></i></span>
                    <span class="search-hit-body">
                        <strong>${escapeHtml(s.title || s.name || s.url || 'Source')}</strong>
                        <span class="pane-sub">${escapeHtml(s.url || '')}</span>
                    </span>
                </button>
            `).join('')}`
        : '';

    const emptyQueryHint = !q
        ? `<p class="search-hint">Recherche dans tes articles, sources, ou lance une action.</p>`
        : '';

    const searchingHint = searching
        ? `<p class="search-hint">Recherche…</p>`
        : '';

    const noHits = q && !searching && !articleHits.length && !siteHits.length
        ? `<p class="search-hint">Rien pour « ${escapeHtml(q)} ». Essaie un autre mot ou ajoute une source.</p>`
        : '';

    const showActions = !q || (!articleHits.length && !searching) || visibleActions.length;
    const actionsBlock = showActions
        ? `<div class="search-palette-section">${q && articleHits.length ? 'Actions' : 'Actions rapides'}</div>${actionButtons}`
        : '';

    return `
        ${emptyQueryHint}
        ${searchingHint}
        ${articlesBlock}
        ${sitesBlock}
        ${actionsBlock}
        ${noHits}
    `;
}

function defaultActions() {
    return [
        { id: 'focus-url', label: 'Ajouter une source', hint: 'Coller une URL', icon: 'fa-plus', kbd: 'N', keywords: ['ajouter', 'source', 'url'] },
        { id: 'go-feed', label: 'Ouvrir le feed', hint: 'Tous les articles', icon: 'fa-stream', kbd: '', keywords: ['feed', 'lire'] },
        { id: 'go-favoris', label: 'Voir les favoris', hint: 'Articles sauvegardes', icon: 'fa-star', keywords: ['favoris', 'star'] },
        { id: 'scroll-sites', label: 'Voir les sources', hint: 'Sites analyses', icon: 'fa-globe', keywords: ['sources', 'sites'] },
        { id: 'go-jobs', label: 'Suivre les jobs', hint: 'Crawl, enrich, NLP', icon: 'fa-briefcase', keywords: ['jobs', 'crawl'] },
        { id: 'go-tendances', label: 'Voir les tendances', hint: 'Sujets qui montent', icon: 'fa-chart-line', keywords: ['tendances', 'trends', 'hot'] },
        { id: 'go-radar', label: 'Ouvrir le radar idees', hint: 'Opportunites SaaS / IT', icon: 'fa-bullseye', keywords: ['radar', 'idees', 'saas', 'opportunite'] },
    ];
}
