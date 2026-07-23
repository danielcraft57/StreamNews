import { storage } from '../services/storage.js';

/** Toast Material-friendly (status bar existante). */
export function showToast(message, type = 'info') {
    const el = document.getElementById('status');
    if (!el) return;
    const settings = storage.loadSettings();
    if (settings.toasts === false && type !== 'error') {
        el.style.display = 'none';
        return;
    }
    el.textContent = message;
    el.className = `status ${type}`;
    el.style.display = 'block';
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => {
        el.style.display = 'none';
    }, 5000);
}
