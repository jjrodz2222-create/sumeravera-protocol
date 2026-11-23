# SumerAvera v2.5.0 — concurrent-writer load test

Date: 2026-11-20. Code under test: the repository root
(HEAD 79f36f9, version 2.5.0).
Core tree spot-checked: the four modules under test are byte-identical to
public, and the core spot runs reproduce the same curve.
Environment: this VM, Linux x86_64, Python 3.12.3, 4 CPUs.
Test key: throwaway 32-byte key via env var only. All DBs in fresh temp dirs.

## Method

`loadtest.py` drives the REAL verify path (Gate 1 / `verify_ingress_packet` +
ledger append), N writer threads x 500 verified ingresses each, all threads
released together by a barrier. Four modes:

- `gate1-shared` — one Gate1 + one shared ledger connection (the code as a
  threaded server would run it).
- `gate1-perthread` — each thread opens its own ledger connection to the same
  file DB + its own Gate1.
- `core-nonce` — `sumeravera_core.verify_ingress_packet(ledger_conn=None)`,
  the module-global nonce connection (shared, `check_same_thread=False`,
  default 5 s busy timeout, no WAL mode on the nonce DB).
- `ledger-only` — direct `local_ledger.append_state_entry`, per-thread
  connections to the same file DB (isolates ledger appends).

Each level ran twice. Reproduce with:
`bash run_matrix.sh` (48 runs, ~2 min) then `python analyze.py results.jsonl`.

## Results (success / attempts, throughput, p50/p95/p99 ms of successful ops)

### gate1-shared — 0% success at every level
| thr | rep1 | rep2 | errors |
|-----|------|------|--------|
| 1–32 | 0/500 … 0/16000 | same | ProgrammingError 100%: "SQLite objects created in a thread can only be used in that same thread" |

A shared `local_ledger` connection cannot be used from ANY thread other than
its creator — even a single worker thread fails 500/500. Chain "valid" is
vacuous (0 rows). This is the code as a threaded server would run it.

### gate1-perthread
| thr | rep1 | rep2 | thrpt/s | p50 | p95 | p99 | errors |
|-----|------|------|---------|-----|-----|-----|--------|
| 1 | 500/500 | 500/500 | 18.7k / 17.1k | 0.044 | 0.07–0.08 | 0.12–0.28 | 0 |
| 2 | 998/1000 | 999/1000 | 13.5k / 14.9k | 0.044–0.048 | 0.11–0.12 | 0.21 | IntegrityError 1–2 |
| 4 | 1990/2000 | 1955/2000 | 12.2k / 11.6k | 0.046–0.051 | 0.21–0.23 | 0.35–0.44 | IntegrityError 10–45 |
| 8 | 3863/4000 | 3964/4000 | 11.3k / 10.0k | 0.045–0.049 | 0.22 | 0.43–0.51 | IntegrityError 36–137 |
| 16 | 7422/8000 | SETUP-FAIL | 10.0k | 0.054 | 0.22 | 0.48 | IntegrityError 578 |
| 32 | 13897/16000 | SETUP-FAIL | 9.5k | 0.055 | 0.24 | 0.60 | IntegrityError 2103 (13.1%) |

Chain valid in every completed run. All errors are one type:
`IntegrityError: UNIQUE constraint failed: state_ledger.sequence_id` — the
SELECT-max-then-INSERT race in `append_state_entry`.

### core-nonce (nonce-store writes alone)
| thr | rep1 | rep2 | thrpt/s | p50 | p95 | p99 | errors |
|-----|------|------|---------|-----|-----|-----|--------|
| 1 | 500/500 | 500/500 | 10.3k / 9.7k | 0.08 | 0.14–0.17 | 0.25 | 0 |
| 2 | 656/1000 | 773/1000 | 6.4k / 5.7k | 0.14 | 0.34–0.44 | 0.54–1.83 | 226–344 |
| 4 | 1180/2000 | 1237/2000 | 5.8k / 6.0k | 0.28–0.31 | 0.89–0.90 | 2.1–2.2 | 762–819 |
| 8 | 2762/4000 | 2271/4000 | 5.4k / 3.8k | 0.50–1.07 | 2.5–3.0 | 8.2–15.6 | 1233–1727 |
| 16 | 4683/8000 | 4357/8000 | 3.4k / 3.5k | 2.1–2.2 | 4.9–8.4 | 23.8–24.9 | 3315–3641 |
| 32 | 8678/16000 | 9238/16000 | 3.5k / 3.6k | 4.0–4.2 | 21–22 | 32–35 | 6753–7316 |

Error mix (same families at every level ≥ 2 threads): InterfaceError
("bad parameter or other API misuse"), SystemError ("error return without
exception set"), OperationalError ("cannot commit/rollback — no transaction
is active", "cannot start a transaction within a transaction"),
DatabaseError ("no more rows available", "not an error"). "database is
locked" essentially never appears — the 5 s busy timeout (sqlite3 default;
the code sets no timeout) is not the bottleneck. The shared connection's
transaction state gets interleaved across threads.
Nonce-row count ≠ success count, in BOTH directions (e.g. 2 threads:
664 rows vs 656 successes; 4 threads: 1097 rows vs 1180 successes):
nonces are sometimes recorded for failed ops and sometimes lost for
verified ops — a replay hole in one direction, false replay rejections
in the other.

### ledger-only (ledger appends alone)
| thr | rep1 | rep2 | thrpt/s | p50 | p95 | p99 | errors |
|-----|------|------|---------|-----|-----|-----|--------|
| 1 | 500/500 | 500/500 | 26.3k / 25.9k | 0.031 | 0.05 | 0.07–0.08 | 0 |
| 2 | 997/1000 | 996/1000 | 22.7k / 20.1k | 0.030–0.031 | 0.05 | 0.08–0.09 | IntegrityError 3–4 |
| 4 | 1982/2000 | 1976/2000 | 22.2k / 19.4k | 0.029–0.030 | 0.05–0.06 | 0.08–0.09 | IntegrityError 18–24 |
| 8 | 3963/4000 | 3975/4000 | 15.3k / 22.7k | 0.030 | 0.06 | 0.09–0.11 | IntegrityError 25–37 |
| 16 | 7862/8000 | SETUP-FAIL | 15.3k | 0.031 | 0.07 | 0.13 | IntegrityError 138 |
| 32 | 15240/16000 | 15202/16000 | 19.8k / 19.7k | 0.032 | 0.07 | 0.14–0.17 | IntegrityError 760–798 (4.8%) |

Latency stays flat at every level; throughput stays 15–26k/s. The ONLY
failure is the duplicate-`sequence_id` race. Chain valid in every
completed run.

## Saturation curve

- The nonce path saturates immediately: peak throughput is at 1 thread
  (~10k/s, 0 errors); at 2 threads errors are already 23–34% and
  throughput falls; by 8 threads p99 is 8–16 ms and ~40% of writes fail;
  at 32 threads ~45% fail and p99 is 32–35 ms. Adding threads never helps.
- Gate 1 as wired (shared ledger connection) has no curve at all: 0%
  success from 1 thread up.
- Gate 1 with per-thread connections: throughput peaks at 1 thread
  (~18k/s) and declines to ~9.5k/s at 32 threads while the loss rate
  climbs 0% → 13%. Latency of successful ops stays low (p50 ~0.05 ms);
  the failure is lost writes, not slowness.
- Ledger alone: throughput 26k/s at 1 thread, 15–22k/s beyond; loss rate
  0% → 4.8% at 32 threads; latency flat.

## What breaks first and why

1. **Shared sqlite3 connections break first — and completely.** The
   ledger connection (`local_ledger.get_connection`, no
   `check_same_thread=False`) refuses any cross-thread use: Gate 1 with a
   shared ledger connection fails 100% of the time, even with one worker
   thread. The nonce connection (`sumeravera_core`, `check_same_thread=
   False`) permits cross-thread use but corrupts: concurrent use
   interleaves transaction state (InterfaceError / SystemError /
   "cannot commit — no transaction is active"), failing ~30% of writes
   at just 2 threads. The flag disables the thread check; it does not
   make the connection thread-safe.
2. **Second: the ledger's SELECT-max-then-INSERT race.** Two threads read
   the same max `sequence_id` and both try to insert the next one; the
   loser gets `IntegrityError: UNIQUE constraint failed:
   state_ledger.sequence_id`. Rate grows with concurrency (ledger-only:
   0.3% at 2 threads → 4.8% at 32; Gate 1: 0.2% → 13.1%). Failed
   appends are atomic — the chain stays valid — but the packet is lost:
   the guardian already consumed its nonce, so a retry with the same
   nonce would be quarantined as a replay.
3. **The guardian never breaks.** Its nonce cache is an in-memory
   OrderedDict; under unique nonces it produced no errors at any level.
   (Cross-thread replay of the SAME nonce was not tested — the
   check-then-insert in `verify_edge_ingress` is not atomic, so a shared
   guardian could admit a duplicate; per-thread guardians sidestep it.)
4. **WAL / checkpointing.** No checkpoint configuration exists. The WAL
   file grows to exactly 1000 frames + header (~4.1 MB, the SQLite
   default 1000-page auto-checkpoint threshold) and stays there; content
   is checkpointed passively, the file is never truncated during a run.
   A clean close of the last connection checkpoints and deletes the WAL
   (verified: 0 bytes after an owning-thread close). Per-thread
   connections could not be closed from the main thread (same
   thread-affinity ProgrammingError, verified separately), so their WAL
   files were still ~4.1 MB at measurement — a harness artifact, not a
   code defect.

## Setup artifacts (3 of 48 runs)

In `gate1-perthread` 16 rep 1, `gate1-perthread` 32 rep 2, and
`ledger-only` 16 rep 2, one thread hit `OperationalError: database is
locked` during concurrent schema initialization, the start barrier broke,
and the run recorded 0 successes. That is a harness-setup race (16–32
threads creating the schema on the same file at once), not steady-state
behavior — but it also shows concurrent first-use of one DB file is
itself fragile.

## Core-tree spot check (same code, byte-identical modules)

- core-nonce 2 threads: 734/1000 (public: 656–773/1000), same error families.
- core-nonce 8 threads: 2319/4000 (public: 2271–2762/4000), same error families.
- gate1-perthread 8 threads: 3844/4000, 156 IntegrityErrors (public:
  3863–3964/4000, 36–137). Same curve.

## Fix the results point to (recommendation only — nothing implemented)

1. Never share one sqlite3 connection across threads. Per-thread
   connections (or a pool) for BOTH the nonce DB and the ledger. This
   alone fixes the 100% Gate 1 failure and the nonce-store corruption.
2. Enable WAL mode on the nonce DB too (ledger already has it), so
   concurrent writer connections serialize on the write lock instead of
   hitting rollback-journal locking.
3. Make ledger sequence assignment atomic: hold one write transaction
   (BEGIN IMMEDIATE) across SELECT-max + INSERT, or let SQLite assign
   the id (INSERT without an explicit sequence_id, then lastrowid) and
   compute prev_hash inside the same transaction — and retry on busy.
   A single-writer thread + queue is the equivalent structural fix and
   also gives deterministic ordering.
4. Set an explicit WAL auto-checkpoint / periodic checkpoint so the WAL
   file is bounded by policy, not by SQLite's default.
5. Note for deployment: the FastAPI `/verify` endpoint runs
   `verify_ingress_packet` on the async event loop (one thread), so a
   single-worker server would not hit the shared-connection corruption —
   but any threaded caller, worker pool, or second process will. The fix
   belongs in the code, not in the deployment shape.

## After the fix (2026-11-20, same harness, same matrix)

All four fixes were implemented in both repos (public + core, version
still 2.5.0): per-thread connections for the nonce DB
(`sumeravera_core._get_nonce_conn`, `threading.local`) and the ledger
(`sumeravera_core.get_ledger_connection`, `Gate1(ledger_db_path=...)`);
WAL mode + `wal_autocheckpoint = 1000` + `busy_timeout = 5000` on both
DBs; ledger sequence assignment inside one `BEGIN IMMEDIATE` write
transaction with bounded retry on busy; connection setup itself retries
on busy (the journal-mode change can collide when threads open
connections at once). The harness was adapted: `gate1-shared` now means
one Gate1 built with `ledger_db_path` shared across threads (the old
shared-connection form is obsolete — no shared-connection API remains
in the gate path); schema is initialized once in the main thread before
workers start; the `core-nonce` row check opens its own connection
(`sumeravera_core.conn` no longer exists).

Full matrix re-run (48 runs, 2 reps per level, same 500/thread):
**0 errors in all 48 runs, 0% loss at every level, chain valid in every
ledger run, ledger rows == successes and nonce rows == successes in
every run, WAL 0 bytes after close in every run.**

| mode | thr 1 | thr 2 | thr 4 | thr 8 | thr 16 | thr 32 |
|------|-------|-------|-------|-------|--------|--------|
| gate1-shared (thrpt/s, rep range) | 15.3–19.4k | 16.9–17.0k | 15.2–16.2k | 14.6–17.4k | 13.9–16.6k | 14.3–15.4k |
| gate1-perthread | 10.6–20.2k | 16.0–16.7k | 14.7–18.6k | 16.7–17.7k | 16.3–17.2k | 14.1–14.3k |
| core-nonce | 22.5–23.9k | 16.2–16.8k | 18.7–18.8k | 18.6–21.1k | 16.0–21.0k | 20.2–21.6k |
| ledger-only | 27.0k | 27.0–27.1k | 19.8–20.3k | 15.9–20.0k | 11.7–17.4k | 13.8–14.9k |

Before/after (worst loss at each level, all modes): before 0% → 45%
(nonce) / 13.1% (Gate 1) / 4.8% (ledger) at 32 threads; after 0% at
every level. Throughput no longer declines with concurrency in any
mode — the curve is flat at 10–27k/s from 1 to 32 threads, so there is
no saturation point inside the tested range on this 4-CPU VM. p50
latency stays ~0.03–0.05 ms at all levels; p99 grows with contention
(3 ms at 8 threads, 8 ms at 16, ~33 ms at 32) — that is lock-wait
serialization (BEGIN IMMEDIATE + busy retry), not lost work. Core-tree
spot check (gate1-shared, core-nonce, ledger-only at 8 and 32 threads):
0 errors, chains valid, rows match — same curve.

Results: `results-before.jsonl` (the pre-fix matrix), `results.jsonl`
(the post-fix matrix).

## Files

- `loadtest.py` — single-run harness (mode, threads, iters, workdir, tree).
- `run_matrix.sh` — full matrix driver (48 runs, ~2 min).
- `analyze.py` — summarizes `results.jsonl` into the table above.
- `results.jsonl` — raw JSON, one line per run.
- `REPORT.md` — this file.
