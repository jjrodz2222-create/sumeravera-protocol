#!/usr/bin/env python3
"""Rebuild the SumerAvera excluded-provider watchlist from HHS-OIG LEIE.

The LEIE (List of Excluded Individuals/Entities) is published by the
HHS Office of Inspector General and updated monthly. This script
downloads the official CSV (or reads a local copy with --csv) and
writes TWO list files for watchlist.py to load:

  * ``watchlist.txt`` -- distinct NPIs, one per line (Gate 2 exact
    NPI matching).
  * ``watchlist-names.txt`` -- name keys, one per line (Gate 2 exact
    name matching and the Gate 3 fuzzy indexes):
    ``P|LASTNAME|FIRSTNAME|DOB|ZIP`` (ZIP may be empty) for people,
    ``B|BUSNAME|STATE`` for businesses. Normalization is the same
    code watchlist.py screens with, imported from there so the two
    can never disagree.

Usage:
    python3 refresh_watchlist.py [--url URL] [--csv PATH]
                                 [--out PATH] [--names-out PATH]

Defaults: --url is the OIG download, --out is
SUMERAVERA_WATCHLIST_PATH when set, else ./watchlist.txt;
--names-out is SUMERAVERA_WATCHLIST_NAMES_PATH when set, else
watchlist-names.txt next to --out (the two files are a pair).
--csv reads a local CSV instead of downloading (useful offline, or
to pin an exact file).

Safety: both new lists are written to temporary files in the same
directory and atomically renamed over the old ones, so a failed run
never leaves a partial list behind. A run that extracts zero NPIs,
or zero name keys, is an error (exit 1) and writes nothing -- an
empty list would silently turn identity screening off. Only stdlib
is used. No keys, no secrets.
"""
import argparse
import csv
import datetime
import os
import sys
import tempfile
import urllib.request

# The script imports normalization from watchlist.py (same directory),
# so the build and the screen can never disagree on a key.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from watchlist import (  # noqa: E402
    normalize_busname,
    normalize_dob,
    normalize_name,
    normalize_state,
    normalize_zip,
)

LEIE_URL = "https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv"


def extract_entries(csv_fh):
    """Extract both lists from an open LEIE CSV.

    Returns a dict: npis (distinct valid NPIs), person_keys
    (distinct (lastname, firstname, dob)), person_zips (key ->
    frozenset of ZIPs seen for it), bus_keys (distinct (busname,
    state)), rows_seen, rows_with_npi, rows_with_person_key,
    rows_with_bus_key.
    """
    npis = set()
    person_keys = set()
    person_zips = {}
    bus_keys = set()
    rows_seen = 0
    rows_with_npi = 0
    rows_with_person_key = 0
    rows_with_bus_key = 0
    reader = csv.DictReader(csv_fh)
    for row in reader:
        rows_seen += 1
        npi = (row.get("NPI") or "").strip()
        if npi and npi != "0":
            rows_with_npi += 1
            if len(npi) == 10 and npi.isdigit():
                npis.add(npi)
        ln = normalize_name(row.get("LASTNAME"))
        fn = normalize_name(row.get("FIRSTNAME"))
        dob = normalize_dob(row.get("DOB"))
        zipc = normalize_zip(row.get("ZIP"))
        if ln and fn and dob:
            key = (ln, fn, dob)
            person_keys.add(key)
            person_zips.setdefault(key, set()).add(zipc or "")
            rows_with_person_key += 1
        bn = normalize_busname(row.get("BUSNAME"))
        st = normalize_state(row.get("STATE"))
        if bn and st:
            bus_keys.add((bn, st))
            rows_with_bus_key += 1
    return {
        "npis": npis,
        "person_keys": person_keys,
        "person_zips": {k: frozenset(v) for k, v in person_zips.items()},
        "bus_keys": bus_keys,
        "rows_seen": rows_seen,
        "rows_with_npi": rows_with_npi,
        "rows_with_person_key": rows_with_person_key,
        "rows_with_bus_key": rows_with_bus_key,
    }


def extract_npis(csv_fh):
    """Backwards-compatible wrapper: (distinct_npis, rows_seen,
    rows_with_npi) from an open LEIE CSV."""
    entries = extract_entries(csv_fh)
    return entries["npis"], entries["rows_seen"], entries["rows_with_npi"]


def _atomic_write(path, header, lines):
    """Write ``lines`` under ``header`` to ``path`` atomically (temp
    file in the same directory + rename). Raises on failure; a failed
    write never leaves a partial list behind."""
    out_dir = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=out_dir, prefix=".watchlist-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(header)
            for line in lines:
                fh.write(line + "\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=LEIE_URL, help="LEIE CSV download URL")
    ap.add_argument("--csv", default=None, help="local LEIE CSV instead of downloading")
    ap.add_argument(
        "--out",
        default=os.environ.get("SUMERAVERA_WATCHLIST_PATH", "watchlist.txt"),
        help="output NPI watchlist file (default: $SUMERAVERA_WATCHLIST_PATH or ./watchlist.txt)",
    )
    ap.add_argument(
        "--names-out",
        default=None,
        help="output name-index file (default: $SUMERAVERA_WATCHLIST_NAMES_PATH, "
        "else watchlist-names.txt next to --out)",
    )
    args = ap.parse_args()

    if args.names_out is None:
        args.names_out = os.environ.get(
            "SUMERAVERA_WATCHLIST_NAMES_PATH"
        ) or os.path.join(
            os.path.dirname(os.path.abspath(args.out)), "watchlist-names.txt"
        )

    if args.csv:
        with open(args.csv, newline="", encoding="utf-8", errors="replace") as fh:
            entries = extract_entries(fh)
        source = f"local file {args.csv}"
    else:
        req = urllib.request.Request(
            args.url, headers={"User-Agent": "SumerAvera-watchlist-refresh/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                text = resp.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001 - report and exit nonzero
            print(f"[refresh] ERROR: download failed ({args.url}): {e}", file=sys.stderr)
            return 1
        import io

        with io.StringIO(text) as fh:
            entries = extract_entries(fh)
        source = args.url

    if not entries["npis"]:
        print(
            "[refresh] ERROR: zero NPIs extracted; refusing to write an "
            "empty list (that would silently disable screening).",
            file=sys.stderr,
        )
        return 1
    if not entries["person_keys"] and not entries["bus_keys"]:
        print(
            "[refresh] ERROR: zero name keys extracted; refusing to write "
            "an empty list (that would silently disable screening).",
            file=sys.stderr,
        )
        return 1

    generated = datetime.datetime.now(datetime.timezone.utc).isoformat() + " UTC"
    counts = (
        f"# LEIE rows seen: {entries['rows_seen']}; "
        f"rows with an NPI: {entries['rows_with_npi']}; "
        f"distinct NPIs: {len(entries['npis'])}; "
        f"person keys: {len(entries['person_keys'])}; "
        f"business keys: {len(entries['bus_keys'])}\n"
    )
    npi_header = (
        "# SumerAvera excluded-provider watchlist (NPI)\n"
        f"# Source: {source}\n"
        f"# Generated: {generated}\n"
        + counts
        + "# Refresh monthly: OIG updates LEIE monthly. Re-run this script.\n"
        "# NOTE: only LEIE records carrying an NPI are in this list "
        f"({len(entries['npis'])} distinct NPIs of "
        f"{entries['rows_seen']} rows in this download).\n"
    )
    names_header = (
        "# SumerAvera excluded-provider watchlist (names)\n"
        f"# Source: {source}\n"
        f"# Generated: {generated}\n"
        + counts
        + "# Refresh monthly: OIG updates LEIE monthly. Re-run this script.\n"
        "# Format: P|LASTNAME|FIRSTNAME|DOB|ZIP (ZIP may be empty) and\n"
        "# B|BUSNAME|STATE. Names are normalized (see watchlist.py).\n"
    )
    npi_lines = sorted(entries["npis"])
    name_lines = []
    for (ln, fn, dob) in sorted(entries["person_keys"]):
        for zipc in sorted(entries["person_zips"][(ln, fn, dob)]):
            name_lines.append(f"P|{ln}|{fn}|{dob}|{zipc}")
    for (bn, st) in sorted(entries["bus_keys"]):
        name_lines.append(f"B|{bn}|{st}")

    try:
        _atomic_write(args.out, npi_header, npi_lines)
        _atomic_write(args.names_out, names_header, name_lines)
    except OSError as e:
        print(f"[refresh] ERROR: could not write lists: {e}", file=sys.stderr)
        return 1

    print(
        f"[refresh] wrote {len(entries['npis'])} NPIs "
        f"({entries['rows_with_npi']} rows with NPI of {entries['rows_seen']} LEIE rows) to {args.out}"
    )
    print(
        f"[refresh] wrote {len(name_lines)} name keys "
        f"({len(entries['person_keys'])} person, {len(entries['bus_keys'])} business) "
        f"to {args.names_out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
