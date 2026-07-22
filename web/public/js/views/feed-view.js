import { escapeHtml, escapeAttr } from '../utils/dom.js';
import { formatRelativeTime } from '../utils/time.js';
import { renderPlainChips } from '../ui/chips.js';
import { shortSiteLabel } from '../models/site.js';

/**
 * Met a jour le titre / sous-titre du pane Feed|Favoris.
 */
export function updateFeedHeader(feedMode, { count = null, sourceLabel = null } = {}) {
    const titleEl = document.getElementById('feedTitle') || document.querySelector('.feed-header h1');
    const subEl = document.getElementById('feedSubtitle');
    if (titleEl) titleEl.textContent = feedMode === 'favorites' ? 'Favoris' : 'Feed';
    if (subEl) {
        if (feedMode === 'favorites') {
            subEl.textContent = count != null
                ? `${count} article${count > 1 ? 's' : ''} sauvegarde${count > 1 ? 's' : ''}`
                : 'Tes articles sauvegardes';
        } else if (sourceLabel) {
            subEl.textContent = count != null
                ? `${sourceLabel} · ${count} article${count > 1 ? 's' : ''}`
                : `Articles de ${sourceLabel}`;
        } else {
            subEl.textContent = count != null
                ? `${count} article${count > 1 ? 's' : ''} · toutes sources`
                : 'Tous tes articles, toutes sources confondues';
        }
    }
}

/**
 * Empty states du feed.
 */
export function renderFeedEmptyHtml({ feedMode, noSources, filteredSite = null, feedCount = 0, loadFailed = false }) {
    if (noSources && feedMode !== 'favorites') {
        return `
            <div class="sources-empty">
                <p class="feed-empty">Ton feed est vide. Ajoute une source pour voir les premiers articles.</p>
                <md-filled-button type="button" id="feedEmptyAddSource">Ajouter une source</md-filled-button>
            </div>`;
    }
    if (feedMode === 'favorites') {
        return `
            <div class="sources-empty favoris-empty">
                <div class="favoris-empty-icon" aria-hidden="true"><i class="fas fa-star"></i></div>
                <p class="feed-empty">Aucun favori pour le moment.</p>
                <p class="pane-sub">Ouvre un article dans le Feed et ajoute-le aux favoris.</p>
                <md-outlined-button type="button" id="favorisEmptyGoFeed">Aller au Feed</md-outlined-button>
            </div>`;
    }
    if (filteredSite && feedCount > 0) {
        const label = shortSiteLabel(filteredSite);
        return `
            <div class="sources-empty">
                <p class="feed-empty">${loadFailed ? 'Chargement impossible' : 'Aucun article affiche'} pour ${escapeHtml(label)}.</p>
                <p class="pane-sub">${feedCount} flux RSS connus — relance un import si besoin.</p>
                <md-filled-button type="button" data-ingest-site="${filteredSite.id}">Recharger le flux</md-filled-button>
            </div>`;
    }
    if (filteredSite) {
        return `<p class="feed-empty">Aucun article pour cette source.</p>`;
    }
    return '<p class="feed-empty">Aucun article pour le moment. Lance une analyse ou recharge le flux dans Sources.</p>';
}

export function renderReaderEmptyMessage({ feedMode, noSources }) {
    if (noSources) return 'Ajoute une source pour commencer a lire.';
    if (feedMode === 'favorites') return 'Selectionne un favori pour le lire ici.';
    return 'Selectionne un article dans le feed pour le lire ici.';
}

/**
 * Ligne article du feed.
 * Chips plaines (pas md-*) : une ligne est un <button>, on ne nest pas d'interactifs.
 */
export function renderFeedRow(article, ctx = {}) {
    const selected = ctx.selectedArticleId === article.id ? ' is-selected' : '';
    const favClass = ctx.isFavorite ? ' is-favorite' : '';
    const readClass = ctx.isRead ? ' is-read' : '';
    const thumbUrl = ctx.hero?.url || '';
    const thumb = thumbUrl
        ? `<img class="js-hide-on-error" src="${escapeAttr(thumbUrl)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
        : `<span class="feed-row-thumb-fallback" aria-hidden="true"></span>`;
    const source = ctx.source || 'Source';
    const timeStr = formatRelativeTime(article.published_at);
    const keywords = ctx.keywords || [];
    const chipsBlock = keywords.length ? renderPlainChips(keywords) : '';

    return `
        <button type="button" class="feed-row article-item${selected}${favClass}${readClass}" data-article-id="${article.id}">
            <div class="feed-row-thumb">${thumb}</div>
            <div class="feed-row-body">
                <div class="feed-row-meta">
                    <span class="feed-source">${escapeHtml(source)}</span>
                    <span class="feed-time">${escapeHtml(timeStr)}</span>
                </div>
                <h3 class="feed-row-title">${escapeHtml(article.title || 'Sans titre')}</h3>
                ${chipsBlock}
            </div>
        </button>
    `;
}
