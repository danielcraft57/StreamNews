const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const compression = require('compression');
const path = require('path');
const axios = require('axios');
const WebSocket = require('ws');
const http = require('http');

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
            imgSrc: ["'self'", "data:", "https:"],
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
app.use(express.static(path.join(__dirname, 'public')));

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
        console.error('Erreur lors de l\'analyse:', error.message);
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
        console.error('Erreur lors de la récupération des sites:', error.message);
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
        console.error('Erreur lors de la récupération du site:', error.message);
        res.status(500).json({ 
            error: 'Erreur lors de la récupération du site',
            details: error.message 
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
        console.error('Erreur lors de la récupération des pages:', error.message);
        const status = error.response?.status || 500;
        res.status(status).json({
            error: 'Erreur lors de la récupération des pages',
            details: error.message
        });
    }
});

// Route pour recevoir les messages WebSocket du service d'analyse
app.post('/api/websocket', (req, res) => {
    try {
        const message = req.body;
        console.log('Message reçu du service d\'analyse:', message);
        
        // Broadcast du message à tous les clients WebSocket
        broadcastMessage(message);
        
        res.json({ status: 'ok' });
    } catch (error) {
        console.error('Erreur lors du traitement du message WebSocket:', error);
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
    console.error('Erreur serveur:', error);
    res.status(500).json({ 
        error: 'Erreur interne du serveur',
        details: process.env.NODE_ENV === 'development' ? error.message : 'Erreur interne'
    });
});

// Gestion des connexions WebSocket
wss.on('connection', (ws) => {
    console.log('Nouvelle connexion WebSocket');
    clients.add(ws);
    
    ws.on('close', () => {
        console.log('Connexion WebSocket fermée');
        clients.delete(ws);
    });
    
    ws.on('error', (error) => {
        console.error('Erreur WebSocket:', error);
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
        console.log(`Serveur web démarré sur le port ${PORT}`);
        console.log(`Service d'analyse: ${ANALYZER_URL}`);
        console.log('WebSocket activé');
    });
}
 