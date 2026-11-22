#!/usr/bin/env python3
"""SumerAvera identity gates -- Gate 2 (exact) and Gate 3 (fuzzy).

Gate 1 (gate1_ingress.py / sumeravera_core.py) verifies that a packet
is REAL: signature, replay, timestamp. Gates 2 and 3 ask the next
question: is the PROVIDER named in the claim excluded from billing?
Both run after integrity verification and before anything is recorded.

Verdicts (see GATES.md):

  * CLEAR    -- no identity match. The packet proceeds on its
    integrity merits.
  * EXCLUDED -- an exact identity match (Gate 2). The provider IS
    excluded; the packet is rejected outright and never reaches the
    ledger, and on the HTTP path it does not consume its nonce.
  * REVIEW   -- a near-match (Gate 3) or an exact name with a
    mismatched ZIP (Gate 2). The packet is HELD for secondary review:
    HTTP 202 / Gate 1 REBALANCING, no ledger entry, nonce not
    consumed on the HTTP path. REVIEW counts as NOT verified.

Gate 2 -- exact identity (watchlist.Watchlist.screen_exact)
-----------------------------------------------------------
NPI, (LASTNAME, FIRSTNAME, DOB), or (BUSNAME, STATE), all normalized
by watchlist.py. One special case returns REVIEW instead of EXCLUDED:
the 3-field person key matches but the claim's ZIP differs from every
LEIE ZIP for that key (same name and birth date, different address).

Gate 3 -- fuzzy identity (this module, deterministic rules only)
-----------------------------------------------------------------
Fuzzy NEVER excludes -- REVIEW only. Every rule is a documented,
deterministic comparison on normalized fields; there is no scoring
model, no learned threshold, and no external data. The rules:

  F1 -- LASTNAME+FIRSTNAME exact, DOB differs in exactly one digit
        (a single-digit typo in the birth date).
  F2 -- LASTNAME+DOB exact, and the FIRSTNAME is a prefix (2+ chars)
        of the listed first name or vice versa, or the first initial
        matches while the rest differs.
  F3 -- FIRSTNAME+DOB exact, and the LASTNAME has a difflib ratio
        >= 0.85 against a listed last name (and is not exact -- an
        exact last name was already Gate 2).
  F4 -- STATE exact, and the normalized BUSNAME has a difflib ratio
        >= 0.85 against a listed business name in that state (and is
        not exact).

Performance: fuzzy is blocked, never a full scan. Rules F1-F3 look up
candidates by DOB (watchlist.candidates_by_dob); rule F4 looks up
candidates by STATE (watchlist.candidates_by_state). A DOB or a state
holds only a handful of listed names, so each check touches a few
candidates. Fuzzy runs only after Gate 2 is CLEAR, and only when the
claim carries identity fields at all -- a claim with no identity
fields is CLEAR without any list lookup.

Why REVIEW and not EXCLUDED: a near-match can be a typo by the
excluded provider, or a different person who happens to share a name
and a near-identical birth date. The protocol cannot tell those
apart, so it holds the packet and lets a human (or a downstream
review queue) decide. A false REVIEW costs a review; a false
EXCLUDED would silently drop a legitimate claim.
"""

import difflib
from typing import NamedTuple, Optional

from watchlist import extract_provider_identity, get_default_watchlist

FUZZY_LASTNAME_RATIO = 0.85
FUZZY_BUSNAME_RATIO = 0.85
MIN_PREFIX_CHARS = 2


class ScreeningResult(NamedTuple):
    """One identity-screening decision.

    ``verdict`` is "CLEAR", "EXCLUDED", or "REVIEW"; ``reason`` is a
    short machine-readable string naming the rule that fired
    ("npi_excluded", "name_exact", "fuzzy_dob_typo", ...). ``verified``
    is True only for CLEAR -- EXCLUDED and REVIEW both count as not
    verified, so a held or rejected packet never enters the ledger.
    """

    verdict: str
    reason: str

    @property
    def verified(self) -> bool:
        return self.verdict == "CLEAR"


def _one_digit_variants(dob: str):
    """All 8-digit strings at Hamming distance exactly 1 from ``dob``.

    8 positions x 9 alternative digits = 72 variants. Used by F1 so
    the check is 72 blocked dict lookups, never a scan.
    """
    for i, ch in enumerate(dob):
        for d in "0123456789":
            if d != ch:
                yield dob[:i] + d + dob[i + 1:]


def _fuzzy_screen(identity: dict, wl) -> ScreeningResult:
    """Gate 3 rules F1-F4, in order. First hit wins. REVIEW only."""
    ln = identity.get("lastname")
    fn = identity.get("firstname")
    dob = identity.get("dob")
    bn = identity.get("busname")
    st = identity.get("state")

    # F1: name exact, DOB one digit off.
    if ln and fn and dob:
        for variant in _one_digit_variants(dob):
            if (ln, fn) in wl.candidates_by_dob(variant):
                return ScreeningResult("REVIEW", "fuzzy_dob_typo")

    # F2/F3: candidates sharing the payload DOB.
    if dob:
        for cln, cfn in wl.candidates_by_dob(dob):
            # F2: last name + DOB exact; first name a prefix (2+ chars)
            # either way, or first initial matches while the rest differs.
            if ln and fn and cln == ln and cfn != fn:
                if len(fn) >= MIN_PREFIX_CHARS and cfn.startswith(fn):
                    return ScreeningResult("REVIEW", "fuzzy_firstname_prefix")
                if len(cfn) >= MIN_PREFIX_CHARS and fn.startswith(cfn):
                    return ScreeningResult("REVIEW", "fuzzy_firstname_prefix")
                if fn[0] == cfn[0]:
                    return ScreeningResult("REVIEW", "fuzzy_firstname_initial")
            # F3: first name + DOB exact; last name similar, not exact.
            if fn and ln and cfn == fn and cln != ln:
                ratio = difflib.SequenceMatcher(None, ln, cln).ratio()
                if ratio >= FUZZY_LASTNAME_RATIO:
                    return ScreeningResult("REVIEW", "fuzzy_lastname_similar")

    # F4: state exact; business name similar, not exact.
    if bn and st:
        for cbn in wl.candidates_by_state(st):
            if cbn == bn:
                continue  # exact -- Gate 2 already handled it
            ratio = difflib.SequenceMatcher(None, bn, cbn).ratio()
            if ratio >= FUZZY_BUSNAME_RATIO:
                return ScreeningResult("REVIEW", "fuzzy_busname_similar")

    return ScreeningResult("CLEAR", "clear")


def screen_identity(payload: bytes, watchlist=None) -> ScreeningResult:
    """Screen one claim payload's provider identity (Gates 2 and 3).

    ``watchlist`` is a watchlist.Watchlist instance; None means "use
    the process default" (SUMERAVERA_WATCHLIST_PATH /
    SUMERAVERA_WATCHLIST_NAMES_PATH or watchlist.txt /
    watchlist-names.txt in the working directory, else screening off).
    Pass watchlist.Watchlist.disabled() to force screening off.

    Order: Gate 2 exact first (EXCLUDED wins outright); then Gate 3
    fuzzy (REVIEW only); otherwise CLEAR. A claim with no identity
    fields is CLEAR -- it is simply not screened. Never raises on a
    malformed payload; a non-JSON payload has no identity fields.
    """
    wl = watchlist if watchlist is not None else get_default_watchlist()
    if not wl.screening_enabled:
        return ScreeningResult("CLEAR", "screening_off")
    identity = extract_provider_identity(payload)
    verdict, reason = wl.screen_exact(identity)
    if verdict == "EXCLUDED":
        return ScreeningResult("EXCLUDED", reason)
    if verdict == "REVIEW":
        return ScreeningResult("REVIEW", reason)
    return _fuzzy_screen(identity, wl)
