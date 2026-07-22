import { escapeHtml, escapeAttr } from '../utils/dom.js';
import { shortSiteLabel } from '../models/site.js';

/**
 * Chips de filtre source sous le header Feed.
 */
export function renderSourceChips(sites = [], activeId = 'all') {
    const allActive = String(activeId) === 'all' ? ' is-active' : '';
    const chips = [
        `<button type="button" class="source-chip${allActive}" data-feed-source="all">
            <span class="source-chip-label">Tous</span>
        </button>`,
    ];

    for (const site of sites || []) {
        const id = String(site.id);
        const active = id === String(activeId) ? ' is-active' : '';
        const label = shortSiteLabel(site);
        let host = '';
        try { host = new URL(site.url).hostname.replace(/^www\./, ''); }
        catch (_) { host = label; }
        const favicon = site.favicon_url
            ? `<img class="source-chip-fav js-hide-on-error" src="${escapeAttr(site.favicon_url)}" alt="" width="16" height="16" loading="lazy">`
            : `<span class="source-chip-fav source-chip-fav-fallback" aria-hidden="true">${escapeHtml((label || '?').slice(0, 1).toUpperCase())}</span>`;
        chips.push(`
            <button type="button" class="source-chip${active}" data-feed-source="${escapeAttr(id)}" title="${escapeAttr(host)}">
                ${favicon}
                <span class="source-chip-label">${escapeHtml(label)}</span>
            </button>
        `);
    }

    return chips.join('');
}
