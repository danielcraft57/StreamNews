import { normalizeComparableText } from '../utils/dom.js';

export function cleanArticleTitle(title, site) {
    let t = String(title || '').trim();
    if (!t) return 'Sans titre';
    const suffixes = [];
    if (site?.site_title) suffixes.push(site.site_title);
    try {
        const host = new URL(site?.url || '').hostname.replace(/^www\./, '');
        if (host) suffixes.push(host);
    } catch (_) { /* ignore */ }
    suffixes.push("METZ TECHNO'PÔLES", 'METZ TECHNO’PÔLES');
    for (const s of suffixes) {
        if (!s) continue;
        const re = new RegExp(`\\s*[|–—-]\\s*${s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`, 'i');
        t = t.replace(re, '').trim();
    }
    return t || String(title || '').trim();
}

export function isNoiseArticle(article) {
    const feed = String(article.feed_url || '').toLowerCase();
    const title = String(article.title || '').trim();
    const titleLow = title.toLowerCase();
    if (feed.includes('/comments/') || feed.includes('comments/feed')) return true;
    if (titleLow.startsWith('commentaires sur ')) return true;
    if (titleLow.startsWith('comments on ')) return true;
    if (/^par\s*:/i.test(title)) return true;
    if (title.length < 8) return true;
    if (/^hello world$/i.test(titleLow)) return true;
    const summary = String(article.summary || '').trim();
    if (summary.length > 0 && summary.length < 40 && /hello world|itstitle|here/i.test(summary)) {
        return true;
    }
    return false;
}

export function isUsefulKeyword(kw) {
    const s = String(kw || '')
        .trim()
        .replace(/[\u2018\u2019\u02BC]/g, "'")
        .replace(/\s+/g, ' ');
    if (s.length < 3 || s.length > 42) return false;
    const words = s.split(' ');
    if (words.length > 3) return false;
    const low = s.toLowerCase();
    if (/\b(c'?est|m'?appelle|je suis|nous sommes|vous etes|vous êtes|qui êtes|qui etes|presentez|présentez|parlez|rôle|role|responsable de)\b/i.test(low)) {
        return false;
    }
    if (/^(le|la|les|un|une|des|du|de|d'|l'|et|ou|en|au|aux)\b/i.test(low) && words.length === 1) {
        return false;
    }
    if (/[,:;!?]/.test(s)) return false;
    return true;
}

export function normalizeKeywords(list, limit = 6) {
    const out = [];
    const seen = [];
    for (const raw of list || []) {
        const kw = String(raw || '').trim().replace(/\s+/g, ' ');
        if (!isUsefulKeyword(kw)) continue;
        const key = normalizeComparableText(kw);
        if (!key) continue;
        if (seen.some((s) => s === key || s.includes(key) || key.includes(s))) continue;
        seen.push(key);
        out.push(kw);
        if (out.length >= limit) break;
    }
    return out;
}

export function articleMeta(article) {
    const meta = article?.article_meta;
    return meta && typeof meta === 'object' ? meta : {};
}
