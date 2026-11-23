#!/usr/bin/env python3
"""SumerAvera LIVE demo: traffic generator + simulation runner.

Sends synthetic claims through the RUNNING demo server (WebSocket
/ws/ingress and HTTP POST /verify) and measures what the real protocol
does with them. Nothing here calls the protocol modules directly -- all
traffic goes over the socket/HTTP to the server.

Ground-truth labeling (every packet is labeled before it is sent)
------------------------------------------------------------------
  legitimate   -- synthetic provider (SYNTH- id, not a real NPI), fresh,
                  valid signature. Expected: accepted.
  fraud_bad_sig-- real HHS-OIG LEIE excluded provider (real NPI/name),
                  corrupted signature. Expected: QUARANTINE / 401.
  fraud_replay -- real LEIE provider, valid signature, sent twice with the
                  same nonce. The 2nd send is the fraud item. Expected:
                  QUARANTINE / 401.
  fraud_stale  -- real LEIE provider, valid signature, timestamp now-400s.
                  Expected: QUARANTINE / 401.
  fraud_drifted-- real LEIE provider, valid signature, timestamp now-30s.
                  Expected: REBALANCING on WS (accepted, staged), 200 on
                  HTTP (core allows 300s). NOT stopped by the protocol.
  fraud_clean  -- real LEIE provider, valid signature, fresh. Expected:
                  STABLE on WS (protocol cannot know the provider is
                  excluded) -- caught only by the demo-layer LEIE watchlist.
  fraud_name_person -- real LEIE row with NO NPI: real LASTNAME /
                  FIRSTNAME / DOB / ZIP in the claim, properly signed
                  and fresh. Expected: QUARANTINE (Gate 2 exact) / 401.
  fraud_name_bus -- real LEIE business row with NO NPI: real BUSNAME /
                  STATE in the claim, properly signed and fresh.
                  Expected: QUARANTINE (Gate 2 exact) / 401.
  fraud_fuzzy_f1 -- same as fraud_name_person but the DOB has one digit
                  changed (single-digit typo). Expected: REBALANCING
                  (202, held for review) on WS, 202 on HTTP -- NOT
                  quarantined/rejected outright.
  fraud_fuzzy_f2 -- same, but FIRSTNAME is the first initial (or a
                  2-3 char prefix). Expected: 202, held.
  fraud_fuzzy_f3 -- same, but LASTNAME has a one-character typo
                  (difflib ratio >= 0.85). Expected: 202, held.
  fraud_fuzzy_f4 -- same as fraud_name_bus but BUSNAME has a
                  one-character typo (ratio >= 0.85). Expected: 202, held.
  legitimate_with_name -- synthetic provider WITH name fields
                  (LASTNAME/FIRSTNAME/DOB/ZIP) that match nothing in
                  LEIE (checked against the file at generation time).
                  Expected: accepted (STABLE / 200), no hold.

"Stopped" for the catch rate means: quarantined/rejected by the protocol
OR flagged by the demo-layer LEIE watchlist (union, counted once).
"Held" means Gate 3 REVIEW (REBALANCING with reason identity_review
on WS, HTTP 202). Held fraud counts separately from stopped fraud:
the headline catch rate stays QUARANTINE/REJECTED-based, and a second
rate including held packets is reported alongside it, so a hold is
never silently counted as a catch -- or as a miss.
Protocol-only and combined rates are reported separately, so the
watchlist never inflates the protocol's own number.

Amounts and dates in the claims are synthetic (seeded RNG). Only the
fraud-class provider identity (NPI, name, exclusion type/date) is real
public data, from HHS-OIG LEIE UPDATED.csv (84,224 records, downloaded
2026-11-20, sha256 e3c50a29...f05346f1eb).

Run:
    cd demo
    SUMERAVERA_SECRET_KEY=<same throwaway as the server> \
    python3 traffic.py
Writes results.json and POSTs the summary to /demo/results.
"""

import asyncio
import csv
import difflib
import hashlib
import hmac
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import websockets

DEMO_DIR = Path(__file__).resolve().parent
SERVER = os.environ.get("DEMO_SERVER", "ws://127.0.0.1:8123")
HTTP_BASE = os.environ.get("DEMO_HTTP", "http://127.0.0.1:8123")
KEY = os.environ["SUMERAVERA_SECRET_KEY"].encode("utf-8")
LEIE_CSV = DEMO_DIR / "data" / "UPDATED.csv"

# The generator imports ONLY the normalization helpers from the
# repository root, so the claims it builds use exactly the keys the
# screen builds. It never calls the protocol modules directly -- all
# verification still goes over the socket/HTTP to the server.
WORK_TREE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORK_TREE))
from watchlist import (  # noqa: E402
    normalize_busname,
    normalize_dob,
    normalize_name,
    normalize_state,
    normalize_zip,
)

random.seed(20261120)


def sign(nonce: str, ts: float, payload: bytes) -> str:
    msg = f"{nonce}:{int(ts)}:".encode("utf-8") + payload
    return hmac.new(KEY, msg, hashlib.sha256).hexdigest()


def load_leie_providers(n: int):
    """Deterministic sample of LEIE rows that carry an NPI."""
    rows = []
    with open(LEIE_CSV, newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            npi = (r.get("NPI") or "").strip()
            if npi and npi != "0":
                name = (r.get("BUSNAME") or
                        ((r.get("LASTNAME") or "") + " " +
                         (r.get("FIRSTNAME") or ""))).strip()
                rows.append({"npi": npi, "name": name,
                             "excltype": r.get("EXCLTYPE", ""),
                             "excldate": r.get("EXCLDATE", "")})
    rows.sort(key=lambda r: r["npi"])
    step = max(1, len(rows) // n)
    return [rows[i * step] for i in range(n)]


def _read_leie_rows():
    with open(LEIE_CSV, newline="", encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(fh))


def load_leie_no_npi_person(n: int):
    """Deterministic sample of LEIE rows with NO NPI that carry a full
    person identity (LASTNAME + FIRSTNAME + DOB). Sorted by the
    normalized key so the sample is stable across runs."""
    rows = []
    for r in _read_leie_rows():
        if (r.get("NPI") or "").strip() not in ("", "0"):
            continue
        ln, fn, dob = (normalize_name(r.get("LASTNAME")),
                       normalize_name(r.get("FIRSTNAME")),
                       normalize_dob(r.get("DOB")))
        if not ln or not fn or not dob:
            continue
        rows.append({"lastname": ln, "firstname": fn, "dob": dob,
                     "zip": normalize_zip(r.get("ZIP")),
                     "name": f"{ln} {fn}", "excltype": r.get("EXCLTYPE", ""),
                     "excldate": r.get("EXCLDATE", "")})
    rows.sort(key=lambda r: (r["lastname"], r["firstname"], r["dob"]))
    step = max(1, len(rows) // n)
    return [rows[i * step] for i in range(n)]


def load_leie_no_npi_bus(n: int):
    """Deterministic sample of LEIE business rows with NO NPI that
    carry BUSNAME + STATE."""
    rows = []
    for r in _read_leie_rows():
        if (r.get("NPI") or "").strip() not in ("", "0"):
            continue
        bn, st = normalize_busname(r.get("BUSNAME")), normalize_state(r.get("STATE"))
        if not bn or not st:
            continue
        rows.append({"busname": bn, "state": st, "name": bn,
                     "excltype": r.get("EXCLTYPE", ""),
                     "excldate": r.get("EXCLDATE", "")})
    rows.sort(key=lambda r: (r["busname"], r["state"]))
    step = max(1, len(rows) // n)
    return [rows[i * step] for i in range(n)]


def load_leie_key_sets():
    """Normalized exact-key sets for the whole LEIE file: person keys
    (lastname, firstname, dob) and business keys (busname, state).
    Used only by the generator to (a) verify a fuzzy variant does not
    accidentally become an exact match, and (b) verify a synthetic
    legitimate name matches nothing in LEIE."""
    person, bus = set(), set()
    for r in _read_leie_rows():
        ln, fn, dob = (normalize_name(r.get("LASTNAME")),
                       normalize_name(r.get("FIRSTNAME")),
                       normalize_dob(r.get("DOB")))
        if ln and fn and dob:
            person.add((ln, fn, dob))
        bn, st = normalize_busname(r.get("BUSNAME")), normalize_state(r.get("STATE"))
        if bn and st:
            bus.add((bn, st))
    return person, bus


def make_name_claim(claim_id, row, cls):
    """A claim carrying identity fields but NO provider_npi, built
    from a real LEIE row. Amounts/dates are synthetic (seeded RNG)."""
    amount = round(random.uniform(50, 5000), 2)
    claim = {"claim_id": claim_id, "amount_usd": amount,
             "service_date": "2026-11-%02d" % random.randint(1, 20),
             "class": cls}
    if "lastname" in row:
        claim["provider_lastname"] = row["lastname"]
        claim["provider_firstname"] = row["firstname"]
        claim["provider_dob"] = row["dob"]
        if row.get("zip"):
            claim["provider_zip"] = row["zip"]
        claim["provider_name"] = row["name"]
    else:
        claim["provider_busname"] = row["busname"]
        claim["provider_state"] = row["state"]
        claim["provider_name"] = row["name"]
    return claim


def _typo_variant(text: str) -> str:
    """A one-character typo of ``text`` with difflib ratio >= 0.85
    against the original (duplicate the last character; for a text of
    length >= 3 that always scores 2*len / (2*len + 1) >= 0.85).
    Raises ValueError when no qualifying typo exists."""
    if len(text) < 3:
        raise ValueError("text too short for a qualifying typo")
    variant = text[:-1] + text[-1] * 2
    if difflib.SequenceMatcher(None, text, variant).ratio() < 0.85:
        raise ValueError("typo does not reach ratio 0.85")
    return variant


def make_fuzzy_claim(claim_id, row, rule, person_keys, bus_keys, variant=0):
    """A fuzzy variant of a real no-NPI LEIE row. The variant is
    verified here to be a NEAR-match, not an accidental exact match
    for some other listed provider: if the variant's exact key is in
    the LEIE key sets, ValueError is raised and the caller picks
    another row."""
    claim = make_name_claim(claim_id, row, f"fraud_fuzzy_{rule}")
    if rule == "f1":
        dob = row["dob"]
        variant_dob = dob[:-1] + ("0" if dob[-1] != "0" else "1")
        if (row["lastname"], row["firstname"], variant_dob) in person_keys:
            raise ValueError("F1 variant is an exact match for another row")
        claim["provider_dob"] = variant_dob
    elif rule == "f2":
        # First initial (variant 0) or a 3-char prefix (variant 1).
        fn = row["firstname"]
        if len(fn) < 2:
            raise ValueError("F2 needs a first name of 2+ chars")
        claim["provider_firstname"] = fn[0] if variant == 0 else fn[:3]
    elif rule == "f3":
        variant = _typo_variant(row["lastname"])
        if (variant, row["firstname"], row["dob"]) in person_keys:
            raise ValueError("F3 variant is an exact match for another row")
        claim["provider_lastname"] = variant
    elif rule == "f4":
        variant = _typo_variant(row["busname"])
        if (variant, row["state"]) in bus_keys:
            raise ValueError("F4 variant is an exact match for another row")
        claim["provider_busname"] = variant
    else:
        raise ValueError(f"unknown fuzzy rule {rule}")
    return claim


def make_claim(claim_id, provider, cls):
    amount = round(random.uniform(50, 5000), 2)
    return {
        "claim_id": claim_id,
        "provider_npi": provider["npi"],
        "provider_name": provider["name"],
        "amount_usd": amount,
        "service_date": "2026-11-%02d" % random.randint(1, 20),
        "class": cls,
    }


class Run:
    def __init__(self):
        self.records = []          # one per fraud/legit ITEM (not per send)
        self.send_count = 0        # every packet actually sent
        self.setup_sends = 0       # replay setup sends (not items)
        self.ws_sends = 0          # WS sends in the main + name phases
        self.http_sends = 0        # HTTP sends
        self.burst_sends = 0       # burst sends
        self.t0 = None

    def record(self, **kw):
        kw.setdefault("reason", None)
        self.records.append(kw)


async def ws_send(ws, claim, nonce, ts, signature, label):
    payload = json.dumps(claim, sort_keys=True)
    await ws.send(json.dumps({
        "payload": payload,
        "signature": signature,
        "nonce": nonce,
        "timestamp": ts,
        "provider_npi": claim.get("provider_npi"),
        "claim_id": claim["claim_id"],
        "label": label,
    }))
    return await ws.recv()


def http_send(claim, nonce, ts, signature):
    payload = json.dumps(claim, sort_keys=True).encode("utf-8")
    req = urllib.request.Request(
        HTTP_BASE + "/verify", data=payload, method="POST",
        headers={"X-Signature": signature, "X-Nonce": nonce,
                 "X-Timestamp": str(ts),
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


async def main():
    run = Run()
    fraud_providers = load_leie_providers(435)
    synth = [{"npi": "SYNTH-%03d" % i, "name": "Synthetic Clinic %03d" % i,
              "excltype": "", "excldate": ""} for i in range(430)]
    fi = iter(fraud_providers)
    si = iter(synth)
    cid = [0]

    def next_id(prefix):
        cid[0] += 1
        return "%s-%04d" % (prefix, cid[0])

    # ---------------- WS main run ----------------
    ws_start = time.time()
    async with websockets.connect(SERVER + "/ws/ingress", max_size=1_000_000) as ws:
        async def send_ws(claim, nonce, ts, sig, label):
            raw = await ws_send(ws, claim, nonce, ts, sig, label)
            run.send_count += 1
            run.ws_sends += 1
            return json.loads(raw)

        # legitimate x200
        for i in range(200):
            p = next(si)
            claim = make_claim(next_id("legit"), p, "legitimate")
            ts = time.time()
            nonce = "ws-legit-%04d" % i
            d = await send_ws(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "legitimate")
            run.record(transport="ws", cls="legitimate", claim_id=claim["claim_id"],
                       tier=d["tier"], status=d["status_code"],
                       watchlist=d["watchlist_hit"], ledger_seq=d["ledger_seq"])

        # fraud_bad_sig x100
        for i in range(100):
            p = next(fi)
            claim = make_claim(next_id("bad"), p, "fraud_bad_sig")
            ts = time.time()
            nonce = "ws-bad-%04d" % i
            good = sign(nonce, ts, json.dumps(claim, sort_keys=True).encode())
            bad = ("0" if good[0] != "0" else "1") + good[1:]
            d = await send_ws(claim, nonce, ts, bad, "fraud_bad_sig")
            run.record(transport="ws", cls="fraud_bad_sig", claim_id=claim["claim_id"],
                       tier=d["tier"], status=d["status_code"],
                       watchlist=d["watchlist_hit"], ledger_seq=d["ledger_seq"])

        # fraud_replay x100 (setup + replay)
        for i in range(100):
            p = next(fi)
            claim = make_claim(next_id("rep"), p, "fraud_replay")
            ts = time.time()
            nonce = "ws-rep-%04d" % i
            sig = sign(nonce, ts, json.dumps(claim, sort_keys=True).encode())
            await send_ws(claim, nonce, ts, sig, "replay_setup")
            run.setup_sends += 1
            d = await send_ws(claim, nonce, ts, sig, "fraud_replay")
            run.record(transport="ws", cls="fraud_replay", claim_id=claim["claim_id"],
                       tier=d["tier"], status=d["status_code"],
                       watchlist=d["watchlist_hit"], ledger_seq=d["ledger_seq"])

        # fraud_stale x100 (ts now-400)
        for i in range(100):
            p = next(fi)
            claim = make_claim(next_id("stale"), p, "fraud_stale")
            ts = time.time() - 400
            nonce = "ws-stale-%04d" % i
            d = await send_ws(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "fraud_stale")
            run.record(transport="ws", cls="fraud_stale", claim_id=claim["claim_id"],
                       tier=d["tier"], status=d["status_code"],
                       watchlist=d["watchlist_hit"], ledger_seq=d["ledger_seq"])

        # fraud_drifted x50 (ts now-30)
        for i in range(50):
            p = next(fi)
            claim = make_claim(next_id("drift"), p, "fraud_drifted")
            ts = time.time() - 30
            nonce = "ws-drift-%04d" % i
            d = await send_ws(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "fraud_drifted")
            run.record(transport="ws", cls="fraud_drifted", claim_id=claim["claim_id"],
                       tier=d["tier"], status=d["status_code"],
                       watchlist=d["watchlist_hit"], ledger_seq=d["ledger_seq"])

        # fraud_clean x50 (valid, fresh, excluded provider)
        for i in range(50):
            p = next(fi)
            claim = make_claim(next_id("clean"), p, "fraud_clean")
            ts = time.time()
            nonce = "ws-clean-%04d" % i
            d = await send_ws(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "fraud_clean")
            run.record(transport="ws", cls="fraud_clean", claim_id=claim["claim_id"],
                       tier=d["tier"], status=d["status_code"],
                       watchlist=d["watchlist_hit"], ledger_seq=d["ledger_seq"])
    ws_secs = time.time() - ws_start

    # ---------------- HTTP phase ----------------
    http_start = time.time()

    def http_item(claim, nonce, ts, sig, label):
        status, body = http_send(claim, nonce, ts, sig)
        run.send_count += 1
        run.http_sends += 1
        return status, body

    for i in range(30):
        p = next(si)
        claim = make_claim(next_id("hlegit"), p, "legitimate")
        ts = time.time()
        nonce = "http-legit-%04d" % i
        status, body = http_item(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "legitimate")
        run.record(transport="http", cls="legitimate", claim_id=claim["claim_id"],
                   tier=("OK" if status == 200 else "REJECTED"), status=status,
                   watchlist=False, ledger_seq=body.get("ledger_seq"))

    for i in range(10):
        p = next(fi)
        claim = make_claim(next_id("hbad"), p, "fraud_bad_sig")
        ts = time.time()
        nonce = "http-bad-%04d" % i
        good = sign(nonce, ts, json.dumps(claim, sort_keys=True).encode())
        bad = ("0" if good[0] != "0" else "1") + good[1:]
        status, body = http_item(claim, nonce, ts, bad, "fraud_bad_sig")
        run.record(transport="http", cls="fraud_bad_sig", claim_id=claim["claim_id"],
                   tier=("OK" if status == 200 else "REJECTED"), status=status,
                   watchlist=False, ledger_seq=body.get("ledger_seq"))

    for i in range(10):
        p = next(fi)
        claim = make_claim(next_id("hrep"), p, "fraud_replay")
        ts = time.time()
        nonce = "http-rep-%04d" % i
        sig = sign(nonce, ts, json.dumps(claim, sort_keys=True).encode())
        http_item(claim, nonce, ts, sig, "replay_setup")
        run.setup_sends += 1
        status, body = http_item(claim, nonce, ts, sig, "fraud_replay")
        run.record(transport="http", cls="fraud_replay", claim_id=claim["claim_id"],
                   tier=("OK" if status == 200 else "REJECTED"), status=status,
                   watchlist=False, ledger_seq=body.get("ledger_seq"))

    for i in range(10):
        p = next(fi)
        claim = make_claim(next_id("hstale"), p, "fraud_stale")
        ts = time.time() - 400
        nonce = "http-stale-%04d" % i
        status, body = http_item(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "fraud_stale")
        run.record(transport="http", cls="fraud_stale", claim_id=claim["claim_id"],
                   tier=("OK" if status == 200 else "REJECTED"), status=status,
                   watchlist=False, ledger_seq=body.get("ledger_seq"))

    for i in range(5):
        p = next(fi)
        claim = make_claim(next_id("hdrift"), p, "fraud_drifted")
        ts = time.time() - 30
        nonce = "http-drift-%04d" % i
        status, body = http_item(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "fraud_drifted")
        run.record(transport="http", cls="fraud_drifted", claim_id=claim["claim_id"],
                   tier=("OK" if status == 200 else "REJECTED"), status=status,
                   watchlist=False, ledger_seq=body.get("ledger_seq"))
    http_secs = time.time() - http_start

    # ---------------- name + fuzzy phases (Gates 2/3) ----------------
    # Real LEIE rows with NO NPI: exact name claims must be quarantined
    # (Gate 2), fuzzy variants must be held at 202 (Gate 3), synthetic
    # named legitimate claims must be accepted. All rows are checked
    # here so a fuzzy variant cannot accidentally be an exact match.
    name_start = time.time()
    person_keys, bus_keys = load_leie_key_sets()
    name_person = load_leie_no_npi_person(50)
    name_bus = load_leie_no_npi_bus(35)
    name_pairs = {(ln, fn) for (ln, fn, _dob) in person_keys}

    def _ws_name_record(d, cls, claim_id, watchlist_hit):
        run.record(transport="ws", cls=cls, claim_id=claim_id,
                   tier=d["tier"], status=d["status_code"],
                   watchlist=watchlist_hit, ledger_seq=d["ledger_seq"],
                   reason=d.get("reason"))

    def _http_name_record(status, body, cls, claim_id):
        tier = "OK" if status == 200 else ("REVIEW" if status == 202
                                           else "REJECTED")
        run.record(transport="http", cls=cls, claim_id=claim_id,
                   tier=tier, status=status, watchlist=False,
                   ledger_seq=body.get("ledger_seq"),
                   reason=body.get("detail"))

    async with websockets.connect(SERVER + "/ws/ingress", max_size=1_000_000) as ws:
        async def send_ws2(claim, nonce, ts, sig, label):
            raw = await ws_send(ws, claim, nonce, ts, sig, label)
            run.send_count += 1
            run.ws_sends += 1
            return json.loads(raw)

        # fraud_name_person x30 (exact, WS)
        for i, row in enumerate(name_person[0:30]):
            claim = make_name_claim(next_id("nper"), row, "fraud_name_person")
            ts = time.time()
            nonce = "ws-nper-%04d" % i
            d = await send_ws2(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "fraud_name_person")
            _ws_name_record(d, "fraud_name_person", claim["claim_id"], False)

        # fraud_name_bus x20 (exact, WS)
        for i, row in enumerate(name_bus[0:20]):
            claim = make_name_claim(next_id("nbus"), row, "fraud_name_bus")
            ts = time.time()
            nonce = "ws-nbus-%04d" % i
            d = await send_ws2(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "fraud_name_bus")
            _ws_name_record(d, "fraud_name_bus", claim["claim_id"], False)

        # fuzzy F1/F2/F3 x10 each (WS), from the next 10 person rows
        for i, row in enumerate(name_person[30:40]):
            for rule in ("f1", "f2", "f3"):
                claim = make_fuzzy_claim(next_id("fz" + rule), row, rule,
                                         person_keys, bus_keys,
                                         variant=i % 2)
                ts = time.time()
                nonce = "ws-fz%s-%04d" % (rule, i)
                d = await send_ws2(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "fraud_fuzzy_" + rule)
                _ws_name_record(d, "fraud_fuzzy_" + rule, claim["claim_id"], False)

        # fuzzy F4 x10 (WS), from the next 10 business rows
        for i, row in enumerate(name_bus[20:30]):
            claim = make_fuzzy_claim(next_id("fzf4"), row, "f4",
                                     person_keys, bus_keys)
            ts = time.time()
            nonce = "ws-fzf4-%04d" % i
            d = await send_ws2(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "fraud_fuzzy_f4")
            _ws_name_record(d, "fraud_fuzzy_f4", claim["claim_id"], False)

        # legitimate_with_name x50 (WS): synthetic names, verified here
        # to match nothing in LEIE (name pair absent from the file).
        for i in range(50):
            ln, fn = "SYNTHETIC", "PERSON%03d" % i
            assert (ln, fn) not in name_pairs
            claim = make_name_claim(next_id("nleg"), {
                "lastname": ln, "firstname": fn, "dob": "19900101",
                "zip": "12345", "name": "Synthetic Person %03d" % i},
                "legitimate_with_name")
            ts = time.time()
            nonce = "ws-nleg-%04d" % i
            d = await send_ws2(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "legitimate_with_name")
            _ws_name_record(d, "legitimate_with_name", claim["claim_id"], False)

    # HTTP name phase: exact + fuzzy + legitimate-with-name
    for i, row in enumerate(name_person[40:50]):
        claim = make_name_claim(next_id("hnper"), row, "fraud_name_person")
        ts = time.time()
        nonce = "http-nper-%04d" % i
        status, body = http_item(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "fraud_name_person")
        _http_name_record(status, body, "fraud_name_person", claim["claim_id"])

    for i, row in enumerate(name_bus[30:35]):
        claim = make_name_claim(next_id("hnbus"), row, "fraud_name_bus")
        ts = time.time()
        nonce = "http-nbus-%04d" % i
        status, body = http_item(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "fraud_name_bus")
        _http_name_record(status, body, "fraud_name_bus", claim["claim_id"])

    for i, row in enumerate(name_person[30:33]):
        for rule in ("f1", "f2", "f3"):
            claim = make_fuzzy_claim(next_id("hfz" + rule), row, rule,
                                     person_keys, bus_keys, variant=i % 2)
            ts = time.time()
            nonce = "http-fz%s-%04d" % (rule, i)
            status, body = http_item(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "fraud_fuzzy_" + rule)
            _http_name_record(status, body, "fraud_fuzzy_" + rule, claim["claim_id"])

    for i, row in enumerate(name_bus[20:23]):
        claim = make_fuzzy_claim(next_id("hfzf4"), row, "f4",
                                 person_keys, bus_keys)
        ts = time.time()
        nonce = "http-fzf4-%04d" % i
        status, body = http_item(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "fraud_fuzzy_f4")
        _http_name_record(status, body, "fraud_fuzzy_f4", claim["claim_id"])

    for i in range(10):
        ln, fn = "SYNTHETIC", "PERSON%03d" % (100 + i)
        assert (ln, fn) not in name_pairs
        claim = make_name_claim(next_id("hnleg"), {
            "lastname": ln, "firstname": fn, "dob": "19900101",
            "zip": "12345", "name": "Synthetic Person %03d" % (100 + i)},
            "legitimate_with_name")
        ts = time.time()
        nonce = "http-nleg-%04d" % i
        status, body = http_item(claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "legitimate_with_name")
        _http_name_record(status, body, "legitimate_with_name", claim["claim_id"])
    name_secs = time.time() - name_start

    # ---------------- concurrent burst: 4 clients x 50 legitimate ----------------
    burst_start = time.time()

    async def burst_client(k):
        async with websockets.connect(SERVER + "/ws/ingress", max_size=1_000_000) as ws:
            for i in range(50):
                p = {"npi": "SYNTH-B%d-%02d" % (k, i), "name": "Synthetic Burst Clinic",
                     "excltype": "", "excldate": ""}
                claim = make_claim("burst-%d-%02d" % (k, i), p, "legitimate")
                ts = time.time()
                nonce = "ws-burst-%d-%02d" % (k, i)
                raw = await ws_send(ws, claim, nonce, ts, sign(nonce, ts, json.dumps(claim, sort_keys=True).encode()), "legitimate")
                run.send_count += 1
                run.burst_sends += 1
                d = json.loads(raw)
                run.record(transport="ws-burst", cls="legitimate", claim_id=claim["claim_id"],
                           tier=d["tier"], status=d["status_code"],
                           watchlist=d["watchlist_hit"], ledger_seq=d["ledger_seq"])

    await asyncio.gather(*[burst_client(k) for k in range(4)])
    burst_secs = time.time() - burst_start

    # ---------------- accounting ----------------
    def is_fraud(r):
        return r["cls"].startswith("fraud")

    def tier_of(r):
        # HTTP 202s were recorded with tier "REJECTED" by the original
        # mapping; a 202 is a hold, not a rejection.
        if r["transport"] == "http" and r["status"] == 202:
            return "REVIEW"
        return r["tier"]

    def stopped_by_protocol(r):
        return tier_of(r) in ("QUARANTINE", "REJECTED")

    def held_for_review(r):
        # Gate 3 REVIEW: HTTP 202, or WS REBALANCING with the
        # identity_review reason. Drifted REBALANCING (reason
        # "verified") is NOT a hold.
        if tier_of(r) == "REVIEW":
            return True
        return r["tier"] == "REBALANCING" and r.get("reason") == "identity_review"

    def stopped_combined(r):
        return stopped_by_protocol(r) or r["watchlist"]

    fraud = [r for r in run.records if is_fraud(r)]
    legit = [r for r in run.records if not is_fraud(r)]
    summary = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "packets_sent_total": run.send_count,
        "replay_setup_sends_not_counted_as_items": run.setup_sends,
        "items_total": len(run.records),
        "fraud_items": len(fraud),
        "legitimate_items": len(legit),
        "by_class": {},
        "fraud_stopped_by_protocol": sum(1 for r in fraud if stopped_by_protocol(r)),
        "fraud_stopped_combined": sum(1 for r in fraud if stopped_combined(r)),
        "fraud_stopped_by_watchlist_only": sum(
            1 for r in fraud if r["watchlist"] and not stopped_by_protocol(r)),
        "fraud_missed_entirely": sum(
            1 for r in fraud if not stopped_combined(r) and not held_for_review(r)),
        "fraud_held_for_review": sum(1 for r in fraud if held_for_review(r)),
        "fraud_stopped_or_held": sum(
            1 for r in fraud if stopped_by_protocol(r) or held_for_review(r)),
        "legitimate_quarantined_or_rejected_false_positives": sum(
            1 for r in legit if stopped_by_protocol(r)),
        "legitimate_held_for_review": sum(
            1 for r in legit if held_for_review(r)),
        "legitimate_watchlist_hits": sum(1 for r in legit if r["watchlist"]),
        "ws_main_run_seconds": round(ws_secs, 2),
        "ws_main_run_packets_per_second": round(700 / ws_secs, 1),
        "http_phase_seconds": round(http_secs, 2),
        "http_phase_packets_per_second": round(75 / http_secs, 1),
        "name_phase_seconds": round(name_secs, 2),
        "name_phase_packets_per_second": round(174 / name_secs, 1),
        "burst_seconds": round(burst_secs, 2),
        "burst_packets_per_second": round(200 / burst_secs, 1),
    }
    for cls in sorted({r["cls"] for r in run.records}):
        rows = [r for r in run.records if r["cls"] == cls]
        tiers = {}
        for r in rows:
            t = tier_of(r)
            tiers[t] = tiers.get(t, 0) + 1
        summary["by_class"][cls] = {
            "items": len(rows), "tiers": tiers,
            "watchlist_hits": sum(1 for r in rows if r["watchlist"]),
        }
    summary["catch_rate_protocol_only"] = round(
        summary["fraud_stopped_by_protocol"] / summary["fraud_items"], 4)
    summary["catch_rate_combined"] = round(
        summary["fraud_stopped_combined"] / summary["fraud_items"], 4)
    summary["catch_rate_including_review"] = round(
        summary["fraud_stopped_or_held"] / summary["fraud_items"], 4)
    summary["false_positive_rate"] = round(
        summary["legitimate_quarantined_or_rejected_false_positives"]
        / summary["legitimate_items"], 4)

    out = {"summary": summary, "records": run.records}
    (DEMO_DIR / "results.json").write_text(json.dumps(out, indent=2))
    req = urllib.request.Request(
        HTTP_BASE + "/demo/results",
        data=json.dumps(summary).encode(),
        method="POST", headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print("WARN: could not POST summary to server:", e)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
