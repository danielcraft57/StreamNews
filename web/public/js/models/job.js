export function createJob(partial = {}) {
    return {
        id: partial.id || `job-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        type: partial.type || 'Crawl',
        title: partial.title || 'Tache',
        detail: partial.detail || '',
        status: partial.status || 'running',
        siteId: partial.siteId || null,
        at: partial.at || new Date().toISOString(),
        progressCurrent: partial.progressCurrent ?? null,
        progressTotal: partial.progressTotal ?? null,
    };
}

export function jobStatusLabel(status) {
    if (status === 'running') return 'En cours';
    if (status === 'error') return 'Erreur';
    return 'Termine';
}

export function jobTypeLabel(type) {
    const t = String(type || '').toLowerCase();
    if (t === 'enrich') return 'Enrich';
    if (t === 'nlp' || t === 'analyse') return 'NLP';
    return 'Crawl';
}

export function jobTypeIcon(type) {
    const t = String(type || '').toLowerCase();
    if (t === 'enrich') return 'fa-database';
    if (t === 'nlp' || t === 'analyse') return 'fa-brain';
    return 'fa-globe';
}
