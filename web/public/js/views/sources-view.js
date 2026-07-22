import { escapeHtml, escapeAttr } from '../utils/dom.js';
import { parseRssFeeds, shortSiteLabel, siteStatusTone, siteStatusLabel } from '../models/site.js';

/**
 * Rendu liste Sources (lignes maquette).
 */
export function renderSourcesList(sites, { viewingSiteId = null } = {}) {
    if (!sites?.length) {
        return `
            <div class="sources-empty">
                <p class="feed-empty">Aucune source pour le moment.</p>
                <md-filled-button type="button" id="emptyAddSource">Ajouter ta premiere source</md-filled-button>
            </div>`;
    }

    return sites.map((site) => {
        const feeds = parseRssFeeds(site.rss_feeds);
        const title = shortSiteLabel(site);
        let host = '';
        try { host = new URL(site.url).hostname.replace(/^www\./, ''); }
        catch (_) { host = site.url || ''; }
        const favicon = site.favicon_url
            ? `<img class="source-favicon js-hide-on-error" src="${escapeAttr(site.favicon_url)}" alt="" width="36" height="36" loading="lazy">`
            : `<span class="source-favicon source-favicon-fallback" aria-hidden="true">${escapeHtml((title || '?').slice(0, 1).toUpperCase())}</span>`;
        const statusClass = siteStatusTone(site.status);
        const statusText = siteStatusLabel(site.status);
        const viewing = Number(viewingSiteId) === Number(site.id) ? ' is-viewing' : '';
        const pages = site.total_pages_analyzed ? `${site.total_pages_analyzed} pages` : '';
        const rss = feeds.length ? `${feeds.length} RSS` : '0 RSS';

        return `
            <article class="source-row${viewing}" data-site-id="${site.id}">
                <button type="button" class="source-row-identity" data-open-site="${site.id}">
                    ${favicon}
                    <span class="source-row-text">
                        <strong>${escapeHtml(title)}</strong>
                        <span class="source-row-host">${escapeHtml(host)}</span>
                    </span>
                </button>
                <span class="source-status ${statusClass}">${escapeHtml(statusText)}</span>
                <div class="source-row-stats">
                    ${pages ? `<span>${escapeHtml(pages)}</span>` : ''}
                    <span>${escapeHtml(rss)}</span>
                </div>
                <div class="source-row-actions">
                    <md-outlined-button type="button" data-open-site="${site.id}">Voir le feed</md-outlined-button>
                    ${feeds.length > 0 ? `<md-outlined-button type="button" data-ingest-site="${site.id}">Recharger</md-outlined-button>` : ''}
                    <md-outlined-button type="button" data-enrich-site="${site.id}">Enrichir</md-outlined-button>
                    <md-outlined-button type="button" data-analyze-site="${site.id}">Analyser</md-outlined-button>
                    <button type="button" class="btn-icon-danger" data-delete-site="${site.id}" title="Supprimer" aria-label="Supprimer">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </div>
            </article>
        `;
    }).join('');
}
