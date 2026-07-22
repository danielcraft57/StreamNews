/** Client REST StreamNews (seul endroit pour fetch API). */

async function request(path, options = {}) {
    const res = await fetch(path, {
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        throw new Error(data.error || data.detail || `Erreur HTTP ${res.status}`);
    }
    return data;
}

export const api = {
    getSites: () => request('/api/sites'),
    getSite: (id) => request(`/api/sites/${id}`),
    deleteSite: (id) => request(`/api/sites/${id}`, { method: 'DELETE' }),
    analyze: (body) => request('/api/analyze', { method: 'POST', body: JSON.stringify(body) }),
    stopSite: (id) => request(`/api/sites/${id}/stop`, { method: 'POST' }),
    ingestArticles: (id) => request(`/api/sites/${id}/ingest-articles`, { method: 'POST' }),
    enrichArticles: (id, limit = 50) =>
        request(`/api/sites/${id}/enrich-articles?limit=${limit}`, { method: 'POST' }),
    analyzeArticles: (id, limit = 50) =>
        request(`/api/sites/${id}/analyze-articles?limit=${limit}`, { method: 'POST' }),
    getSiteArticles: (id, limit = 100) =>
        request(`/api/sites/${id}/articles?limit=${limit}`),
    searchArticles: (q, { siteId = null, limit = 40 } = {}) => {
        const params = new URLSearchParams({ q: String(q || ''), limit: String(limit) });
        if (siteId) params.set('site_id', String(siteId));
        return request(`/api/articles/search?${params}`);
    },
    getTrends: ({ days = 30, kind = 'all', siteId = null, limit = 40, refresh = false } = {}) => {
        const params = new URLSearchParams({
            days: String(days),
            kind: String(kind || 'all'),
            limit: String(limit),
        });
        if (siteId) params.set('site_id', String(siteId));
        if (refresh) params.set('refresh', '1');
        return request(`/api/trends?${params}`);
    },
    refreshTrends: ({ days = 30, siteId = null, limit = 50 } = {}) => {
        const params = new URLSearchParams({
            days: String(days),
            limit: String(limit),
        });
        if (siteId) params.set('site_id', String(siteId));
        return request(`/api/trends/refresh?${params}`, { method: 'POST' });
    },
    getRadar: ({ days = 30, theme = 'all', limit = 40, refresh = false } = {}) => {
        const params = new URLSearchParams({
            days: String(days),
            theme: String(theme || 'all'),
            limit: String(limit),
        });
        if (refresh) params.set('refresh', '1');
        return request(`/api/radar?${params}`);
    },
    refreshRadar: ({ days = 30, limit = 40 } = {}) => {
        const params = new URLSearchParams({
            days: String(days),
            limit: String(limit),
        });
        return request(`/api/radar/refresh?${params}`, { method: 'POST' });
    },
    getArticle: (id) => request(`/api/articles/${id}`),
    enrichArticle: (id, force = false) =>
        request(`/api/articles/${id}/enrich${force ? '?force=1' : ''}`, { method: 'POST' }),
    analyzeArticle: (id, force = false) =>
        request(`/api/articles/${id}/analyze${force ? '?force=1' : ''}`, { method: 'POST' }),
};
