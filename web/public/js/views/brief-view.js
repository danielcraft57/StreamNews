import { escapeHtml, escapeAttr } from '../utils/dom.js';

export function renderBrief(brief) {
    if (!brief || !Array.isArray(brief.topics)) {
        return '<p class="feed-empty">Brief indisponible. Clique Generer.</p>';
    }
    const topics = brief.topics || [];
    const period = brief.period || (brief.day ? 'daily' : 'weekly');
    const emptyHint = period === 'daily'
        ? 'Rien a briefer aujourd\'hui. Ajoute des sources puis regenerer.'
        : 'Rien a briefer cette semaine. Ajoute des sources radar puis regenerer.';
    if (!topics.length) {
        return `
            <div class="sources-empty">
                <p class="feed-empty">${emptyHint}</p>
            </div>`;
    }
    return `
        <p class="pane-sub">${escapeHtml(brief.headline || '')} · maj ${escapeHtml(brief.computed_at || brief.generated_at || '')}</p>
        <div class="brief-topics">
            ${topics.map((t, idx) => {
                const titles = Array.isArray(t.sample_titles) ? t.sample_titles.slice(0, 3) : [];
                const term = t.term || t.theme || 'Sujet';
                return `
                <article class="brief-card" data-brief-term="${escapeAttr(String(term))}">
                    <header>
                        <span class="trend-kind">${escapeHtml(t.kind || 'topic')}</span>
                        <strong>${idx + 1}. ${escapeHtml(term)}</strong>
                    </header>
                    <div class="trend-row-meta">
                        <span>score ${t.score || 0}</span>
                        <span>${t.article_count || 0} arts</span>
                        ${t.theme ? `<span>${escapeHtml(t.theme)}</span>` : ''}
                    </div>
                    ${titles.length ? `<ul>${titles.map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul>` : ''}
                    <div class="brief-card-actions">
                        <button type="button" class="feed-tool-btn" data-brief-search="${escapeAttr(String(term))}">Chercher</button>
                        <button type="button" class="feed-tool-btn" data-brief-idea="${escapeAttr(String(term))}" data-brief-theme="${escapeAttr(String(t.theme || ''))}">Creer fiche</button>
                    </div>
                </article>`;
            }).join('')}
        </div>`;
}
