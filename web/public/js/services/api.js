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
    refreshAllFeeds: () => request('/api/feeds/refresh-all', { method: 'POST' }),
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
    getTrends: ({ days = 30, kind = 'all', siteId = null, collectionId = null, limit = 40, refresh = false } = {}) => {
        const params = new URLSearchParams({
            days: String(days),
            kind: String(kind || 'all'),
            limit: String(limit),
        });
        if (siteId) params.set('site_id', String(siteId));
        if (collectionId) params.set('collection_id', String(collectionId));
        if (refresh) params.set('refresh', '1');
        return request(`/api/trends?${params}`);
    },
    refreshTrends: ({ days = 30, siteId = null, collectionId = null, limit = 50 } = {}) => {
        const params = new URLSearchParams({
            days: String(days),
            limit: String(limit),
        });
        if (siteId) params.set('site_id', String(siteId));
        if (collectionId) params.set('collection_id', String(collectionId));
        return request(`/api/trends/refresh?${params}`, { method: 'POST' });
    },
    getRadar: ({ days = 30, theme = 'all', limit = 40, refresh = false, collectionId = null } = {}) => {
        const params = new URLSearchParams({
            days: String(days),
            theme: String(theme || 'all'),
            limit: String(limit),
        });
        if (refresh) params.set('refresh', '1');
        if (collectionId) params.set('collection_id', String(collectionId));
        return request(`/api/radar?${params}`);
    },
    refreshRadar: ({ days = 30, limit = 40, collectionId = null } = {}) => {
        const params = new URLSearchParams({
            days: String(days),
            limit: String(limit),
        });
        if (collectionId) params.set('collection_id', String(collectionId));
        return request(`/api/radar/refresh?${params}`, { method: 'POST' });
    },
    getWatchKeywords: () => request('/api/watchlist/keywords'),
    addWatchKeyword: (keyword) =>
        request('/api/watchlist/keywords', { method: 'POST', body: JSON.stringify({ keyword }) }),
    deleteWatchKeyword: (id) =>
        request(`/api/watchlist/keywords/${id}`, { method: 'DELETE' }),
    getWatchAlerts: ({ days = 7, limit = 40, refresh = false } = {}) => {
        const params = new URLSearchParams({ days: String(days), limit: String(limit) });
        if (refresh) params.set('refresh', '1');
        return request(`/api/watchlist/alerts?${params}`);
    },
    refreshWatchlist: ({ days = 7 } = {}) =>
        request(`/api/watchlist/refresh?days=${days}`, { method: 'POST' }),
    getWeeklyBrief: ({ week = null, refresh = false } = {}) => {
        const params = new URLSearchParams();
        if (week) params.set('week', week);
        if (refresh) params.set('refresh', '1');
        const q = params.toString();
        return request(`/api/brief/weekly${q ? `?${q}` : ''}`);
    },
    refreshWeeklyBrief: ({ week = null } = {}) => {
        const params = new URLSearchParams();
        if (week) params.set('week', week);
        const q = params.toString();
        return request(`/api/brief/weekly/refresh${q ? `?${q}` : ''}`, { method: 'POST' });
    },
    getDailyBrief: ({ day = null, refresh = false, auto = true } = {}) => {
        const params = new URLSearchParams();
        if (day) params.set('day', day);
        if (refresh) params.set('refresh', '1');
        if (!auto) params.set('auto', 'false');
        const q = params.toString();
        return request(`/api/brief/daily${q ? `?${q}` : ''}`);
    },
    refreshDailyBrief: ({ day = null } = {}) => {
        const params = new URLSearchParams();
        if (day) params.set('day', day);
        const q = params.toString();
        return request(`/api/brief/daily/refresh${q ? `?${q}` : ''}`, { method: 'POST' });
    },
    getCollections: () => request('/api/collections'),
    getCollection: (id) => request(`/api/collections/${id}`),
    addCollectionSite: (id, siteId) =>
        request(`/api/collections/${id}/sites`, {
            method: 'POST',
            body: JSON.stringify({ site_id: siteId }),
        }),
    removeCollectionSite: (id, siteId) =>
        request(`/api/collections/${id}/sites/${siteId}`, { method: 'DELETE' }),
    getIdeas: ({ limit = 50 } = {}) => request(`/api/ideas?limit=${limit}`),
    createIdea: (body) => request('/api/ideas', { method: 'POST', body: JSON.stringify(body) }),
    createIdeaFromRadar: (body) =>
        request('/api/ideas/from-radar', { method: 'POST', body: JSON.stringify(body) }),
    getIdea: (id) => request(`/api/ideas/${id}`),
    updateIdea: (id, body) =>
        request(`/api/ideas/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    deleteIdea: (id) => request(`/api/ideas/${id}`, { method: 'DELETE' }),
    getIdeaMarkdown: (id) => request(`/api/ideas/${id}/markdown`),
    getArticle: (id) => request(`/api/articles/${id}`),
    enrichArticle: (id, force = false) =>
        request(`/api/articles/${id}/enrich${force ? '?force=1' : ''}`, { method: 'POST' }),
    analyzeArticle: (id, force = false) =>
        request(`/api/articles/${id}/analyze${force ? '?force=1' : ''}`, { method: 'POST' }),
};
