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
            styleSrc: ["'self'", "'unsafe-inline'", "https://cdnjs.cloudflare.com"],
            scriptSrc: ["'self'"],
            imgSrc: ["'self'", "data:", "http:", "https:"],
            fontSrc: ["'self'", "https://cdnjs.cloudflare.com", "data:"],
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
 