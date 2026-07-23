import { escapeHtml, escapeAttr } from '../utils/dom.js';

const KIND_LABEL = {
    keyword: 'Mot-cle',
    entity: 'Entite',
    yake: 'YAKE',
};

/**
 * Liste des tendances (maquette style Jobs/Sources).
 */
export function renderTrendsList(trends, { selectedTerm = null, maxScore = 1 } = {}) {
    if (!trends?.length) {
        return `
            <div class="sources-empty">
                <p class="feed-empty">Pas encore de tendances.</p>
                <p class="pane-sub">Clique <strong>Recalculer</strong> apres avoir analyse quelques articles (mots-cles / NLP).</p>
            </div>`;
    }

    const top = Number(maxScore) || Math.max(...trends.map((t) => Number(t.score) || 0), 1);

    return trends.map((t) => {
        const selected = t.term === selectedTerm ? ' is-selected' : '';
        const score = Number(t.score) || 0;
        const pct = Math.max(6, Math.round((score / top) * 100));
        const kind = KIND_LABEL[t.kind] || t.kind || 'Mot-cle';
        const samples = Array.isArray(t.sample_titles) ? t.sample_titles.slice(0, 2) : [];
        return `
            <button type="button" class="trend-row${selected}" data-trend-term="${escapeAttr(t.term)}" data-trend-kind="${escapeAttr(t.kind || '')}">
                <div class="trend-row-top">
                    <strong class="trend-term">${escapeHtml(t.term)}</strong>
                    <span class="trend-kind">${escapeHtml(kind)}</span>
                </div>
                <div class="trend-row-meta">
                    <span>${t.article_count || 0} article${(t.article_count || 0) > 1 ? 's' : ''}</span>
                    <span>score ${score}</span>
                </div>
                <div class="trend-bar" aria-hidden="true"><span style="width:${pct}%"></span></div>
                ${samples.length ? `<span class="pane-sub trend-sample">${escapeHtml(samples[0])}</span>` : ''}
            </button>`;
    }).join('');
}

export function renderTrendsDetail(trend) {
    if (!trend) {
        return '<p class="feed-empty">Selectionne une tendance pour voir le detail.</p>';
    }
    const kind = KIND_LABEL[trend.kind] || trend.kind || 'Mot-cle';
    const samples = Array.isArray(trend.sample_titles) ? trend.sample_titles : [];
    return `
        <p class="job-type">${escapeHtml(kind)}${trend.label ? ` · ${escapeHtml(trend.label)}` : ''}</p>
        <h3 class="jobs-detail-title">${escapeHtml(trend.term)}</h3>
        <dl class="jobs-detail-grid">
            <div><dt>Articles</dt><dd>${trend.article_count || 0}</dd></div>
            <div><dt>Score</dt><dd>${trend.score || 0}</dd></div>
            <div><dt>Fenetre</dt><dd>${trend.window_days || '?'} jours</dd></div>
        </dl>
        ${samples.length ? `
            <div class="trends-samples">
                <h4>Exemples</h4>
                <ul>${samples.map((s) => `<li>${escapeHtml(s)}</li>`).join('')}</ul>
            </div>` : ''}
        <md-filled-button type="button" data-trend-search="${escapeAttr(trend.term)}" style="width:100%">
            Chercher dans le feed
        </md-filled-button>
    `;
}
