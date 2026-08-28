'use strict';

/**
 * Honeypot Perimeter — Edge Decoy & Threat Telemetry Service
 *
 * Presents a low-interaction decoy surface at the network perimeter.
 * All inbound probes are captured, fingerprinted, and logged as threat
 * telemetry. A dynamic blocklist is maintained and served to peer nodes
 * so firewall rules can be updated in real time.
 */

const express = require('express');
const crypto = require('crypto');
const client = require('prom-client');

const PORT = process.env.PORT || 3003;
const SUMERA_URL = process.env.SUMERA_URL || 'http://sumera-layer:3001';

// ── In-memory threat store ────────────────────────────────────────────────────
const MAX_THREAT_LOG = 10000;
const threatLog = [];       // { id, ip, timestamp, method, path, headers, body, severity }
const blocklist = new Set(); // IPs flagged as malicious

// ── Prometheus metrics ────────────────────────────────────────────────────────
const register = new client.Registry();
client.collectDefaultMetrics({ register });

const threatsTotal = new client.Counter({
  name: 'honeypot_threats_total',
  help: 'Total threat events captured by honeypot',
  labelNames: ['severity'],
  registers: [register],
});

const blocklistSize = new client.Gauge({
  name: 'honeypot_blocklist_size',
  help: 'Number of IPs currently in the dynamic blocklist',
  registers: [register],
});

// ── Threat classification ─────────────────────────────────────────────────────
function classifySeverity(req) {
  const path = req.path.toLowerCase();
  if (/\/(admin|config|env|\.git|wp-login|phpmyadmin)/.test(path)) return 'critical';
  if (/\/(login|auth|api\/v[0-9])/.test(path)) return 'warning';
  return 'info';
}

function fingerprint(req) {
  const raw = `${req.ip}${req.method}${req.path}${JSON.stringify(req.headers)}`;
  return crypto.createHash('sha256').update(raw).digest('hex');
}

async function recordThreat(event) {
  if (threatLog.length >= MAX_THREAT_LOG) threatLog.shift();
  threatLog.push(event);
  threatsTotal.inc({ severity: event.severity });

  if (event.severity === 'critical') {
    blocklist.add(event.ip);
    blocklistSize.set(blocklist.size);
  }

  // Fire-and-forget: log to SumerA ledger
  try {
    const { default: fetch } = await import('node-fetch');
    await fetch(`${SUMERA_URL}/ledger/append`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category: 'THREAT', payload: event }),
    });
  } catch (_) { /* ledger unavailable — continue */ }
}

// ── Express app ───────────────────────────────────────────────────────────────
const app = express();
app.use(express.json());

// ── Honeypot decoy surface ────────────────────────────────────────────────────
// Every route that is NOT an admin endpoint is a decoy trap.
app.use(async (req, res, next) => {
  // Pass through legitimate management paths
  if (['/health', '/metrics', '/telemetry', '/blocklist'].includes(req.path)) {
    return next();
  }

  const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress || 'unknown';
  const severity = classifySeverity(req);
  const event = {
    id: crypto.randomUUID(),
    ip,
    timestamp: new Date().toISOString(),
    method: req.method,
    path: req.path,
    fingerprint: fingerprint(req),
    severity,
    headers: req.headers,
    body: req.body,
  };

  await recordThreat(event);

  // Respond with a plausible decoy to keep the attacker engaged
  res.set('X-Powered-By', 'PHP/7.4.3');
  res.status(200).json({ status: 'ok', token: crypto.randomBytes(16).toString('hex') });
});

// ── Admin / telemetry endpoints ───────────────────────────────────────────────

// Retrieve recent threat telemetry
app.get('/telemetry', (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 100, 1000);
  const severity = req.query.severity;
  const filtered = severity
    ? threatLog.filter((e) => e.severity === severity)
    : threatLog;
  res.json({
    total: filtered.length,
    events: filtered.slice(-limit).reverse(),
  });
});

// Retrieve current blocklist
app.get('/blocklist', (_req, res) => {
  res.json({ size: blocklist.size, ips: [...blocklist] });
});

// Manually add to blocklist
app.post('/blocklist', (req, res) => {
  const { ip } = req.body;
  if (!ip) return res.status(400).json({ error: 'ip is required' });
  blocklist.add(ip);
  blocklistSize.set(blocklist.size);
  res.status(201).json({ blocked: ip, size: blocklist.size });
});

// Health check
app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'honeypot-perimeter', threats_captured: threatLog.length }));

// Prometheus metrics
app.get('/metrics', async (_req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

app.listen(PORT, () => {
  console.log(`[Honeypot Perimeter] Edge decoy running on port ${PORT}`);
  console.log(`[Honeypot Perimeter] SumerA ledger: ${SUMERA_URL}`);
});
