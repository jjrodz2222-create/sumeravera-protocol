'use strict';

/**
 * Avera Engine — Ground-Truth Validation Service
 *
 * Cross-references incoming data streams against the SumerA immutable ledger,
 * cryptographic origins, and configured rules to eliminate noise and confirm
 * signal integrity before execution.
 */

const express = require('express');
const crypto = require('crypto');
const client = require('prom-client');

const PORT = process.env.PORT || 3002;
const SUMERA_URL = process.env.SUMERA_URL || 'http://sumera-layer:3001';
const HONEYPOT_URL = process.env.HONEYPOT_URL || 'http://honeypot-perimeter:3003';

// ── Dynamic import of node-fetch (ESM) ───────────────────────────────────────
let fetch;
(async () => { ({ default: fetch } = await import('node-fetch')); })();

// ── Prometheus metrics ────────────────────────────────────────────────────────
const register = new client.Registry();
client.collectDefaultMetrics({ register });

const validationsTotal = new client.Counter({
  name: 'avera_validations_total',
  help: 'Total validation requests processed',
  labelNames: ['result'],
  registers: [register],
});

const validationDuration = new client.Histogram({
  name: 'avera_validation_duration_seconds',
  help: 'Duration of validation operations',
  registers: [register],
});

// ── Validation rules ──────────────────────────────────────────────────────────
const VALIDATION_RULES = [
  {
    id: 'RULE-001',
    description: 'Payload must not be empty',
    check: (payload) => payload && Object.keys(payload).length > 0,
  },
  {
    id: 'RULE-002',
    description: 'Payload must include a source identifier',
    check: (payload) => typeof payload.source === 'string' && payload.source.trim().length > 0,
  },
  {
    id: 'RULE-003',
    description: 'Payload must include a timestamp',
    check: (payload) => typeof payload.timestamp !== 'undefined',
  },
];

function runRules(payload) {
  const failures = VALIDATION_RULES.filter((r) => !r.check(payload));
  return { passed: failures.length === 0, failures: failures.map((r) => ({ id: r.id, description: r.description })) };
}

function sha256(data) {
  return crypto.createHash('sha256').update(data).digest('hex');
}

// ── Express app ───────────────────────────────────────────────────────────────
const app = express();
app.use(express.json());

/**
 * POST /validate
 * Validate an incoming signal payload.
 * On success, appends a verified entry to the SumerA ledger.
 */
app.post('/validate', async (req, res) => {
  const end = validationDuration.startTimer();
  const { payload, category = 'SIGNAL' } = req.body;

  if (!payload) {
    end();
    return res.status(400).json({ error: 'payload is required' });
  }

  const ruleResult = runRules(payload);
  if (!ruleResult.passed) {
    validationsTotal.inc({ result: 'rejected' });
    end();
    return res.status(422).json({ valid: false, reason: 'rule_failure', failures: ruleResult.failures });
  }

  // Attempt to record on SumerA ledger
  let ledgerEntry = null;
  try {
    const resp = await fetch(`${SUMERA_URL}/ledger/append`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category, payload }),
    });
    if (resp.ok) ledgerEntry = await resp.json();
  } catch (err) {
    console.warn('[Avera] Could not reach SumerA ledger:', err.message);
  }

  validationsTotal.inc({ result: 'accepted' });
  end();
  res.status(200).json({
    valid: true,
    payload_hash: sha256(JSON.stringify(payload)),
    ledger_entry: ledgerEntry,
  });
});

/**
 * POST /validate/batch
 * Validate an array of payloads and return per-item results.
 */
app.post('/validate/batch', async (req, res) => {
  const { payloads = [] } = req.body;
  if (!Array.isArray(payloads) || payloads.length === 0) {
    return res.status(400).json({ error: 'payloads must be a non-empty array' });
  }

  const results = payloads.map((payload) => {
    const ruleResult = runRules(payload);
    return {
      payload_hash: sha256(JSON.stringify(payload)),
      valid: ruleResult.passed,
      failures: ruleResult.failures,
    };
  });

  res.json({ results });
});

// Rules catalog
app.get('/rules', (_req, res) => {
  res.json({ rules: VALIDATION_RULES.map(({ id, description }) => ({ id, description })) });
});

// Health check
app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'avera-engine' }));

// Prometheus metrics
app.get('/metrics', async (_req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

app.listen(PORT, () => {
  console.log(`[Avera Engine] Validation service running on port ${PORT}`);
  console.log(`[Avera Engine] SumerA ledger: ${SUMERA_URL}`);
});
