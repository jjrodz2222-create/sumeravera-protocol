# SumerAvera ingress gates

Three gates, in order, on both ingress paths (`POST /verify` and
`/ws/ingress` via Gate 1). A packet must clear each gate in turn; a
gate that stops it ends the journey there.

## Gate 1 -- ingress integrity

What it checks: the packet is REAL. HMAC-SHA256 signature over the
canonical `nonce:timestamp:payload` frame, replay rejection (nonce
store), timestamp within 65s past / 5s future of now. Fail-closed
without a provisioned secret (>= 32 bytes).

Where it lives: `edge_guardian.py` (EdgeTelemetryGuardian) for the
socket path; the same bounds and checks in `sumeravera_core.py` for
the HTTP path. Both paths share the check order; see
`sumeravera_core._screen_ingress_packet`.

Tiers: STABLE (200, fresh <= 5s), REBALANCING (202, drifted 5-65s),
QUARANTINE (403, integrity failure). STABLE and drifted REBALANCING
are appended to the hash-chained state ledger; QUARANTINE is not.

## Gate 2 -- exact identity

What it checks: the PROVIDER named in the claim is excluded from
billing, by exact match against the HHS-OIG LEIE (see WATCHLIST.md).
Runs after signature verification and before the nonce is recorded,
so an excluded packet never consumes a nonce and never reaches the
ledger.

Exact keys (all normalized by `watchlist.py`):

  * NPI -- `provider_npi` in the claim.
  * Person -- (`provider_lastname`, `provider_firstname`,
    `provider_dob`), with a ZIP rule: when the claim also carries
    `provider_zip`, the 4-field key must match; when the 3-field key
    matches but the claim's ZIP differs from every LEIE ZIP for that
    key, the packet is NOT excluded -- it goes to Gate 3 as REVIEW
    (same name and birth date, different address). When the LEIE
    rows for the key carry no ZIP, there is nothing to contradict the
    claim and the 3-field match excludes.
  * Business -- (`provider_busname`, `provider_state`), with legal
    suffixes (INC, LLC, CORP, LTD, CO) and punctuation stripped.

Verdict: EXCLUDED. `POST /verify` returns 401; Gate 1 returns
QUARANTINE (403), reason `identity_excluded`. A claim with no
identity fields at all is not screened -- it proceeds on its
integrity merits.

## Gate 3 -- fuzzy identity (secondary review)

What it checks: NEAR-matches against the LEIE name index, by
deterministic rules only (see `gates.py`). Fuzzy NEVER excludes --
REVIEW only.

  * F1 -- LASTNAME+FIRSTNAME exact, DOB differs in exactly one digit.
  * F2 -- LASTNAME+DOB exact, and FIRSTNAME is a prefix (2+ chars)
    of the listed first name or vice versa, or the first initial
    matches while the rest differs.
  * F3 -- FIRSTNAME+DOB exact, and LASTNAME has a difflib ratio
    >= 0.85 against a listed last name (and is not exact).
  * F4 -- STATE exact, and the normalized BUSNAME has a difflib
    ratio >= 0.85 against a listed business name in that state (and
    is not exact).

Performance: fuzzy is blocked, never a full scan. Rules F1-F3 look up
candidates by DOB; F4 looks up candidates by STATE. A DOB or a state
holds only a handful of listed names. Fuzzy runs only after Gate 2
is CLEAR, and only when the claim carries identity fields.

Verdict: REVIEW. `POST /verify` returns 202 ("held for secondary
review"); Gate 1 returns REBALANCING (202), action
`HELD_FOR_REVIEW`, reason `identity_review`. A held packet is NOT
appended to the ledger on either path -- unlike drifted REBALANCING,
which is staged and recorded. REVIEW counts as NOT verified, so
`verify_ingress_packet` returns False for it.

## Verdicts and tier mapping

| Verdict  | Meaning | POST /verify | Gate 1 |
|---|---|---|---|
| CLEAR    | No identity match (or screening off) | 200 + ledger entry | STABLE / REBALANCING by drift, ledger entry |
| EXCLUDED | Exact identity match, or integrity failure (reason says which) | 401 | QUARANTINE (403) |
| REVIEW   | Near-match held for secondary review | 202, no ledger entry | REBALANCING (202), no ledger entry |

EXCLUDED covers both identity exclusion and integrity failure; the
reason string distinguishes them (`npi_excluded`, `name_exact`,
`bad_signature`, `replay`, `stale_timestamp`, ...). REVIEW reasons
are `fuzzy_dob_typo`, `fuzzy_firstname_prefix`,
`fuzzy_firstname_initial`, `fuzzy_lastname_similar`,
`fuzzy_busname_similar`, and `name_zip_mismatch`.

## Design rules

  * Identity never weakens integrity. Gates 2 and 3 run after
    signature verification; a packet that fails Gate 1 never reaches
    them.
  * Fuzzy never excludes. A near-match can be a typo by the excluded
    provider or a different person who happens to share a name and a
    near-identical birth date. The protocol cannot tell those apart,
    so it holds the packet for a human (or a downstream review queue)
    instead of silently dropping a legitimate claim.
  * Unconfigured = screening off. With no list files, Gates 2 and 3
    are no-ops and the protocol behaves exactly as before (fail-open
    for identity, fail-closed for integrity).
  * One source of truth for the check order.
    `sumeravera_core._screen_ingress_packet` runs the full sequence
    (window -> key -> HMAC -> identity -> replay -> ledger);
    `verify_ingress_packet` (boolean) and `screen_ingress_packet`
    (verdict) are thin wrappers over it, so the two can never drift
    apart. `screen_ingress_packet` lives in `sumeravera_core.py`
    rather than `gates.py` because it needs the HMAC/nonce/ledger
    primitives that live there; `gates.py` holds only the
    identity-screening verdicts (Gate 2 exact via
    `watchlist.screen_exact`, Gate 3 fuzzy).
  * A held packet never enters the verified ledger. REVIEW is
    verified=False on both paths, including Gate 1's REBALANCING
    tier for REVIEW (which records no ledger entry, unlike drifted
    REBALANCING). One ordering consequence remains on the Gate 1
    path: the guardian consumes the nonce during verification before
    the identity check runs, so a held or quarantined packet's nonce
    IS consumed there (unlike POST /verify). The packet still never
    reaches the ledger either way.
