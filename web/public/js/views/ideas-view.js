import { escapeHtml, escapeAttr } from '../utils/dom.js';

export function renderIdeasList(ideas = [], selectedId = null) {
    if (!ideas.length) {
        return `
            <div class="sources-empty">
                <p class="feed-empty">Pas encore de fiche.</p>
                <p class="pane-sub">Cree-en depuis le Radar ou le Brief.</p>
            </div>`;
    }
    return ideas.map((idea) => {
        const sel = Number(idea.id) === Number(selectedId) ? ' is-selected' : '';
        return `
            <button type="button" class="radar-row${sel}" data-idea-id="${escapeAttr(String(idea.id))}">
                <div class="trend-row-top">
                    <strong class="trend-term">${escapeHtml(idea.title || 'Idee')}</strong>
                    <span class="trend-kind">${escapeHtml(idea.status || 'draft')}</span>
                </div>
                <span class="pane-sub">${escapeHtml(idea.theme || '')}</span>
            </button>`;
    }).join('');
}

export function renderIdeaDetail(idea) {
    if (!idea) {
        return '<p class="feed-empty">Selectionne une fiche.</p>';
    }
    const evidence = Array.isArray(idea.evidence) ? idea.evidence.join('\n') : (idea.evidence || '');
    return `
        <form id="ideaEditForm" class="idea-edit-form" data-idea-id="${escapeAttr(String(idea.id))}">
            <label>Titre<input name="title" value="${escapeAttr(idea.title || '')}" required></label>
            <label>Theme<input name="theme" value="${escapeAttr(idea.theme || '')}"></label>
            <label>Probleme<textarea name="problem" rows="4">${escapeHtml(idea.problem || '')}</textarea></label>
            <label>Preuves (1 par ligne)<textarea name="evidence" rows="4">${escapeHtml(evidence)}</textarea></label>
            <label>MVP 2 semaines<textarea name="mvp_plan" rows="4">${escapeHtml(idea.mvp_plan || '')}</textarea></label>
            <label>Status
                <select name="status">
                    ${['draft', 'active', 'parked', 'shipped'].map((s) =>
                        `<option value="${s}" ${idea.status === s ? 'selected' : ''}>${s}</option>`
                    ).join('')}
                </select>
            </label>
            <div class="idea-edit-actions">
                <md-filled-button type="submit">Enregistrer</md-filled-button>
                <md-outlined-button type="button" data-idea-md="${escapeAttr(String(idea.id))}">Copier Markdown</md-outlined-button>
                <md-outlined-button type="button" data-idea-download="${escapeAttr(String(idea.id))}">Telecharger .md</md-outlined-button>
                <md-outlined-button type="button" data-idea-notion="${escapeAttr(String(idea.id))}">Ouvrir Notion</md-outlined-button>
                <md-outlined-button type="button" data-idea-linear="${escapeAttr(String(idea.id))}">Ouvrir Linear</md-outlined-button>
                <md-text-button type="button" data-idea-delete="${escapeAttr(String(idea.id))}">Supprimer</md-text-button>
            </div>
        </form>`;
}
