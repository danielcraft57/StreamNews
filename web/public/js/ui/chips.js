import { escapeAttr, escapeHtml } from '../utils/dom.js';

/** Tone Material chip → CSS class. */
export function entityTone(label) {
    const l = String(label || '').toUpperCase();
    if (l === 'PER' || l === 'PERSON') return 'tone-per';
    if (l === 'ORG' || l === 'ORGANIZATION') return 'tone-org';
    if (l === 'LOC' || l === 'GPE' || l === 'LOCATION') return 'tone-loc';
    return 'tone-org';
}

/**
 * Chips mots-cles (Material assist-chip).
 * @param {string[]} keywords
 */
export function renderKeywordChips(keywords = []) {
    if (!keywords.length) return '';
    return `<div class="sn-chips" role="list">${keywords.map((kw, i) => {
        const tone = i % 2 ? 'tone-teal' : 'tone-amber';
        return `<md-assist-chip role="listitem" class="${tone}" label="${escapeAttr(kw)}"></md-assist-chip>`;
    }).join('')}</div>`;
}

/**
 * Chips entites NER.
 * @param {{text:string,label?:string}[]} entities
 */
export function renderEntityChips(entities = []) {
    if (!entities.length) return '';
    return `<div class="sn-chips" role="list">${entities.map((ent) => {
        const tone = entityTone(ent.label);
        const label = ent.text || '';
        return `<md-assist-chip role="listitem" class="${tone}" label="${escapeAttr(label)}" title="${escapeAttr(ent.label || '')}"></md-assist-chip>`;
    }).join('')}</div>`;
}

/** Fallback HTML chips (sans Material) — utile pour tests / print. */
export function renderPlainChips(keywords = []) {
    if (!keywords.length) return '';
    return `<div class="feed-item-chips">${keywords.map((kw, i) =>
        `<span class="feed-chip${i > 0 ? ' teal' : ''}">${escapeHtml(kw)}</span>`
    ).join('')}</div>`;
}
