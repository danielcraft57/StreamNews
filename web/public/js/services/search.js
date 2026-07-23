/**
 * Moteur de recherche articles — score local + API.
 */

function tokenize(q) {
    return String(q || '')
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .split(/[^\p{L}\p{N}]+/u)
        .filter((t) => t.length >= 2);
}

function scoreArticle(article, tokens) {
    if (!tokens.length) return 0;
    const title = String(article.title || '').toLowerCase();
    const summary = String(article.summary || '').toLowerCase();
    const source = String(article.source || article._siteLabel || '').toLowerCase();
    const author = String(article.author || '').toLowerCase();
    let score = 0;
    for (const t of tokens) {
        if (title.includes(t)) score += title.startsWith(t) ? 12 : 8;
        if (source.includes(t)) score += 4;
        if (author.includes(t)) score += 3;
        if (summary.includes(t)) score += 2;
    }
    return score;
}

/**
 * Recherche locale (fallback) sur une liste d'articles deja charges.
 */
export function searchLocal(articles, query, { limit = 40 } = {}) {
    const tokens = tokenize(query);
    if (!tokens.length) return [];
    return (articles || [])
        .map((a) => ({ article: a, score: scoreArticle(a, tokens) }))
        .filter((x) => x.score > 0)
        .sort((a, b) => b.score - a.score || String(b.article.published_at || '').localeCompare(String(a.article.published_at || '')))
        .slice(0, limit)
        .map((x) => x.article);
}

/**
 * Recherche via API, avec fallback local.
 */
export async function searchArticles(query, {
    siteId = null,
    limit = 40,
    localArticles = [],
    api = null,
} = {}) {
    const q = String(query || '').trim();
    if (q.length < 2) return { query: q, articles: [], source: 'none' };

    if (api?.searchArticles) {
        try {
            const data = await api.searchArticles(q, { siteId, limit });
            const articles = Array.isArray(data.articles) ? data.articles : [];
            if (articles.length || !localArticles.length) {
                return { query: q, articles, source: 'api', count: data.count ?? articles.length };
            }
        } catch (_) {
            /* fallback local */
        }
    }

    let pool = localArticles || [];
    if (siteId) {
        pool = pool.filter((a) => Number(a.site_id || a._siteId) === Number(siteId));
    }
    const articles = searchLocal(pool, q, { limit });
    return { query: q, articles, source: 'local', count: articles.length };
}

export function highlightMatch(text, query) {
    const raw = String(text || '');
    const q = String(query || '').trim();
    if (!q || raw.length < 2) return escapeBasic(raw);
    try {
        const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'ig');
        return escapeBasic(raw).replace(re, '<mark>$1</mark>');
    } catch (_) {
        return escapeBasic(raw);
    }
}

function escapeBasic(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
