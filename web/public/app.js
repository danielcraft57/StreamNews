class StreamNewsApp {
    constructor() {
        this.socket = null;
        this.currentAnalysis = null;
        this.analysisMaxPages = 50;   // plafond formulaire
        this.analysisTotalPages = null; // vrai total apres discovery
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadSites();
        this.connectWebSocket();
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
        sitesList.addEventListener('click', (e) => {
            const deleteBtn = e.target.closest('[data-delete-site]');
            if (deleteBtn) {
                e.preventDefault();
                e.stopPropagation();
                const siteId = Number(deleteBtn.dataset.deleteSite);
                if (siteId) this.deleteSite(siteId);
                return;
            }
            const item = e.target.closest('.site-item[data-site-id]');
            if (!item) return;
            const siteId = Number(item.dataset.siteId);
            if (siteId) this.showSiteDetails(siteId);
        });
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        this.socket = new WebSocket(wsUrl);
        
        this.socket.onopen = () => {
            console.log('WebSocket connecté');
            this.updateStatus('WebSocket connecté', 'success');
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
                this.loadSites();
                return;
            }
            const articlesBit = data.articles_count != null ? ` · ${data.articles_count} articles` : '';
            this.updateStatus(
                `Analyse terminée ! ${data.rss_count} flux RSS trouvés${articlesBit}`,
                'success'
            );
            this.showLoading(false);
            const pages = data.total_pages ?? this.analysisTotalPages;
            if (pages != null) this.updateProgress(pages, pages);
            this.loadSites();
            this.currentAnalysis = null;
            if (data.site_id) {
                this.showSiteDetails(Number(data.site_id));
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
        
        const formData = new FormData(e.target);
        const url = formData.get('url');
        const maxPages = parseInt(formData.get('maxPages'), 10);
        const depth = parseInt(formData.get('depth'), 10);
        
        if (!url) {
            this.updateStatus('Veuillez saisir une URL', 'error');
            return;
        }

        this.analysisMaxPages = Number.isFinite(maxPages) && maxPages > 0 ? maxPages : 50;
        this.analysisTotalPages = null;
        
        try {
            this.updateStatus('Lancement de l\'analyse...', 'info');
            this.showLoading(true);
            this.setLoadingText('Lancement...');
            this.clearResults();
            
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url,
                    max_pages: this.analysisMaxPages,
                    depth: depth
                })
            });
            
            const result = await response.json();
            
            if (response.ok) {
                this.updateStatus(`Analyse lancée (ID: ${result.site_id})`, 'success');
                this.currentAnalysis = Number(result.site_id);
                this._watchAnalysisFinish(Number(result.site_id));
            } else {
                throw new Error(result.error || 'Erreur lors du lancement');
            }
            
        } catch (error) {
            this.updateStatus(`Erreur: ${error.message}`, 'error');
            this.showLoading(false);
            this.currentAnalysis = null;
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
            
            const sitesList = document.getElementById('sitesList');
            
            if (data.sites && data.sites.length > 0) {
                sitesList.innerHTML = data.sites.map(site => {
                    const feeds = this.parseRssFeeds(site.rss_feeds);
                    return `
                    <div class="site-item" data-site-id="${site.id}" role="button" tabindex="0">
                        <div class="site-item-header">
                            <h4>${this.escapeHtml(site.url)}</h4>
                            <button type="button" class="btn-delete" data-delete-site="${site.id}" title="Supprimer le site">
                                Supprimer
                            </button>
                        </div>
                        <div class="site-info">
                            <span class="status ${site.status}">${this.getStatusText(site.status)}</span>
                            <span class="date">${new Date(site.created_at).toLocaleString()}</span>
                        </div>
                        ${site.total_pages_analyzed ? `<div>Pages: ${site.total_pages_analyzed}</div>` : ''}
                        ${feeds.length > 0 ? `<div>RSS: ${feeds.length}</div>` : ''}
                    </div>
                `;
                }).join('');
            } else {
                sitesList.innerHTML = '<p>Aucun site analysé pour le moment</p>';
            }
        } catch (error) {
            console.error('Erreur lors du chargement des sites:', error);
        }
    }

    async showSiteDetails(siteId) {
        try {
            const [siteRes, articlesRes] = await Promise.all([
                fetch(`/api/sites/${siteId}`),
                fetch(`/api/sites/${siteId}/articles?limit=100`)
            ]);
            const site = await siteRes.json();
            const articlesData = articlesRes.ok ? await articlesRes.json() : { articles: [] };
            const feeds = this.parseRssFeeds(site.rss_feeds);
            const articles = Array.isArray(articlesData.articles) ? articlesData.articles : [];
            
            this.clearResults();
            this.showResults();
            
            const resultsDiv = document.getElementById('results');
            resultsDiv.innerHTML = `
                <h3>Détails de l'analyse</h3>
                <div class="site-details">
                    <p><strong>URL:</strong> ${this.escapeHtml(site.url)}</p>
                    <p><strong>Statut:</strong> <span class="status ${site.status}">${this.getStatusText(site.status)}</span></p>
                    <p><strong>Pages analysées:</strong> ${site.total_pages_analyzed || 0}</p>
                    <p><strong>Date:</strong> ${new Date(site.created_at).toLocaleString()}</p>
                    <p style="margin-top:12px">
                        <button type="button" class="btn btn-danger" data-delete-site-detail="${siteId}" style="width:auto;padding:10px 16px;font-size:14px;background:linear-gradient(135deg,#c0392b 0%,#922b21 100%)">
                            Supprimer ce site
                        </button>
                    </p>
                </div>
                
                ${feeds.length > 0 ? `
                    <h4>Flux RSS trouvés (${feeds.length})</h4>
                    <div class="rss-feeds">
                        ${feeds.map(feed => `
                            <div class="rss-feed">
                                <h4>${this.escapeHtml(feed.title || 'Flux RSS')}</h4>
                                <p><a href="${this.escapeAttr(feed.url)}" target="_blank" rel="noopener noreferrer">${this.escapeHtml(feed.url)}</a></p>
                                <small>Type: ${this.escapeHtml(feed.type || '-')} | Source: ${this.escapeHtml(feed.source_page || '-')}</small>
                            </div>
                        `).join('')}
                    </div>
                    <p style="margin-top:12px">
                        <button type="button" class="btn" data-ingest-site="${siteId}" style="width:auto;padding:10px 16px;font-size:14px">
                            Recharger les articles des flux
                        </button>
                    </p>
                ` : '<p>Aucun flux RSS trouvé</p>'}

                <h4 style="margin-top:24px">Articles (${articles.length})</h4>
                ${articles.length > 0 ? `
                    <div class="rss-feeds" data-testid="articles-list">
                        ${articles.map(article => `
                            <div class="rss-feed">
                                <h4>${this.escapeHtml(article.title || 'Sans titre')}</h4>
                                <p><a href="${this.escapeAttr(article.link)}" target="_blank" rel="noopener noreferrer">${this.escapeHtml(article.link)}</a></p>
                                ${article.summary ? `<p>${this.escapeHtml(this.stripHtml(article.summary).slice(0, 280))}${this.stripHtml(article.summary).length > 280 ? '…' : ''}</p>` : ''}
                                <small>
                                    ${article.published_at ? this.escapeHtml(new Date(article.published_at).toLocaleString()) : 'Date inconnue'}
                                    ${article.feed_url ? ` | Feed: ${this.escapeHtml(article.feed_url)}` : ''}
                                </small>
                            </div>
                        `).join('')}
                    </div>
                ` : '<p>Aucun article importé pour le moment. Lance une analyse ou clique « Recharger les articles ».</p>'}
            `;

            const ingestBtn = resultsDiv.querySelector('[data-ingest-site]');
            if (ingestBtn) {
                ingestBtn.addEventListener('click', async () => {
                    ingestBtn.disabled = true;
                    ingestBtn.textContent = 'Import en cours…';
                    try {
                        const res = await fetch(`/api/sites/${siteId}/ingest-articles`, { method: 'POST' });
                        const data = await res.json();
                        if (!res.ok) throw new Error(data.error || 'Erreur import');
                        this.updateStatus(`${data.articles_count || 0} articles traités`, 'success');
                        await this.showSiteDetails(siteId);
                    } catch (err) {
                        this.updateStatus(`Erreur: ${err.message}`, 'error');
                        ingestBtn.disabled = false;
                        ingestBtn.textContent = 'Recharger les articles des flux';
                    }
                });
            }

            const deleteDetailBtn = resultsDiv.querySelector('[data-delete-site-detail]');
            if (deleteDetailBtn) {
                deleteDetailBtn.addEventListener('click', () => this.deleteSite(siteId));
            }
            
        } catch (error) {
            console.error('Erreur lors du chargement des détails:', error);
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
            const resultsCard = document.getElementById('resultsCard');
            if (resultsCard) resultsCard.style.display = 'none';
            await this.loadSites();
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
        const statusDiv = document.getElementById('status');
        statusDiv.textContent = message;
        statusDiv.className = `status ${type}`;
        statusDiv.style.display = 'block';
        
        setTimeout(() => {
            statusDiv.style.display = 'none';
        }, 5000);
    }

    showLoading(show) {
        const loadingDiv = document.getElementById('loading');
        const analyzeBtn = document.getElementById('analyzeBtn');
        const stopBtn = document.getElementById('stopAnalyzeBtn');
        
        if (show) {
            loadingDiv.style.display = 'block';
            analyzeBtn.disabled = true;
            if (stopBtn) stopBtn.disabled = false;
        } else {
            loadingDiv.style.display = 'none';
            analyzeBtn.disabled = false;
            if (stopBtn) stopBtn.disabled = false;
        }
    }

    setLoadingText(text) {
        const loadingDiv = document.getElementById('loading');
        const progressText = loadingDiv && loadingDiv.querySelector('p');
        if (progressText) progressText.textContent = text;
    }

    updateProgress(current, total) {
        const loadingDiv = document.getElementById('loading');
        const progressText = loadingDiv.querySelector('p');
        if (!progressText) return;

        const cur = Number(current);
        const tot = Number(total);
        const safeCur = Number.isFinite(cur) && cur >= 0 ? cur : 0;
        const safeTot = Number.isFinite(tot) && tot > 0 ? tot : null;

        if (safeTot == null) {
            progressText.textContent = safeCur > 0
                ? `Analyse en cours... ${safeCur} page(s)`
                : 'Discovery des liens...';
            return;
        }

        const percentage = Math.min(100, Math.max(0, Math.round((safeCur / safeTot) * 100)));
        if (safeCur >= safeTot) {
            progressText.textContent = `Crawl terminé (${safeCur} page${safeCur > 1 ? 's' : ''}) — import des articles...`;
        } else {
            progressText.textContent = `Analyse en cours... ${safeCur}/${safeTot} pages (${percentage}%)`;
        }
    }

    /**
     * Filet de securite : si le WS rate analysis_completed, on poll le statut.
     */
    _watchAnalysisFinish(siteId) {
        const started = Date.now();
        const maxMs = 15 * 60 * 1000;
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
                    if (st === 'completed' || st === 'error' || st === 'cancelled') {
                        if (st === 'completed') {
                            const feeds = this.parseRssFeeds(site.rss_feeds);
                            this.updateStatus(
                                `Analyse terminée ! ${feeds.length} flux RSS`,
                                'success'
                            );
                            this.showSiteDetails(siteId);
                        } else if (st === 'error') {
                            this.updateStatus('Analyse en erreur', 'error');
                        } else {
                            this.updateStatus('Analyse arrêtée', 'info');
                        }
                        this.showLoading(false);
                        this.currentAnalysis = null;
                        await this.loadSites();
                        return;
                    }
                    if (st === 'analyzing' || st === 'pending') {
                        // encore en cours (souvent phase ingest apres 100% crawl)
                    }
                }
            } catch (_) {
                /* ignore */
            }
            setTimeout(tick, 4000);
        };
        setTimeout(tick, 8000);
    }

    addPageLog(message, type) {
        const resultsDiv = document.getElementById('results');
        if (!resultsDiv.querySelector('.page-logs')) {
            resultsDiv.innerHTML = '<div class="page-logs"></div>' + resultsDiv.innerHTML;
        }
        
        const logsDiv = resultsDiv.querySelector('.page-logs');
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${type}`;
        logEntry.innerHTML = `<span class="time">${new Date().toLocaleTimeString()}</span> ${message}`;
        logsDiv.appendChild(logEntry);
        
        // Garder seulement les 50 dernières entrées
        while (logsDiv.children.length > 50) {
            logsDiv.removeChild(logsDiv.firstChild);
        }
    }

    addRssFeed(data) {
        const resultsDiv = document.getElementById('results');
        if (!resultsDiv.querySelector('.rss-feeds')) {
            resultsDiv.innerHTML = '<h4>Flux RSS trouvés</h4><div class="rss-feeds"></div>' + resultsDiv.innerHTML;
        }
        
        const feedsDiv = resultsDiv.querySelector('.rss-feeds');
        const feedDiv = document.createElement('div');
        feedDiv.className = 'rss-feed new-feed';
        feedDiv.innerHTML = `
            <h4>${data.title || 'Flux RSS'}</h4>
            <p><a href="${data.rss_url}" target="_blank">${data.rss_url}</a></p>
            <small>Source: ${data.source_page}</small>
        `;
        feedsDiv.appendChild(feedDiv);
        
        // Animation pour le nouveau flux
        setTimeout(() => feedDiv.classList.remove('new-feed'), 1000);
    }

    clearResults() {
        const resultsDiv = document.getElementById('results');
        resultsDiv.innerHTML = '';
    }

    showResults() {
        const resultsCard = document.getElementById('resultsCard');
        resultsCard.style.display = 'block';
        resultsCard.scrollIntoView({ behavior: 'smooth' });
    }

    getStatusText(status) {
        const statusMap = {
            'pending': 'En attente',
            'analyzing': 'En cours',
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

// Initialisation de l'application
const app = new StreamNewsApp(); 