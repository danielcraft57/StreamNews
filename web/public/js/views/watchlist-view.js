import { escapeHtml, escapeAttr } from '../utils/dom.js';
import { COMPETITOR_SOURCES } from './radar-view.js';

export function renderWatchKeywords(keywords = []) {
    if (!keywords.length) {
        return '<p class="feed-empty">Aucun mot-cle. Ajoute billing, auth, RAG…</p>';
    }
    return keywords.map((k) => `
        <div class="watch-kw-row" data-watch-kw-id="${escapeAttr(String(k.id))}">
            <strong>${escapeHtml(k.keyword)}</strong>
            <button type="button" class="feed-tool-btn" data-watch-kw-delete="${escapeAttr(String(k.id))}">Supprimer</button>
        </div>
    `).join('');
}

export function renderWatchAlerts(alerts = [], { selected = null } = {}) {
    if (!alerts.length) {
        return '<p class="feed-empty">Pas d\'alerte. Clique Recalculer apres avoir ajoute des sources.</p>';
    }
    return alerts.map((a) => {
        const sel = a.keyword === selected ? ' is-selected' : '';
        const delta = Number(a.delta) || 0;
        const deltaLabel = delta > 0 ? `+${delta}` : String(delta);
        return `
            <button type="button" class="radar-row${sel}" data-watch-alert="${escapeAttr(a.keyword)}">
                <div class="trend-row-top">
                    <strong class="trend-term">${escapeHtml(a.keyword)}</strong>
                    <span class="trend-kind">${escapeHtml(deltaLabel)}</span>
                </div>
                <div class="trend-row-meta">
                    <span>${a.current_count || 0} cette fenetre</span>
                    <span>${a.previous_count || 0} avant</span>
                    <span>score ${a.score || 0}</span>
                </div>
            </button>`;
    }).join('');
}

export function renderWatchDetail(alert) {
    if (!alert) {
        return `
            <p class="feed-empty">Selectionne une alerte.</p>
            <div class="radar-pack">
                <h4>Sources concurrents</h4>
                <p class="pane-sub">Changelogs utiles a surveiller.</p>
                <div class="radar-pack-list">
                    ${COMPETITOR_SOURCES.map((s) => `
                        <button type="button" class="radar-pack-item" data-radar-source-url="${escapeAttr(s.url)}">
                            <strong>${escapeHtml(s.label)}</strong>
                            <span class="pane-sub">${escapeHtml(s.hint || '')}</span>
                        </button>`).join('')}
                </div>
            </div>`;
    }
    const titles = Array.isArray(alert.sample_titles) ? alert.sample_titles : [];
    return `
        <p class="job-type">Watchlist</p>
        <h3 class="jobs-detail-title">${escapeHtml(alert.keyword)}</h3>
        <dl class="jobs-detail-grid">
            <div><dt>Maintenant</dt><dd>${alert.current_count || 0}</dd></div>
            <div><dt>Avant</dt><dd>${alert.previous_count || 0}</dd></div>
            <div><dt>Delta</dt><dd>${alert.delta || 0}</dd></div>
            <div><dt>Score</dt><dd>${alert.score || 0}</dd></div>
        </dl>
        ${titles.length ? `<div class="trends-samples"><h4>Exemples</h4><ul>${titles.map((t) => `<li>${escapeHtml(t)}</li>`).join('')}</ul></div>` : ''}
        <md-filled-button type="button" data-watch-search="${escapeAttr(alert.keyword)}" style="width:100%">
            Chercher dans le feed
        </md-filled-button>`;
}

export function renderWatchForm() {
    return `
        <form id="watchKwForm" class="watch-kw-form" style="display:flex;gap:8px;margin-bottom:12px">
            <input type="text" id="watchKwInput" placeholder="ex: billing" required minlength="2" style="flex:1;padding:8px 10px;border:1px solid var(--line);border-radius:8px">
            <button type="submit" class="feed-tool-btn">Ajouter</button>
        </form>`;
}
