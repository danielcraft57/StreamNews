import { defaultSettings } from '../models/settings.js';

const KEYS = {
    settings: 'streamnews.settings',
    favorites: 'streamnews.favorites',
    read: 'streamnews.read',
};

function loadIdSet(key) {
    try {
        const raw = JSON.parse(localStorage.getItem(key) || '[]');
        return new Set((Array.isArray(raw) ? raw : []).map(Number).filter(Boolean));
    } catch (_) {
        return new Set();
    }
}

function saveIdSet(key, set) {
    localStorage.setItem(key, JSON.stringify([...set]));
}

export const storage = {
    keys: KEYS,

    loadSettings() {
        try {
            const raw = JSON.parse(localStorage.getItem(KEYS.settings) || '{}');
            return { ...defaultSettings(), ...(raw && typeof raw === 'object' ? raw : {}) };
        } catch (_) {
            return defaultSettings();
        }
    },

    saveSettings(settings) {
        localStorage.setItem(KEYS.settings, JSON.stringify(settings));
        document.body.classList.toggle('dense-feed', Boolean(settings.denseList));
        return settings;
    },

    favorites() {
        return loadIdSet(KEYS.favorites);
    },

    isFavorite(id) {
        return loadIdSet(KEYS.favorites).has(Number(id));
    },

    toggleFavorite(id) {
        const n = Number(id);
        if (!n) return false;
        const set = loadIdSet(KEYS.favorites);
        if (set.has(n)) set.delete(n);
        else set.add(n);
        saveIdSet(KEYS.favorites, set);
        return set.has(n);
    },

    isRead(id) {
        return loadIdSet(KEYS.read).has(Number(id));
    },

    markRead(id, value = true) {
        const n = Number(id);
        if (!n) return;
        const set = loadIdSet(KEYS.read);
        if (value) set.add(n);
        else set.delete(n);
        saveIdSet(KEYS.read, set);
    },

    clearLocal() {
        localStorage.removeItem(KEYS.favorites);
        localStorage.removeItem(KEYS.read);
        localStorage.removeItem(KEYS.settings);
        return this.saveSettings(defaultSettings());
    },
};
