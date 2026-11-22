#!/usr/bin/env python3
"""SumerAvera identity screening -- excluded-provider watchlist.

What this is
------------
An ADDITIVE check on top of packet-integrity verification. The protocol
verifies that a packet is real (signature / replay / timestamp); this
module answers a different question -- is the provider named in the
claim excluded from billing? The source list is the HHS-OIG List of
Excluded Individuals/Entities (LEIE), refreshed monthly (see
refresh_watchlist.py and WATCHLIST.md).

Two gates share this list (see GATES.md):

  * Gate 2 -- exact identity. An exact NPI match, an exact
    (LASTNAME, FIRSTNAME, DOB) match, or an exact (BUSNAME, STATE)
    match means the provider IS excluded. Runs after signature
    verification and before the nonce is recorded, so an excluded
    packet never consumes a nonce and never reaches the ledger.
  * Gate 3 -- fuzzy identity (gates.py). Near-matches never exclude;
    they hold the packet for secondary review (REBALANCING / HTTP 202).

Design rules, settled 2026-11-20 and extended 2026-11-21:

  * Identity screening NEVER weakens an integrity check. It runs after
    signature verification, and a packet rejected here is rejected
    outright -- it is never recorded in the ledger.
  * Identity screening NEVER blocks legitimate traffic when no list is
    configured. When no list file is present, screening is OFF and
    verification behaves exactly as before (fail-open for identity,
    fail-closed for integrity). A list file that cannot be read, or
    that loads zero entries, also disables screening with a warning on
    stderr -- it never raises and never blocks a packet.
  * Exact matching is deterministic. Names are normalized (upper
    case, periods/commas stripped, whitespace collapsed); DOBs are
    8 digits YYYYMMDD; ZIPs are the first 5 digits; business names
    additionally lose trailing legal suffixes (INC, LLC, CORP, LTD,
    CO) and punctuation. A claim field that is missing or
    un-normalizable is simply not screened on that key.
  * Only 9,023 of the 84,224 LEIE records carry an NPI. Name matching
    covers the rest: 71,471 no-NPI rows carry LASTNAME+FIRSTNAME+DOB
    and 2,870 carry BUSNAME+STATE (2026-11-20 download). A claim with
    no provider identity in its payload is simply not screened.
  * The provider identity is read from the signed payload itself (the
    JSON claim's ``provider_npi`` / ``provider_lastname`` /
    ``provider_firstname`` / ``provider_dob`` / ``provider_zip`` /
    ``provider_busname`` / ``provider_state`` fields), so the check
    works identically on both ingress paths -- POST /verify and Gate 1
    -- with no change to the wire format and no extra header.

List formats (plain text, one entry per line; blank lines and lines
starting with ``#`` are ignored). Build both with refresh_watchlist.py;
do NOT commit the full 84k-record LEIE extract into a repo.

  * ``watchlist.txt`` -- one NPI per line.
  * ``watchlist-names.txt`` -- one name key per line:
    ``P|LASTNAME|FIRSTNAME|DOB|ZIP`` (ZIP may be empty) for people,
    ``B|BUSNAME|STATE`` for businesses.

Configuration: SUMERAVERA_WATCHLIST_PATH (a file path) wins for the
NPI list; SUMERAVERA_WATCHLIST_NAMES_PATH wins for the name index.
Otherwise ``watchlist.txt`` / ``watchlist-names.txt`` in the process
working directory are used when they exist. No env var and no file
means screening is off. A refreshed list takes effect without a
process restart: get_default_watchlist() re-stats the list files on
every call and reloads when one changes (see "mtime reload" below).
"""

import json
import os
import re
import sys
import threading
from typing import Dict, FrozenSet, List, Optional, Tuple

LEIE_DOWNLOAD_URL = "https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv"
WATCHLIST_ENV_VAR = "SUMERAVERA_WATCHLIST_PATH"
WATCHLIST_NAMES_ENV_VAR = "SUMERAVERA_WATCHLIST_NAMES_PATH"
DEFAULT_WATCHLIST_FILENAME = "watchlist.txt"
DEFAULT_WATCHLIST_NAMES_FILENAME = "watchlist-names.txt"

# Trailing tokens stripped from a business name when building the exact
# key ("ACME CLINIC, INC." and "ACME CLINIC LLC" are the same business
# for matching). Only whole trailing tokens are stripped, so "MEXICO"
# (one token) is untouched.
BUSNAME_SUFFIXES = frozenset({"INC", "LLC", "CORP", "LTD", "CO"})

_default_lock = threading.Lock()
_default_watchlist = None


# ---------------------------------------------------------------------------
# Normalization (one definition; refresh_watchlist.py imports these too)
# ---------------------------------------------------------------------------

def normalize_name(value) -> str:
    """Upper-case, strip, drop periods/commas, collapse whitespace.

    Returns "" for a missing or blank value. Apostrophes and hyphens
    are kept: "O'BRIEN" and "O'BRIEN." normalize the same, but
    "O'BRIEN" and "OBRIEN" do not -- exact matching stays predictable.
    """
    if not isinstance(value, str):
        return ""
    cleaned = value.upper().replace(".", "").replace(",", "")
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_dob(value) -> Optional[str]:
    """Strip non-digits; return the 8-digit YYYYMMDD string, else None.

    LEIE stores DOB as YYYYMMDD. A claim may write it "1980-01-01" or
    "01/01/1980" -- both reduce to 8 digits only when they are already
    in YYYYMMDD order after stripping separators; a value that does
    not reduce to exactly 8 digits is treated as missing, never
    guessed at.
    """
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str):
        return None
    digits = re.sub(r"\D", "", value)
    return digits if len(digits) == 8 else None


def normalize_zip(value) -> Optional[str]:
    """First 5 digits of the ZIP, else None (missing / too short)."""
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str):
        return None
    digits = re.sub(r"\D", "", value)
    return digits[:5] if len(digits) >= 5 else None


def normalize_busname(value) -> str:
    """Upper-case, drop punctuation, collapse whitespace, strip
    trailing legal-suffix tokens (INC, LLC, CORP, LTD, CO)."""
    if not isinstance(value, str):
        return ""
    cleaned = re.sub(r"[^A-Z0-9 ]", " ", value.upper())
    tokens = re.sub(r"\s+", " ", cleaned).strip().split(" ")
    tokens = [t for t in tokens if t]
    while tokens and tokens[-1] in BUSNAME_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def normalize_state(value) -> str:
    """Upper-case 2-letter state code, else ""."""
    if not isinstance(value, str):
        return ""
    return value.strip().upper()


# ---------------------------------------------------------------------------
# Claim identity extraction
# ---------------------------------------------------------------------------

def extract_provider_identity(payload: bytes) -> dict:
    """Best-effort extraction of provider identity from a claim payload.

    The payload is a JSON object with optional fields ``provider_npi``,
    ``provider_lastname``, ``provider_firstname``, ``provider_dob``,
    ``provider_zip``, ``provider_busname``, ``provider_state``. Every
    field is normalized (see above); a missing or un-normalizable
    field becomes None, which means "not screened on that key". Never
    raises. Non-JSON payloads return an all-None identity.
    """
    identity = {
        "npi": None,
        "lastname": None,
        "firstname": None,
        "dob": None,
        "zip": None,
        "busname": None,
        "state": None,
    }
    if not isinstance(payload, (bytes, bytearray)):
        return identity
    try:
        data = json.loads(bytes(payload).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return identity
    if not isinstance(data, dict):
        return identity
    npi = data.get("provider_npi")
    if isinstance(npi, int):
        npi = str(npi)
    if isinstance(npi, str):
        npi = npi.strip()
        identity["npi"] = npi or None
    identity["lastname"] = normalize_name(data.get("provider_lastname")) or None
    identity["firstname"] = normalize_name(data.get("provider_firstname")) or None
    identity["dob"] = normalize_dob(data.get("provider_dob"))
    identity["zip"] = normalize_zip(data.get("provider_zip"))
    identity["busname"] = normalize_busname(data.get("provider_busname")) or None
    identity["state"] = normalize_state(data.get("provider_state")) or None
    return identity


def extract_provider_npi(payload: bytes) -> Optional[str]:
    """Best-effort extraction of a provider NPI from a claim payload.

    Kept for existing callers; implemented on top of
    extract_provider_identity so the JSON is parsed once per caller.
    Anything that is not a JSON object with a usable ``provider_npi``
    returns None, which means "not screened". Never raises.
    """
    return extract_provider_identity(payload)["npi"]


# ---------------------------------------------------------------------------
# List loading
# ---------------------------------------------------------------------------

def load_npi_set(path: str) -> set:
    """Load NPIs from a watchlist file (one per line, ``#`` comments
    and blank lines ignored). Raises OSError when the file cannot be
    read; the caller decides what that means."""
    npis = set()
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            npis.add(line)
    return npis


def load_name_index(path: str) -> dict:
    """Load the name index from a watchlist-names file.

    Lines are ``P|LASTNAME|FIRSTNAME|DOB|ZIP`` (ZIP may be empty) or
    ``B|BUSNAME|STATE``. Names in the file are expected already
    normalized (refresh_watchlist.py writes them that way); loading
    re-normalizes defensively, so a hand-written file still works.
    Malformed lines are skipped with a stderr warning, never fatal.

    Returns a dict with:
      person_keys: set of (lastname, firstname, dob)
      person_zips: dict (lastname, firstname, dob) -> frozenset of ZIPs
                   seen for that key ("" when the LEIE row had no ZIP)
      bus_keys:    set of (busname, state)
      by_dob:      dict dob -> sorted tuple of (lastname, firstname)
                   (the blocked index Gate 3 fuzzy rules F1-F3 use)
      by_state:    dict state -> sorted tuple of busnames
                   (the blocked index Gate 3 rule F4 uses)
    Raises OSError when the file cannot be read.
    """
    person_keys = set()
    person_zips: Dict[Tuple[str, str, str], set] = {}
    bus_keys = set()
    by_dob: Dict[str, set] = {}
    by_state: Dict[str, set] = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            kind = parts[0].strip().upper()
            if kind == "P" and len(parts) in (4, 5):
                ln = normalize_name(parts[1])
                fn = normalize_name(parts[2])
                dob = normalize_dob(parts[3])
                zipc = normalize_zip(parts[4]) if len(parts) == 5 else None
                if not ln or not fn or not dob:
                    print(
                        f"[watchlist] WARNING: {path}:{lineno}: "
                        "person line missing a field; skipped.",
                        file=sys.stderr,
                    )
                    continue
                key = (ln, fn, dob)
                person_keys.add(key)
                person_zips.setdefault(key, set()).add(zipc or "")
                by_dob.setdefault(dob, set()).add((ln, fn))
            elif kind == "B" and len(parts) == 3:
                bn = normalize_busname(parts[1])
                st = normalize_state(parts[2])
                if not bn or not st:
                    print(
                        f"[watchlist] WARNING: {path}:{lineno}: "
                        "business line missing a field; skipped.",
                        file=sys.stderr,
                    )
                    continue
                bus_keys.add((bn, st))
                by_state.setdefault(st, set()).add(bn)
            else:
                print(
                    f"[watchlist] WARNING: {path}:{lineno}: "
                    f"unrecognized line {line!r}; skipped.",
                    file=sys.stderr,
                )
                continue
    return {
        "person_keys": frozenset(person_keys),
        "person_zips": {k: frozenset(v) for k, v in person_zips.items()},
        "bus_keys": frozenset(bus_keys),
        "by_dob": {k: tuple(sorted(v)) for k, v in by_dob.items()},
        "by_state": {k: tuple(sorted(v)) for k, v in by_state.items()},
    }


def _empty_name_index() -> dict:
    return {
        "person_keys": frozenset(),
        "person_zips": {},
        "bus_keys": frozenset(),
        "by_dob": {},
        "by_state": {},
    }


def _stat_signature(path: Optional[str]):
    """(mtime_ns, size) for a path, None when the path is not
    configured or the file does not exist, "unknown" when the stat
    itself fails transiently (a transient failure must not look like
    a change)."""
    if path is None:
        return None
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except FileNotFoundError:
        return None
    except OSError:
        return "unknown"


class Watchlist:
    """An immutable set of excluded providers (NPIs and name keys), or
    a disabled (empty) one.

    ``Watchlist(path, names_path)`` loads both files; a missing /
    unreadable / empty file leaves that component disabled (screening
    off for that component) and prints a warning instead of raising.
    ``Watchlist.disabled()`` is explicitly off. Instances are
    immutable after construction, so a reloaded list is published by
    swapping the reference (see get_default_watchlist), never by
    mutating a live instance.
    """

    def __init__(self, path: Optional[str] = None, names_path: Optional[str] = None) -> None:
        self.path = path
        self.names_path = names_path
        self.excluded_npis: frozenset = frozenset()
        self.enabled = False
        self.loaded_from: Optional[str] = None
        self.names_enabled = False
        self.loaded_names_from: Optional[str] = None
        self._name_index = _empty_name_index()
        self._signatures = {
            "npi": _stat_signature(path),
            "names": _stat_signature(names_path),
        }
        if path is not None:
            self._load(path)
        if names_path is not None:
            self._load_names(names_path)

    @property
    def screening_enabled(self) -> bool:
        """True when either component (NPI list or name index) is on."""
        return self.enabled or self.names_enabled

    def _load(self, path: str) -> None:
        try:
            npis = load_npi_set(path)
        except OSError as e:
            print(
                f"[watchlist] WARNING: could not read {path} ({e}); "
                "identity screening OFF.",
                file=sys.stderr,
            )
            return
        if not npis:
            print(
                f"[watchlist] WARNING: {path} loaded no NPIs; "
                "identity screening OFF.",
                file=sys.stderr,
            )
            return
        self.excluded_npis = frozenset(npis)
        self.enabled = True
        self.loaded_from = path

    def _load_names(self, names_path: str) -> None:
        try:
            index = load_name_index(names_path)
        except OSError as e:
            print(
                f"[watchlist] WARNING: could not read {names_path} ({e}); "
                "name screening OFF.",
                file=sys.stderr,
            )
            return
        if not index["person_keys"] and not index["bus_keys"]:
            print(
                f"[watchlist] WARNING: {names_path} loaded no name keys; "
                "name screening OFF.",
                file=sys.stderr,
            )
            return
        self._name_index = index
        self.names_enabled = True
        self.loaded_names_from = names_path

    def is_excluded(self, npi) -> bool:
        """True only when NPI screening is on and the NPI is on the list."""
        if not self.enabled or not npi:
            return False
        return str(npi).strip() in self.excluded_npis

    def screen_exact(self, identity) -> Tuple[str, str]:
        """Gate 2 -- exact identity match. Returns (verdict, reason).

        ``identity`` is the NORMALIZED dict from
        extract_provider_identity (keys npi, lastname, firstname,
        dob, zip, busname, state); callers that have a raw claim
        should go through gates.screen_identity instead.

        Verdicts: "EXCLUDED" (an exact NPI, person, or business key
        matched), "REVIEW" (only the ZIP check: the 3-field person key
        matched but the claim's ZIP differs from every LEIE ZIP for
        that key -- same name and birth date, different address, so it
        is held for secondary review instead of excluded), "CLEAR"
        (no exact key matched, or no identity was supplied at all).

        Exact keys, in order: NPI; (LASTNAME, FIRSTNAME, DOB) with
        the ZIP rule above; (BUSNAME, STATE). An EXCLUDED from any key
        wins over a REVIEW from another key.
        """
        if not isinstance(identity, dict):
            return ("CLEAR", "no_identity")
        review_reason = None

        npi = identity.get("npi")
        if npi and self.enabled and str(npi).strip() in self.excluded_npis:
            return ("EXCLUDED", "npi_excluded")

        if self.names_enabled:
            ln = identity.get("lastname")
            fn = identity.get("firstname")
            dob = identity.get("dob")
            if ln and fn and dob:
                key = (ln, fn, dob)
                zips = self._name_index["person_zips"].get(key)
                if zips is not None:
                    zipc = identity.get("zip")
                    if zipc is None:
                        return ("EXCLUDED", "name_exact")
                    if not zips or all(z == "" for z in zips):
                        # The LEIE rows for this key carry no ZIP, so
                        # there is nothing to contradict the claim.
                        return ("EXCLUDED", "name_exact")
                    if zipc in zips:
                        return ("EXCLUDED", "name_zip_exact")
                    review_reason = "name_zip_mismatch"

            bn = identity.get("busname")
            st = identity.get("state")
            if bn and st and (bn, st) in self._name_index["bus_keys"]:
                return ("EXCLUDED", "busname_exact")

        if review_reason is not None:
            return ("REVIEW", review_reason)
        return ("CLEAR", "clear")

    def candidates_by_dob(self, dob: Optional[str]) -> Tuple[Tuple[str, str], ...]:
        """(lastname, firstname) pairs listed under one DOB -- the
        blocked candidate set Gate 3 rules F1-F3 use. Empty when name
        screening is off or the DOB is not listed."""
        if not dob or not self.names_enabled:
            return ()
        return self._name_index["by_dob"].get(dob, ())

    def candidates_by_state(self, state: Optional[str]) -> Tuple[str, ...]:
        """Business names listed under one state -- the blocked
        candidate set Gate 3 rule F4 uses. Empty when name screening
        is off or the state is not listed."""
        if not state or not self.names_enabled:
            return ()
        return self._name_index["by_state"].get(state, ())

    @property
    def person_key_count(self) -> int:
        return len(self._name_index["person_keys"])

    @property
    def bus_key_count(self) -> int:
        return len(self._name_index["bus_keys"])

    @classmethod
    def disabled(cls) -> "Watchlist":
        return cls()


def resolve_watchlist_path() -> Optional[str]:
    """Where the default NPI list comes from: the env var wins, else
    ``watchlist.txt`` in the working directory when it exists, else
    None (screening off)."""
    env_path = os.environ.get(WATCHLIST_ENV_VAR)
    if env_path:
        return env_path
    candidate = os.path.join(os.getcwd(), DEFAULT_WATCHLIST_FILENAME)
    return candidate if os.path.exists(candidate) else None


def resolve_watchlist_names_path() -> Optional[str]:
    """Where the default name index comes from: the env var wins,
    else ``watchlist-names.txt`` in the working directory when it
    exists, else None (name screening off). Resolved independently
    of the NPI list, so one component can be on while the other is
    off."""
    env_path = os.environ.get(WATCHLIST_NAMES_ENV_VAR)
    if env_path:
        return env_path
    candidate = os.path.join(os.getcwd(), DEFAULT_WATCHLIST_NAMES_FILENAME)
    return candidate if os.path.exists(candidate) else None


def _load_default() -> Watchlist:
    npi_path = resolve_watchlist_path()
    names_path = resolve_watchlist_names_path()
    if npi_path is None and names_path is None:
        return Watchlist.disabled()
    return Watchlist(npi_path, names_path)


def _default_changed(wl: Watchlist) -> bool:
    """True when either list file's resolved path or stat signature
    differs from what ``wl`` was loaded from. A transient stat
    failure ("unknown") never counts as a change, so a flaky
    filesystem cannot silently reload -- or unload -- the lists."""
    current = {
        "npi": (resolve_watchlist_path(), _stat_signature(resolve_watchlist_path())),
        "names": (
            resolve_watchlist_names_path(),
            _stat_signature(resolve_watchlist_names_path()),
        ),
    }
    recorded = {
        "npi": (wl.path, wl._signatures["npi"]),
        "names": (wl.names_path, wl._signatures["names"]),
    }
    for key in ("npi", "names"):
        cur_path, cur_sig = current[key]
        rec_path, rec_sig = recorded[key]
        if cur_sig == "unknown" or rec_sig == "unknown":
            continue
        if cur_path != rec_path or cur_sig != rec_sig:
            return True
    return False


def get_default_watchlist() -> Watchlist:
    """The process-wide default watchlist, loaded once on first use
    and reloaded (under the lock) when either list file changes on
    disk -- a monthly refresh takes effect without a process restart.

    The mtime check is two stat calls per invocation and takes no
    lock; only a detected change takes the lock, and the change is
    re-checked inside the lock, so concurrent callers cannot reload
    twice or observe a half-loaded list. Never raises; returns a
    disabled instance when no list is configured. Callers that need a
    specific list should construct Watchlist(path, names_path)
    directly and pass it in."""
    global _default_watchlist
    wl = _default_watchlist
    if wl is None:
        with _default_lock:
            if _default_watchlist is None:
                _default_watchlist = _load_default()
            wl = _default_watchlist
    if _default_changed(wl):
        with _default_lock:
            if _default_changed(_default_watchlist):
                _default_watchlist = _load_default()
            wl = _default_watchlist
    return wl


def _reset_default_watchlist() -> None:
    """Drop the cached default (tests only). The next call to
    get_default_watchlist() re-resolves the path and reloads."""
    global _default_watchlist
    with _default_lock:
        _default_watchlist = None
