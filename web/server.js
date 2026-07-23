const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const compression = require('compression');
const path = require('path');
const axios = require('axios');
const WebSocket = require('ws');
const http = require('http');
const { logger } = require('./logger');

const app = express();
const server = http.createServer(app);
const PORT = process.env.PORT || 3000;

// Configuration WebSocket
const wss = new WebSocket.Server({ server });
const clients = new Set();

// Configuration des variables d'environnement
const ANALYZER_URL = process.env.ANALYZER_URL || 'http://localhost:8000';

// Helmet en mode HTTP LAN (homelab) : pas de HSTS / upgrade HTTPS
// sinon le navigateur force https://node7.lan et casse app.js / le formulaire.
app.use(helmet({
    contentSecurityPolicy: {
        useDefaults: true,
        directives: {
            defaultSrc: ["'self'"],
            styleSrc: ["'self'", "'unsafe-inline'", "https://cdnjs.cloudflare.com", "https://fonts.googleapis.com"],
            styleSrcElem: ["'self'", "'unsafe-inline'", "https://cdnjs.cloudflare.com", "https://fonts.googleapis.com"],
            scriptSrc: ["'self'"],
            imgSrc: ["'self'", "data:", "http:", "https:"],
            fontSrc: ["'self'", "https://cdnjs.cloudflare.com", "https://fonts.gstatic.com", "data:"],
            connectSrc: ["'self'", "ws:", "wss:"],
            upgradeInsecureRequests: null,
        },
    },
    hsts: false,
    crossOriginOpenerPolicy: false,
    originAgentCluster: false,
    crossOriginEmbedderPolicy: false,
}));

// Middleware
app.use(compression());
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public'), {
    setHeaders: (res, filePath) => {
        if (filePath.endsWith('.js') || filePath.endsWith('.html')) {
            res.setHeader('Cache-Control', 'no-cache');
        }
    },
}));

// Evite le 404 navigateur sur /favicon.ico
app.get('/favicon.ico', (req, res) => {
    res.redirect(302, '/favicon.svg');
});

// Routes API
app.get('/api/health', (req, res) => {
    res.json({ status: 'healthy', service: 'web' });
});

// Proxy vers le service d'analyse
app.post('/api/analyze', async (req, res) => {
    try {
        const response = await axios.post(`${ANALYZER_URL}/analyze`, req.body, {
            timeout: 10000
        });
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur lors de l\'analyse:', error.message);
        res.status(500).json({ 
            error: 'Erreur lors de l\'analyse du site',
            details: error.message 
        });
    }
});

app.get('/api/sites', async (req, res) => {
    try {
        const response = await axios.get(`${ANALYZER_URL}/sites`, {
            timeout: 5000
        });
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur lors de la récupération des sites:', error.message);
        res.status(500).json({ 
            error: 'Erreur lors de la récupération des sites',
            details: error.message 
        });
    }
});

app.get('/api/sites/:id', async (req, res) => {
    try {
        const response = await axios.get(`${ANALYZER_URL}/sites/${req.params.id}`, {
            timeout: 5000
        });
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur lors de la récupération du site:', error.message);
        res.status(500).json({ 
            error: 'Erreur lors de la récupération du site',
            details: error.message 
        });
    }
});

app.delete('/api/sites/:id', async (req, res) => {
    try {
        const response = await axios.delete(`${ANALYZER_URL}/sites/${req.params.id}`, {
            timeout: 15000
        });
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur lors de la suppression du site:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors de la suppression du site',
            details: error.response?.data?.detail || error.message
        });
    }
});

app.post('/api/sites/:id/stop', async (req, res) => {
    try {
        const response = await axios.post(`${ANALYZER_URL}/sites/${req.params.id}/stop`, {}, {
            timeout: 15000
        });
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur lors de l\'arret de l\'analyse:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors de l\'arret de l\'analyse',
            details: error.response?.data?.detail || error.message
        });
    }
});

app.get('/api/sites/:id/pages', async (req, res) => {
    try {
        const response = await axios.get(`${ANALYZER_URL}/sites/${req.params.id}/pages`, {
            timeout: 5000
        });
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur lors de la récupération des pages:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors de la récupération des pages',
            details: error.message
        });
    }
});

app.get('/api/sites/:id/articles', async (req, res) => {
    try {
        const response = await axios.get(`${ANALYZER_URL}/sites/${req.params.id}/articles`, {
            timeout: 15000,
            params: { limit: req.query.limit || 100 }
        });
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur lors de la récupération des articles:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors de la récupération des articles',
            details: error.message
        });
    }
});

app.get('/api/articles/search', async (req, res) => {
    try {
        const response = await axios.get(`${ANALYZER_URL}/articles/search`, {
            timeout: 20000,
            params: {
                q: req.query.q || '',
                limit: req.query.limit || 40,
                ...(req.query.site_id ? { site_id: req.query.site_id } : {}),
            },
        });
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur recherche articles:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors de la recherche',
            details: error.message,
        });
    }
});

app.get('/api/trends', async (req, res) => {
    try {
        const response = await axios.get(`${ANALYZER_URL}/trends`, {
            timeout: 60000,
            params: {
                days: req.query.days || 30,
                limit: req.query.limit || 40,
                kind: req.query.kind || 'all',
                ...(req.query.site_id ? { site_id: req.query.site_id } : {}),
                ...(req.query.collection_id ? { collection_id: req.query.collection_id } : {}),
                ...(req.query.refresh ? { refresh: req.query.refresh } : {}),
            },
        });
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur tendances:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors du chargement des tendances',
            details: error.message,
        });
    }
});

app.post('/api/trends/refresh', async (req, res) => {
    try {
        const response = await axios.post(`${ANALYZER_URL}/trends/refresh`, null, {
            timeout: 90000,
            params: {
                days: req.query.days || req.body?.days || 30,
                limit: req.query.limit || req.body?.limit || 50,
                ...(req.query.site_id || req.body?.site_id
                    ? { site_id: req.query.site_id || req.body.site_id }
                    : {}),
                ...(req.query.collection_id || req.body?.collection_id
                    ? { collection_id: req.query.collection_id || req.body.collection_id }
                    : {}),
            },
        });
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur refresh tendances:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors du calcul des tendances',
            details: error.message,
        });
    }
});

app.get('/api/radar', async (req, res) => {
    try {
        const response = await axios.get(`${ANALYZER_URL}/radar`, {
            timeout: 60000,
            params: {
                days: req.query.days || 30,
                limit: req.query.limit || 40,
                theme: req.query.theme || 'all',
                ...(req.query.refresh ? { refresh: req.query.refresh } : {}),
                ...(req.query.collection_id ? { collection_id: req.query.collection_id } : {}),
            },
        });
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur radar:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors du chargement du radar',
            details: error.message,
        });
    }
});

app.post('/api/radar/refresh', async (req, res) => {
    try {
        const response = await axios.post(`${ANALYZER_URL}/radar/refresh`, null, {
            timeout: 90000,
            params: {
                days: req.query.days || req.body?.days || 30,
                limit: req.query.limit || req.body?.limit || 40,
                ...(req.query.collection_id || req.body?.collection_id
                    ? { collection_id: req.query.collection_id || req.body.collection_id }
                    : {}),
            },
        });
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur refresh radar:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors du calcul du radar',
            details: error.message,
        });
    }
});

async function proxyAnalyzer(req, res, { method = 'get', path, timeout = 60000, params, data } = {}) {
    try {
        const response = await axios({
            method,
            url: `${ANALYZER_URL}${path}`,
            timeout,
            params,
            data,
        });
        res.json(response.data);
    } catch (error) {
        logger.error(`Erreur proxy ${path}:`, error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: error.response?.data?.detail || error.message,
            details: error.message,
        });
    }
}

app.get('/api/watchlist/keywords', (req, res) =>
    proxyAnalyzer(req, res, { path: '/watchlist/keywords' }));
app.post('/api/watchlist/keywords', (req, res) =>
    proxyAnalyzer(req, res, { method: 'post', path: '/watchlist/keywords', data: req.body }));
app.delete('/api/watchlist/keywords/:id', (req, res) =>
    proxyAnalyzer(req, res, { method: 'delete', path: `/watchlist/keywords/${req.params.id}` }));
app.get('/api/watchlist/alerts', (req, res) =>
    proxyAnalyzer(req, res, {
        path: '/watchlist/alerts',
        params: {
            days: req.query.days || 7,
            limit: req.query.limit || 40,
            ...(req.query.refresh ? { refresh: req.query.refresh } : {}),
        },
    }));
app.post('/api/watchlist/refresh', (req, res) =>
    proxyAnalyzer(req, res, {
        method: 'post',
        path: '/watchlist/refresh',
        timeout: 90000,
        params: { days: req.query.days || req.body?.days || 7 },
    }));

app.get('/api/brief/weekly', (req, res) =>
    proxyAnalyzer(req, res, {
        path: '/brief/weekly',
        timeout: 120000,
        params: {
            ...(req.query.week ? { week: req.query.week } : {}),
            ...(req.query.refresh ? { refresh: req.query.refresh } : {}),
        },
    }));
app.post('/api/brief/weekly/refresh', (req, res) =>
    proxyAnalyzer(req, res, {
        method: 'post',
        path: '/brief/weekly/refresh',
        timeout: 120000,
        params: { ...(req.query.week || req.body?.week ? { week: req.query.week || req.body.week } : {}) },
    }));
app.get('/api/brief/daily', (req, res) =>
    proxyAnalyzer(req, res, {
        path: '/brief/daily',
        timeout: 120000,
        params: {
            ...(req.query.day ? { day: req.query.day } : {}),
            ...(req.query.refresh ? { refresh: req.query.refresh } : {}),
            ...(req.query.auto != null ? { auto: req.query.auto } : {}),
        },
    }));
app.post('/api/brief/daily/refresh', (req, res) =>
    proxyAnalyzer(req, res, {
        method: 'post',
        path: '/brief/daily/refresh',
        timeout: 120000,
        params: { ...(req.query.day || req.body?.day ? { day: req.query.day || req.body.day } : {}) },
    }));

app.get('/api/collections', (req, res) =>
    proxyAnalyzer(req, res, { path: '/collections' }));
app.get('/api/collections/:id', (req, res) =>
    proxyAnalyzer(req, res, { path: `/collections/${req.params.id}` }));
app.post('/api/collections/:id/sites', (req, res) =>
    proxyAnalyzer(req, res, {
        method: 'post',
        path: `/collections/${req.params.id}/sites`,
        data: req.body,
    }));
app.delete('/api/collections/:id/sites/:siteId', (req, res) =>
    proxyAnalyzer(req, res, {
        method: 'delete',
        path: `/collections/${req.params.id}/sites/${req.params.siteId}`,
    }));

app.get('/api/ideas', (req, res) =>
    proxyAnalyzer(req, res, { path: '/ideas', params: { limit: req.query.limit || 50 } }));
app.post('/api/ideas', (req, res) =>
    proxyAnalyzer(req, res, { method: 'post', path: '/ideas', data: req.body }));
app.post('/api/ideas/from-radar', (req, res) =>
    proxyAnalyzer(req, res, { method: 'post', path: '/ideas/from-radar', data: req.body }));
app.get('/api/ideas/:id/markdown', (req, res) =>
    proxyAnalyzer(req, res, { path: `/ideas/${req.params.id}/markdown` }));
app.get('/api/ideas/:id', (req, res) =>
    proxyAnalyzer(req, res, { path: `/ideas/${req.params.id}` }));
app.patch('/api/ideas/:id', (req, res) =>
    proxyAnalyzer(req, res, { method: 'patch', path: `/ideas/${req.params.id}`, data: req.body }));
app.delete('/api/ideas/:id', (req, res) =>
    proxyAnalyzer(req, res, { method: 'delete', path: `/ideas/${req.params.id}` }));

app.post('/api/sites/:id/ingest-articles', async (req, res) => {
    try {
        const response = await axios.post(
            `${ANALYZER_URL}/sites/${req.params.id}/ingest-articles`,
            {},
            { timeout: 120000 }
        );
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur lors de l\'ingestion des articles:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors de l\'ingestion des articles',
            details: error.message
        });
    }
});

app.post('/api/feeds/refresh-all', (req, res) =>
    proxyAnalyzer(req, res, { method: 'post', path: '/feeds/refresh-all', timeout: 30000 }));

app.get('/api/articles/:id', async (req, res) => {
    try {
        const response = await axios.get(`${ANALYZER_URL}/articles/${req.params.id}`, {
            timeout: 15000
        });
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur lors de la récupération de l\'article:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors de la récupération de l\'article',
            details: error.response?.data?.detail || error.message
        });
    }
});

app.post('/api/articles/:id/enrich', async (req, res) => {
    try {
        const response = await axios.post(
            `${ANALYZER_URL}/articles/${req.params.id}/enrich`,
            {},
            {
                timeout: 15000,
                params: { force: req.query.force === '1' || req.query.force === 'true' }
            }
        );
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur lors de l\'enrichissement de l\'article:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors de l\'enrichissement de l\'article',
            details: error.response?.data?.detail || error.message
        });
    }
});

app.post('/api/sites/:id/enrich-articles', async (req, res) => {
    try {
        const response = await axios.post(
            `${ANALYZER_URL}/sites/${req.params.id}/enrich-articles`,
            {},
            {
                timeout: 30000,
                params: { limit: req.query.limit || 50 }
            }
        );
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur lors de l\'enrichissement bulk:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors de l\'enrichissement des articles',
            details: error.response?.data?.detail || error.message
        });
    }
});

app.post('/api/articles/:id/analyze', async (req, res) => {
    try {
        const response = await axios.post(
            `${ANALYZER_URL}/articles/${req.params.id}/analyze`,
            {},
            {
                timeout: 15000,
                params: {
                    force: req.query.force === '1' || req.query.force === 'true',
                    tools: req.query.tools || undefined,
                }
            }
        );
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur lors de l\'analyse texte:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors de l\'analyse texte',
            details: error.response?.data?.detail || error.message
        });
    }
});

app.post('/api/sites/:id/analyze-articles', async (req, res) => {
    try {
        const response = await axios.post(
            `${ANALYZER_URL}/sites/${req.params.id}/analyze-articles`,
            {},
            {
                timeout: 30000,
                params: { limit: req.query.limit || 50 }
            }
        );
        res.json(response.data);
    } catch (error) {
        logger.error('Erreur lors de l\'analyse bulk:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors de l\'analyse des articles',
            details: error.response?.data?.detail || error.message
        });
    }
});

// Route pour recevoir les messages WebSocket du service d'analyse
app.post('/api/websocket', (req, res) => {
    try {
        const message = req.body;
        logger.info('Message reçu du service d\'analyse:', message);
        
        // Broadcast du message à tous les clients WebSocket
        broadcastMessage(message);
        
        res.json({ status: 'ok' });
    } catch (error) {
        logger.error('Erreur lors du traitement du message WebSocket:', error);
        res.status(500).json({ error: 'Erreur interne' });
    }
});

// Route principale - interface utilisateur
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Gestion des erreurs 404
app.use((req, res) => {
    res.status(404).json({ error: 'Route non trouvée' });
});

// Gestionnaire d'erreurs global
app.use((error, req, res, next) => {
    logger.error('Erreur serveur:', error);
    res.status(500).json({ 
        error: 'Erreur interne du serveur',
        details: process.env.NODE_ENV === 'development' ? error.message : 'Erreur interne'
    });
});

// Gestion des connexions WebSocket
wss.on('connection', (ws) => {
    logger.info('Nouvelle connexion WebSocket');
    clients.add(ws);
    
    ws.on('close', () => {
        logger.info('Connexion WebSocket fermée');
        clients.delete(ws);
    });
    
    ws.on('error', (error) => {
        logger.error('Erreur WebSocket:', error);
        clients.delete(ws);
    });
});

// Fonction pour envoyer des messages à tous les clients
function broadcastMessage(message) {
    const messageStr = JSON.stringify(message);
    clients.forEach(client => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(messageStr);
        }
    });
}

// Export de la fonction pour l'utiliser dans d'autres modules
global.broadcastMessage = broadcastMessage;

module.exports = { app, server, broadcastMessage, ANALYZER_URL };

if (require.main === module) {
    server.listen(PORT, () => {
        logger.info(`Serveur web démarré sur le port ${PORT}`);
        logger.info(`Service d'analyse: ${ANALYZER_URL}`);
        logger.info('WebSocket activé');
    });
}
 