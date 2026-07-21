class StreamNewsApp {
    constructor() {
        this.socket = null;
        this.currentAnalysis = null;
        this.analysisMaxPages = 50;   // plafond formulaire
        this.analysisTotalPages = null; // vrai total apres discovery
        this.selectedArticleId = null;
        this.viewingSiteId = null;
        this._articlePollTimer = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupImageFallbacks();
        this.loadSites();
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
            case 'site_meta':
                this.loadSites();
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
                    const title = site.site_title || site.url;
                    const favicon = site.favicon_url
                        ? `<img class="site-favicon js-hide-on-error" src="${this.escapeAttr(site.favicon_url)}" alt="" width="20" height="20" loading="lazy">`
                        : `<span class="site-favicon site-favicon-fallback" aria-hidden="true"></span>`;
                    const desc = site.meta_description
                        ? `<div class="site-desc">${this.escapeHtml(site.meta_description.slice(0, 140))}${site.meta_description.length > 140 ? '…' : ''}</div>`
                        : '';
                    return `
                    <div class="site-item" data-site-id="${site.id}" role="button" tabindex="0">
                        <div class="site-item-header">
                            <div class="site-title-row">
                                ${favicon}
                                <div class="site-title-block">
                                    <h4>${this.escapeHtml(title)}</h4>
                                    <div class="site-url">${this.escapeHtml(site.url)}</div>
                                </div>
                            </div>
                            <button type="button" class="btn-delete" data-delete-site="${site.id}" title="Supprimer le site">
                                Supprimer
                            </button>
                        </div>
                        ${desc}
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
            this.viewingSiteId = siteId;
            this.selectedArticleId = null;
            this._clearArticlePoll();

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
            const extra = site.meta_extra && typeof site.meta_extra === 'object' ? site.meta_extra : {};
            const favicon = site.favicon_url
                ? `<img class="site-favicon site-favicon-lg js-hide-on-error" src="${this.escapeAttr(site.favicon_url)}" alt="" width="32" height="32">`
                : '';
            resultsDiv.innerHTML = `
                <h3>Détails de l'analyse</h3>
                <div class="site-details">
                    <div class="site-title-row" style="margin-bottom:12px">
                        ${favicon}
                        <div>
                            <h4 style="margin:0 0 4px">${this.escapeHtml(site.site_title || site.url)}</h4>
                            <p style="margin:0"><a href="${this.escapeAttr(site.url)}" target="_blank" rel="noopener noreferrer">${this.escapeHtml(site.url)}</a></p>
                        </div>
                    </div>
                    ${site.meta_description ? `<p>${this.escapeHtml(site.meta_description)}</p>` : ''}
                    ${extra.og_image ? `<p><img class="js-hide-on-error" src="${this.escapeAttr(extra.og_image)}" alt="" style="max-width:100%;max-height:160px;border-radius:8px"></p>` : ''}
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
                    <p style="margin-top:12px;display:flex;flex-wrap:wrap;gap:8px">
                        <button type="button" class="btn" data-ingest-site="${siteId}" style="width:auto;padding:10px 16px;font-size:14px">
                            Recharger les articles des flux
                        </button>
                        ${articles.length > 0 ? `
                            <button type="button" class="btn" data-enrich-site="${siteId}" style="width:auto;padding:10px 16px;font-size:14px;background:linear-gradient(135deg,#2c7a7b 0%,#285e61 100%)">
                                Enrichir les articles
                            </button>
                            <button type="button" class="btn" data-analyze-site="${siteId}" style="width:auto;padding:10px 16px;font-size:14px;background:linear-gradient(135deg,#4c51bf 0%,#553c9a 100%)">
                                Analyser le texte
                            </button>
                        ` : ''}
                    </p>
                ` : '<p>Aucun flux RSS trouvé</p>'}

                <h4 style="margin-top:24px">Articles (${articles.length})</h4>
                ${articles.length > 0 ? `
                    <div class="articles-layout" data-testid="articles-layout">
                        <div class="articles-list-pane rss-feeds" data-testid="articles-list">
                            ${articles.map(article => this.renderArticleListItem(article)).join('')}
                        </div>
                        <div class="article-reader empty" id="articleReader" data-testid="article-reader">
                            Clique un article pour lire le contenu
                        </div>
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

            const enrichBtn = resultsDiv.querySelector('[data-enrich-site]');
            if (enrichBtn) {
                enrichBtn.addEventListener('click', async () => {
                    enrichBtn.disabled = true;
                    enrichBtn.textContent = 'Enrichissement lancé…';
                    try {
                        const res = await fetch(`/api/sites/${siteId}/enrich-articles?limit=50`, { method: 'POST' });
                        const data = await res.json();
                        if (!res.ok) throw new Error(data.error || 'Erreur enrichissement');
                        this.updateStatus('Enrichissement en file (les articles se mettront a jour)', 'success');
                        enrichBtn.textContent = 'Enrichir les articles';
                        enrichBtn.disabled = false;
                    } catch (err) {
                        this.updateStatus(`Erreur: ${err.message}`, 'error');
                        enrichBtn.disabled = false;
                        enrichBtn.textContent = 'Enrichir les articles';
                    }
                });
            }

            const analyzeSiteBtn = resultsDiv.querySelector('[data-analyze-site]');
            if (analyzeSiteBtn) {
                analyzeSiteBtn.addEventListener('click', async () => {
                    analyzeSiteBtn.disabled = true;
                    analyzeSiteBtn.textContent = 'Analyse lancée…';
                    try {
                        const res = await fetch(`/api/sites/${siteId}/analyze-articles?limit=50`, { method: 'POST' });
                        const data = await res.json();
                        if (!res.ok) throw new Error(data.error || 'Erreur analyse');
                        this.updateStatus('Analyse texte en file (les articles se mettront a jour)', 'success');
                        analyzeSiteBtn.textContent = 'Analyser le texte';
                        analyzeSiteBtn.disabled = false;
                    } catch (err) {
                        this.updateStatus(`Erreur: ${err.message}`, 'error');
                        analyzeSiteBtn.disabled = false;
                        analyzeSiteBtn.textContent = 'Analyser le texte';
                    }
                });
            }

            const deleteDetailBtn = resultsDiv.querySelector('[data-delete-site-detail]');
            if (deleteDetailBtn) {
                deleteDetailBtn.addEventListener('click', () => this.deleteSite(siteId));
            }

            resultsDiv.querySelectorAll('[data-article-id]').forEach((el) => {
                el.addEventListener('click', (e) => {
                    if (e.target.closest('a')) return;
                    const id = Number(el.dataset.articleId);
                    if (id) this.selectArticle(id);
                });
            });
            
        } catch (error) {
            console.error('Erreur lors du chargement des détails:', error);
        }
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
        if (!hero) return article.content_html;
        return this.stripHeroImagesFromHtml(article.content_html, hero, article);
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

    renderArticleListItem(article) {
        const status = article.enrich_status || '';
        const badge = status
            ? `<span class="article-enrich-badge ${this.escapeAttr(status)}">${this.escapeHtml(this.enrichStatusLabel(status))}</span>`
            : '';
        const analysisStatus = this.articleAnalysisStatus(article);
        const analysisBadge = analysisStatus
            ? `<span class="article-analysis-badge ${this.escapeAttr(analysisStatus)}">${this.escapeHtml(this.analysisStatusLabel(analysisStatus))}</span>`
            : '';
        const selected = this.selectedArticleId === article.id ? ' is-selected' : '';
        const hero = this.articleHero(article);
        const heroBlock = hero
            ? this.renderHeroImg(hero, { wrapperClass: 'article-item-hero', imgClass: 'article-item-hero-img' })
            : '';
        const noThumbClass = hero ? '' : ' article-item--no-thumb';
        const domain = this.articleDomain(article);
        const chapo = this.articleChapo(article);
        const dateStr = article.published_at
            ? new Date(article.published_at).toLocaleDateString()
            : 'Date inconnue';

        return `
            <div class="rss-feed article-item${selected}${noThumbClass}" data-article-id="${article.id}">
                <div class="article-item-body">
                    <h4>${this.escapeHtml(article.title || 'Sans titre')}${badge}${analysisBadge}</h4>
                    ${heroBlock}
                    ${chapo ? `<p>${this.escapeHtml(chapo.slice(0, 140))}${chapo.length > 140 ? '…' : ''}</p>` : ''}
                    <small class="article-item-meta">
                        ${domain ? `${this.escapeHtml(domain)} · ` : ''}${this.escapeHtml(dateStr)}
                    </small>
                </div>
            </div>
        `;
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
        document.querySelectorAll('.article-item').forEach((el) => {
            el.classList.toggle('is-selected', Number(el.dataset.articleId) === articleId);
        });

        const reader = document.getElementById('articleReader');
        if (!reader) return;
        reader.classList.remove('empty');
        reader.innerHTML = `<p class="reader-meta">Chargement…</p>`;

        try {
            let article = await this.fetchArticle(articleId);
            if (!article) throw new Error('Article introuvable');

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
            ? yakeBlock.keywords : [];
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
        reader.classList.remove('empty');

        // Ne pas afficher "enrichissement..." si deja enrichi (race WS / poll)
        if (loading && article.enrich_status === 'ok') loading = false;

        const meta = this.articleMeta(article);
        const hero = this.pickArticleHero(article);
        const gallery = this.articleImages(article, hero);
        const author = article.author || meta.author || '';
        const published = article.published_at
            ? new Date(article.published_at).toLocaleString()
            : (meta.date_published || '');
        const chapo = this.articleChapo(article);
        const domain = this.articleDomain(article);
        const reading = this.formatReadingTime(meta);
        const keywords = Array.isArray(meta.keywords) ? meta.keywords : [];
        const status = article.enrich_status || '';
        const statusBadge = status
            ? `<span class="article-enrich-badge ${this.escapeAttr(status)}">${this.escapeHtml(this.enrichStatusLabel(status))}</span>`
            : '';
        const analysisStatus = meta.analysis_status || '';
        const analysisBadge = analysisStatus
            ? `<span class="article-analysis-badge ${this.escapeAttr(analysisStatus)}">${this.escapeHtml(this.analysisStatusLabel(analysisStatus))}</span>`
            : '';
        const typeBadge = meta.schema_type || meta.og_type
            ? `<span class="reader-type-badge">${this.escapeHtml(meta.schema_type || meta.og_type)}</span>`
            : '';

        let bodyHtml = '';
        if (loading) {
            bodyHtml = `<p class="reader-meta">Enrichissement en cours (fetch de la page)…</p>
                ${chapo ? `<p class="reader-chapo">${this.escapeHtml(chapo)}</p>` : ''}`;
        } else if (article.enrich_status === 'error') {
            bodyHtml = `<p class="reader-meta">Enrichissement echoue: ${this.escapeHtml(article.enrich_error || 'erreur')}</p>
                ${chapo ? `<p class="reader-chapo">${this.escapeHtml(chapo)}</p>` : ''}`;
        } else if (article.content_html) {
            const cleanedHtml = this.prepareArticleBodyHtml(article, hero);
            bodyHtml = `<div class="reader-body">${cleanedHtml}</div>`;
        } else if (article.content_text) {
            bodyHtml = `<div class="reader-body"><p>${this.escapeHtml(article.content_text).replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>')}</p></div>`;
        } else if (chapo) {
            bodyHtml = `<p class="reader-chapo">${this.escapeHtml(chapo)}</p>`;
        } else {
            bodyHtml = `<p class="reader-meta">Pas de contenu disponible</p>`;
        }

        const chapoBlock = (!loading && article.enrich_status !== 'error' && chapo && article.content_html)
            ? `<p class="reader-chapo">${this.escapeHtml(chapo)}</p>`
            : '';

        const keywordsBlock = keywords.length
            ? `<div class="reader-keywords">${keywords.map((kw) =>
                `<span class="reader-keyword">${this.escapeHtml(kw)}</span>`).join('')}</div>`
            : '';

        const galleryBlock = gallery.length
            ? `<div class="reader-gallery">${gallery.map((img) =>
                `<img class="js-hide-on-error" src="${this.escapeAttr(img.url)}" alt="${this.escapeAttr(img.alt || '')}" loading="lazy" title="${this.escapeAttr(img.source || '')}">`
            ).join('')}</div>`
            : '';

        const metaRows = [
            ['Sources', (meta.sources || []).join(', ')],
            ['Flux RSS', article.feed_url],
            ['Schema', meta.schema_type],
            ['OG type', meta.og_type],
            ['Domaine', meta.domain || domain],
            ['Canonique', meta.canonical_url],
            ['Modifie', meta.date_modified],
            ['Enrichi', article.enriched_at ? new Date(article.enriched_at).toLocaleString() : ''],
            ['Images', `${(hero ? 1 : 0) + gallery.length}${hero ? ` (hero + ${gallery.length} galerie)` : ''}`],
        ].filter(([, val]) => val);

        const metaPanel = metaRows.length
            ? `<details class="reader-meta-panel">
                <summary>Metadonnees techniques</summary>
                <dl>${metaRows.map(([label, val]) =>
                    `<dt>${this.escapeHtml(label)}</dt><dd>${this.escapeHtml(String(val))}</dd>`
                ).join('')}</dl>
               </details>`
            : '';

        const analysisPanel = this.renderAnalysisPanel(article, { loadingAnalysis });
        const heroBlock = this.renderHeroImg(hero);

        reader.innerHTML = `
            <div class="reader-badge-row">${statusBadge}${analysisBadge}${typeBadge}</div>
            <header class="reader-header">
                <h3>${this.escapeHtml(article.title || 'Sans titre')}</h3>
                <div class="reader-meta">
                    ${published ? this.escapeHtml(published) : ''}
                    ${author ? ` · ${this.escapeHtml(author)}` : ''}
                    ${domain ? ` · ${this.escapeHtml(domain)}` : ''}
                    ${reading ? ` · ${this.escapeHtml(reading)}` : ''}
                </div>
                ${heroBlock}
            </header>
            ${analysisPanel}
            <section class="reader-article-section">
                <span class="reader-section-label">Article</span>
                ${keywordsBlock}
                ${chapoBlock}
                ${bodyHtml}
                ${galleryBlock}
            </section>
            <div class="reader-actions">
                <a href="${this.escapeAttr(article.link)}" target="_blank" rel="noopener noreferrer">Ouvrir l'original</a>
                ${article.enrich_status === 'ok' ? `
                    · <button type="button" class="btn" data-reenrich="${article.id}" style="width:auto;padding:6px 12px;font-size:13px;display:inline-block">Relire la page</button>
                ` : ''}
            </div>
            ${metaPanel}
        `;

        const reBtn = reader.querySelector('[data-reenrich]');
        if (reBtn) {
            reBtn.addEventListener('click', async () => {
                reBtn.disabled = true;
                try {
                    await fetch(`/api/articles/${article.id}/enrich?force=1`, { method: 'POST' });
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
                    await fetch(`/api/articles/${article.id}/analyze?force=1`, { method: 'POST' });
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
        if (this.selectedArticleId === articleId) {
            this.fetchArticle(articleId)
                .then(async (article) => {
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