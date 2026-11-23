# SumerAvera LIVE demo — measured outcome

**Run:** 2026-11-20 ~23:09 UTC (17:09 CST). Protocol code: public-repo work tree,
version 2.5.0 (code at e8ee616; workflow-only commits after it did not touch code).
Full audit (13 checks) passes in both repos; CI green in both. This demo does not
re-prove the modules — it puts them behind a live socket and measures them under
traffic. No random/fake telemetry anywhere: every number below comes from the
running gateway and the simulation client's per-packet accounting, which
reconcile with each other.

## What the demo is

- **Server** (`server.py`, running now): the REAL protocol app imported unchanged
  (`sumeravera_core.py` — `POST /verify`, `GET /`), plus a REAL WebSocket
  endpoint `/ws/ingress` that routes each packet through the real Gate 1
  (`gate1_ingress.py`) live and streams the decision back. Also `/dashboard`
  (live page) and `/stats` (JSON). Demo code only; nothing in the repos or the
  fix-work trees was modified.
- **Live socket:** `ws://127.0.0.1:8123/ws/ingress` — client sends a signed
  packet, server returns tier (STABLE 200 / REBALANCING 202 / QUARANTINE 403),
  ledger sequence when accepted, reason, drift, and a LEIE watchlist flag.
- **Dashboard:** http://127.0.0.1:8123/dashboard — live counts by decision, recent
  decisions, ledger head, last simulation summary.
- **Reach:** the server binds `0.0.0.0:8123` on this VM and is reachable at
  `http://127.0.0.1:8123` (VM private IP 198.19.0.2, not publicly routable).
  **There is no public URL.** Do not claim one.
- **Server process:** pid 11894 (started 23:09 UTC, still running), cwd
  `demo/`, ledger `demo_ledger.db`, nonce store
  `nonce_cache.db`. Restart: `./start_demo.sh`. Re-run traffic:
  `SUMERAVERA_SECRET_KEY='ci-test-only-key-not-a-production-secret' python3 traffic.py`
  (same throwaway key the server uses; never a real key, never written to a file).
- **Key:** throwaway test key only, via environment variable.

## Dataset — real public data, synthetic claims

- **Real:** HHS-OIG **LEIE** (List of Excluded Individuals/Entities),
  `UPDATED.csv`, downloaded 2026-11-20 from
  https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv
  (correction: LEIE is published by HHS-OIG, not CMS; the file is the OIG's
  official download). 84,224 records; 9,023 with an NPI (8,844 distinct NPIs);
  sha256 `e3c50a291e7ff5e333959fb44173552caaf1c3e8f3d5e1c95b4a79f05346f1eb`.
  Stored at `demo/data/UPDATED.csv`. Fraud-class packets use real LEIE
  provider NPI + name + exclusion type/date (435 distinct excluded providers
  sampled deterministically).
- **Synthetic:** every claim payload (claim id, amount $50–$5,000, service date)
  is a synthetic claim invented for the demo; legitimate-class providers are
  synthetic (`SYNTH-` ids, not real NPIs). Amounts/dates prove nothing about
  real claims — only the provider identity and exclusion status are real.
- **Watchlist:** the demo loads the 8,844 LEIE NPIs and flags packets whose
  provider NPI is on it. This is a **demo-layer check, not a protocol
  decision** — the protocol verifies packet integrity only. It exists to show
  that boundary honestly.

## Method

`traffic.py` sent **975 packets** through the running server (not against
imported functions): 700 sequential WebSocket sends (main run), 75 HTTP
`POST /verify` sends, 200 WebSocket sends in a 4-client concurrent burst.
Every packet was labeled before sending: class (legitimate / fraud type),
transport, expected outcome. 110 extra sends were replay *setup* sends
(first send of a replayed pair) and are counted separately, not as items.

Classes: `legitimate` 430 items; fraud 435 items — `fraud_bad_sig` 110,
`fraud_replay` 110, `fraud_stale` 110, `fraud_drifted` 55, `fraud_clean` 50.
"Stopped" = quarantined/rejected by the protocol OR flagged by the demo-layer
LEIE watchlist (union, counted once). Protocol-only and combined rates are
reported separately so the watchlist never inflates the protocol's own number.

## Measured numbers

| Measure | Value |
|---|---|
| Packets sent (WS main + HTTP + burst) | 975 (700 + 75 + 200) |
| Items scored (fraud + legitimate) | 865 (435 fraud, 430 legitimate) |
| WS STABLE / REBALANCING / QUARANTINE | 550 / 50 / 300 (of 900 WS sends) |
| HTTP /verify 200 / 401 / 500 | 45 / 30 / 0 (of 75 sends) |
| Bad signatures caught | 110 / 110 (100 QUARANTINE + 10 HTTP 401) |
| Replays caught | 110 / 110 (100 QUARANTINE + 10 HTTP 401) |
| Stale (400 s old) caught | 110 / 110 (100 QUARANTINE + 10 HTTP 401) |
| Drifted (30 s old) | 50 REBALANCING (WS) + 5 accepted HTTP 200 |
| Clean fraud (valid + fresh, excluded provider) | 50 STABLE — protocol let them through |
| **Catch rate, protocol only** | **330 / 435 = 75.9%** |
| **Catch rate, protocol + LEIE watchlist** | **430 / 435 = 98.9%** |
| Fraud stopped by watchlist only | 100 (50 drifted + 50 clean, WS) |
| Fraud missed entirely | 5 (HTTP drifted: accepted by core's 300 s window, no watchlist on HTTP path) |
| False positives (legitimate quarantined/rejected) | 0 / 430 = 0.0% |
| Legitimate watchlist hits | 0 |
| Ledger entries written | 645 (400 WS + 45 HTTP + 200 burst) |
| Ledger chain valid at end | **True** (head seq 645, hash `0b8f6143e7f4f037…`) |
| WS main run throughput (sequential round trips) | 1,174.8 packets/s (700 in 0.6 s) |
| HTTP phase throughput | 253.1 packets/s (75 in 0.3 s) |
| Concurrent burst throughput (4 clients) | 1,548.1 packets/s (200 in 0.13 s) |

Per-class outcome (items): bad_sig 110 → 100 QUARANTINE + 10 REJECTED;
replay 110 → 100 QUARANTINE + 10 REJECTED; stale 110 → 100 QUARANTINE +
10 REJECTED; drifted 55 → 50 REBALANCING + 5 OK; clean 50 → 50 STABLE;
legitimate 430 → 400 STABLE + 30 OK. Full per-packet records: `results.json`.

Server-side counters reconcile with the client accounting (WS received 900,
stable 550, rebalancing 50, quarantine 300, watchlist hits 500 — the 500
includes the 100 replay-setup sends from excluded providers; HTTP ok 45,
rejected 30).

## What this shows — and what it does not

- **Shows:** the verification core does what it claims under live traffic:
  every forged, replayed, and stale packet was caught (330/330); no legitimate
  packet was wrongly stopped (0/430); the ledger recorded every accepted packet
  and the chain verifies. The live socket works end to end.
- **Shows the boundary:** the protocol verifies *packet integrity*, not
  *provider identity*. A properly signed, fresh claim from an excluded provider
  sails through Gate 1 (50/50 STABLE) — the only thing that caught those was
  the demo-layer LEIE watchlist. Drifted (30 s) claims are accepted by design
  on both paths (REBALANCING on WS, plain 200 on HTTP).
- **Does not show:** real fraud detection on real claims. The claims are
  synthetic; the amounts and dates are invented. The "fraud" in this run is
  integrity fraud (forgery/replay/stale) plus real excluded identities. A real
  catch rate on real claims still needs real claim data (e.g. CMS public
  datasets) and a deployment where the watchlist — or an equivalent identity
  check — is part of the pipeline, not a demo extra.

## Re-run after the 2026-11-20 lockdown fix (same day, ~21:00 CST)

The protocol fix landed in the work trees (not yet committed or pushed):
POST /verify's window tightened to 65s past / 5s future, and identity
screening (LEIE watchlist, `watchlist.py`) added to both paths. The demo
server was restarted on the fixed code with
`SUMERAVERA_WATCHLIST_PATH=$PWD/data/watchlist.txt` (8,844 NPIs, built
by `refresh_watchlist.py` from this same UPDATED.csv; the pre-fix run is
preserved as `results-2026-11-20-prefixed.json`). Same 975 packets, same
labels, same traffic generator.

| Measure | Before fix | After fix |
|---|---|---|
| Catch rate, protocol only | 330 / 435 = 75.9% | **435 / 435 = 100%** |
| Catch rate, protocol + watchlist | 430 / 435 = 98.9% | 435 / 435 = 100% |
| Fraud missed entirely | 5 (HTTP drifted) | **0** |
| Fraud stopped by watchlist only | 100 | 0 (the protocol catches them itself now) |
| Clean fraud (excluded, valid, fresh) | 50 STABLE | 50 QUARANTINE |
| Drifted fraud (30s old, excluded) | 50 REBALANCING + 5 OK | 50 QUARANTINE + 5 REJECTED |
| False positives | 0 / 430 | 0 / 430 |
| Ledger entries / chain valid | 645 / True | 430 / True (only legitimate traffic is recorded now) |
| WS STABLE / REBALANCING / QUARANTINE | 550 / 50 / 300 | 400 / 0 / 500 |
| HTTP /verify 200 / 401 | 45 / 30 | 30 / 45 |
| WS throughput | 1,174.8 pkts/s | 1,916.4 pkts/s |
| HTTP throughput | 253.1 pkts/s | 260.7 pkts/s |

Server-side counters reconcile with the client accounting (WS received
900, quarantine 500 = 400 fraud items + 100 replay-setup sends from
excluded providers, now quarantined for identity; HTTP 30 OK / 45
rejected). The demo-layer watchlist flag is now redundant for the
decision -- the protocol quarantines first -- but it still records,
and it agrees with the protocol on every packet.

## Re-run after the Gates 2/3 build (2026-11-21, ~11:30 CST)

Gate 2 (exact name matching) and Gate 3 (fuzzy identity → secondary
review) landed in the work trees (not yet committed or pushed). The demo
server was restarted on the new code with both watchlist files built by
the extended `refresh_watchlist.py` from this same UPDATED.csv:
`watchlist.txt` (8,844 NPIs) and `watchlist-names.txt` (78,794 person
keys, 3,493 business keys). The previous run is preserved as
`results-2026-11-20-lockdown.json`. The original 975-packet matrix was
re-run unchanged, plus 177 new items exercising the new gates: name
fraud built from real LEIE rows with NO NPI (real LASTNAME/FIRSTNAME/
DOB/ZIP and real BUSNAME/STATE, properly signed and fresh), fuzzy
variants of those rows (one-digit DOB typo, first-name initial or
3-char prefix, surname typo, business-name typo), and synthetic
legitimate claims carrying name fields that match nothing in LEIE
(verified against the file at generation time). 1,152 packets total,
1,042 items, 552 fraud, 490 legitimate.

| Measure | Lockdown re-run | Gates 2/3 re-run |
|---|---|---|
| Fraud items | 435 | 552 |
| Fraud stopped by protocol (QUARANTINE/REJECTED) | 435 / 435 = 100% | 500 / 552 = 90.6% |
| Fraud held for secondary review (REBALANCING identity_review / HTTP 202) | — (no Gate 3) | 52 / 552 |
| Fraud stopped OR held | 435 / 435 | **552 / 552 = 100%** |
| Fraud missed entirely | 0 | **0** |
| Name fraud, exact person (LAST+FIRST+DOB) | — | 40 / 40 stopped (30 QUARANTINE WS, 10 REJECTED HTTP) |
| Name fraud, exact business (BUSNAME+STATE) | — | 25 / 25 stopped (20 QUARANTINE WS, 5 REJECTED HTTP) |
| Fuzzy fraud F1–F4 | — | 52 / 52 held (40 REBALANCING WS, 12 REVIEW HTTP), none quarantined, none accepted |
| Legitimate with name fields | — | 60 / 60 accepted (50 STABLE WS, 10 OK HTTP), 0 held |
| False positives | 0 / 430 | 0 / 490 |
| Ledger entries / chain valid | 430 / True | 490 / True (only legitimate traffic is recorded; chain re-verified by hand, head hash matches /stats) |
| HTTP /verify 200 / 202 / 401 | 30 / 0 / 45 | 40 / 12 / 60 |
| WS throughput (main run) | 1,916.4 pkts/s | 1,390.9 pkts/s |
| HTTP throughput | 260.7 pkts/s | 274.4 pkts/s |
| Name-phase throughput | — | 67.5 pkts/s (generator-bound: the generator reads the full LEIE CSV three times to build its key sets; not protocol throughput) |
| Burst throughput | 1,548.1 pkts/s | 638.0 pkts/s |

Notes on the numbers. The headline protocol-only catch rate fell from
100% to 90.6% because the denominator grew by 117 fraud items and the
52 fuzzy items are HELD, not stopped — by design, Gate 3 never
excludes. The honest statement is the pair: 500 stopped + 52 held =
552 accounted for, 0 missed. The demo-layer watchlist flag adds
nothing now (0 watchlist-only stops): name fraud carries no NPI, so the
flag cannot see it, and the protocol catches it first. Throughput
varies run to run on this shared VM (WS main 1,391 vs 1,916; burst 638
vs 1,548); the protocol benchmark is the stable measure (public
12,169/s, core 13,153/s, no regression vs ~10,600/s on Nov 20).

## Gaps / findings to carry forward (updated 2026-11-21)

1. ~~**HTTP path has no watchlist and a wider skew window.**~~ CLOSED
   2026-11-20 by the lockdown fix (65s/5s window, watchlist on both
   paths); re-verified in this run (HTTP rejects name fraud 401).
2. ~~**The watchlist is demo-only.**~~ CLOSED in the work trees
   2026-11-21: `watchlist.py` + `refresh_watchlist.py` live in the
   protocol code, with a monthly systemd timer delivered (not yet
   installed) and mtime-based reload. Still unpushed; still needs a
   deployment decision.
3. ~~**Only 9,023 of 84,224 LEIE records carry an NPI.**~~ CLOSED in
   the work trees 2026-11-21: Gate 2 exact name matching covers the
   no-NPI rows (78,794 person keys + 3,493 business keys from this
   file); Gate 3 holds near-matches for review. Measured in this run:
   65/65 exact name fraud stopped, 52/52 fuzzy held, 0 false
   positives on 60 named legitimate claims.
4. **Throughput here is localhost round-trip throughput**, not a load test
   (the earlier load test measured 10k–27k verifications/s under concurrency).
   The 253/s HTTP number is dominated by per-request connection setup in the
   generator (urllib, no keep-alive), not by the protocol.
5. **No public URL.** The demo is reachable only on this VM. A public demo
   needs a hosted deployment, which does not exist yet.
