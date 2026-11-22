#!/usr/bin/env python3
"""Tests for Gates 2 and 3: exact identity matching (name + NPI),
fuzzy identity held for secondary review, tier wiring on both paths,
mtime reload of the default watchlist, and the extended refresh
script (NPI + name index from the LEIE CSV).

Run from the repo root:  python3 tests/test_gates.py
Also works under pytest (each test_* function is independent).

Uses a throwaway 32-byte test key only. Identity data under test is
tests/data/watchlist_sample.txt (synthetic NPIs) and
tests/data/watchlist_names_sample.txt (synthetic names) -- no real
exclusions. The core verify path writes to the nonce store
(nonce_cache.db, gitignored); every test uses a fresh uuid nonce so
tests never collide with each other or with earlier runs.
"""
import difflib
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ["SUMERAVERA_SECRET_KEY"] = "K" * 32
os.environ.pop("SUMER_SECRET_ZERO_DRIFT", None)
os.environ["SUMER_ALLOW_LEGACY_SIG"] = "0"
# The default watchlist must stay off for these tests unless a test
# sets it up explicitly: point both at paths that do not exist.
os.environ["SUMERAVERA_WATCHLIST_PATH"] = os.path.join(
    tempfile.gettempdir(), "sumeravera-no-such-watchlist.txt"
)
os.environ["SUMERAVERA_WATCHLIST_NAMES_PATH"] = os.path.join(
    tempfile.gettempdir(), "sumeravera-no-such-watchlist-names.txt"
)

import gate1_ingress
import local_ledger
import watchlist
from gates import screen_identity
from sumeravera_core import screen_ingress_packet, verify_ingress_packet
from watchlist import Watchlist, extract_provider_identity

KEY = b"K" * 32
SAMPLE = os.path.join(ROOT, "tests", "data", "watchlist_sample.txt")
NAMES_SAMPLE = os.path.join(ROOT, "tests", "data", "watchlist_names_sample.txt")
EXCLUDED_NPI = "1111111111"  # first entry of the synthetic NPI sample
LEGIT_NPI = "1000000099"  # not in the sample list

# Synthetic people/businesses from the names sample (NOT real).
DOE_JOHN = {"provider_lastname": "Doe", "provider_firstname": "John",
            "provider_dob": "1980-01-01", "provider_zip": "12345"}
DOE_JANE = {"provider_lastname": "Doe", "provider_firstname": "Jane",
            "provider_dob": "1975-12-24", "provider_zip": "12345"}
SMITH_ALICE = {"provider_lastname": "Smith", "provider_firstname": "Alice",
               "provider_dob": "19900303"}  # sample row has no ZIP
ACME_TX = {"provider_busname": "Acme Clinic, Inc.", "provider_state": "TX"}


def _sig(nonce, ts, payload):
    msg = f"{nonce}:{int(ts)}:".encode("utf-8") + payload
    return hmac.new(KEY, msg, hashlib.sha256).hexdigest()


def _now():
    return time.time()


def _nonce(prefix):
    return f"{prefix}-{uuid.uuid4().hex}"


def _claim(fields, claim_id="g1"):
    claim = {"claim_id": claim_id, "amount_usd": 100.0}
    claim.update(fields)
    return json.dumps(claim, sort_keys=True).encode("utf-8")


def _wl():
    return Watchlist(SAMPLE, NAMES_SAMPLE)


def _gate(wl):
    conn = local_ledger.get_connection(":memory:")
    local_ledger.initialize_ledger(conn)
    return gate1_ingress.Gate1(ledger_conn=conn, watchlist=wl), conn


def _screen(claim_fields, wl=None):
    return screen_identity(_claim(claim_fields), wl if wl is not None else _wl())


# --- identity extraction / normalization -------------------------------

def test_extract_provider_identity():
    ident = extract_provider_identity(_claim({
        "provider_npi": 1234567890,
        "provider_lastname": "Doe.",
        "provider_firstname": "  john ",
        "provider_dob": "1980-01-01",
        "provider_zip": "12345-6789",
        "provider_busname": "Acme Clinic, Inc.",
        "provider_state": "tx",
    }))
    assert ident["npi"] == "1234567890"
    assert ident["lastname"] == "DOE"
    assert ident["firstname"] == "JOHN"
    assert ident["dob"] == "19800101"
    assert ident["zip"] == "12345"
    assert ident["busname"] == "ACME CLINIC"
    assert ident["state"] == "TX"


def test_extract_identity_missing_fields():
    ident = extract_provider_identity(_claim({"amount_usd": 1}))
    assert ident == {"npi": None, "lastname": None, "firstname": None,
                     "dob": None, "zip": None, "busname": None,
                     "state": None}
    assert extract_provider_identity(b"not json")["npi"] is None
    # A DOB that does not reduce to 8 digits is missing, never guessed.
    assert extract_provider_identity(
        _claim({"provider_dob": "Jan 1980"}))["dob"] is None
    assert extract_provider_identity(
        _claim({"provider_dob": "1980"}))["dob"] is None


def test_names_sample_loads():
    wl = _wl()
    assert wl.enabled is True
    assert wl.names_enabled is True
    assert wl.person_key_count == 4
    assert wl.bus_key_count == 2
    assert wl.candidates_by_dob("19800101") == (("DOE", "JOHN"),)
    assert wl.candidates_by_state("TX") == ("ACME CLINIC",)
    assert wl.candidates_by_dob("19000101") == ()
    assert wl.candidates_by_state("ZZ") == ()


def test_npi_only_watchlist_has_names_off():
    wl = Watchlist(SAMPLE)
    assert wl.enabled is True
    assert wl.names_enabled is False
    assert wl.screen_exact({"npi": EXCLUDED_NPI}) == ("EXCLUDED", "npi_excluded")
    # Normalized identity for DOE/JOHN/19800101 (a listed name key in
    # the sample file) -- with names off it must be CLEAR.
    assert wl.screen_exact({"npi": None, "lastname": "DOE", "firstname": "JOHN",
                            "dob": "19800101", "zip": "12345",
                            "busname": None, "state": None}) == ("CLEAR", "clear")


# --- Gate 2 exact matching ----------------------------------------------

def test_exact_name_match():
    assert _screen(DOE_JOHN).verdict == "EXCLUDED"
    assert _screen(DOE_JOHN).reason == "name_zip_exact"


def test_exact_name_without_zip():
    fields = {k: v for k, v in DOE_JOHN.items() if k != "provider_zip"}
    r = _screen(fields)
    assert (r.verdict, r.reason) == ("EXCLUDED", "name_exact")


def test_exact_name_empty_zip_row():
    # The SMITH/ALICE sample row carries no ZIP, so any claim ZIP
    # (or none) still excludes: there is nothing to contradict.
    assert _screen(SMITH_ALICE).verdict == "EXCLUDED"
    with_zip = dict(SMITH_ALICE, provider_zip="99999")
    assert _screen(with_zip).verdict == "EXCLUDED"


def test_exact_name_zip_mismatch_is_review_not_excluded():
    fields = dict(DOE_JOHN, provider_zip="99999")
    r = _screen(fields)
    assert (r.verdict, r.reason) == ("REVIEW", "name_zip_mismatch")


def test_exact_busname_match():
    assert _screen(ACME_TX).reason == "busname_exact"
    assert _screen(ACME_TX).verdict == "EXCLUDED"
    # Legal suffixes and case do not matter after normalization.
    assert _screen({"provider_busname": "acme clinic llc",
                    "provider_state": "tx"}).verdict == "EXCLUDED"
    assert _screen({"provider_busname": "Acme Clinic",
                    "provider_state": "CA"}).verdict == "CLEAR"


def test_exact_npi_still_works_via_screen_identity():
    r = _screen({"provider_npi": EXCLUDED_NPI})
    assert (r.verdict, r.reason) == ("EXCLUDED", "npi_excluded")
    assert _screen({"provider_npi": LEGIT_NPI}).verdict == "CLEAR"


def test_no_identity_fields_is_clear():
    assert _screen({"amount_usd": 1}).verdict == "CLEAR"
    assert _screen({"amount_usd": 1}).reason == "clear"
    assert screen_identity(b"not json", _wl()).verdict == "CLEAR"


def test_screening_off_is_clear():
    assert screen_identity(_claim(DOE_JOHN),
                           Watchlist.disabled()).verdict == "CLEAR"


# --- Gate 3 fuzzy rules ---------------------------------------------------

def test_f1_dob_typo_is_review():
    # One digit off the listed DOB (19800101 -> 19800102).
    fields = dict(DOE_JOHN, provider_dob="1980-01-02")
    r = _screen(fields)
    assert (r.verdict, r.reason) == ("REVIEW", "fuzzy_dob_typo")


def test_f2_firstname_prefix_is_review():
    fields = dict(DOE_JOHN, provider_firstname="Joh")
    r = _screen(fields)
    assert (r.verdict, r.reason) == ("REVIEW", "fuzzy_firstname_prefix")


def test_f2_firstname_initial_is_review():
    fields = dict(DOE_JOHN, provider_firstname="J")
    r = _screen(fields)
    assert (r.verdict, r.reason) == ("REVIEW", "fuzzy_firstname_initial")


def test_f3_lastname_typo_is_review():
    # "DOEE" vs "DOE": difflib ratio 6/7 = 0.857 >= 0.85.
    assert difflib.SequenceMatcher(None, "DOE", "DOEE").ratio() >= 0.85
    fields = dict(DOE_JOHN, provider_lastname="Doee")
    r = _screen(fields)
    assert (r.verdict, r.reason) == ("REVIEW", "fuzzy_lastname_similar")


def test_f3_lastname_too_different_is_clear():
    fields = dict(DOE_JOHN, provider_lastname="Zanzibar")
    assert _screen(fields).verdict == "CLEAR"


def test_f4_busname_typo_is_review():
    # "ACME CLINIK" vs "ACME CLINIC": ratio 20/22 = 0.909 >= 0.85.
    assert difflib.SequenceMatcher(None, "ACME CLINIC", "ACME CLINIK").ratio() >= 0.85
    fields = {"provider_busname": "Acme Clinik", "provider_state": "TX"}
    r = _screen(fields)
    assert (r.verdict, r.reason) == ("REVIEW", "fuzzy_busname_similar")


def test_f4_busname_wrong_state_is_clear():
    fields = {"provider_busname": "Acme Clinik", "provider_state": "CA"}
    assert _screen(fields).verdict == "CLEAR"


def test_fuzzy_never_excludes():
    for fields in (
        dict(DOE_JOHN, provider_dob="1980-01-02"),
        dict(DOE_JOHN, provider_firstname="J"),
        dict(DOE_JOHN, provider_lastname="Doee"),
        {"provider_busname": "Acme Clinik", "provider_state": "TX"},
    ):
        assert _screen(fields).verdict == "REVIEW"


# --- verdict plumbing: verify path ----------------------------------------

def test_review_is_not_verified_and_consumes_no_nonce():
    wl = _wl()
    now = _now()
    nonce = _nonce("g-review")
    payload = _claim(dict(DOE_JOHN, provider_dob="1980-01-02"))
    sig = _sig(nonce, now, payload)
    assert verify_ingress_packet(payload, sig, nonce, now, watchlist=wl) is False
    # The nonce was never consumed: the same packet verifies once
    # screening is off (as if the review had cleared it).
    assert verify_ingress_packet(
        payload, sig, nonce, now, watchlist=Watchlist.disabled()
    ) is True


def test_review_writes_no_ledger_entry():
    wl = _wl()
    now = _now()
    nonce = _nonce("g-revled")
    payload = _claim(dict(DOE_JOHN, provider_dob="1980-01-02"))
    conn = local_ledger.get_connection(":memory:")
    local_ledger.initialize_ledger(conn)
    r = screen_ingress_packet(payload, _sig(nonce, now, payload), nonce, now,
                              ledger_conn=conn, watchlist=wl)
    assert (r.verdict, r.reason, r.verified) == ("REVIEW", "fuzzy_dob_typo", False)
    assert conn.execute("SELECT COUNT(*) FROM state_ledger").fetchone()[0] == 0
    assert local_ledger.verify_chain_integrity(conn) is True
    conn.close()


def test_screen_ingress_packet_verdicts():
    wl = _wl()
    now = _now()
    nonce = _nonce("g-clear2")
    payload = _claim({"provider_npi": LEGIT_NPI})
    clear = screen_ingress_packet(payload, _sig(nonce, now, payload), nonce, now,
                                  watchlist=wl)
    assert (clear.verdict, clear.reason, clear.verified) == ("CLEAR", "verified", True)
    nonce = _nonce("g-excl")
    payload = _claim(DOE_JOHN)
    excl = screen_ingress_packet(payload, _sig(nonce, now, payload), nonce, now,
                                 watchlist=wl)
    assert (excl.verdict, excl.reason, excl.verified) == ("EXCLUDED", "name_zip_exact", False)
    nonce = _nonce("g-rev")
    payload = _claim(dict(DOE_JOHN, provider_dob="1980-01-02"))
    rev = screen_ingress_packet(payload, _sig(nonce, now, payload), nonce, now,
                                watchlist=wl)
    assert (rev.verdict, rev.reason, rev.verified) == ("REVIEW", "fuzzy_dob_typo", False)
    # Integrity failures are EXCLUDED too, with a reason that says so.
    nonce = _nonce("g-bad")
    payload = _claim({"provider_npi": LEGIT_NPI})
    bad = screen_ingress_packet(payload, "00" * 32, nonce, now, watchlist=wl)
    assert (bad.verdict, bad.reason) == ("EXCLUDED", "bad_signature")


# --- tier wiring: Gate 1 ----------------------------------------------------

def test_gate1_review_is_rebalancing_without_ledger_entry():
    gate, conn = _gate(_wl())
    now = _now()
    nonce = _nonce("g-g1rev")
    payload = _claim(dict(DOE_JOHN, provider_dob="1980-01-02"))
    r = gate.route(payload, _sig(nonce, now, payload), nonce, now)
    assert r["tier"] == "REBALANCING" and r["status_code"] == 202
    assert r["action"] == "HELD_FOR_REVIEW" and r["reason"] == "identity_review"
    assert r["ledger_seq"] is None and r["ledger_hash"] is None
    assert conn.execute("SELECT COUNT(*) FROM state_ledger").fetchone()[0] == 0
    assert local_ledger.verify_chain_integrity(conn) is True
    conn.close()


def test_gate1_exact_name_is_quarantine_without_ledger_entry():
    gate, conn = _gate(_wl())
    now = _now()
    nonce = _nonce("g-g1ex")
    payload = _claim(DOE_JOHN)
    r = gate.route(payload, _sig(nonce, now, payload), nonce, now)
    assert r["tier"] == "QUARANTINE" and r["status_code"] == 403
    assert r["action"] == "ISOLATED" and r["reason"] == "identity_excluded"
    assert r["ledger_seq"] is None
    conn.close()


def test_gate1_clear_drifted_still_rebalancing_with_ledger_entry():
    gate, conn = _gate(_wl())
    old = _now() - 30
    nonce = _nonce("g-g1drift")
    payload = _claim({"provider_npi": LEGIT_NPI})
    r = gate.route(payload, _sig(nonce, old, payload), nonce, old)
    assert r["tier"] == "REBALANCING" and r["status_code"] == 202
    assert r["action"] == "AUTO_STAGED" and r["reason"] == "verified"
    assert r["ledger_seq"] == 1
    conn.close()


# --- mtime reload -------------------------------------------------------------

def test_default_watchlist_reloads_when_files_change():
    tmp = tempfile.mkdtemp(prefix="svp_mtime_")
    npi_path = os.path.join(tmp, "watchlist.txt")
    names_path = os.path.join(tmp, "watchlist-names.txt")
    with open(npi_path, "w") as fh:
        fh.write("# test\n1111111111\n")
    with open(names_path, "w") as fh:
        fh.write("# test\nP|DOE|JOHN|19800101|12345\n")
    os.environ["SUMERAVERA_WATCHLIST_PATH"] = npi_path
    os.environ["SUMERAVERA_WATCHLIST_NAMES_PATH"] = names_path
    watchlist._reset_default_watchlist()
    try:
        wl = watchlist.get_default_watchlist()
        assert wl.is_excluded("1111111111") is True
        assert wl.is_excluded("2222222222") is False
        assert wl.screen_exact({"npi": None, "lastname": "DOE",
                                "firstname": "JOHN", "dob": "19800101",
                                "zip": "12345", "busname": None,
                                "state": None})[0] == "EXCLUDED"
        # Append a new NPI and a new name, bump the mtimes, and the
        # next call must see them without a process restart.
        with open(npi_path, "a") as fh:
            fh.write("2222222222\n")
        with open(names_path, "a") as fh:
            fh.write("P|DOE|JANE|19751224|12345\n")
        bump = time.time_ns() + 2_000_000_000
        os.utime(npi_path, ns=(bump, bump))
        os.utime(names_path, ns=(bump, bump))
        wl2 = watchlist.get_default_watchlist()
        assert wl2.is_excluded("2222222222") is True
        assert wl2.screen_exact({"npi": None, "lastname": "DOE",
                                 "firstname": "JANE", "dob": "19751224",
                                 "zip": "12345", "busname": None,
                                 "state": None})[0] == "EXCLUDED"
        # The old entries are still there after the reload.
        assert wl2.is_excluded("1111111111") is True
    finally:
        os.environ["SUMERAVERA_WATCHLIST_PATH"] = os.path.join(
            tempfile.gettempdir(), "sumeravera-no-such-watchlist.txt")
        os.environ["SUMERAVERA_WATCHLIST_NAMES_PATH"] = os.path.join(
            tempfile.gettempdir(), "sumeravera-no-such-watchlist-names.txt")
        watchlist._reset_default_watchlist()


# --- refresh script -----------------------------------------------------------

DEMO_LEIE = os.path.normpath(
    os.path.join(ROOT, "..", "..", "..", "demo", "data", "UPDATED.csv")
)


def test_refresh_script_counts_on_demo_leie():
    # Counts are pinned to demo/data/UPDATED.csv (the 2026-11-20
    # HHS-OIG download: 84,224 rows). If the file is refreshed, these
    # numbers move with it -- update them from the script's own output.
    if not os.path.exists(DEMO_LEIE):
        import pytest

        pytest.skip("demo LEIE file not present")
    tmp = tempfile.mkdtemp(prefix="svp_refresh_")
    out = os.path.join(tmp, "watchlist.txt")
    names_out = os.path.join(tmp, "watchlist-names.txt")
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "refresh_watchlist.py"),
         "--csv", DEMO_LEIE, "--out", out, "--names-out", names_out],
        capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr
    with open(out, encoding="utf-8") as fh:
        npi_lines = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    assert len(npi_lines) == 8844
    assert len(set(npi_lines)) == 8844
    with open(names_out, encoding="utf-8") as fh:
        name_lines = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    p_lines = [ln for ln in name_lines if ln.startswith("P|")]
    b_lines = [ln for ln in name_lines if ln.startswith("B|")]
    assert len(p_lines) + len(b_lines) == len(name_lines)
    assert len({ln.split("|")[1] + "|" + ln.split("|")[2] + "|" + ln.split("|")[3]
                for ln in p_lines}) == 78794
    assert len(set(b_lines)) == 3493
    # Headers carry source, timestamp, and row counts.
    with open(out, encoding="utf-8") as fh:
        header = fh.read(2000)
    assert "LEIE rows seen: 84224" in header and "distinct NPIs: 8844" in header
    # A second run overwrites atomically and yields the same files.
    proc2 = subprocess.run(
        [sys.executable, os.path.join(ROOT, "refresh_watchlist.py"),
         "--csv", DEMO_LEIE, "--out", out, "--names-out", names_out],
        capture_output=True, text=True, cwd=ROOT)
    assert proc2.returncode == 0, proc2.stderr
    with open(out, encoding="utf-8") as fh:
        assert len([ln for ln in fh if ln.strip() and not ln.startswith("#")]) == 8844


def test_refresh_script_refuses_empty_csv():
    tmp = tempfile.mkdtemp(prefix="svp_refresh_empty_")
    empty_csv = os.path.join(tmp, "empty.csv")
    with open(empty_csv, "w") as fh:
        fh.write("LASTNAME,FIRSTNAME,MIDNAME,BUSNAME,GENERAL,SPECIALTY,UPIN,"
                 "NPI,DOB,ADDRESS,CITY,STATE,ZIP,EXCLTYPE,EXCLDATE,REINDATE,"
                 "WAIVERDATE,WVRSTATE\n")
    out = os.path.join(tmp, "watchlist.txt")
    names_out = os.path.join(tmp, "watchlist-names.txt")
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "refresh_watchlist.py"),
         "--csv", empty_csv, "--out", out, "--names-out", names_out],
        capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 1
    assert not os.path.exists(out)
    assert not os.path.exists(names_out)
    assert "zero NPIs" in proc.stderr


def test_refresh_names_file_format():
    tmp = tempfile.mkdtemp(prefix="svp_refresh_fmt_")
    out = os.path.join(tmp, "watchlist.txt")
    names_out = os.path.join(tmp, "watchlist-names.txt")
    if not os.path.exists(DEMO_LEIE):
        import pytest

        pytest.skip("demo LEIE file not present")
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "refresh_watchlist.py"),
         "--csv", DEMO_LEIE, "--out", out, "--names-out", names_out],
        capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr
    with open(names_out, encoding="utf-8") as fh:
        checked = 0
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if parts[0] == "P":
                assert len(parts) in (4, 5)
                assert len(parts[3]) == 8 and parts[3].isdigit()
            elif parts[0] == "B":
                assert len(parts) == 3
            else:
                raise AssertionError(f"unexpected line kind: {line!r}")
            checked += 1
        assert checked == 82833


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]


if __name__ == "__main__":
    failures = 0
    for fn in TESTS:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as e:  # noqa: BLE001 - report and continue
            failures += 1
            print(f"FAIL {fn.__name__}: {e!r}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} passed")
    sys.exit(1 if failures else 0)
