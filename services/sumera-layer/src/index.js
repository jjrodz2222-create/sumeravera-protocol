'use strict';

/**
 * SumerA Layer — Append-Only Immutable Ledger Service
 *
 * Provides deterministic, tamper-proof record storage for all SVP state
 * transitions, contributor provenance, and raw data inputs.
 */

const express = require('express');
const crypto = require('crypto');
const Database = require('better-sqlite3');
const client = require('prom-client');
const path = require('path');
const fs = require('fs');

const PORT = process.env.PORT || 3001;
const DB_PATH = process.env.DB_PATH || '/data/sumera.db';

// ── Ensure data directory ─────────────────────────────────────────────────────
const dataDir = path.dirname(DB_PATH);
if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

// ── Database bootstrap ────────────────────────────────────────────────────────
const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');
db.exec(`
  CREATE TABLE IF NOT EXISTS ledger (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id     TEXT    NOT NULL UNIQUE,
    timestamp    TEXT    NOT NULL,
    category     TEXT    NOT NULL,
    payload_hash TEXT    NOT NULL,
    payload      TEXT    NOT NULL,
    prev_hash    TEXT    NOT NULL DEFAULT '',
    chain_hash   TEXT    NOT NULL
  );
`);

// ── Prometheus metrics ────────────────────────────────────────────────────────
const register = new client.Registry();
client.collectDefaultMetrics({ register });

const ledgerEntries = new client.Counter({
  name: 'sumera_ledger_entries_total',
  help: 'Total entries appended to the ledger',
  labelNames: ['category'],
  registers: [register],
});

// ── Ledger helpers ────────────────────────────────────────────────────────────
function sha256(data) {
  return crypto.createHash('sha256').update(data).digest('hex');
}

function lastChainHash() {
  const row = db.prepare('SELECT chain_hash FROM ledger ORDER BY seq DESC LIMIT 1').get();
  return row ? row.chain_hash : '0'.repeat(64);
}

function appendEntry(category, payload) {
  const entry_id = crypto.randomUUID();
  const timestamp = new Date().toISOString();
  const payload_hash = sha256(JSON.stringify(payload));

  const insert = db.transaction(() => {
    const prev_hash = lastChainHash();
    const chain_hash = sha256(`${prev_hash}${payload_hash}${timestamp}`);
    db.prepare(`
      INSERT INTO ledger (entry_id, timestamp, category, payload_hash, payload, prev_hash, chain_hash)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(entry_id, timestamp, category, payload_hash, JSON.stringify(payload), prev_hash, chain_hash);
    return { entry_id, timestamp, chain_hash };
  });

  const result = insert();
  ledgerEntries.inc({ category });
  return result;
}

function verifyChain() {
  const rows = db.prepare('SELECT * FROM ledger ORDER BY seq ASC').all();
  let prevHash = '0'.repeat(64);
  for (const row of rows) {
    if (row.prev_hash !== prevHash) return false;
    const expected = sha256(`${row.prev_hash}${row.payload_hash}${row.timestamp}`);
    if (row.chain_hash !== expected) return false;
    prevHash = row.chain_hash;
  }
  return true;
}

// ── Express app ───────────────────────────────────────────────────────────────
const app = express();
app.use(express.json());

// Append a new entry to the ledger
app.post('/ledger/append', (req, res) => {
  const { category, payload } = req.body;
  if (!category || !payload) {
    return res.status(400).json({ error: 'category and payload are required' });
  }
  const result = appendEntry(category, payload);
  res.status(201).json(result);
});

// Retrieve ledger entries (paginated)
app.get('/ledger', (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 50, 500);
  const offset = parseInt(req.query.offset) || 0;
  const rows = db.prepare('SELECT seq, entry_id, timestamp, category, payload_hash, chain_hash FROM ledger ORDER BY seq DESC LIMIT ? OFFSET ?').all(limit, offset);
  const total = db.prepare('SELECT COUNT(*) as cnt FROM ledger').get().cnt;
  res.json({ total, offset, limit, entries: rows });
});

// Retrieve a single entry by ID
app.get('/ledger/:entry_id', (req, res) => {
  const row = db.prepare('SELECT * FROM ledger WHERE entry_id = ?').get(req.params.entry_id);
  if (!row) return res.status(404).json({ error: 'Entry not found' });
  res.json({ ...row, payload: JSON.parse(row.payload) });
});

// Verify full chain integrity
app.get('/ledger/verify/chain', (_req, res) => {
  const valid = verifyChain();
  res.json({ valid, checked_at: new Date().toISOString() });
});

// Health check
app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'sumera-layer' }));

// Prometheus metrics
app.get('/metrics', async (_req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

app.listen(PORT, () => {
  console.log(`[SumerA Layer] Ledger service running on port ${PORT}`);
  console.log(`[SumerA Layer] Database: ${DB_PATH}`);
});
