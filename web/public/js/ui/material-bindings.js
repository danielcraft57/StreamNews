/**
 * Controllers Material pour dialog ajout source + reglages.
 * Decouple le DOM Material du monolithe.
 */
import { bus } from '../core/bus.js';

export function bindAddSourceDialog({ onSubmit, onStop, onReadFirst }) {
    const modal = document.getElementById('addSourceModal');
    if (!modal) return { open() {}, close() {} };

    const form = document.getElementById('analyzeForm');
    const open = () => {
        modal.hidden = false;
        modal.classList.add('open');
        setTimeout(() => document.getElementById('url')?.focus?.(), 40);
    };
    const close = ({ force = false } = {}) => {
        if (modal.dataset.busy === '1' && !force) {
            bus.emit('toast', { message: 'Analyse en cours — laisse le dialog ouvert', type: 'info' });
            return;
        }
        modal.classList.remove('open');
        modal.hidden = true;
    };

    document.body.addEventListener('click', (e) => {
        const openBtn = e.target.closest?.(
            '#openAddSource, #openAddSourceFromFeed, #emptyAddSource, #feedEmptyAddSource'
        );
        if (openBtn) open();
    });
    document.getElementById('closeAddSource')?.addEventListener('click', () => close());
    modal.addEventListener('click', (e) => {
        if (e.target === modal) close({ force: modal.dataset.busy !== '1' });
    });

    form?.addEventListener('submit', (e) => {
        e.preventDefault();
        const urlField = document.getElementById('url');
        const url = String(urlField?.value || '').trim();
        const maxPages = Number(document.getElementById('maxPages')?.value || 50);
        const depth = Number(document.getElementById('depth')?.value || 3);
        onSubmit?.({ url, maxPages, depth });
    });

    document.getElementById('stopAnalyzeBtn')?.addEventListener('click', () => onStop?.());
    document.getElementById('addSourceReadFirst')?.addEventListener('click', () => onReadFirst?.());

    bus.on('add-source:busy', (busy) => {
        modal.dataset.busy = busy ? '1' : '0';
        const progress = document.getElementById('addSourceProgress');
        const victory = document.getElementById('addSourceVictory');
        const formEl = document.getElementById('analyzeForm');
        const actions = document.getElementById('addSourceActions');
        if (busy) {
            if (formEl) formEl.hidden = true;
            if (actions) actions.hidden = true;
            if (progress) progress.hidden = false;
            if (victory) victory.hidden = true;
        } else if (progress) {
            progress.hidden = true;
            if (actions) actions.hidden = false;
        }
    });

    bus.on('add-source:progress', ({ text, value }) => {
        const label = document.getElementById('addSourceProgressLabel');
        const bar = document.getElementById('addSourceProgressBar');
        if (label && text) label.textContent = text;
        if (bar && value != null) {
            bar.setAttribute('value', String(Math.max(0, Math.min(1, value))));
            bar.removeAttribute('indeterminate');
        } else if (bar) {
            bar.setAttribute('indeterminate', '');
        }
    });

    bus.on('add-source:victory', ({ text }) => {
        const victory = document.getElementById('addSourceVictory');
        const victoryText = document.getElementById('addSourceVictoryText');
        const progress = document.getElementById('addSourceProgress');
        const formEl = document.getElementById('analyzeForm');
        const actions = document.getElementById('addSourceActions');
        if (progress) progress.hidden = true;
        if (formEl) formEl.hidden = true;
        if (actions) actions.hidden = true;
        if (victory) {
            victory.hidden = false;
            if (victoryText) victoryText.textContent = text || '';
        }
        open();
    });

    return { open, close, dialog: modal };
}

export function bindSettingsForm({ onSave, onClear }) {
    const form = document.getElementById('settingsForm');
    if (!form) return;

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const next = {};
        form.querySelectorAll('[data-setting]').forEach((el) => {
            const key = el.dataset.setting;
            if (el.tagName === 'MD-SWITCH') next[key] = Boolean(el.selected);
            else if ('checked' in el) next[key] = Boolean(el.checked);
        });
        onSave?.(next);
    });

    document.getElementById('clearLocalCache')?.addEventListener('click', () => onClear?.());
}

export function hydrateSettingsForm(settings) {
    const form = document.getElementById('settingsForm');
    if (!form || !settings) return;
    Object.entries(settings).forEach(([key, val]) => {
        const el = form.querySelector(`[data-setting="${key}"]`);
        if (!el) return;
        if (el.tagName === 'MD-SWITCH') el.selected = Boolean(val);
        else if ('checked' in el) el.checked = Boolean(val);
    });
}
