#!/bin/bash
# Start (or restart) the SumerAvera live demo gateway.
# Usage: ./start_demo.sh
# The server stays in the foreground when run this way; use nohup to
# background it. The throwaway key below is test-only, never a real key.
set -e
cd "$(dirname "$0")"
export SUMERAVERA_SECRET_KEY='ci-test-only-key-not-a-production-secret'
export SUMERAVERA_LEDGER_DB="$PWD/demo_ledger.db"
# Protocol-level identity screening (2026-11-20 lockdown fix, extended
# 2026-11-21 with Gates 2/3 name matching): the server now enforces the
# LEIE watchlist itself on both paths. Without these, screening is off
# and the demo falls back to its demo-layer flag.
export SUMERAVERA_WATCHLIST_PATH="$PWD/data/watchlist.txt"
export SUMERAVERA_WATCHLIST_NAMES_PATH="$PWD/data/watchlist-names.txt"
export PYTHONDONTWRITEBYTECODE=1
# Needs fastapi + uvicorn (see ../requirements.txt); traffic.py also needs
# the websockets package.
exec python3 server.py
