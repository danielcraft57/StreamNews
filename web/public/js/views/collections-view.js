import { escapeHtml, escapeAttr } from '../utils/dom.js';
import { shortSiteLabel } from '../models/site.js';

export function renderCollectionsList(collections = [], selectedId = null) {
    if (!collections.length) {
        return '<p class="feed-empty">Aucune collection.</p>';
    }
    return collections.map((c) => {
        const sel = Number(c.id) === Number(selectedId) ? ' is-selected' : '';
        return `
            <button type="button" class="radar-row${sel}" data-collection-id="${escapeAttr(String(c.id))}">
                <div class="trend-row-top">
                    <strong class="trend-term">${escapeHtml(c.name)}</strong>
                    <span class="trend-kind">${c.site_count || 0} src</span>
                </div>
                <span class="pane-sub">${escapeHtml(c.description || c.slug || '')}</span>
            </button>`;
    }).join('');
}

export function renderCollectionDetail(col, allSites = []) {
    if (!col) {
        return '<p class="feed-empty">Selectionne une collection.</p>';
    }
    const linked = new Set((col.site_ids || []).map(Number));
    const sites = col.sites || [];
    const options = (allSites || [])
        .filter((s) => !linked.has(Number(s.id)))
        .map((s) => `<option value="${escapeAttr(String(s.id))}">${escapeHtml(shortSiteLabel(s))}</option>`)
        .join('');

    return `
        <p class="job-type">Collection</p>
        <h3 class="jobs-detail-title">${escapeHtml(col.name)}</h3>
        <p class="pane-sub">${escapeHtml(col.description || '')}</p>
        <h4 style="margin:16px 0 8px">Sources liees</h4>
        ${sites.length ? `
            <ul class="collection-sites">
                ${sites.map((s) => `
                    <li>
                        <span>${escapeHtml(shortSiteLabel(s))}</span>
                        <button type="button" class="feed-tool-btn" data-collection-remove-site="${escapeAttr(String(s.id))}">Retirer</button>
                    </li>`).join('')}
            </ul>` : '<p class="feed-empty">Aucune source dans cette collection.</p>'}
        <form id="collectionAddSiteForm" style="display:flex;gap:8px;margin-top:12px">
            <select id="collectionAddSiteSelect" style="flex:1;padding:8px;border-radius:8px;border:1px solid var(--line)">
                <option value="">Ajouter une source…</option>
                ${options}
            </select>
            <button type="submit" class="feed-tool-btn">Lier</button>
        </form>
        <md-outlined-button type="button" data-collection-open-radar="${escapeAttr(String(col.id))}" style="width:100%;margin-top:12px">
            Voir le radar filtre
        </md-outlined-button>
        <md-outlined-button type="button" data-collection-open-trends="${escapeAttr(String(col.id))}" style="width:100%;margin-top:8px">
            Voir les tendances filtrees
        </md-outlined-button>`;
}
