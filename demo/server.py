#!/usr/bin/env python3
"""SumerAvera LIVE demo gateway (version 2.5.0 protocol code, demo wrapper).

What this is
------------
A demo server that puts the REAL SumerAvera protocol modules behind a live
socket. It does NOT re-implement verification:

  * POST /verify and GET / come from the real protocol app
    (sumeravera_core.py, imported unchanged from the public-repo work tree).
  * /ws/ingress routes each packet through the real Gate 1
    (gate1_ingress.py) live and streams the decision back.
  * /dashboard is a small live page fed only by this gateway's own counts.
  * /stats is the same state as JSON.

What is NOT protocol
--------------------
  * The LEIE watchlist flag: the demo loads the real HHS-OIG LEIE
    (UPDATED.csv) and flags packets whose provider NPI is on it. Since
    the 2026-11-20 lockdown fix the PROTOCOL enforces the same list
    itself (Gates 2/3, watchlist.py + gates.py), so the flag is now an
    independent cross-check label, not a decision -- it agrees with
    the protocol on every packet. It is NPI-only; the protocol's name
    matching (Gate 2/3) has no demo-layer equivalent.
  * All claim payloads in the simulation are synthetic claims. Only the
    fraud-class provider identities (NPI + name + exclusion) are real
    public data (HHS-OIG LEIE). Legitimate-class providers are synthetic.

Run from the demo directory (the core module's nonce store is a relative
path, nonce_cache.db, so the working directory decides where it lands):
    cd demo
    SUMERAVERA_SECRET_KEY=<throwaway, >= 32 bytes> \
    SUMERAVERA_LEDGER_DB=$PWD/demo_ledger.db \
    PYTHONDONTWRITEBYTECODE=1 \
    /tmp/audit-venv/bin/python server.py
"""

import csv
import json
import os
import sqlite3
import sys
import time
from collections import deque
from pathlib import Path

# Read the protocol modules from the repository root. This demo lives in
# demo/; import the modules, never copy-and-modify them.
WORK_TREE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORK_TREE))

DEMO_DIR = Path(__file__).resolve().parent
LEDGER_DB = os.environ.get("SUMERAVERA_LEDGER_DB", str(DEMO_DIR / "demo_ledger.db"))
LEIE_CSV = DEMO_DIR / "data" / "UPDATED.csv"

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

import sumeravera_core  # noqa: E402  (needs SUMERAVERA_SECRET_KEY set first)
from gate1_ingress import Gate1  # noqa: E402

app = sumeravera_core.app  # the real protocol app: GET / and POST /verify

STARTED = time.time()
gate = Gate1(ledger_db_path=LEDGER_DB)

# --- LEIE watchlist (protocol-enforced since the 2026-11-20 lockdown
# fix; the demo-layer flag below is retained as an independent
# cross-check label, not a decision) ---
EXCLUDED_NPIS: set = set()
if LEIE_CSV.exists():
    with open(LEIE_CSV, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            npi = (row.get("NPI") or "").strip()
            if npi and npi != "0":
                EXCLUDED_NPIS.add(npi)

# --- live state (this gateway only) ---
stats = {
    "ws": {"received": 0, "stable": 0, "rebalancing": 0, "quarantine": 0,
           "watchlist_hits": 0},
    "http": {"verify_ok": 0, "verify_held": 0, "verify_rejected": 0,
             "verify_error": 0},
}
recent = deque(maxlen=20)  # newest last; each entry is a dict
simulation_summary = {"summary": None}  # client-reported, labeled as such


def ledger_head():
    """Read the ledger head directly (fresh read-only connection)."""
    if not os.path.exists(LEDGER_DB):
        return {"entries": 0, "head_seq": None, "head_hash": None}
    try:
        conn = sqlite3.connect(f"file:{LEDGER_DB}?mode=ro", uri=True, timeout=5)
        try:
            n = conn.execute("SELECT COUNT(*) FROM state_ledger").fetchone()[0]
            row = conn.execute(
                "SELECT sequence_id, entry_hash FROM state_ledger "
                "ORDER BY sequence_id DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        return {"entries": n,
                "head_seq": row[0] if row else None,
                "head_hash": row[1] if row else None}
    except sqlite3.Error:
        return {"entries": 0, "head_seq": None, "head_hash": None}


def snapshot():
    return {
        "server": "SumerAvera demo gateway (protocol 2.5.0)",
        "uptime_seconds": round(time.time() - STARTED, 1),
        "ws": dict(stats["ws"]),
        "http": dict(stats["http"]),
        "ledger": ledger_head(),
        "watchlist": {"source": "HHS-OIG LEIE UPDATED.csv (real public data)",
                      "excluded_npis_loaded": len(EXCLUDED_NPIS),
                      "protocol_screening": _protocol_screening()},
        "recent": list(recent),
        "simulation": simulation_summary["summary"],
        "labels": {
            "traffic": "All claim payloads are synthetic claims created for "
                       "this demo.",
            "fraud_identities": "Fraud-class provider NPI/name/exclusion "
                                "are real HHS-OIG LEIE records.",
            "legitimate_identities": "Legitimate-class providers are "
                                     "synthetic (SYNTH- ids, not real NPIs).",
            "watchlist": "Protocol-enforced since the 2026-11-20 lockdown "
                         "fix (Gates 2/3); the demo-layer NPI flag is an "
                         "independent cross-check label.",
        },
    }


def _protocol_screening():
    """What the protocol's own watchlist currently holds (live reload
    applies, so this reflects the list files on disk, not a stale
    import-time snapshot)."""
    try:
        from watchlist import get_default_watchlist

        wl = get_default_watchlist()
        return {"npi_enabled": wl.enabled,
                "excluded_npis": len(wl.excluded_npis),
                "names_enabled": wl.names_enabled,
                "person_keys": wl.person_key_count,
                "business_keys": wl.bus_key_count}
    except Exception as e:  # noqa: BLE001 - /stats must never fail
        return {"error": str(e)}


@app.middleware("http")
async def count_verify_outcomes(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/verify" and request.method == "POST":
        if response.status_code == 200:
            stats["http"]["verify_ok"] += 1
        elif response.status_code == 202:
            stats["http"]["verify_held"] += 1
        elif response.status_code == 401:
            stats["http"]["verify_rejected"] += 1
        else:
            stats["http"]["verify_error"] += 1
    return response


@app.websocket("/ws/ingress")
async def ws_ingress(ws: WebSocket):
    """Live socket: one signed packet in, one Gate 1 decision out.

    Client message (JSON): {"payload": str, "signature": str,
    "nonce": str, "timestamp": float, "provider_npi": str|None,
    "claim_id": str|None, "label": str|None (client-asserted, echoed)}.
    The decision comes from the real Gate 1; the watchlist flag is an
    independent NPI cross-check label, not a decision.
    """
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            payload = str(msg.get("payload", "")).encode("utf-8")
            decision = gate.route(
                payload,
                str(msg.get("signature", "")),
                str(msg.get("nonce", "")),
                msg.get("timestamp", 0),
            )
            npi = msg.get("provider_npi")
            watchlist_hit = bool(npi) and str(npi) in EXCLUDED_NPIS
            tier = decision["tier"]
            stats["ws"]["received"] += 1
            if tier == "STABLE":
                stats["ws"]["stable"] += 1
            elif tier == "REBALANCING":
                stats["ws"]["rebalancing"] += 1
            else:
                stats["ws"]["quarantine"] += 1
            if watchlist_hit:
                stats["ws"]["watchlist_hits"] += 1
            record = {
                "ts": round(time.time(), 3),
                "transport": "ws",
                "claim_id": msg.get("claim_id"),
                "provider_npi": npi,
                "client_label": msg.get("label"),
                "tier": tier,
                "status_code": decision["status_code"],
                "reason": decision["reason"],
                "drift_ms": decision["drift_ms"],
                "ledger_seq": decision["ledger_seq"],
                "watchlist_hit": watchlist_hit,
            }
            recent.append(record)
            await ws.send_json({
                **{k: decision[k] for k in
                   ("tier", "status_code", "action", "reason", "nonce",
                    "drift_ms", "ledger_seq", "ledger_hash")},
                "watchlist_hit": watchlist_hit,
                "watchlist_note": "independent NPI cross-check label; the protocol enforces Gates 2/3 itself",
                "claim_id": msg.get("claim_id"),
            })
    except WebSocketDisconnect:
        pass


@app.get("/stats")
def get_stats():
    return JSONResponse(snapshot())


@app.post("/demo/results")
async def post_results(request: Request):
    """Accept the simulation client's summary. Stored as client-reported;
    the dashboard labels it as such."""
    body = await request.json()
    body["_reported_by"] = "simulation client (client-side accounting)"
    simulation_summary["summary"] = body
    return {"stored": True}


DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>SumerAvera live demo</title>
<style>body{font-family:monospace;max-width:900px;margin:2em auto;padding:0 1em}
h1{font-size:1.3em}table{border-collapse:collapse}td,th{border:1px solid #999;padding:4px 8px;text-align:left}
.banner{background:#fff3cd;padding:8px;border:1px solid #cc9}</style></head>
<body><h1>SumerAvera live demo gateway (protocol 2.5.0)</h1>
<div class="banner"><b>Labels:</b> all claim payloads are synthetic claims made for this demo.
Fraud-class provider identities are real HHS-OIG LEIE records. Legitimate-class
providers are synthetic. The protocol enforces the LEIE watchlist itself
(Gates 2/3); the LEIE flag shown here is an independent cross-check label.
No random/fake telemetry: every number below comes from this
running gateway.</div>
<p>Uptime: <span id="up"></span>s &nbsp;|&nbsp; <a href="/stats">/stats (JSON)</a>
&nbsp;|&nbsp; WebSocket: <code>/ws/ingress</code> &nbsp;|&nbsp; HTTP verify: <code>POST /verify</code></p>
<h2>Decisions (live)</h2><table>
<tr><th>WebSocket received</th><td id="ws_recv"></td></tr>
<tr><th>STABLE (200)</th><td id="ws_st"></td></tr>
<tr><th>REBALANCING (202)</th><td id="ws_re"></td></tr>
<tr><th>QUARANTINE (403)</th><td id="ws_qu"></td></tr>
<tr><th>Watchlist hits (demo layer)</th><td id="ws_wl"></td></tr>
<tr><th>HTTP /verify OK (200)</th><td id="h_ok"></td></tr>
<tr><th>HTTP /verify held (202)</th><td id="h_held"></td></tr>
<tr><th>HTTP /verify rejected (401)</th><td id="h_rej"></td></tr>
<tr><th>Ledger entries</th><td id="led_n"></td></tr>
<tr><th>Ledger head</th><td id="led_h"></td></tr>
</table>
<h2>Last simulation (client-reported)</h2><pre id="sim">none yet</pre>
<h2>Recent decisions (last 20)</h2><pre id="rec"></pre>
<script>
async function tick(){
  const s = await (await fetch('/stats')).json();
  document.getElementById('up').textContent = s.uptime_seconds;
  document.getElementById('ws_recv').textContent = s.ws.received;
  document.getElementById('ws_st').textContent = s.ws.stable;
  document.getElementById('ws_re').textContent = s.ws.rebalancing;
  document.getElementById('ws_qu').textContent = s.ws.quarantine;
  document.getElementById('ws_wl').textContent = s.ws.watchlist_hits;
  document.getElementById('h_ok').textContent = s.http.verify_ok;
  document.getElementById('h_held').textContent = s.http.verify_held;
  document.getElementById('h_rej').textContent = s.http.verify_rejected;
  document.getElementById('led_n').textContent = s.ledger.entries;
  document.getElementById('led_h').textContent =
    s.ledger.head_seq + ' / ' + (s.ledger.head_hash||'').slice(0,16) + '...';
  document.getElementById('sim').textContent =
    s.simulation ? JSON.stringify(s.simulation, null, 2) : 'none yet';
  document.getElementById('rec').textContent =
    s.recent.slice().reverse().map(r =>
      new Date(r.ts*1000).toISOString().slice(11,19) + ' ' + r.transport + ' ' +
      (r.claim_id||'') + ' ' + (r.client_label||'') + ' -> ' + r.tier +
      (r.watchlist_hit ? ' [LEIE-WATCHLIST]' : '') +
      (r.ledger_seq ? ' seq=' + r.ledger_seq : '')).join('\\n');
}
tick(); setInterval(tick, 2000);
</script></body></html>
"""


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("DEMO_PORT", "8123"))
    print(f"[demo] ledger: {LEDGER_DB}", flush=True)
    print(f"[demo] LEIE watchlist NPIs loaded: {len(EXCLUDED_NPIS)}", flush=True)
    print(f"[demo] listening on 0.0.0.0:{port}  dashboard /dashboard", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
