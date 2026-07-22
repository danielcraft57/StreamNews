/**
 * Orchestrateur StreamNews (migration progressive).
 * Couches propres : /js/{core,models,services,views,ui}
 * Material Web charge via /js/main.js
 */
/* global SN */

export class StreamNewsApp {
    constructor() {
        this.socket = null;
        this.currentAnalysis = null;
        this.analysisMaxPages = 50;   // plafond formulaire
        this.analysisTotalPages = null; // vrai total apres discovery
        this.selectedArticleId = null;
        this.viewingSiteId = null;
        this._articlePollTimer = null;
        this._feedArticles = [];
        this._sitesCache = [];
        this.currentView = 'feed';
        this.feedMode = 'all'; // all | favorites
        this._favStorageKey = 'streamnews.favorites';
        this._readStorageKey = 'streamnews.read';
        this._settingsKey = 'streamnews.settings';
        this._jobLog = [];
        this._selectedJobId = null;
        this.jobsFilter = 'all';
        this._trends = [];
        this.trendsDays = 30;
        this.trendsKind = 'all';
        this._selectedTrendTerm = null;
        this._pendingVictorySiteId = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupConsoleUX();
        this.setupImageFallbacks();
        this.setupAddSourceModal();
        this.setupSettings();
        this.setupJobsPane();
        this.setupTrendsPane();
        this.loadSites();
        this.loadFeed();
        this.connectWebSocket();
    }

    setupImageFallbacks() {
        // Pas de onerror= inline (CSP script-src-attr 'none' via Helmet)
        document.addEventListener('error', (e) => {
            const img = e.target;
            if (!(img instanceof HTMLImageElement)) return;
            if (img.classList.contains('js-hide-on-error')) {
                img.style.display = 'none';
            }
            if (img.classList.contains('js-hide-parent-on-error')) {
                const parent = img.parentElement;
                if (parent) parent.style.display = 'none';
            }
            if (img.classList.contains('article-item-thumb') || img.classList.contains('article-item-hero-img')) {
                const hero = img.closest('.article-item-hero');
                if (hero) hero.remove();
                else img.remove();
                const item = img.closest('.article-item');
                if (item) item.classList.add('article-item--no-thumb');
            }
        }, true);
    }

    setupEventListeners() {
        const form = document.getElementById('analyzeForm');
        form.addEventListener('submit', (e) => this.handleAnalyzeSubmit(e));

        const stopBtn = document.getElementById('stopAnalyzeBtn');
        if (stopBtn) {
            stopBtn.addEventListener('click', () => this.stopCurrentAnalysis());
        }

        // Delegation : evite onclick= inline (bloque par CSP script-src-attr)
        const sitesList = document.getElementById('sitesList');
        sitesList.addEventListener('click', async (e) => {
            const deleteBtn = e.target.closest('[data-delete-site]');
            if (deleteBtn) {
                e.preventDefault();
                e.stopPropagation();
                const siteId = Number(deleteBtn.dataset.deleteSite);
                if (siteId) this.deleteSite(siteId);
                return;
            }

            const ingestBtn = e.target.closest('[data-ingest-site]');
            if (ingestBtn) {
                e.preventDefault();
                e.stopPropagation();
                const siteId = Number(ingestBtn.dataset.ingestSite);
                if (!siteId) return;
                ingestBtn.disabled = true;
                const prev = ingestBtn.textContent;
                ingestBtn.textContent = 'Import…';
                try {
                    const res = await fetch(`/api/sites/${siteId}/ingest-articles`, { method: 'POST' });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.error || 'Erreur import');
                    this.updateStatus(`${data.articles_count || 0} articles traités`, 'success');
                    await this.loadFeed({ keepSelection: true });
                } catch (err) {
                    this.updateStatus(`Erreur: ${err.message}`, 'error');
                } finally {
                    ingestBtn.disabled = false;
                    ingestBtn.textContent = prev;
                }
                return;
            }

            const enrichBtn = e.target.closest('[data-enrich-site]');
            if (enrichBtn) {
                e.preventDefault();
                e.stopPropagation();
                const siteId = Number(enrichBtn.dataset.enrichSite);
                if (!siteId) return;
                enrichBtn.disabled = true;
                try {
                    const res = await fetch(`/api/sites/${siteId}/enrich-articles?limit=50`, { method: 'POST' });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.error || 'Erreur enrichissement');
                    const site = this._sitesCache.find((s) => Number(s.id) === siteId);
                    this.pushJob({
                        type: 'Enrich',
                        title: this.shortSiteLabel(site) || `Source #${siteId}`,
                        detail: data.message || 'Enrichissement en file',
                        status: 'done',
                        siteId,
                    });
                    this.updateStatus('Enrichissement en file', 'success');
                } catch (err) {
                    this.updateStatus(`Erreur: ${err.message}`, 'error');
                } finally {
                    enrichBtn.disabled = false;
                }
                return;
            }

            const analyzeBtn = e.target.closest('[data-analyze-site]');
            if (analyzeBtn) {
                e.preventDefault();
                e.stopPropagation();
                const siteId = Number(analyzeBtn.dataset.analyzeSite);
                if (!siteId) return;
                analyzeBtn.disabled = true;
                try {
                    const res = await fetch(`/api/sites/${siteId}/analyze-articles?limit=50`, { method: 'POST' });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.error || 'Erreur analyse');
                    const site = this._sitesCache.find((s) => Number(s.id) === siteId);
                    this.pushJob({
                        type: 'NLP',
                        title: this.shortSiteLabel(site) || `Source #${siteId}`,
                        detail: data.message || 'Analyse texte en file',
                        status: 'done',
                        siteId,
                    });
                    this.updateStatus('Analyse texte en file', 'success');
                } catch (err) {
                    this.updateStatus(`Erreur: ${err.message}`, 'error');
                } finally {
                    analyzeBtn.disabled = false;
                }
                return;
            }

            const openBtn = e.target.closest('[data-open-site]');
            if (openBtn) {
                e.preventDefault();
                const siteId = Number(openBtn.dataset.openSite);
                if (siteId) this.showSiteDetails(siteId);
                return;
            }
        });

        sitesList.addEventListener('keydown', (e) => {
            const item = e.target.closest('[data-open-site]');
            if (!item) return;
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                const siteId = Number(item.dataset.openSite);
                if (siteId) this.showSiteDetails(siteId);
            }
        });
    }

    setupConsoleUX() {
        const overlay = document.getElementById('searchOverlay');
        const openBtn = document.getElementById('openSearch');
        const input = document.getElementById('searchInput');
        const results = document.getElementById('searchResults');
        let searchTimer = null;
        let searchSeq = 0;

        const renderSearch = async () => {
            if (!results) return;
            const query = input?.value || '';
            const sites = (this._sitesCache || []).map((s) => ({
                id: s.id,
                title: this.shortSiteLabel(s),
                name: s.name,
                url: s.url,
            }));
            const localArticles = (this._feedArticles || []).map((a) => ({
                id: a.id,
                title: a.title,
                summary: a.summary,
                author: a.author,
                source: a._siteLabel || '',
                site_id: a.site_id || a._siteId,
                published_at: a.published_at,
            }));

            const q = query.trim();
            if (q.length < 2) {
                results.innerHTML = window.SN?.searchView?.renderSearchPalette
                    ? window.SN.searchView.renderSearchPalette({ query, articles: [], sites })
                    : '';
                return;
            }

            const seq = ++searchSeq;
            results.innerHTML = window.SN?.searchView?.renderSearchPalette
                ? window.SN.searchView.renderSearchPalette({ query, articles: [], sites, searching: true })
                : '';

            const filterVal = document.getElementById('feedFilter')?.value || 'all';
            const siteId = filterVal !== 'all' ? Number(filterVal) : null;
            const found = window.SN?.searchService
                ? await window.SN.searchService.searchArticles(q, {
                    siteId,
                    limit: 40,
                    localArticles,
                    api: window.SN.api,
                })
                : { articles: [], source: 'none' };

            if (seq !== searchSeq) return;

            const enriched = (found.articles || []).map((a) => {
                const site = (this._sitesCache || []).find((s) => Number(s.id) === Number(a.site_id));
                return {
                    ...a,
                    source: site ? this.shortSiteLabel(site) : (a.source || a._siteLabel || ''),
                };
            });

            results.innerHTML = window.SN?.searchView?.renderSearchPalette
                ? window.SN.searchView.renderSearchPalette({
                    query,
                    articles: enriched,
                    sites,
                    searchSource: found.source,
                })
                : '';
        };

        const toggleSearch = (open) => {
            if (!overlay) return;
            overlay.classList.toggle('open', open);
            if (open && input) {
                input.value = '';
                renderSearch();
                input.focus();
            }
        };

        const runSearchAction = (action) => {
            toggleSearch(false);
            if (action === 'focus-url') this.openAddSourceModal();
            else if (action === 'scroll-sites' || action === 'go-sources') this.showView('sources');
            else if (action === 'go-feed') this.showView('feed');
            else if (action === 'go-favoris') this.showView('favoris');
            else if (action === 'go-jobs') this.showView('jobs');
            else if (action === 'go-tendances') this.showView('tendances');
            else if (action === 'reload-site') {
                this.showView('sources');
                this.updateStatus('Recharge le flux depuis Sources', 'info');
            }
        };

        if (openBtn) openBtn.addEventListener('click', () => toggleSearch(true));
        if (overlay) {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) toggleSearch(false);
            });
        }
        input?.addEventListener('input', () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => renderSearch(), 220);
        });
        results?.addEventListener('click', (e) => {
            const actionBtn = e.target.closest('[data-search-action]');
            if (actionBtn) {
                runSearchAction(actionBtn.dataset.searchAction);
                return;
            }
            const articleBtn = e.target.closest('[data-search-article]');
            if (articleBtn) {
                const id = Number(articleBtn.dataset.searchArticle);
                toggleSearch(false);
                this.showView('feed');
                if (id) {
                    const exists = (this._feedArticles || []).some((a) => Number(a.id) === id);
                    if (exists) this.selectArticle(id);
                    else {
                        // article hors feed charge : ouvrir via API detail
                        this.selectArticle(id);
                    }
                }
                return;
            }
            const siteBtn = e.target.closest('[data-search-site]');
            if (siteBtn) {
                const id = Number(siteBtn.dataset.searchSite);
                toggleSearch(false);
                if (id) this.showSiteDetails(id);
            }
        });

        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                toggleSearch(!overlay?.classList.contains('open'));
            }
            if (e.key === 'Escape') toggleSearch(false);
            if (overlay?.classList.contains('open') && (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter')) {
                const hits = [...(results?.querySelectorAll('.search-hit') || [])];
                if (!hits.length) return;
                const idx = hits.findIndex((h) => h.classList.contains('is-active'));
                if (e.key === 'Enter') {
                    e.preventDefault();
                    (hits[idx] || hits[0])?.click();
                    return;
                }
                e.preventDefault();
                const next = e.key === 'ArrowDown'
                    ? (idx + 1) % hits.length
                    : (idx <= 0 ? hits.length - 1 : idx - 1);
                hits.forEach((h, i) => h.classList.toggle('is-active', i === next));
                hits[next]?.scrollIntoView({ block: 'nearest' });
            }
        });

        document.querySelector('[data-nav="sources"]')?.addEventListener('click', () => {
            this.showView('sources');
        });
        document.querySelector('[data-nav="feed"]')?.addEventListener('click', () => {
            this.showView('feed');
        });
        document.querySelector('[data-nav="favoris"]')?.addEventListener('click', () => {
            this.showView('favoris');
        });
        document.querySelector('[data-nav="jobs"]')?.addEventListener('click', () => {
            this.showView('jobs');
        });
        document.querySelector('[data-nav="tendances"]')?.addEventListener('click', () => {
            this.showView('tendances');
        });
        document.querySelector('[data-nav="settings"]')?.addEventListener('click', () => {
            this.showView('settings');
        });

        document.getElementById('feedFilter')?.addEventListener('change', () => {
            this.syncSourceChips();
            this.loadFeed({ keepSelection: false });
        });

        document.getElementById('feedRefresh')?.addEventListener('click', async () => {
            await this.loadSites();
            await this.loadFeed({ keepSelection: true });
            this.updateStatus('Feed actualise', 'success');
        });

        document.getElementById('feedSourceChips')?.addEventListener('click', (e) => {
            const chip = e.target.closest('[data-feed-source]');
            if (!chip) return;
            const filter = document.getElementById('feedFilter');
            if (filter) filter.value = chip.dataset.feedSource || 'all';
            this.syncSourceChips();
            if (this.currentView !== 'feed' && this.currentView !== 'favoris') {
                this.showView('feed');
            } else {
                this.loadFeed({ keepSelection: false });
            }
        });

        const feedList = document.getElementById('feedList');
        feedList?.addEventListener('click', (e) => {
            if (e.target.closest('#favorisEmptyGoFeed')) {
                this.showView('feed');
                return;
            }
            const row = e.target.closest('[data-article-id]');
            if (!row) return;
            const id = Number(row.dataset.articleId);
            if (id) this.selectArticle(id);
        });
    }

    showView(view) {
        this.currentView = view;
        const workspace = document.getElementById('workspace');
        const feedPane = document.getElementById('feedPane');
        const readerPane = document.getElementById('readerPane');
        const sourcesPane = document.getElementById('sourcesPane');
        const jobsPane = document.getElementById('jobsPane');
        const trendsPane = document.getElementById('trendsPane');
        const settingsPane = document.getElementById('settingsPane');

        const isSources = view === 'sources';
        const isJobs = view === 'jobs';
        const isTendances = view === 'tendances';
        const isSettings = view === 'settings';
        const isFavoris = view === 'favoris';
        const isFeedLike = view === 'feed' || isFavoris;

        if (workspace) {
            workspace.classList.toggle('view-sources', isSources);
            workspace.classList.toggle('view-jobs', isJobs);
            workspace.classList.toggle('view-tendances', isTendances);
            workspace.classList.toggle('view-settings', isSettings);
        }
        if (feedPane) feedPane.hidden = !isFeedLike;
        if (readerPane) readerPane.hidden = !isFeedLike;
        if (sourcesPane) sourcesPane.hidden = !isSources;
        if (jobsPane) jobsPane.hidden = !isJobs;
        if (trendsPane) trendsPane.hidden = !isTendances;
        if (settingsPane) settingsPane.hidden = !isSettings;

        document.querySelectorAll('.sidebar-nav-item[data-nav]').forEach((btn) => {
            btn.classList.toggle('is-active', btn.dataset.nav === view);
        });

        if (isSources) {
            this.loadSites();
            return;
        }
        if (isJobs) {
            this.syncJobsFromSites();
            this.renderJobs();
            return;
        }
        if (isTendances) {
            this.loadTrends();
            return;
        }
        if (isSettings) {
            this.hydrateSettingsForm();
            return;
        }

        this.feedMode = isFavoris ? 'favorites' : 'all';
        const sourceBar = document.getElementById('feedSourceBar');
        if (sourceBar) sourceBar.hidden = isFavoris;
        this.syncSourceChips();
        this.renderFeedList({ keepSelection: true, autoSelect: true });
    }

    syncSourceChips() {
        const host = document.getElementById('feedSourceChips');
        if (!host || !window.SN?.feedChips?.renderSourceChips) return;
        const active = document.getElementById('feedFilter')?.value || 'all';
        host.innerHTML = window.SN.feedChips.renderSourceChips(this._sitesCache || [], active);
        host.querySelectorAll('.js-hide-on-error').forEach((img) => {
            img.addEventListener('error', () => { img.style.display = 'none'; }, { once: true });
        });
    }

    setupAddSourceModal() {
        // Delegation : marche avec md-* et boutons crees dynamiquement
        document.body.addEventListener('click', (e) => {
            const openBtn = e.target.closest?.(
                '#openAddSource, #openAddSourceFromFeed, #emptyAddSource, #feedEmptyAddSource, #favorisEmptyGoFeed'
            );
            if (openBtn) {
                e.preventDefault();
                if (openBtn.id === 'favorisEmptyGoFeed') {
                    this.showView('feed');
                    return;
                }
                this.openAddSourceModal();
                return;
            }
            if (e.target.closest?.('#closeAddSource')) {
                this.closeAddSourceModal();
                return;
            }
            if (e.target?.id === 'addSourceModal') {
                this.closeAddSourceModal({ force: !this.currentAnalysis });
                return;
            }
            if (e.target.closest?.('#addSourceReadFirst')) {
                const siteId = this._pendingVictorySiteId;
                this.closeAddSourceModal({ force: true });
                if (siteId) {
                    const filter = document.getElementById('feedFilter');
                    if (filter) filter.value = String(siteId);
                }
                this.showView('feed');
                (async () => {
                    if (siteId) await this.ensureSiteArticles(siteId);
                    await this.loadFeed({ keepSelection: false });
                })();
            }
        });
        // md-filled-button type=submit : fallback si le submit natif ne part pas
        document.getElementById('analyzeBtn')?.addEventListener('click', (e) => {
            const form = document.getElementById('analyzeForm');
            if (!form || form.hidden) return;
            e.preventDefault();
            form.requestSubmit?.() || form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.closeAddSourceModal({ force: !this.currentAnalysis });
        });
    }

    async openAddSourceModal({ keepVictory = false } = {}) {
        const modal = document.getElementById('addSourceModal');
        if (modal) {
            modal.hidden = false;
            modal.classList.add('open');
        }
        const victory = document.getElementById('addSourceVictory');
        const form = document.getElementById('analyzeForm');
        const progress = document.getElementById('addSourceProgress');
        const actions = document.getElementById('addSourceActions');
        const analyzeBtn = document.getElementById('analyzeBtn');

        if (keepVictory || (victory && !victory.hidden)) {
            if (form) form.hidden = true;
            if (progress) progress.hidden = true;
            if (actions) actions.hidden = true;
            if (victory) victory.hidden = false;
        } else {
            if (victory && !this.currentAnalysis) victory.hidden = true;
            if (form && !this.currentAnalysis) form.hidden = false;
            if (progress && !this.currentAnalysis) progress.hidden = true;
            if (actions && !this.currentAnalysis) actions.hidden = false;
            if (analyzeBtn && !this.currentAnalysis) {
                analyzeBtn.disabled = false;
                analyzeBtn.hidden = false;
            }
            setTimeout(() => document.getElementById('url')?.focus?.(), 40);
        }
    }

    async closeAddSourceModal({ force = false } = {}) {
        if (this.currentAnalysis && !force) {
            this.updateStatus('Analyse en cours — tu peux laisser le dialog ouvert', 'info');
            return;
        }
        const modal = document.getElementById('addSourceModal');
        if (modal) {
            modal.classList.remove('open');
            modal.hidden = true;
        }
        if (!this.currentAnalysis) {
            const form = document.getElementById('analyzeForm');
            if (form) form.hidden = false;
            const victory = document.getElementById('addSourceVictory');
            if (victory) victory.hidden = true;
            const actions = document.getElementById('addSourceActions');
            if (actions) actions.hidden = false;
            this.showLoading(false);
        }
    }

    defaultSettings() {
        return (window.SN?.defaultSettings?.() || {
            autoMarkRead: false,
            showSummaryFirst: true,
            denseList: false,
            autoEnrich: true,
            celebrateFirst: true,
            toasts: true,
        });
    }

    loadSettings() {
        if (window.SN?.storage) return window.SN.storage.loadSettings();
        try {
            const raw = JSON.parse(localStorage.getItem(this._settingsKey) || '{}');
            return { ...this.defaultSettings(), ...(raw && typeof raw === 'object' ? raw : {}) };
        } catch (_) {
            return this.defaultSettings();
        }
    }

    saveSettings(settings) {
        if (window.SN?.storage) return window.SN.storage.saveSettings(settings);
        localStorage.setItem(this._settingsKey, JSON.stringify(settings));
        document.body.classList.toggle('dense-feed', Boolean(settings.denseList));
        return settings;
    }

    hydrateSettingsForm() {
        if (window.SN?.hydrateSettingsForm) {
            window.SN.hydrateSettingsForm(this.loadSettings());
            return;
        }
        const form = document.getElementById('settingsForm');
        if (!form) return;
        const s = this.loadSettings();
        Object.entries(s).forEach(([key, val]) => {
            const el = form.querySelector(`[data-setting="${key}"]`);
            if (!el) return;
            if (el.tagName === 'MD-SWITCH') el.selected = Boolean(val);
            else if ('checked' in el) el.checked = Boolean(val);
        });
    }

    setupSettings() {
        this.saveSettings(this.loadSettings());
        this.hydrateSettingsForm();
        document.getElementById('settingsForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            const form = e.target;
            const next = this.defaultSettings();
            form.querySelectorAll('[data-setting]').forEach((el) => {
                const key = el.dataset.setting;
                if (!key) return;
                if (el.tagName === 'MD-SWITCH') next[key] = Boolean(el.selected);
                else if ('checked' in el) next[key] = Boolean(el.checked);
            });
            this.saveSettings(next);
            this.updateStatus('Reglages enregistres', 'success');
        });
        document.getElementById('clearLocalCache')?.addEventListener('click', () => {
            if (!confirm('Vider favoris, articles lus et reglages locaux ?')) return;
            if (window.SN?.storage) window.SN.storage.clearLocal();
            else {
                localStorage.removeItem(this._favStorageKey);
                localStorage.removeItem(this._readStorageKey);
                localStorage.removeItem(this._settingsKey);
                this.saveSettings(this.defaultSettings());
            }
            this.hydrateSettingsForm();
            this.renderFeedList({ keepSelection: true, autoSelect: false });
            this.updateStatus('Cache local vide', 'success');
        });
    }

    setupJobsPane() {
        document.getElementById('jobsFilters')?.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-jobs-filter]');
            if (!btn) return;
            this.jobsFilter = btn.dataset.jobsFilter || 'all';
            document.querySelectorAll('[data-jobs-filter]').forEach((el) => {
                el.classList.toggle('is-active', el.dataset.jobsFilter === this.jobsFilter);
            });
            this.renderJobs();
        });
        document.getElementById('jobsList')?.addEventListener('click', (e) => {
            const row = e.target.closest('[data-job-id]');
            if (!row) return;
            this._selectedJobId = row.dataset.jobId;
            this.renderJobs();
        });
        document.getElementById('jobsRefresh')?.addEventListener('click', async () => {
            await this.loadSites();
            this.syncJobsFromSites();
            this.renderJobs();
            this.updateStatus('Jobs actualises', 'success');
        });
        document.getElementById('jobsDetail')?.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-open-job-site]');
            if (!btn) return;
            const siteId = Number(btn.dataset.openJobSite);
            if (siteId) this.showSiteDetails(siteId);
        });
    }

    setupTrendsPane() {
        document.getElementById('trendsWindow')?.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-trends-days]');
            if (!btn) return;
            this.trendsDays = Number(btn.dataset.trendsDays) || 30;
            document.querySelectorAll('[data-trends-days]').forEach((el) => {
                el.classList.toggle('is-active', Number(el.dataset.trendsDays) === this.trendsDays);
            });
            this.loadTrends({ refresh: false });
        });
        document.getElementById('trendsKind')?.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-trends-kind]');
            if (!btn) return;
            this.trendsKind = btn.dataset.trendsKind || 'all';
            document.querySelectorAll('[data-trends-kind]').forEach((el) => {
                el.classList.toggle('is-active', el.dataset.trendsKind === this.trendsKind);
            });
            this.renderTrends();
        });
        document.getElementById('trendsRefresh')?.addEventListener('click', () => {
            this.loadTrends({ refresh: true });
        });
        document.getElementById('trendsList')?.addEventListener('click', (e) => {
            const row = e.target.closest('[data-trend-term]');
            if (!row) return;
            this._selectedTrendTerm = row.dataset.trendTerm;
            this.renderTrends();
        });
        document.getElementById('trendsDetail')?.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-trend-search]');
            if (!btn) return;
            const term = btn.dataset.trendSearch;
            if (!term) return;
            this.showView('feed');
            const overlay = document.getElementById('searchOverlay');
            const input = document.getElementById('searchInput');
            if (overlay && input) {
                overlay.classList.add('open');
                input.value = term;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.focus();
            }
        });
    }

    async loadTrends({ refresh = false } = {}) {
        const list = document.getElementById('trendsList');
        if (list) list.innerHTML = '<p class="feed-empty">Calcul des tendances...</p>';
        try {
            const data = window.SN?.api
                ? await window.SN.api.getTrends({
                    days: this.trendsDays,
                    kind: 'all',
                    limit: 50,
                    refresh,
                })
                : await (async () => {
                    const params = new URLSearchParams({
                        days: String(this.trendsDays),
                        limit: '50',
                        kind: 'all',
                    });
                    if (refresh) params.set('refresh', '1');
                    const res = await fetch(`/api/trends?${params}`);
                    return res.json();
                })();
            this._trends = Array.isArray(data.trends) ? data.trends : [];
            const sub = document.getElementById('trendsSubtitle');
            if (sub) {
                const when = data.computed_at
                    ? `Maj ${new Date(data.computed_at).toLocaleString('fr-FR')}`
                    : 'Calculees depuis mots-cles / NLP';
                sub.textContent = `${data.count || this._trends.length} sujets · ${this.trendsDays} j · ${when}`;
            }
            if (!this._selectedTrendTerm && this._trends.length) {
                this._selectedTrendTerm = this._trends[0].term;
            }
            this.renderTrends();
            if (refresh) this.updateStatus('Tendances mises a jour', 'success');
        } catch (err) {
            console.error(err);
            if (list) {
                list.innerHTML = `<p class="feed-empty">Impossible de charger les tendances (${this.escapeHtml(err.message || 'erreur')}).</p>`;
            }
            this.updateStatus('Erreur tendances', 'error');
        }
    }

    renderTrends() {
        const list = document.getElementById('trendsList');
        const detail = document.getElementById('trendsDetail');
        if (!list || !detail) return;
        const tv = window.SN?.trendsView;
        let trends = this._trends.slice();
        if (this.trendsKind && this.trendsKind !== 'all') {
            trends = trends.filter((t) => t.kind === this.trendsKind);
        }
        if (!trends.length) {
            list.innerHTML = tv?.renderTrendsList
                ? tv.renderTrendsList([])
                : '<p class="feed-empty">Aucune tendance pour ce filtre.</p>';
            detail.innerHTML = tv?.renderTrendsDetail
                ? tv.renderTrendsDetail(null)
                : '';
            return;
        }
        if (!trends.some((t) => t.term === this._selectedTrendTerm)) {
            this._selectedTrendTerm = trends[0].term;
        }
        const maxScore = Math.max(...trends.map((t) => Number(t.score) || 0), 1);
        list.innerHTML = tv?.renderTrendsList
            ? tv.renderTrendsList(trends, { selectedTerm: this._selectedTrendTerm, maxScore })
            : '';
        const selected = trends.find((t) => t.term === this._selectedTrendTerm) || trends[0];
        detail.innerHTML = tv?.renderTrendsDetail
            ? tv.renderTrendsDetail(selected)
            : '';
    }

    pushJob(job) {
        const entry = window.SN?.createJob
            ? window.SN.createJob(job)
            : {
                id: job.id || `job-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
                type: job.type || 'Crawl',
                title: job.title || 'Tache',
                detail: job.detail || '',
                status: job.status || 'running',
                siteId: job.siteId || null,
                at: job.at || new Date().toISOString(),
                progressCurrent: job.progressCurrent ?? null,
                progressTotal: job.progressTotal ?? null,
            };
        this._jobLog = [entry, ...this._jobLog.filter((j) => j.id !== entry.id)].slice(0, 40);
        if (this.currentView === 'jobs') this.renderJobs();
        return entry.id;
    }

    updateJob(id, patch) {
        const job = this._jobLog.find((j) => j.id === id);
        if (!job) return;
        Object.assign(job, patch, { at: patch.at || new Date().toISOString() });
        if (this.currentView === 'jobs') this.renderJobs();
    }

    syncJobsFromSites() {
        for (const site of this._sitesCache || []) {
            const id = `crawl-site-${site.id}`;
            const existing = this._jobLog.find((j) => j.id === id);
            const status = site.status === 'completed' || site.status === 'ok'
                ? 'done'
                : (site.status === 'error' ? 'error' : (site.status === 'analyzing' || site.status === 'running' || site.status === 'ingesting' || site.status === 'pending' ? 'running' : 'done'));
            const feeds = this.parseRssFeeds(site.rss_feeds);
            const pages = Number(site.total_pages_analyzed) || 0;
            const payload = {
                id,
                type: 'Crawl',
                title: this.shortSiteLabel(site),
                detail: status === 'done'
                    ? `${feeds.length} flux RSS${pages ? ` · ${pages} pages` : ''}`
                    : (site.status === 'ingesting' ? 'Import des articles RSS…' : (site.status || '')),
                status,
                siteId: site.id,
                at: site.updated_at || site.created_at || new Date().toISOString(),
                progressCurrent: pages || null,
                progressTotal: pages || null,
            };
            if (!existing) this._jobLog.push(payload);
            else Object.assign(existing, payload);
        }
        this._jobLog.sort((a, b) => new Date(b.at) - new Date(a.at));
    }

    renderJobs() {
        const list = document.getElementById('jobsList');
        const detail = document.getElementById('jobsDetail');
        if (!list || !detail) return;

        let jobs = this._jobLog.slice();
        if (this.jobsFilter === 'running') jobs = jobs.filter((j) => j.status === 'running');
        if (this.jobsFilter === 'done') jobs = jobs.filter((j) => j.status === 'done' || j.status === 'error');

        const jv = window.SN?.jobsView;
        if (!jobs.length) {
            list.innerHTML = jv?.renderJobsList
                ? jv.renderJobsList([])
                : '<p class="feed-empty">Aucun job pour ce filtre.</p>';
            detail.innerHTML = jv?.renderJobsDetail
                ? jv.renderJobsDetail(null)
                : '<p class="feed-empty">Selectionne un job pour voir le detail.</p>';
            return;
        }

        if (!this._selectedJobId || !jobs.some((j) => j.id === this._selectedJobId)) {
            this._selectedJobId = jobs[0].id;
        }

        list.innerHTML = jv?.renderJobsList
            ? jv.renderJobsList(jobs, this._selectedJobId)
            : '';
        const selectedJob = jobs.find((j) => j.id === this._selectedJobId) || jobs[0];
        detail.innerHTML = jv?.renderJobsDetail
            ? jv.renderJobsDetail(selectedJob)
            : '';
    }

    loadIdSet(key) {
        if (window.SN?.storage) {
            if (key === this._favStorageKey) return window.SN.storage.favorites();
        }
        try {
            const raw = JSON.parse(localStorage.getItem(key) || '[]');
            return new Set((Array.isArray(raw) ? raw : []).map(Number).filter(Boolean));
        } catch (_) {
            return new Set();
        }
    }

    saveIdSet(key, set) {
        localStorage.setItem(key, JSON.stringify([...set]));
    }

    isFavorite(articleId) {
        if (window.SN?.storage) return window.SN.storage.isFavorite(articleId);
        return this.loadIdSet(this._favStorageKey).has(Number(articleId));
    }

    isRead(articleId) {
        if (window.SN?.storage) return window.SN.storage.isRead(articleId);
        return this.loadIdSet(this._readStorageKey).has(Number(articleId));
    }

    toggleFavorite(articleId) {
        if (window.SN?.storage) return window.SN.storage.toggleFavorite(articleId);
        const id = Number(articleId);
        if (!id) return false;
        const set = this.loadIdSet(this._favStorageKey);
        if (set.has(id)) set.delete(id);
        else set.add(id);
        this.saveIdSet(this._favStorageKey, set);
        return set.has(id);
    }

    markRead(articleId, value = true) {
        if (window.SN?.storage) return window.SN.storage.markRead(articleId, value);
        const id = Number(articleId);
        if (!id) return;
        const set = this.loadIdSet(this._readStorageKey);
        if (value) set.add(id);
        else set.delete(id);
        this.saveIdSet(this._readStorageKey, set);
    }

    _markViewingSite(siteId) {
        document.querySelectorAll('.site-item[data-site-id]').forEach((el) => {
            el.classList.toggle('is-viewing', Number(el.dataset.siteId) === Number(siteId));
        });
    }

    _updateTopbar(_title) {
        /* topbar retiree dans la maquette */
    }

    _setMobileReaderMode(on) {
        const workspace = document.getElementById('workspace');
        if (!workspace) return;
        workspace.classList.toggle('show-reader', Boolean(on));
    }

    _readerBackButtonHtml() {
        return `<button type="button" class="reader-back" id="readerBack" aria-label="Retour a la liste">
            <i class="fas fa-arrow-left"></i> Retour
        </button>`;
    }

    _bindReaderBackButton() {
        document.getElementById('readerBack')?.addEventListener('click', () => {
            this._setMobileReaderMode(false);
        });
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        this.socket = new WebSocket(wsUrl);
        
        this.socket.onopen = () => {
            console.log('WebSocket connecté');
        };
        
        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleWebSocketMessage(data);
        };
        
        this.socket.onclose = () => {
            console.log('WebSocket déconnecté');
            setTimeout(() => this.connectWebSocket(), 5000);
        };
        
        this.socket.onerror = (error) => {
            console.error('Erreur WebSocket:', error);
        };
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'analysis_started':
                this.handleAnalysisStarted(data);
                break;
            case 'page_analyzed':
                this.handlePageAnalyzed(data);
                break;
            case 'rss_found':
                this.handleRssFound(data);
                break;
            case 'analysis_completed':
                this.handleAnalysisCompleted(data);
                break;
            case 'analysis_error':
                this.handleAnalysisError(data);
                break;
            case 'progress_update':
                this.handleProgressUpdate(data);
                break;
            case 'articles_ingest_started':
                this.handleArticlesIngestStarted(data);
                break;
            case 'site_meta':
                this.loadSites();
                this.loadFeed({ keepSelection: true });
                break;
            case 'article_enriched':
                this.handleArticleEnriched(data);
                break;
            case 'article_analyzed':
                this.handleArticleAnalyzed(data);
                break;
            case 'analysis_cancelled':
                this.handleAnalysisCancelled(data);
                break;
        }
    }

    sameSite(siteId) {
        if (this.currentAnalysis == null || siteId == null) return false;
        return Number(this.currentAnalysis) === Number(siteId);
    }

    handleAnalysisStarted(data) {
        this.currentAnalysis = Number(data.site_id);
        // plafond optionnel ; le vrai total arrive apres discovery (progress_update / page_analyzed)
        const maxPages = Number(data.max_pages ?? data.total_pages);
        if (Number.isFinite(maxPages) && maxPages > 0) {
            this.analysisMaxPages = maxPages;
        }
        this.analysisTotalPages = null;
        this.updateStatus(`Analyse démarrée pour ${data.url}`, 'info');
        this.showLoading(true);
        this.setLoadingText('Discovery des liens...');
    }

    handlePageAnalyzed(data) {
        if (this.sameSite(data.site_id)) {
            const current = data.pages_analyzed ?? data.current;
            const total = data.total_pages ?? data.total ?? this.analysisTotalPages ?? this.analysisMaxPages;
            if (data.total_pages != null || data.total != null) {
                const t = Number(data.total_pages ?? data.total);
                if (Number.isFinite(t) && t > 0) this.analysisTotalPages = t;
            }
            this.updateProgress(current, this.analysisTotalPages ?? total);
            this.addPageLog(`Page analysée: ${data.url}`, 'success');
            const cur = Number(current);
            const tot = Number(this.analysisTotalPages ?? total);
            this.updateJob(`crawl-site-${data.site_id}`, {
                status: 'running',
                detail: Number.isFinite(cur) && Number.isFinite(tot) && tot > 0
                    ? `${cur} / ${tot} pages`
                    : `Page ${cur || '?'}`,
                progressCurrent: Number.isFinite(cur) ? cur : null,
                progressTotal: Number.isFinite(tot) && tot > 0 ? tot : null,
            });
            if (Number.isFinite(cur) && Number.isFinite(tot) && tot > 0 && cur >= tot) {
                this.setLoadingText(`Crawl terminé (${cur} pages). Import des articles...`);
            }
        }
    }

    handleRssFound(data) {
        if (this.sameSite(data.site_id)) {
            this.addPageLog(`Flux RSS trouvé: ${data.rss_url}`, 'rss');
            this.addRssFeed(data);
        }
    }

    handleArticlesIngestStarted(data) {
        if (this.sameSite(data.site_id)) {
            const n = data.feeds_count != null ? data.feeds_count : '?';
            this.setLoadingText(`Import des articles (${n} flux)...`);
            this.updateStatus(`Import des articles depuis ${n} flux...`, 'info');
        }
    }

    handleAnalysisCompleted(data) {
        if (this.sameSite(data.site_id)) {
            if (data.status === 'error') {
                this.updateStatus(`Erreur: analyse incomplete`, 'error');
                this.showLoading(false);
                this.currentAnalysis = null;
                this.updateJob(`crawl-site-${data.site_id}`, { status: 'error', detail: 'Analyse incomplete' });
                const form = document.getElementById('analyzeForm');
                if (form) form.style.display = '';
                this.loadSites();
                return;
            }
            const articlesBit = data.articles_count != null ? ` · ${data.articles_count} articles` : '';
            this.showLoading(false);
            const pages = data.total_pages ?? this.analysisTotalPages;
            if (pages != null) this.updateProgress(pages, pages);
            this.updateJob(`crawl-site-${data.site_id}`, {
                status: 'done',
                detail: `${data.rss_count || 0} flux RSS${data.articles_count != null ? ` · ${data.articles_count} articles` : ''}`,
            });
            this.loadSites();
            this.currentAnalysis = null;

            // Toujours recharger le feed (pas seulement si 0 article)
            const siteId = data.site_id;
            const maybeIngest = (data.articles_count == null || Number(data.articles_count) === 0)
                && (data.rss_count || 0) > 0
                ? this.ensureSiteArticles(siteId)
                : Promise.resolve(0);
            maybeIngest.then(() => {
                const filter = document.getElementById('feedFilter');
                if (filter && siteId) filter.value = String(siteId);
                return this.loadFeed({ keepSelection: false });
            }).catch(() => this.loadFeed({ keepSelection: true }));

            const settings = this.loadSettings();
            const isFirst = (this._sitesCache || []).length <= 1;
            const celebrate = settings.celebrateFirst && isFirst;
            this._pendingVictorySiteId = data.site_id;
            const victory = document.getElementById('addSourceVictory');
            const victoryText = document.getElementById('addSourceVictoryText');
            const form = document.getElementById('analyzeForm');
            const progress = document.getElementById('addSourceProgress');
            const actions = document.getElementById('addSourceActions');
            if (form) form.hidden = true;
            if (progress) progress.hidden = true;
            if (actions) actions.hidden = true;
            if (victory) {
                victory.hidden = false;
                if (victoryText) {
                    victoryText.textContent = celebrate
                        ? `${data.rss_count || 0} flux trouves${articlesBit}. Première victoire — lis ton premier article.`
                        : `${data.rss_count || 0} flux trouves${articlesBit}. Pret a lire.`;
                }
                window.SN?.bus?.emit('add-source:victory', { text: victoryText?.textContent });
                this.openAddSourceModal({ keepVictory: true });
                // toast discret seulement (plus de bandeau "page")
                this.updateStatus(`${data.rss_count || 0} flux RSS prets`, 'success');
            } else if (data.site_id) {
                this.updateStatus(
                    `Analyse terminée ! ${data.rss_count} flux RSS trouvés${articlesBit}`,
                    'success'
                );
                this.showView('feed');
            }
        }
    }

    handleAnalysisError(data) {
        if (this.sameSite(data.site_id)) {
            this.updateStatus(`Erreur: ${data.error}`, 'error');
            this.showLoading(false);
            this.currentAnalysis = null;
            this.loadSites();
        }
    }

    handleAnalysisCancelled(data) {
        if (this.currentAnalysis == null || this.sameSite(data.site_id)) {
            this.updateStatus('Analyse arrêtée', 'info');
            this.showLoading(false);
            this.currentAnalysis = null;
            this.loadSites();
        }
    }

    handleProgressUpdate(data) {
        if (this.sameSite(data.site_id)) {
            const tot = data.total ?? data.total_pages;
            if (tot != null && Number.isFinite(Number(tot)) && Number(tot) > 0) {
                this.analysisTotalPages = Number(tot);
            }
            this.updateProgress(
                data.current ?? data.pages_analyzed ?? 0,
                this.analysisTotalPages
            );
            if (data.message) {
                this.updateStatus(data.message, 'info');
                this.setLoadingText(data.message);
            }
        }
    }

    async handleAnalyzeSubmit(e) {
        e.preventDefault();
        
        const urlField = document.getElementById('url');
        const url = String(urlField?.value || urlField?.getAttribute?.('value') || '').trim();
        const maxPages = parseInt(document.getElementById('maxPages')?.value, 10);
        const depth = parseInt(document.getElementById('depth')?.value, 10);
        
        if (!url) {
            this.updateStatus('Veuillez saisir une URL', 'error');
            urlField?.focus?.();
            return;
        }
        if (!/^https?:\/\//i.test(url)) {
            this.updateStatus('L\'URL doit commencer par http:// ou https://', 'error');
            return;
        }

        this.analysisMaxPages = Number.isFinite(maxPages) && maxPages > 0 ? maxPages : 50;
        this.analysisTotalPages = null;
        
        try {
            this.updateStatus('Lancement de l\'analyse...', 'info');
            this.openAddSourceModal();
            this.showLoading(true);
            this.setLoadingText('Lancement...');
            this.clearResults();
            document.getElementById('addSourceVictory')?.setAttribute('hidden', '');
            const form = document.getElementById('analyzeForm');
            if (form) form.hidden = true;

            const result = window.SN?.api
                ? await window.SN.api.analyze({
                    url,
                    max_pages: this.analysisMaxPages,
                    depth,
                })
                : await (async () => {
                    const response = await fetch('/api/analyze', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            url,
                            max_pages: this.analysisMaxPages,
                            depth,
                        }),
                    });
                    const data = await response.json();
                    if (!response.ok) throw new Error(data.error || 'Erreur lors du lancement');
                    return data;
                })();

            this.updateStatus(`Analyse lancée (ID: ${result.site_id})`, 'success');
            this.currentAnalysis = Number(result.site_id);
            this._activeCrawlJobId = this.pushJob({
                id: `crawl-site-${result.site_id}`,
                type: 'Crawl',
                title: url,
                detail: 'Discovery des liens…',
                status: 'running',
                siteId: result.site_id,
            });
            this.showView('sources');
            this._watchAnalysisFinish(Number(result.site_id));
            
        } catch (error) {
            this.updateStatus(`Erreur: ${error.message}`, 'error');
            this.showLoading(false);
            this.currentAnalysis = null;
            const form = document.getElementById('analyzeForm');
            if (form) form.hidden = false;
        }
    }

    async stopCurrentAnalysis() {
        const siteId = this.currentAnalysis;
        if (!siteId) {
            this.showLoading(false);
            return;
        }

        const stopBtn = document.getElementById('stopAnalyzeBtn');
        if (stopBtn) stopBtn.disabled = true;

        try {
            this.updateStatus('Arrêt de l\'analyse...', 'info');
            const res = await fetch(`/api/sites/${siteId}/stop`, { method: 'POST' });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(data.error || data.detail || 'Impossible d\'arreter');
            }
            this.updateStatus('Analyse arrêtée', 'info');
            this.showLoading(false);
            this.currentAnalysis = null;
            await this.loadSites();
        } catch (err) {
            console.error(err);
            this.updateStatus(`Erreur: ${err.message}`, 'error');
        } finally {
            if (stopBtn) stopBtn.disabled = false;
        }
    }

    parseRssFeeds(value) {
        if (!value) return [];
        if (Array.isArray(value)) return value;
        if (typeof value === 'string') {
            try {
                const parsed = JSON.parse(value);
                return Array.isArray(parsed) ? parsed : [];
            } catch (e) {
                return [];
            }
        }
        return [];
    }

    async loadSites() {
        try {
            const response = await fetch('/api/sites');
            const data = await response.json();
            this._sitesCache = Array.isArray(data.sites) ? data.sites : [];

            const filter = document.getElementById('feedFilter');
            if (filter) {
                const current = filter.value;
                filter.innerHTML = '<option value="all">Tous les articles</option>'
                    + this._sitesCache.map((site) =>
                        `<option value="${site.id}">${this.escapeHtml(this.shortSiteLabel(site))}</option>`
                    ).join('');
                filter.value = this._sitesCache.some((s) => String(s.id) === current) ? current : 'all';
            }
            this.syncSourceChips();
            
            const sitesList = document.getElementById('sitesList');
            if (sitesList) {
                const sv = window.SN?.sourcesView;
                sitesList.innerHTML = sv?.renderSourcesList
                    ? sv.renderSourcesList(this._sitesCache, { viewingSiteId: this.viewingSiteId })
                    : '<p class="feed-empty">Impossible d\'afficher les sources.</p>';
            }
            this.syncJobsFromSites();
        } catch (error) {
            console.error('Erreur lors du chargement des sites:', error);
        }
    }

    async loadFeed({ keepSelection = true } = {}) {
        const feedList = document.getElementById('feedList');
        if (!feedList) return;

        try {
            if (!this._sitesCache.length) {
                const response = await fetch('/api/sites');
                const data = await response.json();
                this._sitesCache = Array.isArray(data.sites) ? data.sites : [];
            }

            const filterVal = document.getElementById('feedFilter')?.value || 'all';
            const siteIds = filterVal === 'all'
                ? this._sitesCache.map((s) => s.id)
                : [Number(filterVal)].filter(Boolean);

            if (!siteIds.length) {
                this._feedArticles = [];
                this.renderFeedList({ keepSelection: false, autoSelect: false });
                return;
            }

            const batches = await Promise.all(siteIds.map(async (siteId) => {
                const res = await fetch(`/api/sites/${siteId}/articles?limit=100`);
                if (!res.ok) {
                    console.warn('Feed site', siteId, 'HTTP', res.status);
                    return { siteId, articles: [], error: true };
                }
                const data = await res.json();
                const site = this._sitesCache.find((s) => Number(s.id) === Number(siteId));
                const siteLabel = this.shortSiteLabel(site);
                const articles = (data.articles || [])
                    .filter((article) => !this.isNoiseArticle(article))
                    .map((article) => ({
                        ...article,
                        title: this.cleanArticleTitle(article.title, site),
                        _siteTitle: site?.site_title || site?.url || this.articleDomain(article),
                        _siteLabel: siteLabel,
                        _siteId: siteId,
                    }));
                return { siteId, articles, error: false };
            }));

            const failed = batches.filter((b) => b.error);
            let articles = batches.flatMap((b) => b.articles);
            articles.sort((a, b) => {
                const da = new Date(a.published_at || 0).getTime();
                const db = new Date(b.published_at || 0).getTime();
                return db - da;
            });
            // Dedup by link/guid (plusieurs flux peuvent renvoyer le meme article)
            const seen = new Set();
            articles = articles.filter((a) => {
                const key = (a.guid || a.link || `${a.id}`).toLowerCase();
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            });
            this._feedArticles = articles;
            this._feedLoadMeta = {
                filterVal,
                failedSiteIds: failed.map((b) => b.siteId),
                emptySiteIds: siteIds.filter((id) => {
                    const batch = batches.find((b) => Number(b.siteId) === Number(id));
                    return batch && !batch.error && batch.articles.length === 0;
                }),
            };
            this.renderFeedList({ keepSelection, autoSelect: true });
            if (failed.length && !articles.length) {
                this.updateStatus('Impossible de charger les articles (analyzer?)', 'error');
            }
        } catch (error) {
            console.error('Erreur feed:', error);
            feedList.innerHTML = '<p class="feed-empty">Impossible de charger le feed.</p>';
        }
    }

    visibleFeedArticles() {
        let articles = this._feedArticles || [];
        if (this.feedMode === 'favorites') {
            const favs = this.loadIdSet(this._favStorageKey);
            articles = articles.filter((a) => favs.has(Number(a.id)));
        }
        return articles;
    }

    renderFeedList({ keepSelection = true, autoSelect = false } = {}) {
        const feedList = document.getElementById('feedList');
        if (!feedList) return;

        const fv = window.SN?.feedView;
        const filterVal = document.getElementById('feedFilter')?.value || 'all';
        const filteredSite = filterVal !== 'all'
            ? (this._sitesCache || []).find((s) => Number(s.id) === Number(filterVal))
            : null;
        const articles = this.visibleFeedArticles();
        if (fv?.updateFeedHeader) {
            fv.updateFeedHeader(this.feedMode, {
                count: articles.length,
                sourceLabel: filteredSite ? this.shortSiteLabel(filteredSite) : null,
            });
        } else {
            const titleEl = document.getElementById('feedTitle') || document.querySelector('.feed-header h1');
            const subEl = document.getElementById('feedSubtitle');
            if (titleEl) titleEl.textContent = this.feedMode === 'favorites' ? 'Favoris' : 'Feed';
            if (subEl) {
                subEl.textContent = this.feedMode === 'favorites'
                    ? 'Tes articles sauvegardes'
                    : 'Tous tes articles, toutes sources confondues';
            }
        }

        if (!articles.length) {
            const noSources = !(this._sitesCache || []).length;
            const feedCount = filteredSite ? this.parseRssFeeds(filteredSite.rss_feeds).length : 0;
            feedList.innerHTML = fv?.renderFeedEmptyHtml
                ? fv.renderFeedEmptyHtml({
                    feedMode: this.feedMode,
                    noSources,
                    filteredSite,
                    feedCount,
                    loadFailed: Boolean(this._feedLoadMeta?.failedSiteIds?.length),
                })
                : '<p class="feed-empty">Aucun article.</p>';

            if (this.feedMode === 'favorites' || noSources || filteredSite) {
                const reader = document.getElementById('articleReader');
                if (reader) {
                    reader.className = 'article-reader empty reader-empty-state';
                    reader.innerHTML = fv?.renderReaderEmptyMessage
                        ? fv.renderReaderEmptyMessage({ feedMode: this.feedMode, noSources })
                        : 'Selectionne un article.';
                }
            }
            return;
        }

        feedList.innerHTML = articles.map((article) => this.renderArticleListItem(article)).join('');

        if (!autoSelect) return;
        const prev = keepSelection ? this.selectedArticleId : null;
        const targetId = prev && articles.some((a) => a.id === prev)
            ? prev
            : articles[0].id;
        this.selectArticle(targetId);
    }

    formatRelativeTime(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        if (Number.isNaN(date.getTime())) return '';
        const diffMs = Date.now() - date.getTime();
        // Dates futures (events) : afficher la date absolue
        if (diffMs < -60 * 1000) {
            return date.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' });
        }
        const mins = Math.floor(Math.max(0, diffMs) / 60000);
        if (mins < 1) return 'A l\'instant';
        if (mins < 60) return `Il y a ${mins} min`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `Il y a ${hours} h`;
        const days = Math.floor(hours / 24);
        if (days < 7) return `Il y a ${days} j`;
        return date.toLocaleDateString('fr-FR');
    }

    cleanArticleTitle(title, site) {
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

    shortSiteLabel(site) {
        if (!site) return 'Source';
        const title = String(site.site_title || '').trim();
        if (title && title.length <= 28) return title;
        try {
            return new URL(site.url).hostname.replace(/^www\./, '');
        } catch (_) {
            return title.slice(0, 28) || 'Source';
        }
    }

    isNoiseArticle(article) {
        const feed = String(article.feed_url || '').toLowerCase();
        const title = String(article.title || '').trim();
        const titleLow = title.toLowerCase();
        if (feed.includes('/comments/') || feed.includes('comments/feed')) return true;
        if (feed.includes('sample-page/feed')) return true;
        if (titleLow.startsWith('commentaires sur ')) return true;
        if (titleLow.startsWith('comments on ')) return true;
        if (/^par\s*:/i.test(title)) return true;
        if (title.length < 8) return true;
        if (/^hello world$/i.test(titleLow)) return true;
        // Pingbacks / commentaires WordPress souvent tres courts
        const summary = String(article.summary || '').trim();
        if (summary.length > 0 && summary.length < 40 && /hello world|itstitle|here/i.test(summary)) {
            return true;
        }
        return false;
    }

    entityPillClass(label) {
        const l = String(label || '').toUpperCase();
        if (l === 'PER' || l === 'PERSON') return 'per';
        if (l === 'ORG' || l === 'ORGANIZATION') return 'org';
        if (l === 'LOC' || l === 'GPE' || l === 'LOCATION') return 'loc';
        return 'org';
    }

    entityCategoryFr(label) {
        const map = {
            ORG: 'ORGANISATION',
            PER: 'PERSONNE',
            PERSON: 'PERSONNE',
            LOC: 'LIEU',
            GPE: 'LIEU',
            LOCATION: 'LIEU',
            MISC: 'AUTRE',
        };
        return map[String(label || '').toUpperCase()] || 'ENTITE';
    }

    async showSiteDetails(siteId) {
        const filter = document.getElementById('feedFilter');
        if (filter) filter.value = String(siteId);
        this.showView('feed');
        await this.loadFeed({ keepSelection: false });
    }

    articleMeta(article) {
        const meta = article?.article_meta;
        return meta && typeof meta === 'object' ? meta : {};
    }

    resolveImageUrl(url, baseLink = '') {
        const raw = String(url || '').trim();
        if (!raw) return null;
        try {
            if (raw.startsWith('//')) return `https:${raw}`;
            if (/^https?:\/\//i.test(raw)) return raw;
            if (baseLink) return new URL(raw, baseLink).href;
            return raw;
        } catch (_) {
            return null;
        }
    }

    firstSrcsetUrl(srcset) {
        if (!srcset) return '';
        const first = String(srcset).split(',')[0] || '';
        return first.trim().split(/\s+/)[0] || '';
    }

    imageUrlFromElement(img, baseLink = '') {
        if (!img) return null;
        const src = (img.getAttribute('src') || '').trim();
        const dataSrc = (img.getAttribute('data-src') || img.getAttribute('data-lazy-src') || '').trim();
        const srcset = this.firstSrcsetUrl(img.getAttribute('srcset'));
        let raw = src;
        if (!raw || raw.startsWith('data:') || /placeholder|1x1|spacer/i.test(raw)) {
            raw = dataSrc || srcset || src;
        }
        if (!raw) raw = dataSrc || srcset;
        return this.resolveImageUrl(raw, baseLink);
    }

    normalizeImageUrl(url, baseLink = '') {
        const resolved = this.resolveImageUrl(url, baseLink);
        if (!resolved) return '';
        try {
            const u = new URL(resolved);
            return `${u.origin}${u.pathname}`.replace(/\/+$/, '').toLowerCase();
        } catch (_) {
            return resolved.toLowerCase();
        }
    }

    imageBasename(url, baseLink = '') {
        const norm = this.normalizeImageUrl(url, baseLink);
        if (!norm) return '';
        try {
            return decodeURIComponent(new URL(norm).pathname.split('/').pop() || '').toLowerCase();
        } catch (_) {
            return norm.split('/').pop()?.toLowerCase() || '';
        }
    }

    imageStem(url, baseLink = '') {
        const base = this.imageBasename(url, baseLink);
        if (!base) return '';
        return base
            .replace(/\.[a-z0-9]{2,5}$/i, '')
            .replace(/-\d+x\d+$/i, '');
    }

    imagesMatch(a, b, baseLink = '') {
        if (!a || !b) return false;
        if (this.normalizeImageUrl(a, baseLink) === this.normalizeImageUrl(b, baseLink)) return true;
        const fa = this.imageBasename(a, baseLink);
        const fb = this.imageBasename(b, baseLink);
        if (fa && fb && fa === fb) return true;
        // WordPress : photo.jpg vs photo-300x200.jpg
        const sa = this.imageStem(a, baseLink);
        const sb = this.imageStem(b, baseLink);
        return Boolean(sa && sb && sa === sb && sa.length > 4);
    }

    collectInlineImages(article) {
        const base = article?.link || '';
        return [
            ...this.extractImagesFromHtml(article?.content_html, base),
            ...this.extractImagesFromHtml(article?.summary, base),
        ];
    }

    pickArticleHero(article) {
        const base = article?.link || '';
        const meta = this.articleMeta(article);
        const inlineImgs = this.collectInlineImages(article);

        const flagged = (Array.isArray(article?.images) ? article.images : [])
            .find((img) => img && img.primary && img.url);
        if (flagged?.url) {
            const url = this.resolveImageUrl(flagged.url, base);
            if (url) {
                return { url, alt: flagged.alt || '', source: flagged.source || 'primary' };
            }
        }

        if (meta.primary_image) {
            const url = this.resolveImageUrl(meta.primary_image, base);
            if (url) {
                const better = inlineImgs.find((b) => this.imagesMatch(b.url, url, base));
                return {
                    url: better?.url || url,
                    alt: better?.alt || '',
                    source: 'primary',
                };
            }
        }

        let metaHero = null;
        for (const img of (Array.isArray(article?.images) ? article.images : [])) {
            if (img && typeof img === 'object' && img.url) {
                const url = this.resolveImageUrl(img.url, base);
                if (url) {
                    metaHero = { url, alt: img.alt || '', source: img.source || 'meta' };
                    break;
                }
            }
        }

        if (!metaHero) {
            const meta = this.articleMeta(article);
            for (const img of (Array.isArray(meta.images) ? meta.images : [])) {
                const raw = typeof img === 'string' ? img : img?.url;
                const url = this.resolveImageUrl(raw, base);
                if (url) {
                    metaHero = { url, alt: '', source: 'meta' };
                    break;
                }
            }
        }

        if (metaHero) {
            const better = inlineImgs.find((b) => this.imagesMatch(b.url, metaHero.url, base));
            if (better) {
                return { ...metaHero, url: better.url, alt: better.alt || metaHero.alt };
            }
            return metaHero;
        }

        if (inlineImgs.length) {
            return { ...inlineImgs[0], source: inlineImgs[0].source || 'html' };
        }

        return null;
    }

    renderHeroImg(hero, { wrapperClass = 'reader-hero', imgClass = '' } = {}) {
        if (!hero?.url) return '';
        const cls = imgClass ? ` class="${this.escapeAttr(imgClass)}"` : '';
        return `<div class="${this.escapeAttr(wrapperClass)}"><img${cls} src="${this.escapeAttr(hero.url)}" alt="${this.escapeAttr(hero.alt || '')}" loading="lazy" decoding="async" referrerpolicy="no-referrer"></div>`;
    }

    articleImages(article, hero = null) {
        const out = [];
        const seen = new Set();
        const base = article?.link || '';

        const add = (url, alt = '', source = '') => {
            const clean = this.resolveImageUrl(url, base);
            if (!clean) return;
            const key = this.normalizeImageUrl(clean, base);
            if (seen.has(key)) return;
            if (hero && this.imagesMatch(clean, hero.url, base)) return;
            seen.add(key);
            out.push({ url: clean, alt: (alt || '').slice(0, 300), source });
        };

        for (const img of this.extractImagesFromHtml(article?.content_html, base)) {
            add(img.url, img.alt, img.source);
        }

        for (const img of (Array.isArray(article?.images) ? article.images : [])) {
            if (img && typeof img === 'object') add(img.url, img.alt, img.source);
            else if (typeof img === 'string') add(img);
        }

        const meta = this.articleMeta(article);
        for (const img of (Array.isArray(meta.images) ? meta.images : [])) {
            if (typeof img === 'string') add(img, '', 'meta');
            else if (img && typeof img === 'object') add(img.url, img.alt, img.source || 'meta');
        }

        for (const img of this.extractImagesFromHtml(article?.summary, base)) {
            add(img.url, img.alt, img.source);
        }

        return out;
    }

    extractImagesFromHtml(html, baseLink = '') {
        if (!html || !/<img/i.test(String(html))) return [];
        const tmp = document.createElement('div');
        tmp.innerHTML = String(html);
        const imgs = [];
        tmp.querySelectorAll('img').forEach((img) => {
            const url = this.imageUrlFromElement(img, baseLink);
            if (!url) return;
            imgs.push({
                url,
                alt: img.getAttribute('alt') || '',
                source: 'html',
            });
        });
        return imgs;
    }

    stripHeroImagesFromHtml(html, hero, article) {
        if (!html) return html || '';
        const base = article?.link || '';
        const refs = [];
        if (hero?.url) refs.push(hero.url);
        for (const img of (Array.isArray(article?.images) ? article.images : [])) {
            const u = this.resolveImageUrl(img?.url, base);
            if (u) refs.push(u);
        }
        const heroStem = hero ? this.imageStem(hero.url, base) : '';

        const tmp = document.createElement('div');
        tmp.innerHTML = String(html);

        tmp.querySelectorAll('img').forEach((img) => {
            const src = this.imageUrlFromElement(img, base);
            let strip = refs.some((ref) => this.imagesMatch(src, ref, base));
            if (!strip && heroStem && this.imageStem(src, base) === heroStem) strip = true;

            if (!strip) return;

            const figure = img.closest('figure, picture');
            if (figure) {
                figure.remove();
                return;
            }
            const p = img.closest('p');
            if (p) {
                const clone = p.cloneNode(true);
                clone.querySelectorAll('img').forEach((node) => node.remove());
                if (!clone.textContent.trim()) p.remove();
                else img.remove();
            } else {
                img.remove();
            }
        });

        return tmp.innerHTML;
    }

    prepareArticleBodyHtml(article, hero) {
        if (!article?.content_html) return '';
        let html = article.content_html;
        if (hero) html = this.stripHeroImagesFromHtml(html, hero, article);
        return this.stripLeadingTitleFromHtml(html, article.title);
    }

    normalizeComparableText(text) {
        return String(text || '')
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .replace(/[«»""']/g, '')
            .replace(/\s+/g, ' ')
            .trim();
    }

    stripLeadingTitleFromHtml(html, title) {
        if (!html || !title) return html || '';
        const wanted = this.normalizeComparableText(title);
        if (wanted.length < 8) return html;

        const tmp = document.createElement('div');
        tmp.innerHTML = String(html);
        const candidates = tmp.querySelectorAll('h1, h2, h3, h4, .entry-title');
        for (const el of candidates) {
            const got = this.normalizeComparableText(el.textContent);
            if (!got) continue;
            if (got === wanted || got.includes(wanted) || wanted.includes(got)) {
                el.remove();
                break;
            }
        }
        return tmp.innerHTML;
    }

    isUsefulKeyword(kw) {
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

    normalizeKeywords(list, limit = 6) {
        const out = [];
        const seen = [];
        for (const raw of list || []) {
            const kw = String(raw || '').trim().replace(/\s+/g, ' ');
            if (!this.isUsefulKeyword(kw)) continue;
            const key = this.normalizeComparableText(kw);
            if (!key) continue;
            if (seen.some((s) => s === key || s.includes(key) || key.includes(s))) continue;
            seen.push(key);
            out.push(kw);
            if (out.length >= limit) break;
        }
        return out;
    }

    splitSummaryParts(text) {
        return String(text || '')
            .split(/\n+|(?<=[.!?…])\s+/)
            .map((s) => s.trim())
            .filter((s) => s.length > 0);
    }

    formatSummaryParagraphs(sumyBlock) {
        const sentences = Array.isArray(sumyBlock?.sentences)
            ? sumyBlock.sentences.filter(Boolean)
            : [];
        let parts = sentences.map((s) => String(s).trim()).filter(Boolean);
        if (!parts.length && sumyBlock?.summary) {
            parts = this.splitSummaryParts(sumyBlock.summary);
            if (parts.length <= 1 && String(sumyBlock.summary).length > 160) {
                parts = String(sumyBlock.summary)
                    .split(/(?<=[;])\s+/)
                    .map((s) => s.trim())
                    .filter(Boolean);
            }
        }
        if (!parts.length) return '';
        return `<div class="reader-analysis-summary">${parts.map((part) =>
            `<p>${this.escapeHtml(part)}</p>`
        ).join('')}</div>`;
    }

    articleHero(article) {
        return this.pickArticleHero(article);
    }

    articleDomain(article) {
        const meta = this.articleMeta(article);
        if (meta.domain) return meta.domain;
        try {
            return new URL(article.link).hostname.replace(/^www\./, '');
        } catch (_) {
            return '';
        }
    }

    articleChapo(article) {
        const meta = this.articleMeta(article);
        return meta.description || this.stripHtml(article.summary || '');
    }

    enrichStatusLabel(status) {
        const map = {
            ok: 'enrichi',
            pending: 'en cours',
            error: 'erreur',
        };
        return map[status] || status || '';
    }

    analysisStatusLabel(status) {
        const map = {
            ok: 'analysé',
            pending: 'analyse…',
            error: 'erreur NLP',
            skipped: 'non analysé',
        };
        return map[status] || status || '';
    }

    langLabel(code) {
        const map = {
            fr: 'Français',
            en: 'Anglais',
            de: 'Allemand',
            es: 'Espagnol',
            it: 'Italien',
            pt: 'Portugais',
            nl: 'Néerlandais',
        };
        return map[code] || code?.toUpperCase() || '';
    }

    entityClass(label) {
        const l = String(label || '').toUpperCase();
        if (l === 'ORG' || l === 'ORGANIZATION') return 'reader-entity-org';
        if (l === 'PER' || l === 'PERSON') return 'reader-entity-per';
        if (l === 'LOC' || l === 'GPE' || l === 'LOCATION') return 'reader-entity-loc';
        return 'reader-entity-misc';
    }

    entityLabelFr(label) {
        const map = {
            ORG: 'org',
            PER: 'pers',
            PERSON: 'pers',
            LOC: 'lieu',
            GPE: 'lieu',
            MISC: 'autre',
            DATE: 'date',
            MONEY: 'montant',
        };
        return map[String(label || '').toUpperCase()] || String(label || '').toLowerCase();
    }

    articleAnalysisStatus(article) {
        return this.articleMeta(article).analysis_status || '';
    }

    articleAnalysisBlocks(article) {
        const analysis = this.articleMeta(article).analysis;
        return analysis && typeof analysis === 'object' ? analysis : {};
    }

    formatReadingTime(meta) {
        const mins = meta?.reading_time_minutes;
        if (!mins) return '';
        return mins === 1 ? '1 min de lecture' : `${mins} min de lecture`;
    }

    articleListKeywords(article) {
        const blocks = this.articleAnalysisBlocks(article);
        const yake = blocks.keywords_yake;
        if (yake?.status === 'ok' && Array.isArray(yake.keywords) && yake.keywords.length) {
            return this.normalizeKeywords(yake.keywords, 2);
        }
        const meta = this.articleMeta(article);
        if (Array.isArray(meta.keywords) && meta.keywords.length) {
            return this.normalizeKeywords(meta.keywords, 2);
        }
        return [];
    }

    renderArticleListItem(article) {
        const fv = window.SN?.feedView;
        const source = article._siteLabel
            || this.articleDomain(article)
            || article._siteTitle
            || 'Source';
        const ctx = {
            selectedArticleId: this.selectedArticleId,
            isFavorite: this.isFavorite(article.id),
            isRead: this.isRead(article.id),
            keywords: this.articleListKeywords(article),
            hero: this.articleHero(article),
            source,
        };
        if (fv?.renderFeedRow) return fv.renderFeedRow(article, ctx);

        // Fallback legacy
        const selected = this.selectedArticleId === article.id ? ' is-selected' : '';
        return `<button type="button" class="feed-row${selected}" data-article-id="${article.id}">
            <h3>${this.escapeHtml(article.title || 'Sans titre')}</h3>
        </button>`;
    }

    _clearArticlePoll() {
        if (this._articlePollTimer) {
            clearInterval(this._articlePollTimer);
            this._articlePollTimer = null;
        }
    }

    _clearAnalysisPoll() {
        if (this._analysisPollTimer) {
            clearInterval(this._analysisPollTimer);
            this._analysisPollTimer = null;
        }
    }

    async selectArticle(articleId) {
        this.selectedArticleId = articleId;
        document.querySelectorAll('.feed-row, .article-item').forEach((el) => {
            el.classList.toggle('is-selected', Number(el.dataset.articleId) === articleId);
        });
        if (this.loadSettings().autoMarkRead) {
            this.markRead(articleId, true);
        }
        this._setMobileReaderMode(true);

        const reader = document.getElementById('articleReader');
        if (!reader) return;
        reader.classList.remove('empty');
        reader.innerHTML = `
            ${this._readerBackButtonHtml()}
            <p class="reader-meta">Chargement…</p>
        `;
        this._bindReaderBackButton();

        try {
            let article = await this.fetchArticle(articleId);
            if (!article) throw new Error('Article introuvable');
            const cached = this._feedArticles.find((a) => a.id === articleId);
            if (cached?._siteTitle) article._siteTitle = cached._siteTitle;
            if (cached?._siteLabel) article._siteLabel = cached._siteLabel;
            if (cached?.title) article.title = cached.title;
            else {
                const site = this._sitesCache.find((s) => Number(s.id) === Number(article.site_id));
                article.title = this.cleanArticleTitle(article.title, site);
            }

            if (article.enrich_status !== 'ok' && article.enrich_status !== 'pending') {
                await fetch(`/api/articles/${articleId}/enrich`, { method: 'POST' });
                this.renderArticleReader(article, { loading: true });
                this._pollArticleUntilDone(articleId);
                return;
            }

            if (article.enrich_status === 'pending') {
                this.renderArticleReader(article, { loading: true });
                this._pollArticleUntilDone(articleId);
                return;
            }

            this.renderArticleReader(article, { loading: false });
            await this._maybeStartAnalysis(articleId, article);
        } catch (err) {
            reader.innerHTML = `<p class="reader-meta">Erreur: ${this.escapeHtml(err.message)}</p>`;
        }
    }

    async _maybeStartAnalysis(articleId, article) {
        if (article.enrich_status !== 'ok') return;
        const meta = this.articleMeta(article);
        const status = meta.analysis_status;
        if (status === 'ok' || status === 'pending') {
            if (status === 'pending') {
                this.renderArticleReader(article, { loadingAnalysis: true });
                this._pollAnalysisUntilDone(articleId);
            }
            return;
        }
        try {
            await fetch(`/api/articles/${articleId}/analyze`, { method: 'POST' });
            this.renderArticleReader(article, { loadingAnalysis: true });
            this._pollAnalysisUntilDone(articleId);
        } catch (_) {
            /* analyse optionnelle */
        }
    }

    async fetchArticle(articleId) {
        const res = await fetch(`/api/articles/${articleId}`);
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.error || data.detail || 'Chargement impossible');
        }
        return res.json();
    }

    _pollArticleUntilDone(articleId) {
        this._clearArticlePoll();
        let tries = 0;
        this._articlePollTimer = setInterval(async () => {
            tries += 1;
            if (this.selectedArticleId !== articleId || tries > 40) {
                this._clearArticlePoll();
                return;
            }
            try {
                const article = await this.fetchArticle(articleId);
                if (article.enrich_status === 'ok' || article.enrich_status === 'error') {
                    this._clearArticlePoll();
                    this.renderArticleReader(article, { loading: false });
                    this._updateArticleBadge(articleId, article.enrich_status);
                    if (article.enrich_status === 'ok') {
                        await this._maybeStartAnalysis(articleId, article);
                    }
                }
            } catch (_) {
                /* ignore transient */
            }
        }, 1500);
    }

    _pollAnalysisUntilDone(articleId) {
        this._clearAnalysisPoll();
        let tries = 0;
        this._analysisPollTimer = setInterval(async () => {
            tries += 1;
            if (this.selectedArticleId !== articleId || tries > 40) {
                this._clearAnalysisPoll();
                return;
            }
            try {
                const article = await this.fetchArticle(articleId);
                const status = this.articleAnalysisStatus(article);
                if (status === 'ok' || status === 'error' || status === 'skipped') {
                    this._clearAnalysisPoll();
                    this.renderArticleReader(article, { loading: false, loadingAnalysis: false });
                    this._updateAnalysisBadge(articleId, status);
                }
            } catch (_) {
                /* ignore transient */
            }
        }, 1500);
    }

    _updateAnalysisBadge(articleId, status) {
        const el = document.querySelector(`.article-item[data-article-id="${articleId}"] h4`);
        if (!el) return;
        let badge = el.querySelector('.article-analysis-badge');
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'article-analysis-badge';
            el.appendChild(badge);
        }
        badge.className = `article-analysis-badge ${status || ''}`;
        badge.textContent = this.analysisStatusLabel(status);
    }

    _updateArticleBadge(articleId, status) {
        const el = document.querySelector(`.article-item[data-article-id="${articleId}"] h4`);
        if (!el) return;
        let badge = el.querySelector('.article-enrich-badge');
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'article-enrich-badge';
            el.appendChild(badge);
        }
        badge.className = `article-enrich-badge ${status || ''}`;
        badge.textContent = this.enrichStatusLabel(status);
    }

    renderAnalysisPanel(article, { loadingAnalysis } = {}) {
        if (article.enrich_status !== 'ok') return '';

        const meta = this.articleMeta(article);
        const analysisStatus = meta.analysis_status || '';
        const blocks = this.articleAnalysisBlocks(article);
        const reanalyzeBtn = `<button type="button" class="btn" data-reanalyze="${article.id}">Reanalyser</button>`;

        if (loadingAnalysis || analysisStatus === 'pending') {
            return `<section class="reader-analysis-section">
                <span class="reader-section-label">Analyse</span>
                <div class="reader-analysis-panel is-loading">
                    <h4>
                        <span class="reader-analysis-head">Analyse texte</span>
                        <span class="reader-analysis-actions">${reanalyzeBtn}</span>
                    </h4>
                    <p class="reader-analysis-empty">Analyse en cours (langue, mots-cles, resume, entites)…</p>
                </div>
            </section>`;
        }

        const langBlock = blocks.lang_detect;
        const yakeBlock = blocks.keywords_yake;
        const sumyBlock = blocks.summary_sumy;
        const nerBlock = blocks.ner_spacy;
        const simBlock = blocks.simhash;

        const hasLang = langBlock?.status === 'ok' && langBlock.lang;
        const yakeKws = yakeBlock?.status === 'ok' && Array.isArray(yakeBlock.keywords)
            ? this.normalizeKeywords(yakeBlock.keywords, 8)
            : [];
        const summaryHtml = sumyBlock?.status === 'ok' ? this.formatSummaryParagraphs(sumyBlock) : '';
        const entities = nerBlock?.status === 'ok' && Array.isArray(nerBlock.entities)
            ? nerBlock.entities : [];
        const simhash = simBlock?.status === 'ok' ? (simBlock.hex || simBlock.value) : '';

        const hasContent = hasLang || yakeKws.length || summaryHtml || entities.length || simhash;

        if (!hasContent) {
            const err = meta.analysis_error;
            const emptyMsg = analysisStatus === 'error'
                ? `Analyse echouee${err ? ` : ${err}` : ''}`
                : 'Pas encore analyse.';
            return `<section class="reader-analysis-section">
                <span class="reader-section-label">Analyse</span>
                <div class="reader-analysis-panel">
                    <h4>
                        <span class="reader-analysis-head">Analyse texte</span>
                        <span class="reader-analysis-actions">${reanalyzeBtn}</span>
                    </h4>
                    <p class="reader-analysis-empty">${this.escapeHtml(emptyMsg)}</p>
                </div>
            </section>`;
        }

        const langBadge = hasLang
            ? `<span class="reader-lang-badge" title="Confiance ${Math.round((langBlock.confidence || 0) * 100)}%">
                ${this.escapeHtml(this.langLabel(langBlock.lang))}
               </span>`
            : '';

        const summaryBlock = summaryHtml || '';

        const yakeBlockHtml = yakeKws.length
            ? `<div class="reader-analysis-keywords">${yakeKws.map((kw) =>
                `<span class="reader-analysis-keyword">${this.escapeHtml(kw)}</span>`
            ).join('')}</div>`
            : '';

        const entitiesBlock = entities.length
            ? `<div class="reader-entities">${entities.map((ent) =>
                `<span class="reader-entity ${this.entityClass(ent.label)}"
                    data-label="${this.escapeAttr(this.entityLabelFr(ent.label))}">
                    ${this.escapeHtml(ent.text)}
                </span>`
            ).join('')}</div>`
            : '';

        const footerBits = [];
        if (simhash) footerBits.push(`Empreinte ${String(simhash).slice(0, 12)}…`);
        if (meta.analyzed_at) {
            footerBits.push(`Analyse ${new Date(meta.analyzed_at).toLocaleString()}`);
        }
        const footer = footerBits.length
            ? `<div class="reader-analysis-meta">${footerBits.map((b) => this.escapeHtml(b)).join(' · ')}</div>`
            : '';

        let sections = '';
        if (summaryBlock) sections += `<div class="reader-analysis-block"><strong>Resume</strong>${summaryBlock}</div>`;
        if (yakeBlockHtml) sections += `<div class="reader-analysis-block"><strong>Mots-cles</strong>${yakeBlockHtml}</div>`;
        if (entitiesBlock) sections += `<div class="reader-analysis-block"><strong>Entites</strong>${entitiesBlock}</div>`;

        return `<section class="reader-analysis-section">
            <span class="reader-section-label">Analyse</span>
            <div class="reader-analysis-panel">
                <h4>
                    <span class="reader-analysis-head">Synthese ${langBadge}</span>
                    <span class="reader-analysis-actions">${reanalyzeBtn}</span>
                </h4>
                ${sections}
                ${footer}
            </div>
        </section>`;
    }

    renderArticleReader(article, { loading, loadingAnalysis } = {}) {
        const reader = document.getElementById('articleReader');
        if (!reader || this.selectedArticleId !== article.id) return;
        reader.classList.remove('empty', 'reader-empty-state');

        if (loading && article.enrich_status === 'ok') loading = false;

        const meta = this.articleMeta(article);
        const hero = this.pickArticleHero(article);
        const gallery = this.articleImages(article, hero);
        const published = article.published_at
            ? new Date(article.published_at).toLocaleString('fr-FR', {
                day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit',
            })
            : (meta.date_published || '');
        const chapo = this.articleChapo(article);
        const sourceName = article._siteLabel || this.articleDomain(article) || article._siteTitle || 'Source';
        const blocks = this.articleAnalysisBlocks(article);
        const sumyBlock = blocks.summary_sumy;
        const nerBlock = blocks.ner_spacy;
        const rv = window.SN?.readerView;

        const summaryHtml = rv?.buildSummaryHtml
            ? rv.buildSummaryHtml({
                loadingAnalysis,
                analysisPending: meta.analysis_status === 'pending',
                sumyBlock,
                chapo,
                escapeHtml: (t) => this.escapeHtml(t),
            })
            : `<p>${this.escapeHtml(chapo || 'Resume indisponible')}</p>`;

        const entities = nerBlock?.status === 'ok' && Array.isArray(nerBlock.entities)
            ? nerBlock.entities.slice(0, 8) : [];
        const yake = blocks.keywords_yake;
        const keywords = (!entities.length && yake?.status === 'ok' && Array.isArray(yake.keywords))
            ? this.normalizeKeywords(yake.keywords, 6)
            : [];

        let preparedHtml = '';
        if (!loading && article.enrich_status !== 'error' && article.content_html) {
            preparedHtml = this.prepareArticleBodyHtml(article, hero);
        }
        const bodyHtml = rv?.buildBodyHtml
            ? rv.buildBodyHtml({
                loading,
                article,
                chapo,
                preparedHtml,
                escapeHtml: (t) => this.escapeHtml(t),
            })
            : '';

        const galleryHtml = gallery.length
            ? `<div class="reader-gallery">${gallery.map((img) =>
                `<img class="js-hide-on-error" src="${this.escapeAttr(img.url)}" alt="${this.escapeAttr(img.alt || '')}" loading="lazy">`
            ).join('')}</div>`
            : '';

        const heroHtml = hero ? this.renderHeroImg(hero, { wrapperClass: 'reader-hero' }) : '';

        reader.className = 'article-reader';
        reader.innerHTML = rv?.buildReaderHtml
            ? rv.buildReaderHtml(article, {
                loading,
                loadingAnalysis,
                backButtonHtml: this._readerBackButtonHtml(),
                heroHtml,
                bodyHtml,
                galleryHtml,
                summaryHtml,
                entities,
                keywords,
                sourceName,
                published,
                isFavorite: this.isFavorite(article.id),
                isRead: this.isRead(article.id),
                showSummaryFirst: this.loadSettings().showSummaryFirst !== false,
            })
            : `<p>${this.escapeHtml(article.title || '')}</p>`;

        this._bindReaderBackButton();

        reader.querySelector('[data-reader-action="share"]')?.addEventListener('click', () => {
            if (navigator.share) {
                navigator.share({ title: article.title, url: article.link }).catch(() => {});
            } else if (article.link) {
                navigator.clipboard?.writeText(article.link);
                this.updateStatus('Lien copie', 'success');
            }
        });
        reader.querySelector('[data-reader-action="favorite"]')?.addEventListener('click', () => {
            const nowFav = this.toggleFavorite(article.id);
            this.updateStatus(nowFav ? 'Ajoute aux favoris' : 'Retire des favoris', 'success');
            this.renderFeedList({ keepSelection: true, autoSelect: false });
            this.renderArticleReader(article);
            if (this.feedMode === 'favorites' && !nowFav) {
                this.renderFeedList({ keepSelection: false, autoSelect: true });
            }
        });
        reader.querySelector('[data-reader-action="read"]')?.addEventListener('click', () => {
            const next = !this.isRead(article.id);
            this.markRead(article.id, next);
            this.updateStatus(next ? 'Marque comme lu' : 'Marque non lu', 'success');
            this.renderFeedList({ keepSelection: true, autoSelect: false });
            this.renderArticleReader(article);
        });

        const reBtn = reader.querySelector('[data-reenrich]');
        if (reBtn) {
            reBtn.addEventListener('click', async () => {
                reBtn.disabled = true;
                try {
                    if (window.SN?.api) await window.SN.api.enrichArticle(article.id, true);
                    else await fetch(`/api/articles/${article.id}/enrich?force=1`, { method: 'POST' });
                    this.renderArticleReader(article, { loading: true });
                    this._pollArticleUntilDone(article.id);
                } catch (err) {
                    this.updateStatus(`Erreur: ${err.message}`, 'error');
                }
            });
        }

        const analyzeBtn = reader.querySelector('[data-reanalyze]');
        if (analyzeBtn) {
            analyzeBtn.addEventListener('click', async () => {
                analyzeBtn.disabled = true;
                try {
                    if (window.SN?.api) await window.SN.api.analyzeArticle(article.id, true);
                    else await fetch(`/api/articles/${article.id}/analyze?force=1`, { method: 'POST' });
                    this.renderArticleReader(article, { loadingAnalysis: true });
                    this._pollAnalysisUntilDone(article.id);
                } catch (err) {
                    this.updateStatus(`Erreur: ${err.message}`, 'error');
                    analyzeBtn.disabled = false;
                }
            });
        }
    }

    handleArticleEnriched(data) {
        const articleId = Number(data.article_id);
        if (!articleId) return;
        this._updateArticleBadge(articleId, data.status);
        // Refresh feed row thumbnail / chips after enrich
        if (data.status === 'ok') {
            this.fetchArticle(articleId).then((article) => {
                const idx = this._feedArticles.findIndex((a) => a.id === articleId);
                if (idx >= 0) {
                    const prev = this._feedArticles[idx];
                    this._feedArticles[idx] = {
                        ...article,
                        _siteTitle: prev._siteTitle,
                        _siteLabel: prev._siteLabel,
                        _siteId: prev._siteId,
                    };
                    const row = document.querySelector(`.feed-row[data-article-id="${articleId}"]`);
                    if (row) {
                        const tmp = document.createElement('div');
                        tmp.innerHTML = this.renderArticleListItem(this._feedArticles[idx]);
                        row.replaceWith(tmp.firstElementChild);
                    }
                }
            }).catch(() => {});
        }
        if (this.selectedArticleId === articleId) {
            this.fetchArticle(articleId)
                .then(async (article) => {
                    const cached = this._feedArticles.find((a) => a.id === articleId);
                    if (cached?._siteLabel) article._siteLabel = cached._siteLabel;
                    if (cached?._siteTitle) article._siteTitle = cached._siteTitle;
                    this.renderArticleReader(article, { loading: false });
                    if (data.status === 'ok') {
                        await this._maybeStartAnalysis(articleId, article);
                    }
                })
                .catch(() => {});
        }
    }

    handleArticleAnalyzed(data) {
        const articleId = Number(data.article_id);
        if (!articleId) return;
        this._updateAnalysisBadge(articleId, data.status);
        if (this.selectedArticleId === articleId) {
            this.fetchArticle(articleId)
                .then((article) => this.renderArticleReader(article, { loading: false, loadingAnalysis: false }))
                .catch(() => {});
        }
    }

    async deleteSite(siteId) {
        const ok = window.confirm(
            `Supprimer le site #${siteId} ?\n\nCela efface aussi les pages crawlees, les feeds detectes et tous les articles importes.`
        );
        if (!ok) return;

        try {
            const res = await fetch(`/api/sites/${siteId}`, { method: 'DELETE' });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.error || data.detail || 'Suppression impossible');

            const d = data.deleted || {};
            this.updateStatus(
                `Site #${siteId} supprimé (${d.pages || 0} pages, ${d.feeds || 0} feeds, ${d.articles || 0} articles)`,
                'success'
            );
            this.viewingSiteId = null;
            this.selectedArticleId = null;
            await this.loadSites();
            await this.loadFeed({ keepSelection: false });
            this.showView('feed');
        } catch (err) {
            console.error(err);
            this.updateStatus(`Erreur: ${err.message}`, 'error');
        }
    }

    escapeHtml(text) {
        return String(text ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    escapeAttr(text) {
        return this.escapeHtml(text).replace(/'/g, '&#39;');
    }

    stripHtml(html) {
        const tmp = document.createElement('div');
        tmp.innerHTML = html || '';
        return tmp.textContent || tmp.innerText || '';
    }

    updateStatus(message, type) {
        const settings = this.loadSettings();
        if (settings.toasts === false && type !== 'error') return;

        const statusDiv = document.getElementById('status');
        if (!statusDiv) return;
        statusDiv.textContent = message;
        // garder status-toast sinon le bandeau redevient une "page" legacy en haut
        statusDiv.className = `status status-toast ${type || 'info'}`;
        statusDiv.style.display = 'block';

        clearTimeout(this._statusTimer);
        this._statusTimer = setTimeout(() => {
            statusDiv.style.display = 'none';
        }, 4500);
    }

    showLoading(show) {
        const progress = document.getElementById('addSourceProgress');
        const analyzeBtn = document.getElementById('analyzeBtn');
        const stopBtn = document.getElementById('stopAnalyzeBtn');
        const form = document.getElementById('analyzeForm');
        const actions = document.getElementById('addSourceActions');
        const legacyLoading = document.getElementById('loading');

        window.SN?.bus?.emit('add-source:busy', show);

        if (show) {
            if (progress) progress.hidden = false;
            if (legacyLoading) legacyLoading.style.display = 'block';
            if (analyzeBtn) analyzeBtn.disabled = true;
            if (actions) actions.hidden = true;
            if (stopBtn) stopBtn.disabled = false;
            if (form) form.hidden = true;
            const bar = document.getElementById('addSourceProgressBar');
            if (bar) {
                bar.setAttribute('indeterminate', '');
                bar.removeAttribute('value');
            }
            const fill = document.getElementById('addSourceProgressFill');
            if (fill) fill.style.width = '8%';
        } else {
            if (progress && document.getElementById('addSourceVictory')?.hidden !== false) {
                progress.hidden = true;
            }
            if (legacyLoading) legacyLoading.style.display = 'none';
            if (analyzeBtn) {
                analyzeBtn.disabled = false;
                analyzeBtn.hidden = false;
            }
            if (actions) actions.hidden = false;
            if (stopBtn) stopBtn.disabled = false;
        }
    }

    setLoadingText(text) {
        const label = document.getElementById('addSourceProgressLabel');
        if (label) label.textContent = text;
        const loadingDiv = document.getElementById('loading');
        const progressText = loadingDiv && loadingDiv.querySelector('p');
        if (progressText) progressText.textContent = text;
        window.SN?.bus?.emit('add-source:progress', { text });
    }

    updateProgress(current, total) {
        const cur = Number(current);
        const tot = Number(total);
        const safeCur = Number.isFinite(cur) && cur >= 0 ? cur : 0;
        const safeTot = Number.isFinite(tot) && tot > 0 ? tot : null;
        const fill = document.getElementById('addSourceProgressFill');
        const bar = document.getElementById('addSourceProgressBar');
        let text = 'Discovery des liens...';
        let value = null;

        if (safeTot == null) {
            text = safeCur > 0
                ? `Analyse en cours... ${safeCur} page(s)`
                : 'Discovery des liens...';
            if (fill) fill.style.width = `${Math.min(40, 8 + safeCur * 2)}%`;
            if (bar) bar.setAttribute('indeterminate', '');
        } else {
            const percentage = Math.min(100, Math.max(0, Math.round((safeCur / safeTot) * 100)));
            value = percentage / 100;
            if (fill) fill.style.width = `${Math.max(8, percentage)}%`;
            if (bar) {
                bar.removeAttribute('indeterminate');
                bar.setAttribute('value', String(value));
            }
            text = safeCur >= safeTot
                ? `Crawl terminé (${safeCur} page${safeCur > 1 ? 's' : ''}) — import des articles...`
                : `Analyse en cours... ${safeCur}/${safeTot} pages (${percentage}%)`;
        }

        this.setLoadingText(text);
        window.SN?.bus?.emit('add-source:progress', { text, value });
    }

    /**
     * Si le crawl a trouve des flux mais 0 article (chord Celery rate / timeout),
     * on reimporte en synchrone via l'API analyzer.
     */
    async ensureSiteArticles(siteId) {
        const id = Number(siteId);
        if (!id) return 0;
        try {
            const res = await fetch(`/api/sites/${id}/articles?limit=5`);
            const data = res.ok ? await res.json() : { articles: [] };
            const existing = (data.articles || []).length;
            if (existing > 0) return existing;

            const siteRes = await fetch(`/api/sites/${id}`);
            const site = siteRes.ok ? await siteRes.json() : null;
            const feeds = this.parseRssFeeds(site?.rss_feeds);
            if (!feeds.length) return 0;

            this.updateStatus('Import des articles RSS…', 'info');
            const ingestRes = await fetch(`/api/sites/${id}/ingest-articles`, { method: 'POST' });
            const ingest = ingestRes.ok ? await ingestRes.json() : {};
            const count = Number(ingest.articles_count) || 0;
            if (count > 0) {
                this.updateStatus(`${count} articles importes`, 'success');
            } else {
                this.updateStatus('Aucun article dans ces flux', 'info');
            }
            return count;
        } catch (err) {
            console.warn('ensureSiteArticles', err);
            return 0;
        }
    }

    /**
     * Filet de securite : si le WS rate analysis_completed, on poll le statut.
     */
    _watchAnalysisFinish(siteId) {
        const started = Date.now();
        const maxMs = 15 * 60 * 1000;
        let ingestFallbackAt = 0;
        const tick = async () => {
            if (!this.sameSite(siteId)) return;
            if (Date.now() - started > maxMs) {
                this.updateStatus('Analyse trop longue — verifie les logs worker', 'error');
                this.showLoading(false);
                this.currentAnalysis = null;
                return;
            }
            try {
                const res = await fetch(`/api/sites/${siteId}`);
                if (res.ok) {
                    const site = await res.json();
                    const st = site.status;
                    const feeds = this.parseRssFeeds(site.rss_feeds);

                    // Import RSS encore en file Celery
                    if (st === 'ingesting' || st === 'analyzing' || st === 'pending') {
                        if (st === 'ingesting') {
                            this.setLoadingText(`Import des articles (${feeds.length || '?'} flux)...`);
                        }
                        // Filet : si l'import Celery traine, on bascule sur l'API sync
                        if (st === 'ingesting' && Date.now() - started > 45000 && !ingestFallbackAt) {
                            ingestFallbackAt = Date.now();
                            await this.ensureSiteArticles(siteId);
                            // Re-check apres import sync
                            const again = await fetch(`/api/sites/${siteId}/articles?limit=3`);
                            const againData = again.ok ? await again.json() : { articles: [] };
                            if ((againData.articles || []).length > 0) {
                                this.updateJob(`crawl-site-${siteId}`, {
                                    status: 'done',
                                    detail: `${feeds.length} flux RSS · ${(againData.articles || []).length}+ articles`,
                                });
                                this._pendingVictorySiteId = siteId;
                                const victory = document.getElementById('addSourceVictory');
                                const victoryText = document.getElementById('addSourceVictoryText');
                                const form = document.getElementById('analyzeForm');
                                if (form) form.style.display = 'none';
                                if (victory) {
                                    victory.hidden = false;
                                    if (victoryText) {
                                        victoryText.textContent = `${feeds.length} flux trouves. Pret a lire.`;
                                    }
                                    this.openAddSourceModal({ keepVictory: true });
                                }
                                this.showLoading(false);
                                this.currentAnalysis = null;
                                await this.loadSites();
                                return;
                            }
                        }
                    } else if (st === 'completed' || st === 'error' || st === 'cancelled') {
                        if (st === 'completed') {
                            if (feeds.length) await this.ensureSiteArticles(siteId);
                            this.updateStatus(
                                `Analyse terminée ! ${feeds.length} flux RSS`,
                                'success'
                            );
                            this.updateJob(`crawl-site-${siteId}`, {
                                status: 'done',
                                detail: `${feeds.length} flux RSS`,
                            });
                            this._pendingVictorySiteId = siteId;
                            const victory = document.getElementById('addSourceVictory');
                            const victoryText = document.getElementById('addSourceVictoryText');
                            const form = document.getElementById('analyzeForm');
                            if (form) form.style.display = 'none';
                            if (victory) {
                                victory.hidden = false;
                                if (victoryText) {
                                    victoryText.textContent = `${feeds.length} flux trouves. Pret a lire.`;
                                }
                                this.openAddSourceModal({ keepVictory: true });
                            } else {
                                this.showView('feed');
                            }
                            const filter = document.getElementById('feedFilter');
                            if (filter) filter.value = String(siteId);
                            await this.loadFeed({ keepSelection: false });
                        } else if (st === 'error') {
                            this.updateStatus('Analyse en erreur', 'error');
                            this.updateJob(`crawl-site-${siteId}`, { status: 'error', detail: 'Erreur' });
                            const form = document.getElementById('analyzeForm');
                            if (form) form.style.display = '';
                        } else {
                            this.updateStatus('Analyse arrêtée', 'info');
                            const form = document.getElementById('analyzeForm');
                            if (form) form.style.display = '';
                        }
                        this.showLoading(false);
                        this.currentAnalysis = null;
                        await this.loadSites();
                        return;
                    }
                }
            } catch (_) {
                /* ignore */
            }
            setTimeout(tick, 4000);
        };
        setTimeout(tick, 8000);
    }

    addPageLog(_message, _type) {
        // Ancien panneau #results desactive : le feedback vit dans le modal
    }

    addRssFeed(_data) {
        // Ancien panneau #results desactive
    }

    clearResults() {
        const resultsDiv = document.getElementById('results');
        if (resultsDiv) {
            resultsDiv.innerHTML = '';
            resultsDiv.hidden = true;
        }
        const resultsCard = document.getElementById('resultsCard');
        if (resultsCard) {
            resultsCard.hidden = true;
            resultsCard.style.display = 'none';
        }
    }

    showResults() {
        // Ne plus afficher l'ancien panneau de resultats live
        this.clearResults();
    }

    getStatusText(status) {
        const statusMap = {
            'pending': 'En attente',
            'analyzing': 'En cours',
            'ingesting': 'Import RSS',
            'completed': 'Terminé',
            'error': 'Erreur',
            'cancelled': 'Arrêté',
            'cancelling': 'Arrêt...'
        };
        return statusMap[status] || status;
    }
}

// Styles additionnels pour les logs et animations
const additionalStyles = `
    <style>
        .page-logs {
            max-height: 200px;
            overflow-y: auto;
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 20px;
        }
        
        .log-entry {
            padding: 5px 0;
            border-bottom: 1px solid #e9ecef;
            font-family: monospace;
            font-size: 12px;
        }
        
        .log-entry:last-child {
            border-bottom: none;
        }
        
        .log-entry.success {
            color: #155724;
        }
        
        .log-entry.rss {
            color: #007bff;
            font-weight: bold;
        }
        
        .log-entry .time {
            color: #6c757d;
            margin-right: 10px;
        }
        
        .rss-feed.new-feed {
            animation: highlight 1s ease-in-out;
        }
        
        @keyframes highlight {
            0% { background: #fff3cd; }
            100% { background: #f8f9fa; }
        }
        
        .site-details {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        
        .site-details p {
            margin-bottom: 8px;
        }
    </style>
`;

document.head.insertAdjacentHTML('beforeend', additionalStyles);

// Bootstrap via /js/main.js (ES module)
const app = new StreamNewsApp();
window.app = app;
export default app; 