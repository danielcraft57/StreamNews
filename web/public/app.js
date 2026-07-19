class StreamNewsApp {
    constructor() {
        this.socket = null;
        this.currentAnalysis = null;
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

        // Delegation : evite onclick= inline (bloque par CSP script-src-attr)
        const sitesList = document.getElementById('sitesList');
        sitesList.addEventListener('click', (e) => {
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
        }
    }

    handleAnalysisStarted(data) {
        this.currentAnalysis = data.site_id;
        this.updateStatus(`Analyse démarrée pour ${data.url}`, 'info');
        this.showLoading(true);
        this.updateProgress(0, data.max_pages);
    }

    handlePageAnalyzed(data) {
        if (this.currentAnalysis === data.site_id) {
            this.updateProgress(data.pages_analyzed, data.total_pages);
            this.addPageLog(`Page analysée: ${data.url}`, 'success');
        }
    }

    handleRssFound(data) {
        if (this.currentAnalysis === data.site_id) {
            this.addPageLog(`Flux RSS trouvé: ${data.rss_url}`, 'rss');
            this.addRssFeed(data);
        }
    }

    handleAnalysisCompleted(data) {
        if (this.currentAnalysis === data.site_id) {
            this.updateStatus(`Analyse terminée ! ${data.rss_count} flux RSS trouvés`, 'success');
            this.showLoading(false);
            this.updateProgress(data.total_pages, data.total_pages);
            this.loadSites(); // Recharger la liste
            this.currentAnalysis = null;
        }
    }

    handleAnalysisError(data) {
        if (this.currentAnalysis === data.site_id) {
            this.updateStatus(`Erreur: ${data.error}`, 'error');
            this.showLoading(false);
            this.currentAnalysis = null;
        }
    }

    handleProgressUpdate(data) {
        if (this.currentAnalysis === data.site_id) {
            this.updateProgress(data.current, data.total);
        }
    }

    async handleAnalyzeSubmit(e) {
        e.preventDefault();
        
        const formData = new FormData(e.target);
        const url = formData.get('url');
        const maxPages = parseInt(formData.get('maxPages'));
        const depth = parseInt(formData.get('depth'));
        
        if (!url) {
            this.updateStatus('Veuillez saisir une URL', 'error');
            return;
        }
        
        try {
            this.updateStatus('Lancement de l\'analyse...', 'info');
            this.showLoading(true);
            this.clearResults();
            
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url,
                    max_pages: maxPages,
                    depth: depth
                })
            });
            
            const result = await response.json();
            
            if (response.ok) {
                this.updateStatus(`Analyse lancée (ID: ${result.site_id})`, 'success');
                this.currentAnalysis = result.site_id;
            } else {
                throw new Error(result.error || 'Erreur lors du lancement');
            }
            
        } catch (error) {
            this.updateStatus(`Erreur: ${error.message}`, 'error');
            this.showLoading(false);
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
                        <h4>${site.url}</h4>
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
            const response = await fetch(`/api/sites/${siteId}`);
            const site = await response.json();
            const feeds = this.parseRssFeeds(site.rss_feeds);
            
            this.clearResults();
            this.showResults();
            
            const resultsDiv = document.getElementById('results');
            resultsDiv.innerHTML = `
                <h3>Détails de l'analyse</h3>
                <div class="site-details">
                    <p><strong>URL:</strong> ${site.url}</p>
                    <p><strong>Statut:</strong> <span class="status ${site.status}">${this.getStatusText(site.status)}</span></p>
                    <p><strong>Pages analysées:</strong> ${site.total_pages_analyzed || 0}</p>
                    <p><strong>Date:</strong> ${new Date(site.created_at).toLocaleString()}</p>
                </div>
                
                ${feeds.length > 0 ? `
                    <h4>Flux RSS trouvés (${feeds.length})</h4>
                    <div class="rss-feeds">
                        ${feeds.map(feed => `
                            <div class="rss-feed">
                                <h4>${feed.title || 'Flux RSS'}</h4>
                                <p><a href="${feed.url}" target="_blank" rel="noopener noreferrer">${feed.url}</a></p>
                                <small>Type: ${feed.type || '-'} | Source: ${feed.source_page || '-'}</small>
                            </div>
                        `).join('')}
                    </div>
                ` : '<p>Aucun flux RSS trouvé</p>'}
            `;
            
        } catch (error) {
            console.error('Erreur lors du chargement des détails:', error);
        }
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
        
        if (show) {
            loadingDiv.style.display = 'block';
            analyzeBtn.disabled = true;
        } else {
            loadingDiv.style.display = 'none';
            analyzeBtn.disabled = false;
        }
    }

    updateProgress(current, total) {
        const loadingDiv = document.getElementById('loading');
        const progressText = loadingDiv.querySelector('p');
        const percentage = Math.round((current / total) * 100);
        progressText.textContent = `Analyse en cours... ${current}/${total} pages (${percentage}%)`;
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
            'error': 'Erreur'
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