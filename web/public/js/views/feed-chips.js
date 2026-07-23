import { escapeHtml, escapeAttr } from '../utils/dom.js';
import { shortSiteLabel } from '../models/site.js';

/** Nombre de sources visibles avant "Voir plus" (hors chip Tous). */
export const SOURCE_CHIPS_VISIBLE = 7;

function hostOf(site) {
    try {
        return new URL(site.url).hostname.replace(/^www\./, '');
    } catch (_) {
        return '';
    }
}

/** Label unique : si deux sources ont le meme titre, on montre le domaine. */
export function chipSiteLabel(site, sites = []) {
    const base = shortSiteLabel(site);
    const dupes = (sites || []).filter((s) => shortSiteLabel(s) === base);
    if (dupes.length > 1) {
        return hostOf(site) || base;
    }
    return base;
}

function chipHtml(site, activeId, sites) {
    const id = String(site.id);
    const active = id === String(activeId) ? ' is-active' : '';
    const label = chipSiteLabel(site, sites);
    const host = hostOf(site) || label;
    const favicon = site.favicon_url
        ? `<img class="source-chip-fav js-hide-on-error" src="${escapeAttr(site.favicon_url)}" alt="" width="16" height="16" loading="lazy">`
        : `<span class="source-chip-fav source-chip-fav-fallback" aria-hidden="true">${escapeHtml((label || '?').slice(0, 1).toUpperCase())}</span>`;
    return `
        <button type="button" class="source-chip${active}" data-feed-source="${escapeAttr(id)}" title="${escapeAttr(host)}">
            ${favicon}
            <span class="source-chip-label">${escapeHtml(label)}</span>
        </button>`;
}

/**
 * Chips de filtre source (pleine largeur, wrap, +Voir plus si trop de sources).
 */
export function renderSourceChips(sites = [], activeId = 'all', { expanded = false } = {}) {
    const list = Array.isArray(sites) ? sites.slice() : [];
    const allActive = String(activeId) === 'all' ? ' is-active' : '';
    const chips = [
        `<button type="button" class="source-chip${allActive}" data-feed-source="all">
            <span class="source-chip-label">Tous</span>
        </button>`,
    ];

    const needsCollapse = list.length > SOURCE_CHIPS_VISIBLE;
    let visible = list;
    if (needsCollapse && !expanded) {
        visible = list.slice(0, SOURCE_CHIPS_VISIBLE);
        if (activeId && String(activeId) !== 'all') {
            const activeSite = list.find((s) => String(s.id) === String(activeId));
            if (activeSite && !visible.some((s) => String(s.id) === String(activeId))) {
                visible = [...visible.slice(0, SOURCE_CHIPS_VISIBLE - 1), activeSite];
            }
        }
    }

    for (const site of visible) {
        chips.push(chipHtml(site, activeId, list));
    }

    if (needsCollapse) {
        const hidden = Math.max(0, list.length - visible.length);
        if (expanded) {
            chips.push(`
                <button type="button" class="source-chip source-chip-more" data-feed-sources-toggle="collapse" title="Reduire la liste">
                    <span class="source-chip-label">Moins</span>
                </button>`);
        } else {
            chips.push(`
                <button type="button" class="source-chip source-chip-more" data-feed-sources-toggle="expand" title="Voir toutes les sources">
                    <span class="source-chip-label">${hidden > 0 ? `+${hidden} autres` : 'Voir plus'}</span>
                </button>`);
        }
    }

    return chips.join('');
}
