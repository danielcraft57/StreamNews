export function parseRssFeeds(value) {
    if (!value) return [];
    if (Array.isArray(value)) return value;
    if (typeof value === 'string') {
        try {
            const parsed = JSON.parse(value);
            return Array.isArray(parsed) ? parsed : [];
        } catch (_) {
            return [];
        }
    }
    return [];
}

export function shortSiteLabel(site) {
    if (!site) return 'Source';
    const title = String(site.site_title || '').trim();
    if (title && title.length <= 28) return title;
    try {
        return new URL(site.url).hostname.replace(/^www\./, '');
    } catch (_) {
        return title.slice(0, 28) || 'Source';
    }
}

export function siteStatusTone(status) {
    if (status === 'completed' || status === 'ok') return 'ok';
    if (status === 'error') return 'error';
    if (status === 'analyzing' || status === 'running' || status === 'ingesting' || status === 'pending') {
        return 'running';
    }
    return 'ok';
}

export function siteStatusLabel(status) {
    const map = {
        pending: 'En attente',
        analyzing: 'En cours',
        ingesting: 'Import RSS',
        completed: 'OK',
        ok: 'OK',
        error: 'Erreur',
        cancelled: 'Arrete',
        cancelling: 'Arret...',
    };
    return map[status] || status || '—';
}
