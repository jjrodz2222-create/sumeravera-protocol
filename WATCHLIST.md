# Excluded-provider watchlist

The protocol verifies that a packet is **real** (signature / replay /
timestamp). The watchlist answers a different question: is the
**provider named in the claim excluded from billing**? The 2026-11-20
live demo showed why both are needed -- a properly signed, fresh claim
from an excluded provider sailed through Gate 1 as STABLE, and only
the demo-layer LEIE flag caught it. With this step in the protocol,
that claim is quarantined on both ingress paths.

## What it is

- Source: the HHS-OIG List of Excluded Individuals/Entities (LEIE),
  the official monthly exclusion list.
- Two files, built together by `refresh_watchlist.py` (see below):
  - `watchlist.txt` -- one NPI per line, `#` comments and blank
    lines ignored.
  - `watchlist-names.txt` -- one name key per line:
    `P|LASTNAME|FIRSTNAME|DOB|ZIP` (ZIP may be empty) for people,
    `B|BUSNAME|STATE` for businesses.
- Coverage (2026-11-20 download, 84,224 LEIE rows): **8,844 distinct
  NPIs** in `watchlist.txt`; **~70,700 person keys and ~2,800
  business keys** in `watchlist-names.txt`. NPI-only matching covered
  9,023 rows; name matching covers the ~75,000 rows that carry no
  NPI. A claim with no provider identity in its payload is simply
  not screened.
- The full LEIE extract is **not** committed to a repo, and neither
  are the generated `watchlist.txt` / `watchlist-names.txt` -- they
  are built at deploy time by `refresh_watchlist.py`. Only the loader
  (`watchlist.py`), the gates (`gates.py`), this doc, `GATES.md`, and
  small synthetic samples for tests (`tests/data/watchlist_sample.txt`,
  `tests/data/watchlist_names_sample.txt`) live in the repo.
- Normalization (one definition, in `watchlist.py`, shared by the
  builder and the screen): names upper-cased, periods/commas
  stripped, whitespace collapsed; DOBs 8 digits YYYYMMDD; ZIPs first
  5 digits; business names additionally lose trailing legal suffixes
  (INC, LLC, CORP, LTD, CO) and punctuation.

## How it is used

Gates 2 and 3 (see `GATES.md`) run after signature verification and
before the packet is recorded anywhere:

- Gate 2 exact match -- `POST /verify` returns 401, Gate 1 returns
  QUARANTINE (403) with reason `identity_excluded`. Nothing is
  written to the ledger.
- Gate 3 near-match -- `POST /verify` returns 202 ("held for
  secondary review"), Gate 1 returns REBALANCING (202) with reason
  `identity_review`. Nothing is written to the ledger.
- A packet rejected or held for identity on the HTTP path does **not**
  consume its nonce (like a bad signature), so it can be re-presented
  if the provider leaves the list or the review clears it. On the
  Gate 1 path the guardian consumes the nonce during verification
  before the identity check runs; the packet is still quarantined or
  held and never reaches the ledger.
- **Fail-open for identity, fail-closed for integrity.** When no list
  file is configured, screening is OFF and verification behaves
  exactly as before. A list file that cannot be read, or that loads
  zero entries, also disables screening with a warning on stderr --
  it never raises and never blocks a packet.

## Configuration

`SUMERAVERA_WATCHLIST_PATH` (a file path) wins for the NPI list;
`SUMERAVERA_WATCHLIST_NAMES_PATH` wins for the name index. Otherwise
`watchlist.txt` / `watchlist-names.txt` in the process working
directory are used when they exist. No env var and no file means
screening is off. The two paths resolve independently, so one
component can be on while the other is off.

## Refresh (monthly -- OIG updates LEIE monthly)

```sh
python3 refresh_watchlist.py            # downloads the official CSV
python3 refresh_watchlist.py --csv path/to/UPDATED.csv --out watchlist.txt
```

Both files are written in the same run (`--names-out` defaults to
`watchlist-names.txt` next to `--out`). The script writes atomically
(temp file + rename) and refuses to write an empty list. A refresh
takes effect **without a process restart**: the default watchlist
re-stats both list files on every call and reloads when one changes
(mtime + size, checked lock-free, re-checked under the lock -- see
`watchlist.get_default_watchlist`).

## Monthly job (systemd)

`systemd/sumeravera-watchlist-refresh.service` and
`systemd/sumeravera-watchlist-refresh.timer` run the refresh once a
month (`OnCalendar=monthly`, `Persistent=true`, so a missed run fires
on the next boot). They are **delivered, not installed** -- install
them on the deployment host:

```sh
# 1. Edit the three paths in the .service file to the install
#    directory (WorkingDirectory, the two Environment= paths,
#    ExecStart), and set User= if the gateway runs as a service
#    account.
sudo cp systemd/sumeravera-watchlist-refresh.service \
        systemd/sumeravera-watchlist-refresh.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sumeravera-watchlist-refresh.timer

# 2. Check it.
systemctl list-timers sumeravera-watchlist-refresh.timer
systemctl status sumeravera-watchlist-refresh.service
journalctl -u sumeravera-watchlist-refresh.service
```

A manual run does the same thing (`python3 refresh_watchlist.py`)
and is the right check after editing the paths: it prints the counts
it wrote for both files.
