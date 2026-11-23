# SumerAvera live demo

A live gateway running the real protocol: a WebSocket ingress and `POST /verify`,
with 1,152 labeled packets sent through it (1,042 items: 552 fraud, 490 legitimate).
The results are in [REPORT.md](REPORT.md) and [results.json](results.json).

## Data

Fraud packets use real identities from the HHS-OIG List of Excluded
Individuals/Entities (LEIE), `data/UPDATED.csv` (84,224 records, downloaded
November 2026; sha256
`e3c50a291e7ff5e333959fb44173552caaf1c3e8f3d5e1c95b4a79f05346f1eb`).
Claim payloads and legitimate providers are synthetic and labeled as such.
The derived watchlists (`data/watchlist.txt`, `data/watchlist-names.txt`) were
generated from that file with `../refresh_watchlist.py`; to refresh against the
current LEIE, download the latest file from HHS-OIG and re-run that script.

## Run it

Needs Python 3.10+, `fastapi` and `uvicorn` (see `../requirements.txt`), and
the `websockets` package for the traffic generator.

    cd demo
    ./start_demo.sh
    python3 traffic.py

`start_demo.sh` sets a throwaway test-only key
(`ci-test-only-key-not-a-production-secret`); never use a real key here. The
server listens on `http://127.0.0.1:8123` (dashboard at `/dashboard`, JSON
state at `/stats`). The run writes `demo_ledger.db` and `nonce_cache.db` into
this directory; they are runtime state, not committed.

## What the numbers mean

See [REPORT.md](REPORT.md) for the full run, including the pre-fix run
(`results-2026-11-20-prefixed.json`) and the lockdown re-run
(`results-2026-11-20-lockdown.json`). The fraud-detection figures are demo
results: claim payloads are synthetic, and no catch rate on real claims has
been measured.
