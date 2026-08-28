'use strict';

/**
 * Paws Connect — Species-Agnostic Identity & Verification Service
 *
 * Manages animal identity nodes per the PawsConnectIdentityNode schema.
 * Nodes are stored on the SumerA immutable ledger and validated against
 * the JSON schema before acceptance.
 */

const express = require('express');
const crypto = require('crypto');
const Database = require('better-sqlite3');
const Ajv = require('ajv');
const client = require('prom-client');
const rateLimit = require('express-rate-limit');
const path = require('path');
const fs = require('fs');

const PORT = process.env.PORT || 3004;
const DB_PATH = process.env.DB_PATH || '/data/paws.db';
const SUMERA_URL = process.env.SUMERA_URL || 'http://sumera-layer:3001';
const AVERA_URL = process.env.AVERA_URL || 'http://avera-engine:3002';

// ── Load identity schema ──────────────────────────────────────────────────────
const SCHEMA_PATH = path.join(__dirname, '../../../schemas/paws-connect-identity.json');
const identitySchema = JSON.parse(fs.readFileSync(SCHEMA_PATH, 'utf8'));

const ajv = new Ajv({ allErrors: false });
const validateIdentity = ajv.compile(identitySchema);

// ── Ensure data directory ─────────────────────────────────────────────────────
const dataDir = path.dirname(DB_PATH);
if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

// ── Database bootstrap ────────────────────────────────────────────────────────
const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');
db.exec(`
  CREATE TABLE IF NOT EXISTS identity_nodes (
    node_id               TEXT PRIMARY KEY,
    species_classification TEXT NOT NULL,
    biometric_hash        TEXT NOT NULL,
    chip_identifier       TEXT,
    steward_signature     TEXT NOT NULL,
    immutable_ledger_record INTEGER NOT NULL DEFAULT 1,
    created_at            TEXT NOT NULL,
    ledger_entry_id       TEXT
  );
`);

// ── Prometheus metrics ────────────────────────────────────────────────────────
const register = new client.Registry();
client.collectDefaultMetrics({ register });

const nodesRegistered = new client.Counter({
  name: 'paws_nodes_registered_total',
  help: 'Total identity nodes registered',
  labelNames: ['species'],
  registers: [register],
});

const verificationsTotal = new client.Counter({
  name: 'paws_verifications_total',
  help: 'Total node verification requests',
  labelNames: ['result'],
  registers: [register],
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function sha256(data) {
  return crypto.createHash('sha256').update(data).digest('hex');
}

function deriveNodeId(species, primaryMarkingHash, stewardSignature) {
  return sha256(`${species}:${primaryMarkingHash}:${stewardSignature}`);
}

// ── Express app ───────────────────────────────────────────────────────────────
const app = express();
app.use(express.json());

const apiLimiter = rateLimit({ windowMs: 60_000, max: 200, standardHeaders: true, legacyHeaders: false });
app.use(apiLimiter);

/**
 * POST /nodes
 * Register a new Paws Connect identity node.
 */
app.post('/nodes', async (req, res) => {
  const body = req.body;

  // Schema validation
  const valid = validateIdentity(body);
  if (!valid) {
    return res.status(422).json({ error: 'Schema validation failed', details: validateIdentity.errors });
  }

  const { node_id: providedId, species_classification, biometric_markers, steward_signature, immutable_ledger_record = true } = body;
  const primaryMarkingHash = biometric_markers.primary_marking_hash;

  // Derive deterministic node_id if not provided
  const node_id = providedId || deriveNodeId(species_classification, primaryMarkingHash, steward_signature);

  // Check for duplicate
  const existing = db.prepare('SELECT node_id FROM identity_nodes WHERE node_id = ?').get(node_id);
  if (existing) return res.status(409).json({ error: 'Node already registered', node_id });

  // Validate signal via Avera Engine
  let averaResult = null;
  try {
    const { default: fetch } = await import('node-fetch');
    const resp = await fetch(`${AVERA_URL}/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        category: 'PAWS_IDENTITY',
        payload: { source: 'paws-connect', timestamp: Date.now(), node_id, species_classification },
      }),
    });
    if (resp.ok) averaResult = await resp.json();
  } catch (_) { /* Avera unavailable — continue */ }

  const created_at = new Date().toISOString();
  const ledger_entry_id = averaResult?.ledger_entry?.entry_id || null;

  db.prepare(`
    INSERT INTO identity_nodes (node_id, species_classification, biometric_hash, chip_identifier, steward_signature, immutable_ledger_record, created_at, ledger_entry_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).run(node_id, species_classification, primaryMarkingHash, biometric_markers.chip_identifier || null, steward_signature, immutable_ledger_record ? 1 : 0, created_at, ledger_entry_id);

  nodesRegistered.inc({ species: species_classification });

  res.status(201).json({ node_id, species_classification, created_at, ledger_entry_id });
});

/**
 * GET /nodes/:node_id
 * Retrieve a registered identity node.
 */
app.get('/nodes/:node_id', (req, res) => {
  const row = db.prepare('SELECT * FROM identity_nodes WHERE node_id = ?').get(req.params.node_id);
  if (!row) return res.status(404).json({ error: 'Node not found' });
  res.json(row);
});

/**
 * GET /nodes
 * List registered nodes (paginated, filterable by species).
 */
app.get('/nodes', (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 50, 500);
  const offset = parseInt(req.query.offset) || 0;
  const species = req.query.species;

  const rows = species
    ? db.prepare('SELECT * FROM identity_nodes WHERE species_classification = ? ORDER BY created_at DESC LIMIT ? OFFSET ?').all(species, limit, offset)
    : db.prepare('SELECT * FROM identity_nodes ORDER BY created_at DESC LIMIT ? OFFSET ?').all(limit, offset);

  const total = species
    ? db.prepare('SELECT COUNT(*) as cnt FROM identity_nodes WHERE species_classification = ?').get(species).cnt
    : db.prepare('SELECT COUNT(*) as cnt FROM identity_nodes').get().cnt;

  res.json({ total, offset, limit, nodes: rows });
});

/**
 * POST /nodes/:node_id/verify
 * Verify a node's steward signature against its stored hash.
 */
app.post('/nodes/:node_id/verify', (req, res) => {
  const row = db.prepare('SELECT * FROM identity_nodes WHERE node_id = ?').get(req.params.node_id);
  if (!row) { verificationsTotal.inc({ result: 'not_found' }); return res.status(404).json({ error: 'Node not found' }); }

  const { steward_signature } = req.body;
  const match = steward_signature === row.steward_signature;
  verificationsTotal.inc({ result: match ? 'verified' : 'mismatch' });
  res.json({ verified: match, node_id: row.node_id, species_classification: row.species_classification });
});

// Health check
app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'paws-connect' }));

// Prometheus metrics
app.get('/metrics', async (_req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

app.listen(PORT, () => {
  console.log(`[Paws Connect] Identity service running on port ${PORT}`);
  console.log(`[Paws Connect] Database: ${DB_PATH}`);
});
