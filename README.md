# SumerAvera Protocol

[![Protocol Verification](https://github.com/jjrodz2222-create/sumeravera-protocol/actions/workflows/verify.yml/badge.svg)](https://github.com/jjrodz2222-create/sumeravera-protocol/actions/workflows/verify.yml)
[![Version 2.5.0](https://img.shields.io/badge/version-2.5.0-blue)](https://github.com/jjrodz2222-create/sumeravera-protocol/blob/main/VERSION)

> Updated 24 November 2026. Public repository head `aef05ba`, private core head
> `5afcfa77` (22 November 2026). Version 2.5.0 in both repositories.
> Continuous integration green in both repositories — Protocol Verification run
> #14 passed on public head `09d16fe`, run #70 passed on core head `6932e33`
> (28s, validate job 25s, 22 November 2026). Runs on the current heads have not been checked yet.

SumerAvera is a fraud detection and mitigation protocol for healthcare and other digital fraud industries, demonstrated on healthcare claims. It verifies that each claim packet is authentic, fresh, and not replayed before recording it, and screens the submitting provider against the HHS-OIG List of Excluded Individuals/Entities (LEIE). Anything it cannot verify is not recorded: the protocol fails closed.

One plus one will never be three. A verified two stays a two.

## How to read this document

Five kinds of statement are kept apart:

- **Verified** — checked against the repositories or a dated record (for example, the 13 of 13 invariant audit).
- **Measured** — a figure from a benchmark or load-test run, with the machine and date named.
- **Measured (demo)** — a figure from the demo, where claim payloads are synthetic.
- **Specified** — stated as a design target. Designed, not yet measured.
- **Open** — undecided or unfinished.

A specified number is never presented here as a measured one.

## Headline numbers

The numbers that stand out. Each is labelled Measured, Measured (demo), or Specified
(designed, not yet measured); the detail and the run conditions are in Numbers.

The fraud-detection figures below are demo results: claim payloads are synthetic. No catch rate on real claims has been measured.

- **115,313 verifications per second** — edge guardian, single-threaded,
  0.009 ms per frame (Measured, 20 November 2026, 4-CPU VM, Python 3.12,
  `benchmark.py`).
- **10,593 verifications per second** — core ingress, single-threaded,
  0.094 ms per verified packet (Measured, 20 November 2026, 4-CPU VM,
  Python 3.12).
- **15,000–30,000 ledger writes per second on the VM, 8,800–10,400 on the Chromebook, 372.7 bytes per recorded state** —
  the ledger costs less than 400 bytes a state; the write rate varies run to run
  on the machine (Measured, 20–22 November 2026).
- **0 errors, 0% loss, 1–32 concurrent writers** — 48 load-test runs
  (20 November 2026), reproduced by five further 48-run matrices (22 November
  2026, VM and Chromebook, both trees): 1,512,000 of 1,512,000 successes,
  chains valid, no saturation point in the tested range; throughput 4–27k/s
  depending on the machine (Measured, 20–22 November 2026).
- **500 of 552 fraud cases stopped, 52 held for review (fuzzy matches), 0 missed; 0 false positives on 490 legitimate cases.** Demo data. The fraud identities come from the list the screen checks, so this shows the lookup works, not that it finds fraud in real claims. (Measured (demo), 21 November 2026).
- **200 of 200 malformed packets rejected** (Measured, 20 November 2026).

### Specified (not measured)

- **PUE 1.12–1.18, about 20,000–23,000 MWh saved per year on a 10 MW cluster
  with half the work shifted** (Specified — design target, not measured). Main
  assumption: half of the cluster's work shifts to the edge, against a central
  average PUE of 1.56.

## Abilities

- **Verify before record.** No state is recorded until its signature is verified.
- **Replay rejection.** A replayed nonce is rejected, including after a restart at the core.
- **Fail-closed on keys.** A missing, too-short, or fallback-literal key fails the
  audit and refuses to start, rather than running on a substitute.
- **Unknown devices rejected.** A device that is not explicitly provisioned is
  rejected outright.
- **Malformed schemas rejected.** Malformed payloads are rejected outright, before
  any state transition.
- **Quarantine.** Anomalous state is quarantined rather than committed. In the
  lockdown re-run of 21 November 2026, 500 of 900 WebSocket packets were
  quarantined (forged signatures, replays, stale timestamps, excluded providers).
- **Held for review.** A fuzzy identity match is held, not accepted and not
  rejected: 52 of 552 fraud items in the Gates 2/3 re-run of 21 November 2026,
  all 52 held, none accepted.
- **Ledger recording.** Every accepted packet is appended to the hash-chained
  ledger: 490 entries in the Gates 2/3 re-run, chain valid at the end. Only
  legitimate traffic is recorded.

## Tests run

Version 2.5.0, 22 November 2026. Public repository
`jjrodz2222-create/sumeravera-protocol` (head `aef05ba`); private core
`jjrodz2222-create/sumeravera-protocol-core` (head `5afcfa77`).

- **Test suite: 90 of 90 passing in each repository** (`python3 -m pytest
  tests/ -q`, verified 22 November 2026): 22 edge-guardian tests, 9 Gate 1 tests,
  6 ledger-wiring tests, 7 concurrency tests, 16 watchlist tests, 30 identity-gate
  tests.
- **Core integration checks: 3** — valid ingress accepted, replay rejected, stale
  timestamp rejected (`direct_test.py`).
- **Standalone invariant audit: 13 of 13 real checks passing in each
  repository** (`audit_verify_standalone.py`). The audit fails closed
  without a key.
- **Model-checked.** TLA+: 297 generated states (261 distinct) at depth 4, 0 violations. Model-checked, not formally verified — the specification is small and models nonce replay only.
- **Continuous integration.** Protocol Verification run #14 passed on public head
  `09d16fe` (22 November 2026); run #70 passed on core head `6932e33` (28s,
  validate job 25s). Both workflows run the pytest suite and set a test-only
  key for all test steps. Runs on the current heads have not been checked yet.

## Numbers

### Measured — 20–22 November 2026

**Live demo, 20 November 2026.** A live demo server ran the real protocol
(public-repo code, version 2.5.0) behind a WebSocket ingress and `POST /verify`,
and 975 labeled packets were sent through it: 700 sequential WebSocket sends,
75 HTTP sends, 200 WebSocket sends in a 4-client concurrent burst. The count
reconciles: 975 packets = 865 items (435 fraud + 430 legitimate) + 110 replay
setup sends — each replay attack first sends the legitimate original, then the
copy with the same nonce. Fraud-class packets used real provider identities
from the HHS-OIG List of Excluded Individuals/Entities (LEIE, 84,224 records,
downloaded 20 November 2026); every claim payload was synthetic, invented for
the demo. The numbers below are that run's, nothing else.

- Integrity attacks caught: **330 of 330** — bad signatures 110 of 110, replays
  110 of 110, stale timestamps (400 s old) 110 of 110.
- False positives: **0 of 430** legitimate items quarantined or rejected.
- Catch rate, protocol only: **75.9% (330 of 435 fraud items)**.
- Catch rate, protocol with the LEIE watchlist: **98.9% (430 of 435)**. On this
  run the watchlist was a demo-layer check, not a protocol decision; the two
  rates are reported separately so the watchlist never inflates the protocol's
  own number.
- Missed: **5 fraud items** — drifted claims (30 s old) accepted by `POST
  /verify` on its old 300-second window. The window was tightened to 65 seconds
  past / 5 seconds future on 20–21 November 2026; see the lockdown re-run below.
- Ledger: **645 entries written (400 WebSocket + 45 HTTP + 200 burst), chain
  valid** at the end of the run.
- Throughput (localhost round trips, not a load test): WebSocket about **1,175
  packets per second** sequential, about **1,548 per second** in a 4-client
  burst; HTTP about **253 per second** — generator-bound (per-request connection
  setup, no keep-alive), not a protocol limit.

**Lockdown re-run, 21 November 2026.** Same 975 packets, same labels, same
traffic generator, on the fixed code (`POST /verify` tightened to 65 seconds
past / 5 seconds future; identity screening now in the protocol on both paths).
Catch rate, protocol only: **435 of 435 = 100%**. Missed: **0**. False
positives: **0 of 430**. Ledger: **430 entries, chain valid** (only legitimate
traffic is recorded now). WebSocket throughput 1,916.4 packets per second.

**Gates 2/3 re-run, 21 November 2026.** The original 975-packet matrix re-run
unchanged, plus 177 new items exercising the new identity gates: name fraud
built from real LEIE rows with no NPI, fuzzy variants of those rows (a one-digit
date typo, a first-name initial or short prefix, a surname or business-name
typo), and synthetic legitimate claims carrying name fields that match nothing
in LEIE. 1,152 packets total = 1,042 items (552 fraud + 490 legitimate) + 110
replay setup sends.

- Fraud stopped: **500 of 552 (90.6%)**.
- Fraud held for secondary review: **52 of 552** — all 52 held, none accepted.
- Fraud stopped or held: **552 of 552 = 100%**. Missed: **0**.
- Name fraud, exact person: **40 of 40 stopped**. Exact business: **25 of 25
  stopped**. Fuzzy variants: **52 of 52 held**.
- Legitimate with name fields: **60 of 60 accepted, 0 held**.
- False positives: **0 of 490**. Ledger: **490 entries, chain valid**.

**The demo's scope.** The claim payloads were synthetic; the identity lookup
was tested against real LEIE records. A catch rate on real claims is the next
measurement, once real claim data is available.

**Single-threaded benchmark, 21–22 November 2026.** `python3 benchmark.py`
(default 2,000 iterations; `--json` writes the results as JSON) measures core
ingress latency, edge-guardian latency, ledger append throughput, and
malformed-packet rejection. It is fail-closed without a key of at least 32
bytes, and all on-disk state lives in a temporary directory. Measured on the
build VM (shared virtual CPU, single-threaded run): core ingress about
**9,000–15,000 verifications per second** across runs (five runs each tree on
22 November: medians 12,846 public, 14,749 core); edge guardian about
**100,000–115,000**; ledger append about **15,000–30,000 writes per second**.
On the Chromebook (4 CPUs, Python 3.13.5, x86_64, 22 November 2026), five runs
in each tree: core ingress about **4,600–4,900 verifications per second**,
edge guardian about **37,000–39,000**, ledger append about **8,800–10,400
writes per second** — slower hardware, same code. Single-machine numbers that vary run to run on the shared
VM, not a production benchmark. Recorded in `BENCHMARKS.md` with the run date
and host.

**Load test, 20 November 2026.** 48 runs, 1–32 concurrent writers: **0 errors,
0% loss at every level**, ledger chain valid in every run. The earlier
concurrency failures were fixed and re-tested.
Re-run 22 November 2026 (48 runs, same matrix, shared 1.5-vCPU cell):
**0 errors, 0% loss at every level, 252,000 of 252,000 successes**; throughput
lower (6.3–25.7k/s) on the smaller machine — the fix's subject is zero loss,
and that reproduces exactly. Two further 48-run matrices the same day:
**504,000 of 504,000 successes, 0 errors, 0% loss**; throughput 4.2–26.0k/s
across both, the low end a single momentarily starved 1-thread run.
Chromebook, 22 November 2026 (4 CPUs, Python 3.13.5): a 48-run matrix in
each tree — **252,000 of 252,000 successes in each, 0 errors, 0% loss**,
chains valid; ledger-only throughput 6.3–9.3k writes per second. Across all
six post-fix matrices (20–22 November, VM and Chromebook, both trees):
**1,512,000 of 1,512,000 successes, 0 errors**.

### Value

Replacement cost of what has actually been built (not concepts) was estimated at
roughly $50,000 to $150,000, the protocol being the bulk of it, discounted for the
rework still owed. Market value is near zero pre-revenue, until a paying pilot exists.
**The work is not for sale at any price.**

## Industry bottlenecks vs what the repository fixes or replaces

The bottlenecks below are stated only as the failure modes the protocol's results
address. No external statistics are cited here.

Fraud is in the trillions and expected to grow.

- **Claims that move without proof.** Verification is an administrative afterthought,
  and an unverified value travels as if it had been proven. The protocol records
  nothing it cannot verify: a packet that cannot prove its integrity is not recorded.
- **Verification latency from probabilistic administrative layers.** Layers that
  estimate, score, or sample instead of verifying add delay and leave the answer
  uncertain. The protocol answers every packet with a verification, not an estimate:
  115,313 verifications per second at the edge, 10,593 per second at core ingress
  (Measured, 20 November 2026, 4-CPU VM, Python 3.12).
- **Assumed proxies treated as verified measurements.** An assumed proxy, used as a
  base metric, compounds downstream every time it is treated as a verified
  measurement. The protocol keeps verified, measured, specified, and open apart, and a
  specified number is never presented as a measured one.
- **State drift across systems.** State held in separate systems diverges, and no
  party can check the whole record. The protocol keeps one record that can be
  checked: a verified two stays a two.
- **Replay without detection.** A signed message can be submitted twice and counted
  twice. The protocol rejects replays: 110 of 110 replay attacks caught in the live
  demo of 20 November 2026, and 0 of 430 legitimate items wrongly stopped.
- **Fail-open defaults.** Systems that keep running on a missing, weak, or fallback
  secret. The protocol fails closed throughout: it refuses to start without a key,
  and it rejects unknown devices and malformed payloads outright.

## Threat model

What the protocol defends against.

**Defends against.** Forged signatures; replayed packets; stale and future
timestamps; excluded providers submitting claims (exact matches are stopped;
fuzzy matches are held for review, not stopped); malformed payloads and unknown
devices (rejected outright); state tampering after the fact (edits to the
record are detectable, provided the record is anchored somewhere the operator
cannot rewrite — external anchoring is not yet implemented).

## Key management

- Keys are environment-only. `SUMERAVERA_SECRET_KEY` must be set and at least
  32 bytes; the protocol refuses to start without it, and there is no fallback
  secret.

## Running it yourself

The core needs only the Python standard library (CI also installs `fastapi`,
`uvicorn`, and `pytest`). Python 3.10 is what the workflow uses. The core is fail-closed by design:
it refuses to start without a key. Set a
throwaway test-only value before running anything. Never commit a real key. Secrets
are environment-only, and the secret is to be rotated.

Try it first — one command, three outcomes: a packet accepted, a replay
rejected, a stale packet rejected.

```bash
# From the repository root. Use a throwaway test-only key, never a real one.
export SUMERAVERA_SECRET_KEY=ci-test-only-key-not-a-production-secret

# Core integration checks (3 checks: valid ingress, replay rejected, stale rejected)
python3 direct_test.py

# Full test suite (90 checks: edge guardian, Gate 1, ledger wiring, concurrency,
# watchlist, identity gates)
python3 -m pytest tests/ -q

# Standalone invariant audit
./run_audit_suite.sh python3 audit_verify_standalone.py proof_re

# Reproducible benchmark (default 2,000 iterations; --json writes the results)
python3 benchmark.py --json benchmark_results.json

# Deployment-state check (prints no secret; exits 1 on failure)
python3 core_status_audit.py
```

For the live demo — a gateway with 1,152 labeled packets through it — see
[demo/](demo/). For the concurrent-writer load test, see [load-test/](load-test/).

## Running it in a container

```bash
# From the repository root. Build the image (no secret is baked in).
docker build -t sumeravera .

# Run it. The service refuses to start without a key of at least 32 bytes;
# use a throwaway test-only value, never a real one.
docker run --rm -p 8000:8000 \
  -e SUMERAVERA_SECRET_KEY=ci-test-only-key-not-a-production-secret \
  sumeravera

# In another terminal: the service answers GET / with its status.
curl http://127.0.0.1:8000/
```

The container runs the protocol's own service (`GET /`, `POST /verify`) as a
non-root user on Python 3.12-slim, with `fastapi` and `uvicorn` pinned in
`requirements.txt`. State is written into `/app` inside the container.
Identity screening is off until the LEIE-derived watchlist files are provided —
mount them and set `SUMERAVERA_WATCHLIST_PATH` and
`SUMERAVERA_WATCHLIST_NAMES_PATH` (see WATCHLIST.md).

## Repository layout

```
sumeravera-protocol/
├── demo/                  # live demo: gateway, traffic generator, results
├── load-test/             # concurrent-writer load test (48-run matrix)
├── tests/                 # 90 tests
├── systemd/               # monthly watchlist refresh service + timer
├── sumeravera_core.py
├── gate1_ingress.py
├── edge_guardian.py
├── edge_socket.py
├── gates.py
├── watchlist.py
├── refresh_watchlist.py
├── local_ledger.py
├── benchmark.py
├── direct_test.py
├── audit_verify_standalone.py
├── run_audit_suite.sh
├── run_core_verification.py
├── test_runner.py
├── hardware_ingress.py
├── ingress.py
├── protocol_gateway.py
├── svp_gateway.py
├── SumerAvera.tla
├── Dockerfile
├── requirements.txt
├── BENCHMARKS.md
├── GATES.md
├── WATCHLIST.md
├── VERIFICATION.md
├── SECURITY.md
└── VERSION
```

## Security

- Report suspected vulnerabilities through GitHub Issues on this repository
  (see Open items for the contact route). Do not include a live secret in a
  report.

## Honest limits

- The private core is fixed and tested (90 of 90, 13 of 13 audit checks, CI run
  #69 green), but it still has no public deployment and no real-claims data.
- The gateway routes live traffic (accepted, held, and quarantined outcomes); there are no honeypot decoys in the repositories — quarantine is rejection, not deception.
- The gateway serves live verification and ledger state. The separate AI Studio
  console app still serves simulated state; it is not this repository.
- A restart can reopen the replay window at the edge layer; the core's record survives a restart.
- Some repository documents have not been reconciled with the fixed code
  (`VERIFICATION.md` states figures the audited model-check run does not support; this
  README cites the audited figures and does not repeat the others).
- Paws Connect removal from the public repository is still outstanding.
- The protocol verifies packet integrity, not claim truth. Identity screening
  now runs in the protocol: exact matching by NPI or name covers
  about 80,000 of 84,224 LEIE rows; fuzzy matches are held, not excluded.
- The ledger is not anchored externally; an operator with write access to the ledger could rewrite the record end to end.
- Key rotation and provisioning are not implemented.
- The live demo ran on a single virtual machine. There is no public demo URL and
  no deployment; the demo's claim payloads were synthetic, so no catch rate on
  real claims has been measured.

## License

The license is the **SumerAvera Perpetual Edge Node License (v1.0)**:
Copyright (c) 2026 John Jamie Rodriguez. Each running instance is granted a perpetual,
non-exclusive, non-transferable license upon payment of a one-time fee of **$5.00 USD
per node**. No central telemetry, no phone-home verification, no recurring subscriptions.
One license covers one physical machine, container, or vehicle edge unit. The license
cannot be remotely deactivated, modified, or expired once deployed. The software is
provided "AS IS", without warranty of any kind.

This license is not an OSI-approved open source license. The source is visible
for inspection; commercial use, service, and results are paid.

## Open items

The demonstrated use is healthcare claims: screening providers against LEIE.
The mechanism — deterministic verification that a fact stays a fact — is not
limited to that domain in principle, but no other use has been demonstrated or
measured.

Reach the project through GitHub Issues on this repository for technical discussion,
and the Omniotica page as the meeting place.

---

*SumerAvera Protocol — public repository. State as of 24 November 2026, public
head `aef05ba`, core head `5afcfa77`, version 2.5.0 in both. The truth is ours.*
