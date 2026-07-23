import { escapeHtml, escapeAttr } from '../utils/dom.js';

const INTENT_LABEL = {
    id_pay: 'Pret a payer',
    looking_for: 'Cherche une solution',
    alternative_to: 'Alternative',
    wish_existed: 'Souhaite que ca existe',
    frustrated: 'Frustration',
    need_tool: 'Besoin outil',
    build_in_public: 'Build in public',
    launch: 'Lancement',
    ask_hn: 'Ask HN',
    pricing_pain: 'Pricing',
    self_host_pain: 'Self-host',
};

const THEME_LABEL = {
    saas: 'SaaS',
    devtools: 'Devtools',
    ai: 'IA',
    billing: 'Billing',
    auth: 'Auth',
    'self-host': 'Self-host',
    'open-source': 'Open source',
    mvp: 'MVP',
    automation: 'Automation',
    general: 'General',
};

/** Prefere des feeds RSS directs quand on les connait (moins de crawl homepage). */
export const RECOMMENDED_SOURCES = [
    { id: 'hn', label: 'Hacker News', hint: 'RSS frontpage', url: 'https://hnrss.org/frontpage' },
    { id: 'hn-ask', label: 'HN Ask', hint: 'Ask HN', url: 'https://hnrss.org/ask' },
    { id: 'hn-show', label: 'HN Show', hint: 'Show HN', url: 'https://hnrss.org/show' },
    { id: 'indiehackers', label: 'Indie Hackers', hint: 'Feed posts', url: 'https://www.indiehackers.com/feed.xml' },
    { id: 'ph', label: 'Product Hunt', hint: 'Feed launches', url: 'https://www.producthunt.com/feed' },
    { id: 'devto', label: 'DEV Community', hint: 'RSS global', url: 'https://dev.to/feed' },
    { id: 'betalist', label: 'BetaList', hint: 'Startups early', url: 'https://betalist.com/feed.rss' },
    { id: 'changelog-gh', label: 'GitHub Blog', hint: 'RSS', url: 'https://github.blog/feed/' },
    { id: 'stripe', label: 'Stripe Blog', hint: 'Billing / SaaS', url: 'https://stripe.com/blog/feed.rss' },
    { id: 'vercel', label: 'Vercel Blog', hint: 'Atom DX', url: 'https://vercel.com/atom' },
    { id: 'supabase', label: 'Supabase Blog', hint: 'RSS', url: 'https://supabase.com/rss.xml' },
    { id: 'cloudflare', label: 'Cloudflare Blog', hint: 'RSS', url: 'https://blog.cloudflare.com/rss/' },
];

export const COMPETITOR_SOURCES = RECOMMENDED_SOURCES.filter((s) =>
    ['stripe', 'vercel', 'supabase', 'cloudflare', 'changelog-gh'].includes(s.id)
);

function scorePartBars(br = {}) {
    const intent = Number(br.intent) || 0;
    const frequency = Number(br.frequency) || 0;
    const novelty = Number(br.novelty) || 0;
    const max = Math.max(intent, frequency, novelty, 1);
    const rows = [
        { key: 'Intent', val: intent },
        { key: 'Frequence', val: frequency },
        { key: 'Nouveaute', val: novelty },
    ];
    return `
        <div class="radar-score-parts" data-testid="radar-score-parts">
            <h4>Decomposition du score</h4>
            ${rows.map((r) => {
                const pct = Math.max(4, Math.round((r.val / max) * 100));
                return `
                <div class="radar-score-row">
                    <span>${escapeHtml(r.key)}</span>
                    <div class="trend-bar" aria-hidden="true"><span style="width:${pct}%"></span></div>
                    <strong>${r.val}</strong>
                </div>`;
            }).join('')}
        </div>`;
}

export function renderRecommendedSources(sources = RECOMMENDED_SOURCES) {
    if (!sources?.length) return '';
    return `
        <div class="radar-pack" data-testid="radar-pack">
            <h4>Sources recommandees</h4>
            <p class="pane-sub">Feeds RSS directs quand possible (pack sequentiel).</p>
            <md-filled-button type="button" data-radar-pack-all="1" style="width:100%;margin:8px 0 12px">
                Ajouter tout le pack
            </md-filled-button>
            <div class="radar-pack-list">
                ${sources.map((s) => `
                    <button type="button" class="radar-pack-item" data-radar-source-url="${escapeAttr(s.url)}" data-radar-source-id="${escapeAttr(s.id)}">
                        <strong>${escapeHtml(s.label)}</strong>
                        <span class="pane-sub">${escapeHtml(s.hint || '')}</span>
                    </button>
                `).join('')}
            </div>
        </div>`;
}

export function renderRadarList(ideas, { selectedTheme = null, maxScore = 1 } = {}) {
    if (!ideas?.length) {
        return `
            <div class="sources-empty">
                <p class="feed-empty">Pas encore de signaux idees.</p>
                <p class="pane-sub">Ajoute le pack HN / Indie Hackers, puis <strong>Recalculer</strong>.</p>
            </div>`;
    }
    const top = Number(maxScore) || Math.max(...ideas.map((i) => Number(i.score) || 0), 1);
    return ideas.map((idea) => {
        const selected = idea.theme === selectedTheme ? ' is-selected' : '';
        const score = Number(idea.score) || 0;
        const pct = Math.max(6, Math.round((score / top) * 100));
        const theme = THEME_LABEL[idea.theme] || idea.theme || 'Idee';
        const sample = Array.isArray(idea.sample_titles) ? idea.sample_titles[0] : '';
        return `
            <button type="button" class="radar-row${selected}" data-radar-theme="${escapeAttr(idea.theme)}">
                <div class="trend-row-top">
                    <strong class="trend-term">${escapeHtml(idea.title || theme)}</strong>
                    <span class="trend-kind">${escapeHtml(theme)}</span>
                </div>
                <div class="trend-row-meta">
                    <span>${idea.article_count || 0} article${(idea.article_count || 0) > 1 ? 's' : ''}</span>
                    <span>${idea.intent_count || 0} intent</span>
                    <span>score ${score}</span>
                </div>
                <div class="trend-bar" aria-hidden="true"><span style="width:${pct}%"></span></div>
                ${sample ? `<span class="pane-sub trend-sample">${escapeHtml(sample)}</span>` : ''}
            </button>`;
    }).join('');
}

export function renderRadarDetail(idea) {
    if (!idea) {
        return '<p class="feed-empty">Selectionne une idee pour voir les preuves.</p>';
    }
    const theme = THEME_LABEL[idea.theme] || idea.theme || '';
    const intents = Array.isArray(idea.intents) ? idea.intents : [];
    const titles = Array.isArray(idea.sample_titles) ? idea.sample_titles : [];
    const snippets = Array.isArray(idea.sample_snippets) ? idea.sample_snippets : [];
    const evidence = Array.isArray(idea.evidence_ids) ? idea.evidence_ids : [];
    const br = idea.score_breakdown || {};
    const searchQ = intents[0]
        ? (INTENT_LABEL[intents[0]] || intents[0])
        : (THEME_LABEL[idea.theme] || idea.theme || idea.title || '');

    return `
        <p class="job-type">Radar · ${escapeHtml(theme)}</p>
        <h3 class="jobs-detail-title">${escapeHtml(idea.title || theme)}</h3>
        <dl class="jobs-detail-grid">
            <div><dt>Score</dt><dd>${idea.score || 0}</dd></div>
            <div><dt>Intent</dt><dd>${br.intent ?? '—'}</dd></div>
            <div><dt>Frequence</dt><dd>${br.frequency ?? '—'}</dd></div>
            <div><dt>Nouveaute</dt><dd>${br.novelty ?? '—'}</dd></div>
            <div><dt>Articles</dt><dd>${idea.article_count || 0}</dd></div>
            <div><dt>Fenetre</dt><dd>${idea.window_days || '?'} j</dd></div>
        </dl>
        ${scorePartBars(br)}
        ${intents.length ? `
            <div class="radar-intents">
                <h4>Signaux</h4>
                <div class="radar-intent-chips">
                    ${intents.map((k) => `<span class="radar-intent-chip">${escapeHtml(INTENT_LABEL[k] || k)}</span>`).join('')}
                </div>
            </div>` : ''}
        ${snippets.length ? `
            <div class="trends-samples">
                <h4>Preuves</h4>
                <ul>${snippets.map((s) => `<li>${escapeHtml(s)}</li>`).join('')}</ul>
            </div>` : ''}
        ${titles.length ? `
            <div class="trends-samples">
                <h4>Titres</h4>
                <ul>${titles.map((t) => `<li>${escapeHtml(t)}</li>`).join('')}</ul>
            </div>` : ''}
        <div class="radar-detail-actions">
            <md-filled-button type="button" data-radar-search="${escapeAttr(String(searchQ))}" style="width:100%">
                Chercher dans le feed
            </md-filled-button>
            <md-filled-tonal-button type="button" data-radar-create-idea="1" style="width:100%;margin-top:8px">
                Creer une fiche idee
            </md-filled-tonal-button>
            ${evidence[0] ? `
            <md-outlined-button type="button" data-radar-article="${escapeAttr(String(evidence[0]))}" style="width:100%;margin-top:8px">
                Ouvrir un article preuve
            </md-outlined-button>` : ''}
        </div>
    `;
}
