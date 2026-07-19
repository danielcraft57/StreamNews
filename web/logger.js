const fs = require('fs');
const path = require('path');
const util = require('util');

const LOG_DIR = process.env.LOG_DIR
    || path.join(__dirname, '..', 'logs');

const LEVELS = { error: 0, warn: 1, info: 2, debug: 3 };
const currentLevel = LEVELS[(process.env.LOG_LEVEL || 'info').toLowerCase()] ?? 2;

function ensureDir() {
    try {
        fs.mkdirSync(LOG_DIR, { recursive: true });
    } catch (_) {
        /* ignore */
    }
}

function stamp() {
    return new Date().toISOString().replace('T', ' ').slice(0, 19);
}

function fmtArg(a) {
    if (a instanceof Error) {
        return a.stack || a.message;
    }
    if (typeof a === 'object' && a !== null) {
        try {
            return JSON.stringify(a);
        } catch (_) {
            return util.inspect(a, { depth: 3, breakLength: 120 });
        }
    }
    return String(a);
}

function write(level, args) {
    if ((LEVELS[level] ?? 2) > currentLevel) return;
    const line = `${stamp()} | ${level.toUpperCase().padEnd(7)} | web | ${args.map(fmtArg).join(' ')}\n`;
    process.stdout.write(line);
    try {
        ensureDir();
        fs.appendFileSync(path.join(LOG_DIR, 'web.log'), line, 'utf8');
        if (level === 'error' || level === 'warn') {
            fs.appendFileSync(path.join(LOG_DIR, 'errors.log'), line, 'utf8');
        }
    } catch (_) {
        /* ignore disk errors */
    }
}

const logger = {
    info: (...a) => write('info', a),
    warn: (...a) => write('warn', a),
    error: (...a) => write('error', a),
    debug: (...a) => write('debug', a),
};

module.exports = { logger, LOG_DIR };
