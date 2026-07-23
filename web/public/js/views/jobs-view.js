import { escapeHtml, escapeAttr } from '../utils/dom.js';
import { formatRelativeTime } from '../utils/time.js';
import { jobStatusLabel, jobTypeIcon, jobTypeLabel } from '../models/job.js';

/**
 * Liste Jobs (maquette 08).
 */
export function renderJobsList(jobs, selectedJobId) {
    if (!jobs?.length) {
        return '<p class="feed-empty">Aucun job pour ce filtre. Lance une analyse ou un enrichissement.</p>';
    }

    return jobs.map((job) => {
        const selected = job.id === selectedJobId ? ' is-selected' : '';
        const status = job.status || 'done';
        const when = formatRelativeTime(job.at) || new Date(job.at).toLocaleString('fr-FR');
        const icon = jobTypeIcon(job.type);
        return `
            <button type="button" class="job-row${selected}" data-job-id="${escapeAttr(job.id)}">
                <div class="job-row-main">
                    <span class="job-type-icon" aria-hidden="true"><i class="fas ${escapeAttr(icon)}"></i></span>
                    <span class="job-row-text">
                        <span class="job-row-top">
                            <span class="job-type">${escapeHtml(jobTypeLabel(job.type))}</span>
                            <span class="job-status-badge ${escapeAttr(status)}">${escapeHtml(jobStatusLabel(status))}</span>
                        </span>
                        <strong class="job-row-title">${escapeHtml(job.title)}</strong>
                        <span class="pane-sub">${escapeHtml(job.detail || when)}</span>
                    </span>
                </div>
                <span class="job-row-chevron" aria-hidden="true"><i class="fas fa-chevron-right"></i></span>
            </button>`;
    }).join('');
}

/**
 * Panneau detail d'un job.
 */
export function renderJobsDetail(job) {
    if (!job) {
        return '<p class="feed-empty">Selectionne un job pour voir le detail.</p>';
    }

    const status = job.status || 'done';
    const when = new Date(job.at).toLocaleString('fr-FR');
    const icon = jobTypeIcon(job.type);
    const cur = Number(job.progressCurrent);
    const tot = Number(job.progressTotal);
    const hasProgress = Number.isFinite(cur) && Number.isFinite(tot) && tot > 0;
    const pct = hasProgress ? Math.min(100, Math.round((cur / tot) * 100)) : (status === 'running' ? null : 100);

    const progressBlock = status === 'running' || hasProgress
        ? `
            <div class="jobs-progress-block">
                <div class="jobs-progress-label">
                    <span>Avancement</span>
                    <span>${hasProgress ? `${cur} / ${tot}` : (status === 'running' ? 'En cours…' : '100%')}</span>
                </div>
                <div class="jobs-progress-track" role="progressbar" aria-valuenow="${pct ?? 0}" aria-valuemin="0" aria-valuemax="100">
                    <div class="jobs-progress-fill${pct == null ? ' is-indeterminate' : ''}" style="${pct != null ? `width:${pct}%` : ''}"></div>
                </div>
            </div>`
        : '';

    return `
        <div class="jobs-detail-head">
            <span class="job-type-icon job-type-icon-lg" aria-hidden="true"><i class="fas ${escapeAttr(icon)}"></i></span>
            <div>
                <p class="job-type">${escapeHtml(jobTypeLabel(job.type))}</p>
                <h3 class="jobs-detail-title">${escapeHtml(job.title)}</h3>
                <span class="job-status-badge ${escapeAttr(status)}">${escapeHtml(jobStatusLabel(status))}</span>
            </div>
        </div>
        <dl class="jobs-detail-grid">
            <div><dt>Detail</dt><dd>${escapeHtml(job.detail || '—')}</dd></div>
            <div><dt>Derniere mise a jour</dt><dd>${escapeHtml(when)}</dd></div>
            ${job.siteId ? `<div><dt>Source</dt><dd>#${escapeHtml(String(job.siteId))}</dd></div>` : ''}
        </dl>
        ${progressBlock}
        ${job.siteId
            ? `<md-filled-button type="button" class="jobs-open-source" data-open-job-site="${escapeAttr(String(job.siteId))}">Ouvrir la source</md-filled-button>`
            : ''}
    `;
}
