import { escapeHtml, escapeAttr } from '../utils/dom.js';
import { renderKeywordChips, renderEntityChips } from '../ui/chips.js';

/**
 * Construit le HTML du lecteur (sans binding d'events).
 * @param {object} article
 * @param {object} ctx
 */
export function buildReaderHtml(article, ctx = {}) {
    const {
        loading = false,
        loadingAnalysis = false,
        backButtonHtml = '',
        heroHtml = '',
        bodyHtml = '',
        galleryHtml = '',
        summaryHtml = '',
        entities = [],
        keywords = [],
        sourceName = 'Source',
        published = '',
        isFavorite = false,
        isRead = false,
        showSummaryFirst = true,
    } = ctx;

    let entitiesBlock = '';
    if (entities.length) {
        entitiesBlock = `<div class="reader-entities-title">Entites cles</div>
            <div class="reader-entities-row">${renderEntityChips(entities)}</div>`;
    } else if (keywords.length) {
        entitiesBlock = `<div class="reader-entities-title">Mots-cles</div>
            <div class="reader-entities-row">${renderKeywordChips(keywords)}</div>`;
    }

    const favLabel = isFavorite ? 'Retirer des favoris' : 'Ajouter aux favoris';
    const readLabel = isRead ? 'Marquer non lu' : 'Marquer comme lu';
    const favIcon = isFavorite ? 'star' : 'star_border';
    const readIcon = isRead ? 'check_circle' : 'radio_button_unchecked';

    const summaryBox = `<div class="reader-summary-box">
        <strong>Resume IA</strong>
        ${summaryHtml}
    </div>`;

    const mainStack = showSummaryFirst
        ? `${summaryBox}${entitiesBlock}${bodyHtml}`
        : `${bodyHtml}${summaryBox}${entitiesBlock}`;

    return `
        ${backButtonHtml}
        <div class="reader-toolbar">
            <md-text-button type="button" data-reader-action="favorite" class="${isFavorite ? 'is-on' : ''}">
                <md-icon slot="icon">${favIcon}</md-icon>
                ${escapeHtml(favLabel)}
            </md-text-button>
            <md-text-button type="button" data-reader-action="read" class="${isRead ? 'is-on' : ''}">
                <md-icon slot="icon">${readIcon}</md-icon>
                ${escapeHtml(readLabel)}
            </md-text-button>
            <md-text-button type="button" data-reader-action="share">
                <md-icon slot="icon">share</md-icon>
                Partager
            </md-text-button>
        </div>
        <div class="reader-content">
            <div class="reader-source-line">${escapeHtml(sourceName)} <span>· ${escapeHtml(published)}</span></div>
            <h1 class="reader-title">${escapeHtml(article.title || 'Sans titre')}</h1>
            ${heroHtml}
            ${mainStack}
            ${galleryHtml}
            <div class="reader-actions">
                <a href="${escapeAttr(article.link || '#')}" target="_blank" rel="noopener noreferrer">Ouvrir l'original</a>
                ${article.enrich_status === 'ok' ? `
                    · <md-outlined-button type="button" data-reenrich="${article.id}">Relire la page</md-outlined-button>
                ` : ''}
                · <md-outlined-button type="button" data-reanalyze="${article.id}">Reanalyser</md-outlined-button>
            </div>
            ${loading ? '' : ''}
            ${loadingAnalysis ? '' : ''}
        </div>
    `;
}

export function buildSummaryHtml({ loadingAnalysis, analysisPending, sumyBlock, chapo, escapeHtml: esc }) {
    const escape = esc || escapeHtml;
    if (loadingAnalysis || analysisPending) {
        return `<p>${escape('Analyse en cours…')}</p>`;
    }
    if (sumyBlock?.status === 'ok') {
        const sentences = Array.isArray(sumyBlock.sentences)
            ? sumyBlock.sentences.map((s) => String(s).trim()).filter(Boolean)
            : [];
        if (sentences.length) {
            return sentences.slice(0, 3).map((s) => `<p>${escape(s)}</p>`).join('');
        }
        if (sumyBlock.summary) {
            return `<p>${escape(String(sumyBlock.summary))}</p>`;
        }
    }
    return `<p>${escape(chapo || 'Resume indisponible pour le moment.')}</p>`;
}

export function buildBodyHtml({ loading, article, chapo, preparedHtml, escapeHtml: esc }) {
    const escape = esc || escapeHtml;
    if (loading) return `<p class="reader-meta">Enrichissement en cours…</p>`;
    if (article.enrich_status === 'error') {
        return `<p class="reader-meta">Enrichissement echoue: ${escape(article.enrich_error || 'erreur')}</p>`;
    }
    if (preparedHtml) return `<div class="reader-body">${preparedHtml}</div>`;
    if (article.content_text) {
        return `<div class="reader-body"><p>${escape(article.content_text).replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>')}</p></div>`;
    }
    if (chapo) return `<p class="reader-chapo">${escape(chapo)}</p>`;
    return '';
}
